#!/usr/bin/env python3
"""
Sentinel Alerts v1
=================
Alert-only CCTV scanner with stable temporal gating.
Defaults: 10s window, 5s step, 16 sampled frames.
"""

import argparse
import os
import re
import sys
import warnings
from collections import deque
from pathlib import Path

import numpy as np
import torch
from decord import VideoReader, cpu
from PIL import Image
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

from qwen_vl_utils import process_vision_info

os.environ["PYTHONUNBUFFERED"] = "1"
warnings.filterwarnings("ignore")


class SentinelAlertEngine:
    """Model wrapper for binary suspicion + descriptor scoring."""

    def __init__(self, device: str = "cuda", model_path: str = "Qwen/Qwen2-VL-2B-Instruct"):
        self.device = device
        self.model_path = model_path

        self.vlm_model = Qwen2VLForConditionalGeneration.from_pretrained(
            self.model_path,
            torch_dtype=torch.float16,
            device_map="auto",
        )
        self.vlm_processor = AutoProcessor.from_pretrained(self.model_path)

    @staticmethod
    def _sample_indices(num_frames: int, samples: int) -> np.ndarray:
        if num_frames <= 0:
            return np.array([], dtype=int)
        samples = max(1, min(samples, num_frames))
        idx = np.linspace(0, num_frames - 1, samples, dtype=int)
        return np.unique(idx)

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"\s+", " ", text.strip())

    def _run_prompt(self, pil_images, prompt: str, max_new_tokens: int) -> str:
        messages = [{
            "role": "user",
            "content": [
                *[{"type": "image", "image": img} for img in pil_images],
                {"type": "text", "text": prompt},
            ],
        }]
        text = self.vlm_processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        img_in, vid_in = process_vision_info(messages)
        inputs = self.vlm_processor(
            text=[text],
            images=img_in,
            videos=vid_in,
            padding=True,
            return_tensors="pt",
        ).to(self.device)

        gen_ids = self.vlm_model.generate(**inputs, max_new_tokens=max_new_tokens)
        raw = self.vlm_processor.batch_decode(gen_ids, skip_special_tokens=True)[0]
        answer = raw.split("assistant\n")[-1]
        return self._normalize_text(answer)

    @staticmethod
    def _yes_vote(text: str) -> int:
        up = text.upper()
        if up.startswith("YES"):
            return 1
        if up.startswith("NO"):
            return 0
        if "YES" in up and "NO" not in up:
            return 1
        if "NO" in up and "YES" not in up:
            return 0
        return 0

    @staticmethod
    def _keyword_severity(desc: str) -> float:
        keywords = {
            "fight": 0.95,
            "attack": 0.95,
            "assault": 0.95,
            "weapon": 1.00,
            "fire": 1.00,
            "smoke": 0.85,
            "explosion": 1.00,
            "crash": 0.95,
            "collision": 0.95,
            "accident": 0.85,
            "steal": 0.80,
            "theft": 0.80,
            "intruder": 0.85,
            "break": 0.80,
            "panic": 0.75,
            "chase": 0.75,
            "fall": 0.70,
            "violence": 0.95,
        }

        low = desc.lower()
        max_hit = 0.0
        for key, value in keywords.items():
            if key in low:
                max_hit = max(max_hit, value)

        if max_hit == 0.0:
            return 0.45
        return max_hit

    @torch.no_grad()
    def analyze_window(self, frames_np: np.ndarray, sample_frames: int) -> dict:
        idx = self._sample_indices(len(frames_np), sample_frames)
        pil_images = [Image.fromarray(frames_np[i]) for i in idx]

        p1 = (
            "Analyze these CCTV frames. Is there any suspicious, aggressive, unsafe, or abnormal "
            "human/vehicle activity (fighting, assault, pushing, kicking, grabbing, chasing, "
            "stealing, break-in, crash, fire, smoke)? Reply ONLY YES or NO."
        )
        p2 = (
            "Check temporal behavior across frames. If you see any physical conflict, forced entry, "
            "dangerous fall, or crash, reply YES. If clearly normal, reply NO."
        )
        p3 = (
            "Look for clear dangerous events: violence/assault/fighting/weapon, "
            "fire/smoke/explosion, crash/collision, theft/break-in, or severe fall/injury. "
            "Reply ONLY YES or NO."
        )

        out1 = self._run_prompt(pil_images, p1, max_new_tokens=4)
        out2 = self._run_prompt(pil_images, p2, max_new_tokens=4)
        out3 = self._run_prompt(pil_images, p3, max_new_tokens=4)

        yes1 = self._yes_vote(out1)
        yes2 = self._yes_vote(out2)
        yes3 = self._yes_vote(out3)
        votes = yes1 + yes2 + yes3
        vote_score = votes / 3.0

        if votes == 0:
            return {
                "window_score": 0.0,
                "descriptor": "normal",
                "raw_binary": [out1, out2, out3],
                "critical_vote": 0,
                "severity": 0.0,
            }

        desc_prompt = (
            "Suspicion detected. Describe the suspicious event in 6-14 words. "
            "If unclear, still summarize the most likely risk behavior."
        )
        desc = self._run_prompt(pil_images, desc_prompt, max_new_tokens=32)
        severity = self._keyword_severity(desc)

        window_score = float(0.55 * vote_score + 0.45 * severity)
        window_score = max(0.0, min(1.0, window_score))

        return {
            "window_score": window_score,
            "descriptor": desc,
            "raw_binary": [out1, out2, out3],
            "critical_vote": yes3,
            "severity": severity,
        }


