#!/usr/bin/env python3
"""
Sentinel Alerts v2
==================
Prompt-engineered CCTV anomaly scanner.

What is new vs v1:
- Structured screening prompt (JSON schema) for more reliable parsing.
- Multi-perspective guard prompts to increase recall for short/brief events.
- Frame selector mixes uniform + motion-peaks to catch events at any point.
- Better uncertainty handling and gate reporting in terminal output.

Defaults: 10s window, 5s step.
"""

import argparse
import json
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


MODE_PRESETS = {
    "fast": {
        "window_sec": 3.0,
        "step_sec": 1.0,
        "sample_frames": 12,
        "vote_horizon_windows": 1,
        "trigger_ratio": 0.46,
        "release_ratio": 0.28,
        "cooldown_windows": 0,
        "min_alert_gap_sec": 0.0,
        "instant_alert_ratio": 0.60,
        "severity_alert_ratio": 0.72,
    },
    "high_accuracy": {
        "window_sec": 10.0,
        "step_sec": 5.0,
        "sample_frames": 18,
        "vote_horizon_windows": 3,
        "trigger_ratio": 0.58,
        "release_ratio": 0.36,
        "cooldown_windows": 2,
        "min_alert_gap_sec": 5.0,
        "instant_alert_ratio": 0.70,
        "severity_alert_ratio": 0.82,
    },
}


