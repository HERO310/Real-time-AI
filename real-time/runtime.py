import json
import os
import sys
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np
import torch
from decord import VideoReader, cpu
from PIL import Image

from alerts import Palette, color_for_bucket, severity_bucket
from vlm_engine import SentinelVLMEngine


class TemporalFilter:
    def __init__(self, horizon: int, trigger: float, release: float, cooldown_windows: int):
        self.scores = deque(maxlen=max(1, horizon))
        self.trigger = trigger
        self.release = release
        self.cooldown_windows = max(0, cooldown_windows)
        self.alert_state = False
        self.cooldown_left = 0

    def update(self, score: float) -> dict:
        self.scores.append(float(score))
        smooth = float(sum(self.scores) / len(self.scores))

        if self.cooldown_left > 0:
            self.cooldown_left -= 1

        if not self.alert_state and self.cooldown_left == 0 and smooth >= self.trigger:
            self.alert_state = True

        if self.alert_state and smooth <= self.release:
            self.alert_state = False
            self.cooldown_left = self.cooldown_windows

        return {
            "smoothed_score": smooth,
            "alert_state": self.alert_state,
        }


class EventDeduplicator:
    """Suppress repeated near-identical alerts over a short time horizon."""

    def __init__(self, dedup_window_sec: float):
        self.dedup_window_sec = max(0.0, dedup_window_sec)
        self.recent = deque(maxlen=128)

    @staticmethod
    def _signature(descriptor: str, tags) -> str:
        tags = tags or []
        head = " ".join(descriptor.lower().split()[:6])
        tag_key = "|".join(sorted(str(t).lower() for t in tags))
        return f"{head}::{tag_key}"

    def is_duplicate(self, t0: float, descriptor: str, tags) -> bool:
        sig = self._signature(descriptor, tags)
        for old_t, old_sig in self.recent:
            if abs(t0 - old_t) <= self.dedup_window_sec and sig == old_sig:
                return True
        self.recent.append((t0, sig))
        return False


class FileWindowReader:
    def __init__(self, file_path: str, window_sec: float, step_sec: float):
        self.file_path = file_path
        self.vr = VideoReader(file_path, ctx=cpu(0))
        self.fps = float(self.vr.get_avg_fps())
        self.total_frames = len(self.vr)
        self.win_f = max(1, int(window_sec * self.fps))
        self.step_f = max(1, int(step_sec * self.fps))

    def iter_windows(self):
        if self.total_frames < self.win_f:
            raise RuntimeError(
                f"Video too short for selected window. frames={self.total_frames}, window_frames={self.win_f}"
            )
        for start in range(0, self.total_frames - self.win_f + 1, self.step_f):
            end = start + self.win_f
            t0 = start / self.fps
            t1 = end / self.fps
            frames_np = self.vr.get_batch(range(start, end)).asnumpy()
            yield t0, t1, frames_np


class StreamWindowReader:
    """OpenCV-based reader for RTSP/USB camera realtime windows."""

    def __init__(
        self,
        source,
        window_sec: float,
        step_sec: float,
        input_type: str,
        reconnect_retries: int = 20,
        reconnect_backoff_sec: float = 1.0,
    ):
        self.source = source
        self.window_sec = window_sec
        self.step_sec = step_sec
        self.input_type = input_type
        self.reconnect_retries = reconnect_retries
        self.reconnect_backoff_sec = reconnect_backoff_sec

        self.cap = None
        self.fps = 25.0
        self._open_capture()

    def _open_capture(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None

        src = self.source
        if self.input_type == "camera":
            src = int(self.source)

        self.cap = cv2.VideoCapture(src)
        if self.cap is None or not self.cap.isOpened():
            raise RuntimeError(f"Failed to open stream source: {self.source}")

        cap_fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 0.0)
        if cap_fps > 1.0:
            self.fps = cap_fps

    def _read_frame_with_reconnect(self):
        retries = 0
        while retries <= self.reconnect_retries:
            ok, frame = self.cap.read()
            if ok and frame is not None:
                # Convert BGR -> RGB for consistency with PIL/Image models.
                return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            retries += 1
            time.sleep(self.reconnect_backoff_sec)
            try:
                self._open_capture()
            except Exception:
                pass
        return None

    def iter_windows(self, max_windows=None):
        win_f = max(1, int(self.window_sec * self.fps))
        step_f = max(1, int(self.step_sec * self.fps))

        ring = deque(maxlen=win_f)
        frame_idx = 0
        produced = 0

        while True:
            frame = self._read_frame_with_reconnect()
            if frame is None:
                break
            ring.append(frame)
            frame_idx += 1

            # Emit a window every step_f frames once ring has enough data.
            if len(ring) == win_f and ((frame_idx - win_f) % step_f == 0):
                frames_np = np.array(list(ring), dtype=np.uint8)
                t1 = frame_idx / self.fps
                t0 = max(0.0, t1 - self.window_sec)
                yield t0, t1, frames_np

                produced += 1
                if max_windows is not None and produced >= max_windows:
                    break

        if self.cap is not None:
            self.cap.release()


