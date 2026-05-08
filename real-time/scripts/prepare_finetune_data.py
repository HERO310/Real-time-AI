#!/usr/bin/env python3
"""
Prepare fine-tuning JSONL from annotated windows.

Input CSV columns:
video_path,start_s,end_s,event_type,description

Output JSONL rows:
{"image_path":"...","prompt":"...","response":"..."}
"""

import argparse
import csv
import json
from pathlib import Path

from decord import VideoReader, cpu
from PIL import Image


def build_prompt(event_type: str) -> str:
    return (
        "You are a CCTV anomaly analyst. Classify this scene and summarize if suspicious behavior exists. "
        f"Focus category hint: {event_type}. Keep answer concise and factual."
    )


def main():
    parser = argparse.ArgumentParser(description="Prepare Qwen2-VL fine-tuning JSONL from window annotations")
    parser.add_argument("--annotations_csv", required=True)
    parser.add_argument("--output_jsonl", required=True)
    parser.add_argument("--frames_dir", default="./data/finetune/frames")
    args = parser.parse_args()

    out_jsonl = Path(args.output_jsonl)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)

    frames_dir = Path(args.frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    with open(args.annotations_csv, "r", encoding="utf-8") as f_in, open(out_jsonl, "w", encoding="utf-8") as f_out:
        reader = csv.DictReader(f_in)
        for i, row in enumerate(reader):
            video_path = row["video_path"]
            start_s = float(row["start_s"])
            end_s = float(row["end_s"])
            event_type = row.get("event_type", "anomaly")
            desc = row.get("description", "suspicious activity")

            vr = VideoReader(video_path, ctx=cpu(0))
            fps = float(vr.get_avg_fps())
            mid_s = 0.5 * (start_s + end_s)
            mid_idx = max(0, min(len(vr) - 1, int(mid_s * fps)))

            frame = vr[mid_idx].asnumpy()
            frame_path = frames_dir / f"sample_{i:06d}.jpg"
            Image.fromarray(frame).save(frame_path)

            sample = {
                "image_path": str(frame_path.resolve()),
                "prompt": build_prompt(event_type),
                "response": f"event_type={event_type}; description={desc}",
            }
            f_out.write(json.dumps(sample, ensure_ascii=True) + "\n")
            written += 1

    print(f"Wrote {written} samples to {out_jsonl}")


if __name__ == "__main__":
    main()
