#!/usr/bin/env python3
import argparse

from configs import MODE_PRESETS, apply_overrides, resolve_crime_target
from runtime import RealTimeScanner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Realtime CCTV anomaly scanner")
    parser.add_argument("--mode", choices=["fast", "high_accuracy"], default="fast")
    parser.add_argument("--video_path", default=None, help="Backward-compatible file input path")
    parser.add_argument("--input_source", default=None, help="File path or RTSP URL")
    parser.add_argument("--input_type", choices=["auto", "file", "rtsp", "camera"], default="auto")
    parser.add_argument("--camera_index", type=int, default=0, help="Used when input_type=camera")
    parser.add_argument("--max_windows", type=int, default=None, help="Optional limit for stream/camera runs")

    # Optional overrides.
    parser.add_argument("--window_sec", type=float, default=None)
    parser.add_argument("--step_sec", type=float, default=None)
    parser.add_argument("--sample_frames", type=int, default=None)
    parser.add_argument("--vote_horizon_windows", type=int, default=None)
    parser.add_argument("--trigger_ratio", type=float, default=None)
    parser.add_argument("--release_ratio", type=float, default=None)
    parser.add_argument("--cooldown_windows", type=int, default=None)
    parser.add_argument("--min_alert_gap_sec", type=float, default=None)
    parser.add_argument("--instant_alert_ratio", type=float, default=None)
    parser.add_argument("--severity_alert_ratio", type=float, default=None)

    parser.add_argument("--save_debug_jsonl", action="store_true")
    parser.add_argument("--model_source", choices=["base", "lora"], default="base")
    parser.add_argument("--lora_adapter_path", default=None)
    parser.add_argument("--dedup_window_sec", type=float, default=4.0)
    parser.add_argument(
        "--crime_target",
        default="all",
        help="Target crime to detect: all, stealing, assault, fire, intrusion, accident, vandalism, robbery",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    source = args.input_source if args.input_source else args.video_path
    if not source and args.input_type != "camera":
        raise ValueError("Provide --input_source or --video_path, or set --input_type camera")

    base_cfg = MODE_PRESETS[args.mode]
    cfg = apply_overrides(base_cfg, args)
    crime_profile = resolve_crime_target(args.crime_target)

    scanner = RealTimeScanner(
        input_source=source,
        input_type=args.input_type,
        camera_index=args.camera_index,
        max_windows=args.max_windows,
        mode=args.mode,
        cfg=cfg,
        save_debug_jsonl=args.save_debug_jsonl,
        model_source=args.model_source,
        lora_adapter_path=args.lora_adapter_path,
        dedup_window_sec=args.dedup_window_sec,
        crime_target=crime_profile.key,
    )
    scanner.run()


if __name__ == "__main__":
    main()