class SentinelPromptEngineV2:
    """VLM wrapper with structured prompting and robust parsing."""

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
    def _normalize_text(text: str) -> str:
        return re.sub(r"\s+", " ", text.strip())

    @staticmethod
    def _clip01(x: float) -> float:
        return max(0.0, min(1.0, float(x)))

    @staticmethod
    def _extract_json(text: str):
        # Best-effort extraction of first JSON object from model output.
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        candidate = match.group(0)
        try:
            return json.loads(candidate)
        except Exception:
            return None

    @staticmethod
    def _yes_vote(text: str) -> int:
        up = text.upper().strip()
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
    def _risk_level_score(level: str) -> float:
        mp = {
            "NONE": 0.00,
            "LOW": 0.35,
            "MEDIUM": 0.60,
            "HIGH": 0.85,
            "CRITICAL": 1.00,
        }
        return mp.get(level.upper().strip(), 0.35)

    @staticmethod
    def _keyword_severity(desc: str) -> float:
        keywords = {
            "fight": 0.95,
            "attack": 0.95,
            "assault": 0.95,
            "weapon": 1.00,
            "gun": 1.00,
            "knife": 1.00,
            "fire": 1.00,
            "smoke": 0.85,
            "explosion": 1.00,
            "crash": 0.95,
            "collision": 0.95,
            "accident": 0.85,
            "steal": 0.80,
            "theft": 0.80,
            "intruder": 0.85,
            "break-in": 0.85,
            "panic": 0.75,
            "chase": 0.75,
            "fall": 0.70,
            "violence": 0.95,
            "bleeding": 1.00,
            "injury": 0.85,
            "vandalism": 0.75,
        }

        low = desc.lower()
        max_hit = 0.0
        for k, v in keywords.items():
            if k in low:
                max_hit = max(max_hit, v)

        if max_hit == 0.0:
            return 0.45
        return max_hit

    @staticmethod
    def _sample_uniform(num_frames: int, n: int) -> np.ndarray:
        n = max(1, min(n, num_frames))
        return np.linspace(0, num_frames - 1, n, dtype=int)

    @staticmethod
    def _sample_motion_peaks(frames_np: np.ndarray, n: int) -> np.ndarray:
        if len(frames_np) <= 1 or n <= 0:
            return np.array([], dtype=int)

        gray = 0.299 * frames_np[..., 0] + 0.587 * frames_np[..., 1] + 0.114 * frames_np[..., 2]
        diffs = np.mean(np.abs(gray[1:] - gray[:-1]), axis=(1, 2))
        if len(diffs) == 0:
            return np.array([], dtype=int)

        top = np.argsort(diffs)[-min(n, len(diffs)):]
        return np.unique(top + 1)

    def _select_indices(self, frames_np: np.ndarray, sample_frames: int) -> np.ndarray:
        num_frames = len(frames_np)
        if num_frames <= 0:
            return np.array([], dtype=int)

        sample_frames = max(1, min(sample_frames, num_frames))
        n_uniform = max(1, sample_frames // 2)
        n_motion = sample_frames - n_uniform

        u = self._sample_uniform(num_frames, n_uniform)
        m = self._sample_motion_peaks(frames_np, n_motion)

        idx = np.unique(np.concatenate([u, m]))
        if len(idx) < sample_frames:
            fill = self._sample_uniform(num_frames, sample_frames)
            idx = np.unique(np.concatenate([idx, fill]))

        if len(idx) > sample_frames:
            # keep temporal coverage by downsampling sorted idx
            pick = np.linspace(0, len(idx) - 1, sample_frames, dtype=int)
            idx = idx[pick]

        return idx

    def _run_prompt(self, pil_images, prompt: str, max_new_tokens: int) -> str:
        messages = [{
            "role": "user",
            "content": [
                *[{"type": "image", "image": img} for img in pil_images],
                {"type": "text", "text": prompt},
            ],
        }]

        text = self.vlm_processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
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

    def _parse_screen(self, text: str) -> dict:
        # expected schema:
        # {"verdict":"YES|NO|UNSURE","confidence":0-100,"risk_level":"NONE|LOW|MEDIUM|HIGH|CRITICAL","event_tags":[...],"short_reason":"..."}
        default = {
            "verdict": "UNSURE",
            "confidence": 50.0,
            "risk_level": "LOW",
            "event_tags": [],
            "short_reason": "uncertain",
        }

        obj = self._extract_json(text)
        if obj is None or not isinstance(obj, dict):
            yes = self._yes_vote(text)
            if yes == 1:
                default["verdict"] = "YES"
                default["confidence"] = 70.0
                default["short_reason"] = text[:120]
            else:
                default["verdict"] = "NO"
                default["confidence"] = 30.0
                default["short_reason"] = text[:120] if text else "no signal"
            return default

        verdict = str(obj.get("verdict", "UNSURE")).upper().strip()
        if verdict not in {"YES", "NO", "UNSURE"}:
            verdict = "UNSURE"

        try:
            confidence = float(obj.get("confidence", 50.0))
        except Exception:
            confidence = 50.0
        confidence = max(0.0, min(100.0, confidence))

        risk_level = str(obj.get("risk_level", "LOW")).upper().strip()
        if risk_level not in {"NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            risk_level = "LOW"

        tags = obj.get("event_tags", [])
        if not isinstance(tags, list):
            tags = []
        tags = [str(t).strip().lower() for t in tags if str(t).strip()]

        reason = str(obj.get("short_reason", "uncertain")).strip()
        if not reason:
            reason = "uncertain"

        return {
            "verdict": verdict,
            "confidence": confidence,
            "risk_level": risk_level,
            "event_tags": tags,
            "short_reason": reason,
        }

    def _parse_detail(self, text: str) -> dict:
        # expected schema:
        # {"event_type":"...","severity_score":0-1,"description":"..."}
        default = {
            "event_type": "unknown",
            "severity_score": 0.45,
            "description": text[:180] if text else "possible anomaly",
        }

        obj = self._extract_json(text)
        if obj is None or not isinstance(obj, dict):
            return default

        event_type = str(obj.get("event_type", "unknown")).strip().lower()

        try:
            severity = float(obj.get("severity_score", 0.45))
        except Exception:
            severity = 0.45
        severity = self._clip01(severity)

        description = str(obj.get("description", "possible anomaly")).strip()
        if not description:
            description = "possible anomaly"

        return {
            "event_type": event_type,
            "severity_score": severity,
            "description": description,
        }

    @torch.no_grad()
    def analyze_window(self, frames_np: np.ndarray, sample_frames: int) -> dict:
        idx = self._select_indices(frames_np, sample_frames)
        pil_images = [Image.fromarray(frames_np[i]) for i in idx]

        screen_prompt = (
            "You are a CCTV safety analyst. Analyze ALL frames and detect if any harmful or anomalous event "
            "occurs even briefly at any point in time. Consider violence, assault, weapon use, theft, break-in, "
            "intrusion, vandalism, fire, smoke, crash, severe fall, medical distress, panic, and unsafe behavior. "
            "Output ONLY valid JSON with this schema: "
            "{\"verdict\":\"YES|NO|UNSURE\",\"confidence\":0-100,\"risk_level\":\"NONE|LOW|MEDIUM|HIGH|CRITICAL\","
            "\"event_tags\":[\"...\"],\"short_reason\":\"...\"}."
        )

        guard_prompt_1 = (
            "High-recall check: Does any frame show direct harm or threat (fight, attack, weapon, fire, crash, "
            "serious fall, forced entry)? Reply ONLY YES or NO."
        )

        guard_prompt_2 = (
            "Intent check across time: Do actions suggest suspicious intent or unsafe escalation at any moment "
            "(chasing, grabbing, theft attempt, stalking, abnormal confrontation)? Reply ONLY YES or NO."
        )

        out_screen = self._run_prompt(pil_images, screen_prompt, max_new_tokens=120)
        out_guard_1 = self._run_prompt(pil_images, guard_prompt_1, max_new_tokens=6)
        out_guard_2 = self._run_prompt(pil_images, guard_prompt_2, max_new_tokens=6)

        screen = self._parse_screen(out_screen)

        verdict_score = {
            "YES": 1.00,
            "UNSURE": 0.50,
            "NO": 0.00,
        }.get(screen["verdict"], 0.50)

        g1 = self._yes_vote(out_guard_1)
        g2 = self._yes_vote(out_guard_2)
        guard_score = (g1 + g2) / 2.0

        conf_score = screen["confidence"] / 100.0
        risk_score = self._risk_level_score(screen["risk_level"])

        suspicion = (screen["verdict"] != "NO") or (g1 == 1) or (g2 == 1)

        detail = {
            "event_type": "normal",
            "severity_score": 0.0,
            "description": "normal",
        }
        if suspicion:
            detail_prompt = (
                "Given potential risk in these frames, output ONLY valid JSON with schema: "
                "{\"event_type\":\"violence|theft|intrusion|fire|crash|fall|medical|vandalism|other\","
                "\"severity_score\":0.0-1.0,\"description\":\"short factual description\"}. "
                "If uncertain, still provide best estimate with lower severity_score."
            )
            out_detail = self._run_prompt(pil_images, detail_prompt, max_new_tokens=80)
            detail = self._parse_detail(out_detail)

        keyword_sev = self._keyword_severity(detail["description"])
        severity = max(risk_score, detail["severity_score"], keyword_sev if suspicion else 0.0)

        # Weighted fusion:
        # - verdict_score: structured high-level decision
        # - guard_score: high-recall safety checks
        # - conf_score: model confidence
        # - severity: semantic severity estimate
        window_score = (
            0.35 * verdict_score
            + 0.25 * guard_score
            + 0.20 * conf_score
            + 0.20 * severity
        )
        window_score = self._clip01(window_score)

        critical_tags = {
            "violence",
            "assault",
            "weapon",
            "fire",
            "explosion",
            "crash",
            "collision",
            "severe_fall",
            "medical_distress",
            "intrusion",
            "theft",
        }
        critical_from_tags = any(t in critical_tags for t in screen["event_tags"])
        critical_from_level = screen["risk_level"] in {"HIGH", "CRITICAL"}
        critical_from_sev = severity >= 0.85
        critical_vote = int(critical_from_tags or critical_from_level or critical_from_sev)

        descriptor = detail["description"] if suspicion else "normal"

        return {
            "window_score": window_score,
            "descriptor": descriptor,
            "severity": severity,
            "critical_vote": critical_vote,
            "risk_level_model": screen["risk_level"],
            "event_tags": screen["event_tags"],
            "debug": {
                "screen": screen,
                "guard_1": out_guard_1,
                "guard_2": out_guard_2,
                "detail": detail,
            },
        }


class TemporalAlertFilter:
    """Hysteresis-based alert state machine over window scores."""

    def __init__(
        self,
        vote_horizon_windows: int = 3,
        trigger_ratio: float = 0.58,
        release_ratio: float = 0.36,
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
    mode: str,
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
    save_debug_jsonl: bool,
) -> None:
    if mode in MODE_PRESETS:
        preset = MODE_PRESETS[mode]
        window_sec = preset["window_sec"]
        step_sec = preset["step_sec"]
        sample_frames = preset["sample_frames"]
        vote_horizon_windows = preset["vote_horizon_windows"]
        trigger_ratio = preset["trigger_ratio"]
        release_ratio = preset["release_ratio"]
        cooldown_windows = preset["cooldown_windows"]
        min_alert_gap_sec = preset["min_alert_gap_sec"]
        instant_alert_ratio = preset["instant_alert_ratio"]
        severity_alert_ratio = preset["severity_alert_ratio"]

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

    engine = SentinelPromptEngineV2()
    filt = TemporalAlertFilter(
        vote_horizon_windows=vote_horizon_windows,
        trigger_ratio=trigger_ratio,
        release_ratio=release_ratio,
        cooldown_windows=cooldown_windows,
    )

    out_dir = Path("./result") / f"{Path(video_path).stem}_alerts_v2"
    out_dir.mkdir(parents=True, exist_ok=True)
    global_log = Path("./result/alerts_global.log")
    window_log = out_dir / "window_flags.jsonl"

    last_alert_ts = -1e9

    print(f"[Scanner v2] Starting: {Path(video_path).name}", flush=True)
    print(
        f"[Scanner v2] mode={mode} window={window_sec:.1f}s step={step_sec:.1f}s "
        f"horizon={vote_horizon_windows} "
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
        instant_hit = result["window_score"] >= instant_alert_ratio

        instant_alert = critical_hit or severity_hit or instant_hit
        stable_alert = state["alert_state"]
        should_emit = (instant_alert or stable_alert) and ((t0 - last_alert_ts) >= min_alert_gap_sec)

        gates = []
        if critical_hit:
            gates.append("critical")
        if severity_hit:
            gates.append("severity")
        if instant_hit:
            gates.append("instant")
        if stable_alert:
            gates.append("stable")
        gate_str = ",".join(gates) if gates else "none"

        status = "ALERT-FAST" if instant_alert else ("ALERT" if stable_alert else "FLAG")
        if should_emit:
            last_alert_ts = t0

        msg = (
            f"{label} {status:<9} | level={state['risk_level']:<6} "
            f"| w={result['window_score']:.2f} s={state['smoothed_score']:.2f} "
            f"| sev={result['severity']:.2f} gates={gate_str} "
            f"| {result['descriptor']}"
        )

        sys.stdout.write(f"\r{msg}\n")
        sys.stdout.flush()

        rec = {
            "start_s": round(t0, 2),
            "end_s": round(t1, 2),
            "window_score": round(float(result["window_score"]), 5),
            "smoothed_score": round(float(state["smoothed_score"]), 5),
            "severity": round(float(result["severity"]), 5),
            "status": status,
            "risk_level": state["risk_level"],
            "gates": gates,
            "descriptor": result["descriptor"],
            "event_tags": result["event_tags"],
            "model_risk_level": result["risk_level_model"],
        }
        with open(window_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

        if should_emit:
            with open(global_log, "a", encoding="utf-8") as f:
                f.write(f"[{Path(video_path).name}] {msg}\n")

            frame_mid = frames_np[len(frames_np) // 2]
            Image.fromarray(frame_mid).save(out_dir / f"alert_{t0:.1f}s.jpg")

        if save_debug_jsonl:
            debug_path = out_dir / "prompt_debug.jsonl"
            dbg = {
                "start_s": round(t0, 2),
                "end_s": round(t1, 2),
                "debug": result["debug"],
            }
            with open(debug_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(dbg) + "\n")

    print(f"[Scanner v2] Complete. Output folder: {out_dir}", flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prompt-engineered alert-only CCTV scanner")
    parser.add_argument(
        "--mode",
        choices=["fast", "high_accuracy", "custom"],
        default="high_accuracy",
        help="Run profile: fast=3s/1s low-latency, high_accuracy=10s/5s stronger stability, custom=manual args",
    )
    parser.add_argument("--video_path", required=True, help="Path to input video")

    parser.add_argument("--window_sec", type=float, default=10.0)
    parser.add_argument("--step_sec", type=float, default=5.0)
    parser.add_argument("--sample_frames", type=int, default=18)

    parser.add_argument("--vote_horizon_windows", type=int, default=3)
    parser.add_argument("--trigger_ratio", type=float, default=0.58)
    parser.add_argument("--release_ratio", type=float, default=0.36)
    parser.add_argument("--cooldown_windows", type=int, default=2)
    parser.add_argument("--min_alert_gap_sec", type=float, default=5.0)

    parser.add_argument("--instant_alert_ratio", type=float, default=0.70)
    parser.add_argument("--severity_alert_ratio", type=float, default=0.82)
    parser.add_argument("--save_debug_jsonl", action="store_true")
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    run_alerts(
        mode=args.mode,
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
        save_debug_jsonl=args.save_debug_jsonl,
    )
