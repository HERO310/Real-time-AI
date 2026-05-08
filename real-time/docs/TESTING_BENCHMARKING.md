# Testing and Benchmarking (Current Project State)

This document explains how testing and benchmarking is done in this project. It is documentation only; no commands are executed here.

## 1) What "Testing" Means Here

There are no unit tests or CI pipelines in this repository. Validation is done by:
- running the realtime pipeline end-to-end,
- checking window-level logs,
- comparing fast vs high_accuracy behavior,
- generating reports from those logs.

These steps are the official, reproducible testing path for this codebase.

## 2) Runtime Validation (Smoke Test)

Purpose:
- prove the pipeline runs end-to-end and writes output files.

Command:
```bash
python run_realtime.py --mode fast --video_path /path/to/video.mp4
```

Expected outputs:
- results/<video>_<mode>[_<crime>]/window_flags.jsonl
- results/alerts_global.log
- alert_*.jpg snapshots on alert windows

What to verify:
- terminal prints per-window lines
- JSONL rows contain window scores, severity, and gate info

## 3) Benchmarking (Fast vs High-Accuracy)

Script:
- scripts/benchmark_modes.py

What it does:
- runs fast mode and high_accuracy mode
- measures elapsed time and windows/sec
- counts alerts and first-alert timing
- writes a benchmark JSON

Command:
```bash
python scripts/benchmark_modes.py --video_path /path/to/video.mp4
```

With annotations (adds precision/recall/F1/FPR and class-wise rates):
```bash
python scripts/benchmark_modes.py \
  --video_path /path/to/video.mp4 \
  --annotations_csv /path/to/annotations.csv \
  --class_wise
```

Targeted crime benchmarking:
```bash
python scripts/benchmark_modes.py \
  --video_path /path/to/video.mp4 \
  --crime_target stealing
```

Output:
- results/<video>_mode_benchmark.json

Fields inside the JSON:
- total_windows
- alerts
- alerts_per_100_windows
- first_alert_s
- elapsed_sec
- windows_per_sec
- eval_metrics (if annotations provided)
- class_metrics (if --class_wise)

## 4) Report Generation (Presentation Summary)

Script:
- scripts/generate_report.py

What it does:
- reads fast and high_accuracy logs
- summarizes total windows, alert counts, and alerts/hour
- writes JSON, CSV, and Markdown reports

Command:
```bash
python scripts/generate_report.py --video_name VideoStem
```

With annotations (adds precision/recall/F1/FPR and class-wise rates):
```bash
python scripts/generate_report.py \
  --video_name VideoStem \
  --annotations_csv /path/to/annotations.csv \
  --class_wise
```

Targeted crime report:
```bash
python scripts/generate_report.py \
  --video_name VideoStem \
  --crime_target stealing
```

Outputs:
- results/<video>_report.json
- results/<video>_report.csv
- results/<video>_report.md

## 5) Crime-Target Validation

The system can focus on a single crime category at runtime using --crime_target.

Command:
```bash
python run_realtime.py --mode fast --crime_target stealing --video_path /path/to/video.mp4
```

Expected proof:
- output folder name includes _stealing
- window_flags.jsonl includes "crime_target": "stealing"

## 6) Fine-Tuning Evaluation (LoRA)

There is a real LoRA training script, but training is manual.

Data preparation:
- scripts/prepare_finetune_data.py reads a CSV and creates JSONL samples.

Training:
- train_vlm_lora.py trains a LoRA adapter.
- Evaluation is done during training on val_jsonl (Trainer eval_steps).

Post-training validation:
- run realtime inference with --model_source lora and compare logs/metrics.

Example commands:
```bash
python scripts/prepare_finetune_data.py \
  --annotations_csv ./data/finetune/annotations.csv \
  --output_jsonl ./data/finetune/train.jsonl \
  --frames_dir ./data/finetune/frames

python train_vlm_lora.py \
  --train_jsonl ./data/finetune/train.jsonl \
  --val_jsonl ./data/finetune/val.jsonl \
  --output_dir ./finetuned_qwen2vl_lora \
  --fp16

python run_realtime.py \
  --mode high_accuracy \
  --video_path /path/to/video.mp4 \
  --model_source lora \
  --lora_adapter_path /data/video_analytics/real-time/finetuned_qwen2vl_lora
```

## 7) Evidence Artifacts You Can Show

- window_flags.jsonl (per-window evidence)
- alerts_global.log (global alert trail)
- alert_*.jpg (visual alert snapshots)
- *_mode_benchmark.json (fast vs high_accuracy metrics)
- *_report.json|csv|md (presentation summary)

## 8) Limitations (Honest Status)

- No automated unit tests exist in this repository.
- Benchmarking is empirical and depends on selected videos.
- Fine-tuning quality depends on the dataset quality and annotation accuracy.
