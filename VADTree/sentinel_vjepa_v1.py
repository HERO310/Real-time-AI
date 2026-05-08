#!/usr/bin/env python3
"""
Sentinel V-JEPA v1
==================
World-model style anomaly scanner using V-JEPA2 embeddings.
- Sliding windows (default 10s / 5s step)
- Real-time per-window terminal output
- Alert-only emission with temporal stabilization

Notes:
- Requires a Transformers version that supports V-JEPA2 (model_type="vjepa2").
- Keeps existing sentinel_alerts_v1.py untouched.
"""

import argparse
import json
import os
import sys
import warnings
from collections import deque
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from decord import VideoReader, cpu
from PIL import Image

os.environ["PYTHONUNBUFFERED"] = "1"
warnings.filterwarnings("ignore")


class TemporalAlertFilter:
    """Hysteresis-based state machine over smoothed anomaly scores."""

    def __init__(
        self,
        vote_horizon_windows: int = 3,
        trigger_ratio: float = 0.55,
        release_ratio: float = 0.35,
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


class VJEPAFeatureEngine:
    """Loads V-JEPA2 model and extracts normalized video embeddings."""

    def __init__(
        self,
        model_id: str,
        device: str,
        attn_implementation: str,
        force_float32: bool,
    ):
        try:
            import transformers
            from transformers import AutoModel
        except Exception as exc:
            raise RuntimeError(
                "Transformers is not available. Install/upgrade transformers first."
            ) from exc

        try:
            from transformers import AutoVideoProcessor
        except Exception as exc:
            raise RuntimeError(
                "AutoVideoProcessor is unavailable in this transformers build. "
                "Upgrade transformers to a release that includes V-JEPA2 support."
            ) from exc

        self.device = device
        self.model_id = model_id
        self.transformers_version = transformers.__version__

        if force_float32 or device == "cpu":
            dtype = torch.float32
        else:
            dtype = torch.float16

        self.processor = AutoVideoProcessor.from_pretrained(model_id)

        try:
            self.model = AutoModel.from_pretrained(
                model_id,
                torch_dtype=dtype,
                attn_implementation=attn_implementation,
            )
        except TypeError:
            # Some versions do not expose attn_implementation.
            self.model = AutoModel.from_pretrained(
                model_id,
                torch_dtype=dtype,
            )
        except ValueError as exc:
            if "model type `vjepa2`" in str(exc):
                raise RuntimeError(
                    "Current transformers does not recognize model_type 'vjepa2'. "
                    "Please upgrade transformers in this environment."
                ) from exc
            raise

        self.model.to(device)
        self.model.eval()

        cfg_frames = getattr(self.model.config, "frames_per_clip", 64)
        self.frames_per_clip = int(cfg_frames) if cfg_frames else 64

    @staticmethod
    def sample_indices(num_frames: int, sample_frames: int) -> np.ndarray:
        if num_frames <= 0:
            return np.array([], dtype=int)
        sample_frames = max(1, min(sample_frames, num_frames))
        idx = np.linspace(0, num_frames - 1, sample_frames, dtype=int)
        return np.unique(idx)

    @torch.no_grad()
    def extract_embedding(self, frames_np: np.ndarray, sample_frames: int) -> torch.Tensor:
        idx = self.sample_indices(len(frames_np), sample_frames)
        clip = frames_np[idx]  # [T, H, W, C]

        inputs = self.processor(clip, return_tensors="pt")
        for key in list(inputs.keys()):
            if hasattr(inputs[key], "to"):
                inputs[key] = inputs[key].to(self.device)

        outputs = self.model(**inputs)

        if hasattr(outputs, "last_hidden_state") and outputs.last_hidden_state is not None:
            hidden = outputs.last_hidden_state
        elif isinstance(outputs, tuple) and len(outputs) > 0:
            hidden = outputs[0]
        else:
            raise RuntimeError("Unexpected model outputs from V-JEPA2.")

        # Average over token/sequence dimension, then L2 normalize.
        emb = hidden.mean(dim=1).squeeze(0).float()
        emb = F.normalize(emb, dim=0)
        return emb.detach().cpu()


class OnlineJEPAAnomalyScorer:
    """Reference-distance + temporal-jump anomaly score."""

    def __init__(
        self,
        warmup_windows: int,
        reference_size: int,
        alpha: float,
        beta: float,
        normal_update_max: float,
    ):
        self.warmup_windows = max(1, warmup_windows)
        self.references = deque(maxlen=max(self.warmup_windows, reference_size))
        self.alpha = alpha
        self.beta = beta
        self.normal_update_max = normal_update_max
        self.prev_emb = None
        self.count = 0

    def _cosine_distance_01(self, a: torch.Tensor, b: torch.Tensor) -> float:
        sim = float(torch.dot(a, b).item())
        sim = max(-1.0, min(1.0, sim))
        return 0.5 * (1.0 - sim)

    def update(self, emb: torch.Tensor) -> dict:
        self.count += 1

        if len(self.references) < self.warmup_windows:
            self.references.append(emb)
            self.prev_emb = emb
            return {
                "warmup": True,
                "window_score": 0.0,
                "ref_distance": 0.0,
                "jump_distance": 0.0,
                "reason": "warmup",
            }

        ref_stack = torch.stack(list(self.references), dim=0)
        ref_center = F.normalize(ref_stack.mean(dim=0), dim=0)

        ref_distance = self._cosine_distance_01(emb, ref_center)
        jump_distance = 0.0 if self.prev_emb is None else self._cosine_distance_01(emb, self.prev_emb)

        raw = self.alpha * ref_distance + self.beta * jump_distance
        raw = max(0.0, min(1.0, float(raw)))

        if ref_distance >= 0.40 and jump_distance >= 0.25:
            reason = "shift+jump"
        elif ref_distance >= 0.40:
            reason = "scene-shift"
        elif jump_distance >= 0.25:
            reason = "motion-jump"
        else:
            reason = "minor"

        if raw <= self.normal_update_max:
            self.references.append(emb)

        self.prev_emb = emb

        return {
            "warmup": False,
            "window_score": raw,
            "ref_distance": ref_distance,
            "jump_distance": jump_distance,
            "reason": reason,
        }


def validate_args(args) -> None:
    if args.window_sec <= 0 or args.step_sec <= 0:
        raise ValueError("window_sec and step_sec must be > 0")
    if not (0.0 <= args.trigger_ratio <= 1.0 and 0.0 <= args.release_ratio <= 1.0):
        raise ValueError("trigger_ratio and release_ratio must be within [0,1]")
    if args.trigger_ratio <= args.release_ratio:
        raise ValueError("trigger_ratio must be greater than release_ratio")
    if not (0.0 <= args.instant_alert_ratio <= 1.0):
        raise ValueError("instant_alert_ratio must be within [0,1]")
    if not (0.0 <= args.alpha <= 1.0 and 0.0 <= args.beta <= 1.0):
        raise ValueError("alpha and beta must be within [0,1]")
    if abs((args.alpha + args.beta) - 1.0) > 1e-6:
        raise ValueError("alpha + beta must equal 1.0")


def run_vjepa(args) -> None:
    validate_args(args)

    device = "cpu" if args.force_cpu or not torch.cuda.is_available() else "cuda"

    print(f"[V-JEPA] Starting: {Path(args.video_path).name}", flush=True)
    print(f"[V-JEPA] Device: {device}", flush=True)

    engine = VJEPAFeatureEngine(
        model_id=args.model_id,
        device=device,
        attn_implementation=args.attn_implementation,
        force_float32=args.force_float32,
    )

    print(
        f"[V-JEPA] Model: {args.model_id} | transformers={engine.transformers_version} | "
        f"frames_per_clip={engine.frames_per_clip}",
        flush=True,
    )

    vr = VideoReader(args.video_path, ctx=cpu(0))
    fps = float(vr.get_avg_fps())
    total_frames = len(vr)

    win_len_f = max(1, int(args.window_sec * fps))
    step_f = max(1, int(args.step_sec * fps))

    if total_frames < win_len_f:
        raise RuntimeError(
            f"Video too short for selected window. frames={total_frames}, window_frames={win_len_f}"
        )

    scorer = OnlineJEPAAnomalyScorer(
        warmup_windows=args.warmup_windows,
        reference_size=args.reference_size,
        alpha=args.alpha,
        beta=args.beta,
        normal_update_max=args.normal_update_max,
    )
    filt = TemporalAlertFilter(
        vote_horizon_windows=args.vote_horizon_windows,
        trigger_ratio=args.trigger_ratio,
        release_ratio=args.release_ratio,
        cooldown_windows=args.cooldown_windows,
    )

    out_dir = Path("./result") / f"{Path(args.video_path).stem}_vjepa_alerts"
    out_dir.mkdir(parents=True, exist_ok=True)
    global_log = Path("./result/alerts_global.log")
    window_log = out_dir / "window_scores.jsonl"

    last_alert_ts = -1e9

    for start in range(0, total_frames - win_len_f + 1, step_f):
        end = start + win_len_f
        t0 = start / fps
        t1 = end / fps
        label = f"[{t0:6.1f}s-{t1:6.1f}s]"

        sys.stdout.write(f"{label} STATUS: ANALYZING...")
        sys.stdout.flush()

        frames_np = vr.get_batch(range(start, end)).asnumpy()

        emb = engine.extract_embedding(
            frames_np,
            sample_frames=max(args.sample_frames, engine.frames_per_clip),
        )
        score_info = scorer.update(emb)

        if score_info["warmup"]:
            msg = (
                f"{label} WARMUP | w=0.00 s=0.00 | ref=0.00 jump=0.00 | reason=warmup"
            )
            sys.stdout.write(f"\r{msg}\n")
            sys.stdout.flush()

            rec = {
                "start_s": round(t0, 2),
                "end_s": round(t1, 2),
                "window_score": 0.0,
                "smoothed_score": 0.0,
                "status": "WARMUP",
                "reason": "warmup",
            }
            with open(window_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
            continue

        state = filt.update(score_info["window_score"])

        instant_alert = score_info["window_score"] >= args.instant_alert_ratio
        stable_alert = state["alert_state"]
        should_emit = (instant_alert or stable_alert) and ((t0 - last_alert_ts) >= args.min_alert_gap_sec)

        status = "ALERT-FAST" if instant_alert else ("ALERT" if stable_alert else "FLAG")

        msg = (
            f"{label} {status:<9} | level={state['risk_level']:<6} "
            f"| w={score_info['window_score']:.2f} s={state['smoothed_score']:.2f} "
            f"| ref={score_info['ref_distance']:.2f} jump={score_info['jump_distance']:.2f} "
            f"| reason={score_info['reason']}"
        )

        if should_emit:
            last_alert_ts = t0
            sys.stdout.write(f"\r{msg}\n")
            sys.stdout.flush()

            with open(global_log, "a", encoding="utf-8") as f:
                f.write(f"[{Path(args.video_path).name}] {msg}\n")

            if args.save_alert_frames:
                frame_mid = frames_np[len(frames_np) // 2]
                Image.fromarray(frame_mid).save(out_dir / f"alert_{t0:.1f}s.jpg")
        else:
            sys.stdout.write(f"\r{msg}\n")
            sys.stdout.flush()

        rec = {
            "start_s": round(t0, 2),
            "end_s": round(t1, 2),
            "window_score": round(float(score_info["window_score"]), 5),
            "smoothed_score": round(float(state["smoothed_score"]), 5),
            "ref_distance": round(float(score_info["ref_distance"]), 5),
            "jump_distance": round(float(score_info["jump_distance"]), 5),
            "risk_level": state["risk_level"],
            "status": status,
            "reason": score_info["reason"],
        }
        with open(window_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

    print(f"[V-JEPA] Completed. Logs: {window_log}", flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="V-JEPA world-model style anomaly scanner")
    parser.add_argument("--video_path", required=True, help="Path to input video")
    parser.add_argument("--model_id", default="facebook/vjepa2-vitl-fpc64-256")

    parser.add_argument("--window_sec", type=float, default=10.0)
    parser.add_argument("--step_sec", type=float, default=5.0)
    parser.add_argument("--sample_frames", type=int, default=64)

    parser.add_argument("--warmup_windows", type=int, default=6)
    parser.add_argument("--reference_size", type=int, default=64)
    parser.add_argument("--alpha", type=float, default=0.70)
    parser.add_argument("--beta", type=float, default=0.30)
    parser.add_argument("--normal_update_max", type=float, default=0.28)

    parser.add_argument("--vote_horizon_windows", type=int, default=3)
    parser.add_argument("--trigger_ratio", type=float, default=0.55)
    parser.add_argument("--release_ratio", type=float, default=0.35)
    parser.add_argument("--cooldown_windows", type=int, default=2)
    parser.add_argument("--instant_alert_ratio", type=float, default=0.72)
    parser.add_argument("--min_alert_gap_sec", type=float, default=5.0)

    parser.add_argument("--attn_implementation", default="sdpa")
    parser.add_argument("--force_cpu", action="store_true")
    parser.add_argument("--force_float32", action="store_true")
    parser.add_argument("--save_alert_frames", action="store_true")
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    run_vjepa(args)