class TemporalAlertFilter:
    """Hysteresis-based alert state machine over window scores."""

    def __init__(
        self,
        vote_horizon_windows: int = 3,
        trigger_ratio: float = 0.62,
        release_ratio: float = 0.38,
        cooldown_windows: int = 2,
    ):
        self.scores = deque(maxlen=max(1, vote_horizon_windows))
        self.trigger_ratio = trigger_ratio
        self.release_ratio = release_ratio
        self.cooldown_windows = max(0, cooldown_windows)

        self.alert_state = False
        self.cooldown_left = 0

    def update(self, score: float) -> dict:
        self.scores.append(float(score))
        smooth = float(sum(self.scores) / len(self.scores))

        if self.cooldown_left > 0:
            self.cooldown_left -= 1

        if not self.alert_state and self.cooldown_left == 0 and smooth >= self.trigger_ratio:
            self.alert_state = True

        if self.alert_state and smooth <= self.release_ratio:
            self.alert_state = False
            self.cooldown_left = self.cooldown_windows

        if smooth >= 0.78:
            level = "HIGH"
        elif smooth >= 0.58:
            level = "MEDIUM"
        elif smooth >= 0.40:
            level = "LOW"
        else:
            level = "NONE"

        return {
            "smoothed_score": smooth,
            "alert_state": self.alert_state,
            "risk_level": level,
        }


def validate_thresholds(
    trigger_ratio: float,
    release_ratio: float,
    instant_alert_ratio: float,
    severity_alert_ratio: float,
) -> None:
    if not (0.0 <= trigger_ratio <= 1.0 and 0.0 <= release_ratio <= 1.0):
        raise ValueError("trigger_ratio and release_ratio must be within [0, 1]")
    if not (0.0 <= instant_alert_ratio <= 1.0):
        raise ValueError("instant_alert_ratio must be within [0, 1]")
    if not (0.0 <= severity_alert_ratio <= 1.0):
        raise ValueError("severity_alert_ratio must be within [0, 1]")
    if trigger_ratio <= release_ratio:
        raise ValueError("trigger_ratio must be greater than release_ratio")