class RealTimeScanner:
    def __init__(
        self,
        input_source: str,
        input_type: str,
        camera_index: int,
        max_windows,
        mode: str,
        cfg,
        save_debug_jsonl: bool = False,
        model_source: str = "base",
        lora_adapter_path: str = None,
        dedup_window_sec: float = 4.0,
        crime_target: str = "all",
    ):
        self.input_source = input_source
        self.input_type = input_type
        self.camera_index = camera_index
        self.max_windows = max_windows
        self.mode = mode
        self.cfg = cfg
        self.save_debug_jsonl = save_debug_jsonl
        self.crime_target = crime_target
        self.palette = Palette()

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.engine = SentinelVLMEngine(
            device=self.device,
            model_source=model_source,
            lora_adapter_path=lora_adapter_path,
            crime_target=crime_target,
        )
        self.temporal = TemporalFilter(
            horizon=cfg.vote_horizon_windows,
            trigger=cfg.trigger_ratio,
            release=cfg.release_ratio,
            cooldown_windows=cfg.cooldown_windows,
        )
        self.dedup = EventDeduplicator(dedup_window_sec=dedup_window_sec)

        self.rt_root = Path(__file__).resolve().parent
        self.results_root = self.rt_root / "results"
        self.results_root.mkdir(parents=True, exist_ok=True)

    def _resolve_input(self):
        src = self.input_source
        typ = self.input_type

        if typ == "camera":
            return "camera", str(self.camera_index)

        if typ == "rtsp":
            return "rtsp", src

        if typ == "file":
            return "file", src

        # auto
        if src and src.lower().startswith(("rtsp://", "rtmp://", "http://", "https://")):
            return "rtsp", src

        if src and os.path.exists(src):
            return "file", src

        # Fallback to camera index when source is empty or digit-like and file doesn't exist.
        if src and src.isdigit() and not os.path.exists(src):
            return "camera", src

        if src:
            # treat unknown as stream source
            return "rtsp", src

        return "camera", str(self.camera_index)

    def run(self):
        src_kind, src = self._resolve_input()

        if src_kind == "file":
            reader = FileWindowReader(src, self.cfg.window_sec, self.cfg.step_sec)
            iter_windows = reader.iter_windows()
            video_name = Path(src).stem
        else:
            stream_type = "camera" if src_kind == "camera" else "rtsp"
            reader = StreamWindowReader(
                source=src,
                window_sec=self.cfg.window_sec,
                step_sec=self.cfg.step_sec,
                input_type=stream_type,
            )
            iter_windows = reader.iter_windows(max_windows=self.max_windows)
            video_name = f"stream_{self.mode}"

        out_name = f"{video_name}_{self.mode}"
        if self.crime_target != "all":
            out_name = f"{out_name}_{self.crime_target}"

        out_dir = self.results_root / out_name
        out_dir.mkdir(parents=True, exist_ok=True)

        window_log = out_dir / "window_flags.jsonl"
        global_log = self.results_root / "alerts_global.log"

        print(
            f"[Realtime] mode={self.mode} crime={self.crime_target} device={self.device} input={src_kind} "
            f"window={self.cfg.window_sec:.1f}s step={self.cfg.step_sec:.1f}s",
            flush=True,
        )

        last_alert_ts = -1e9
        windows_seen = 0

        for t0, t1, frames_np in iter_windows:
            label = f"[{t0:6.1f}s-{t1:6.1f}s]"
            sys.stdout.write(f"{label} STATUS: ANALYZING...")
            sys.stdout.flush()

            res = self.engine.analyze_window(
                frames_np,
                sample_frames=self.cfg.sample_frames,
                mode=self.mode,
                crime_target=self.crime_target,
            )
            state = self.temporal.update(res["window_score"])

            critical_hit = res["critical_vote"] == 1
            severity_hit = res["severity"] >= self.cfg.severity_alert_ratio
            instant_hit = res["window_score"] >= self.cfg.instant_alert_ratio
            stable_hit = state["alert_state"]

            should_emit = (critical_hit or severity_hit or instant_hit or stable_hit) and (
                (t0 - last_alert_ts) >= self.cfg.min_alert_gap_sec
            )

            # Dedup repeated same event text in short horizon.
            if should_emit and self.dedup.is_duplicate(t0, res["descriptor"], res.get("event_tags", [])):
                should_emit = False

            if should_emit:
                last_alert_ts = t0

            if should_emit and (critical_hit or severity_hit or instant_hit):
                status = "ALERT-FAST"
            elif should_emit:
                status = "ALERT"
            else:
                status = "FLAG"

            bucket = severity_bucket(state["smoothed_score"])
            color = color_for_bucket(bucket, self.palette)

            gates = []
            if critical_hit:
                gates.append("critical")
            if severity_hit:
                gates.append("severity")
            if instant_hit:
                gates.append("instant")
            if stable_hit:
                gates.append("stable")
            gate_str = ",".join(gates) if gates else "none"

            line = (
                f"{label} {status:<10} | level={bucket:<6} | "
                f"w={res['window_score']:.2f} s={state['smoothed_score']:.2f} "
                f"sev={res['severity']:.2f} gates={gate_str} | {res['descriptor']}"
            )

            sys.stdout.write(f"\r{color}{line}{self.palette.reset}\n")
            sys.stdout.flush()

            record = {
                "video": src if src_kind == "file" else src_kind,
                "mode": self.mode,
                "crime_target": self.crime_target,
                "start_s": round(t0, 2),
                "end_s": round(t1, 2),
                "status": status,
                "level": bucket,
                "window_score": round(float(res["window_score"]), 5),
                "smoothed_score": round(float(state["smoothed_score"]), 5),
                "severity": round(float(res["severity"]), 5),
                "gates": gates,
                "descriptor": res["descriptor"],
                "event_tags": res.get("event_tags", []),
                "source_type": src_kind,
            }
            with open(window_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")

            if should_emit:
                with open(global_log, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
                frame_mid = frames_np[len(frames_np) // 2]
                Image.fromarray(frame_mid).save(out_dir / f"alert_{t0:.1f}s.jpg")

            windows_seen += 1
            if self.max_windows is not None and windows_seen >= self.max_windows:
                break

        print(f"[Realtime] Complete. Output: {out_dir} | windows={windows_seen}", flush=True)
