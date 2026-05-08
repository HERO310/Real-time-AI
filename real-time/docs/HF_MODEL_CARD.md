---
license: apache-2.0
tags:
- video-analytics
- cctv
- anomaly-detection
- realtime
- qwen2-vl
- lora
---

# Realtime CCTV Anomaly Sentinel

This repository contains a realtime CCTV anomaly alert system with two operating modes:
- fast
- high_accuracy

It supports optional targeted crime filtering, for example:
- stealing
- assault
- fire
- intrusion
- accident
- vandalism
- robbery

## Highlights

- Sliding-window video analysis
- Temporal smoothing and alert hysteresis
- Fast alert gating for critical events
- File, RTSP, and camera input support
- Optional LoRA adapter inference path

## What is included

- Realtime inference code and configuration.
- Optional LoRA adapter metadata (if present in the repo).
- No base model weights are included; Qwen2-VL is pulled via transformers at runtime.

## Intended use

Use this repo for research, demonstrations, and controlled CCTV analytics experiments.

## Local inference examples

Fast mode:
```bash
python run_realtime.py --mode fast --video_path /path/to/video.mp4
```

High-accuracy mode:
```bash
python run_realtime.py --mode high_accuracy --video_path /path/to/video.mp4
```

Targeted crime mode:
```bash
python run_realtime.py --mode fast --crime_target stealing --video_path /path/to/video.mp4
```

LoRA inference:
```bash
python run_realtime.py \
  --mode high_accuracy \
  --video_path /path/to/video.mp4 \
  --model_source lora \
  --lora_adapter_path /data/video_analytics/real-time/finetuned_qwen2vl_lora
```

## Upload note

If you publish this project to Hugging Face Hub, keep the local runtime folder structure unchanged so the CLI commands remain valid.