def run_alerts(
    video_path: str,
    window_sec: float,
    step_sec: float,
    sample_frames: int,
    vote_horizon_windows: int,
    trigger_ratio: float,
    release_ratio: float,
    cooldown_windows: int,
    min_alert_gap_sec: float,
    instant_alert_ratio: float,
    severity_alert_ratio: float,
) -> None:
    validate_thresholds(trigger_ratio, release_ratio, instant_alert_ratio, severity_alert_ratio)

    vr = VideoReader(video_path, ctx=cpu(0))
    fps = float(vr.get_avg_fps())
    total_frames = len(vr)

    win_len_f = max(1, int(window_sec * fps))
    step_f = max(1, int(step_sec * fps))

    if total_frames < win_len_f:
        raise RuntimeError(
            f"Video too short for selected window. frames={total_frames}, window_frames={win_len_f}"
        )

    engine = SentinelAlertEngine()
    filt = TemporalAlertFilter(
        vote_horizon_windows=vote_horizon_windows,
        trigger_ratio=trigger_ratio,
        release_ratio=release_ratio,
        cooldown_windows=cooldown_windows,
    )

    out_dir = Path("./result") / f"{Path(video_path).stem}_alerts"
    out_dir.mkdir(parents=True, exist_ok=True)
    global_log = Path("./result/alerts_global.log")

    last_alert_ts = -1e9

    print(f"[Scanner] Starting: {Path(video_path).name}", flush=True)
    print(
        f"[Scanner] window={window_sec:.1f}s step={step_sec:.1f}s horizon={vote_horizon_windows} "
        f"instant={instant_alert_ratio:.2f} severity={severity_alert_ratio:.2f}",
        flush=True,
    )

    for start in range(0, total_frames - win_len_f + 1, step_f):
        end = start + win_len_f
        t0 = start / fps
        t1 = end / fps

        label = f"[{t0:6.1f}s-{t1:6.1f}s]"
        sys.stdout.write(f"{label} STATUS: ANALYZING...")
        sys.stdout.flush()

        frames_np = vr.get_batch(range(start, end)).asnumpy()
        result = engine.analyze_window(frames_np, sample_frames=sample_frames)
        state = filt.update(result["window_score"])

        critical_hit = result["critical_vote"] == 1
        severity_hit = result["severity"] >= severity_alert_ratio
        instant_alert = (
            critical_hit or severity_hit or (result["window_score"] >= instant_alert_ratio)
        )
        stable_alert = state["alert_state"]
        should_emit = (instant_alert or stable_alert) and ((t0 - last_alert_ts) >= min_alert_gap_sec)

        if should_emit:
            last_alert_ts = t0
            alert_kind = "ALERT-FAST" if instant_alert else "ALERT"
            msg = (
                f"{label} {alert_kind} | level={state['risk_level']} "
                f"| w={result['window_score']:.2f} s={state['smoothed_score']:.2f} "
                f"| crit={int(critical_hit)} sev={result['severity']:.2f} "
                f"| {result['descriptor']}"
            )
            sys.stdout.write(f"\r{msg}\n")
            sys.stdout.flush()

            with open(global_log, "a", encoding="utf-8") as f:
                f.write(f"[{Path(video_path).name}] {msg}\n")

            frame_mid = frames_np[len(frames_np) // 2]
            Image.fromarray(frame_mid).save(out_dir / f"alert_{t0:.1f}s.jpg")
        else:
            msg = (
                f"{label} FLAG  | level={state['risk_level']} "
                f"| w={result['window_score']:.2f} s={state['smoothed_score']:.2f} "
                f"| crit={int(critical_hit)} sev={result['severity']:.2f} "
                f"| {result['descriptor']}"
            )
            sys.stdout.write(f"\r{msg}\n")
            sys.stdout.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Alert-only CCTV scanner")
    parser.add_argument("--video_path", required=True, help="Path to input video")

    parser.add_argument("--window_sec", type=float, default=10.0)
    parser.add_argument("--step_sec", type=float, default=5.0)
    parser.add_argument("--sample_frames", type=int, default=16)

    parser.add_argument("--vote_horizon_windows", type=int, default=3)
    parser.add_argument("--trigger_ratio", type=float, default=0.62)
    parser.add_argument("--release_ratio", type=float, default=0.38)
    parser.add_argument("--cooldown_windows", type=int, default=2)
    parser.add_argument("--min_alert_gap_sec", type=float, default=10.0)
    parser.add_argument("--instant_alert_ratio", type=float, default=0.72)
    parser.add_argument("--severity_alert_ratio", type=float, default=0.90)
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    run_alerts(
        video_path=args.video_path,
        window_sec=args.window_sec,
        step_sec=args.step_sec,
        sample_frames=args.sample_frames,
        vote_horizon_windows=args.vote_horizon_windows,
        trigger_ratio=args.trigger_ratio,
        release_ratio=args.release_ratio,
        cooldown_windows=args.cooldown_windows,
        min_alert_gap_sec=args.min_alert_gap_sec,
        instant_alert_ratio=args.instant_alert_ratio,
        severity_alert_ratio=args.severity_alert_ratio,
    )
