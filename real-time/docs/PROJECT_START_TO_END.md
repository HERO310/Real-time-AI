# Project Start-to-End Guide

This document explains the full project from setup to final outputs, including model choices, runtime flow, optional fine-tuning, and reporting.

## 1) Goal

Build a realtime CCTV anomaly detection system that can:
- process video files, RTSP streams, or cameras,
- detect suspicious events in temporal windows,
- emit stable alerts with severity levels,
- support fast and high-accuracy modes,
- optionally focus on a selected crime target,
- log outputs for audit and reports,
- optionally use LoRA-adapted model weights.

## 1.1) How the Project Evolved (Start -> Now)

What we tried at the start:
- A single-window, threshold-only alert path.
- Simple yes/no prompts without temporal smoothing.
- Immediate alerting on any positive window.

Problems we saw early:
- Alerts oscillated quickly (on/off flicker).
- Too many false positives on normal motion.
- Missed short but critical events when a single window was weak.

What we do now:
- Sliding windows with temporal smoothing and hysteresis.
- Dual modes (fast and high_accuracy) for latency vs stability.
- Instant and severity gates for critical moments.
- Dedup and alert gap control to reduce spam.
- Optional crime targeting to focus on one class only.

How it evolved to the current pipeline:
1. Added window sampling (uniform + motion peaks) for better context.
2. Added temporal filter (trigger/release) to stabilize alerts.
3. Added fast mode for low latency and high_accuracy mode for precision.
4. Added dedup and cooldown to control repeated alerts.
5. Added LoRA path for future adaptation without breaking base inference.
6. Added crime-target selection to focus on a single crime at run time.

## 2) Project Structure

Core files:
- run_realtime.py: CLI entrypoint.
- runtime.py: window loop, temporal filter, dedup, alert output.
- vlm_engine.py: VLM prompts, scoring, and gating.
- configs.py: mode presets and validation.
- alerts.py: severity buckets and terminal coloring.

Supporting scripts:
- scripts/benchmark_modes.py
- scripts/generate_report.py
- scripts/prepare_finetune_data.py
- scripts/push_to_hf.py

Docs:
- docs/ARCHITECTURE.md
- docs/TUNING.md
- docs/FINETUNE.md
- docs/HUGGINGFACE.md
- docs/modle.md

## 3) Environment Setup

1. Go to project folder.
2. Activate environment.
3. Install dependencies if needed.

Example:
```bash
cd /data/video_analytics/real-time
conda activate VADTree
```

## 4) Run Modes

Two core modes:
- fast: lower latency, faster reaction, less context.
- high_accuracy: higher precision, more context, slower.

Optional crime targeting:
- Use --crime_target to focus on a single crime category.
- Supported: all, stealing, assault, fire, intrusion, accident, vandalism, robbery.

## 5) Input Types

Supported input sources:
- file (video_path or input_source)
- rtsp stream
- camera index

## 6) Windowed Processing

The runtime divides video into windows:
- window_sec: window duration
- step_sec: step between windows

Each window is sampled into frames using:
- uniform sampling
- motion-peak sampling

## 7) VLM Analysis and Scoring

For each window:
1. Selected frames are passed to Qwen2-VL.
2. Prompts produce structured signals and short descriptions.
3. A window_score is computed from votes, confidence, and severity.

Fast mode:
- quick yes/no prompts
- fast keyword and severity scoring

High-accuracy mode:
- structured JSON output with verdict, confidence, risk level

## 8) Alert Decision Logic

Runtime applies:
- temporal smoothing (vote_horizon_windows)
- trigger/release thresholds (hysteresis)
- instant and severity gates
- cooldown and alert gap control
- deduplication of repeated alerts

## 9) Outputs

Per run outputs:
- results/<video>_<mode>_<crime>/window_flags.jsonl
- results/alerts_global.log
- alert_*.jpg snapshots on alert windows

## 10) Benchmark and Report

Benchmark modes:
```bash
python scripts/benchmark_modes.py --video_path /path/video.mp4
```

Generate report:
```bash
python scripts/generate_report.py --video_name VideoName
```

## 11) Optional LoRA Fine-Tuning

Steps:
1. Create annotations CSV
2. Convert to JSONL + frames
3. Train LoRA
4. Run inference with adapter

Example:
```bash
python run_realtime.py \
  --mode high_accuracy \
  --video_path /path/video.mp4 \
  --model_source lora \
  --lora_adapter_path /data/video_analytics/real-time/finetuned_qwen2vl_lora
```

## 12) Hugging Face Publish

Publish code or adapters:
```bash
python3 scripts/push_to_hf.py --repo_id username/realtime-sentinel --source project --private
python3 scripts/push_to_hf.py --repo_id username/realtime-sentinel-lora --source lora --private
```

## 13) Full Minimal Run Examples

Fast mode:
```bash
python run_realtime.py --mode fast --video_path /path/video.mp4
```

High-accuracy mode:
```bash
python run_realtime.py --mode high_accuracy --video_path /path/video.mp4
```

Targeted crime:
```bash
python run_realtime.py --mode fast --crime_target stealing --video_path /path/video.mp4
```

## 14) Notes for Presentation

- Emphasize dual-mode design for latency vs stability.
- Explain why windowed processing reduces noise.
- Highlight the optional crime-target mode for focused detection.
- Mention LoRA path is optional and does not break base inference.
- Show sample outputs and alert snapshots for evidence.
