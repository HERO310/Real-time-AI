# Model Documentation (Professor Brief)

Date: 30 April 2026
Project: Realtime CCTV Anomaly Alerting
Location: /data/video_analytics/real-time

## 1) What We Built

We built a realtime anomaly alerting system for CCTV-style video streams with two operating modes:
- Fast mode: lower latency, approximate decisions, early warning intent.
- High-accuracy mode: slower than fast mode, stronger evidence aggregation, higher precision.
- Optional crime-target mode: focus on a single crime category (for example stealing or fire).

The pipeline processes short temporal windows, analyzes representative frames with a vision-language model, then applies temporal and safety logic before raising alerts.

## 2) Models Used

Primary inference model:
- Qwen2-VL-2B-Instruct (base VLM).

Optional adapted model path:
- Qwen2-VL base + LoRA adapter (produced by our fine-tuning pipeline).

Why this family:
- Strong instruction-following for structured anomaly reasoning.
- Practical deployment size for realtime experiments on available hardware.
- Compatible with prompt-based risk scoring and event descriptions.

## 3) Current System Files and Responsibilities

Core runtime:
- run_realtime.py: CLI entrypoint and runtime options.
- runtime.py: sliding-window loop, file/RTSP/camera reading, dedup behavior.
- vlm_engine.py: prompt orchestration, scoring, mode-specific logic.
- configs.py: mode presets and validation.
- alerts.py: severity mapping and console color output.

Training artifacts:
- train_vlm_lora.py: LoRA fine-tuning script.
- scripts/prepare_finetune_data.py: annotation to JSONL conversion and frame extraction.
- configs_finetune.yaml: training configuration template.

Support and reporting:
- scripts/benchmark_modes.py: mode performance comparison.
- scripts/generate_report.py: JSON/CSV/Markdown reporting.
- ui/app.py: Streamlit dashboard.

## 4) How Inference Works (End to End)

1. Input source selection
- Video file, RTSP stream, or local camera.

2. Windowing
- The stream is split into short windows (mode dependent).
- Each window is sampled into key frames.

3. VLM analysis
- The model receives frames and structured prompts.
- It returns anomaly likelihood, event cues, and severity hints.

Optional focus:
- `--crime_target` limits detection to one selected crime category.

4. Scoring and gating
- Mode-specific scoring (fast vs high-accuracy).
- Critical-event checks for high-risk cues (example: fire/smoke/weapon/assault).

5. Temporal stability
- Smoothing and dedup logic reduce oscillation and repeated spam alerts.

6. Output
- Per-window terminal status.
- Alert logs and optional keyframe snapshots for audits.

## 5) Fast vs High-Accuracy: Why Two Modes

Fast mode:
- Goal: quick warning, low latency, acceptable recall.
- Tradeoff: can be noisier or less semantically rich.

High-accuracy mode:
- Goal: stronger confidence and event detail.
- Tradeoff: more compute and slower response.

Reason for dual-mode design:
- Realtime CCTV operations often require different behaviors during live monitoring vs post-event verification.
- One fixed mode cannot satisfy both latency-critical and precision-critical scenarios.

## 6) Fine-Tuning Strategy (LoRA)

We implemented a real fine-tuning path, but kept training manual to prevent accidental unstable deployments.

Current adapter artifact location in this repository:
- /data/video_analytics/real-time/finetuned_qwen2vl_lora
- Config file available at: /data/video_analytics/real-time/finetuned_qwen2vl_lora/adapter_config.json
- Run metadata available at: /data/video_analytics/real-time/finetuned_qwen2vl_lora/training_summary.json
Note: adapter weights (`adapter_model.safetensors`) are not included by default.

Data flow:
1. Prepare CSV annotations:
- video_path,start_s,end_s,event_type,description

2. Convert to JSONL + extracted frames:
- scripts/prepare_finetune_data.py

3. Train LoRA adapter:
- train_vlm_lora.py

4. Inference with adapter:
- run_realtime.py with --model_source lora and --lora_adapter_path

Important:
- Runtime does not auto-load this adapter.
- Adapter loading is only explicit via CLI flags, which keeps the default path non-breaking.

Why LoRA, not full-model fine-tuning:
- Lower GPU memory and faster iteration.
- Safer rollback (base model remains intact).
- Better for experimental cycles where labels and prompts evolve.

## 7) Why We Did This, Not That

1. Chosen: Prompted VLM + temporal logic
Not chosen: Pure single-window threshold script
Reason:
- Single-window thresholding was unstable and oscillatory.
- Temporal logic provides robust alerts in noisy CCTV conditions.

2. Chosen: Qwen2-VL base + optional LoRA
Not chosen: Immediate full-parameter retraining
Reason:
- Full retraining is costly, slower, and harder to maintain.
- LoRA gives adaptation with lower risk and faster turnaround.

3. Chosen: Two runtime modes
Not chosen: One universal profile
Reason:
- Latency and precision requirements conflict in real operations.
- Dual mode is operationally practical.

4. Chosen: Dedup and false-positive suppression
Not chosen: Emit all positive windows
Reason:
- Raw positives overwhelm operators.
- Suppression and dedup improve actionability.

5. Chosen: Keep baseline scripts untouched while adding standalone folder
Not chosen: invasive edits across old files
Reason:
- Reduced regression risk.
- Easier to compare old vs new behavior.

6. Chosen: Optional crime-target filtering
Not chosen: separate scripts per crime type
Reason:
- One configurable runtime is easier to maintain and demo.
- Crime-specific focus is selected at run time via CLI.

## 8) Reliability and Non-Breaking Approach

Practices used to avoid breaking the pipeline:
- New capability added under a separate standalone realtime folder.
- Base model path preserved as default fallback.
- LoRA path is optional and explicit.
- Training is manual only (never auto-triggered by inference scripts).
- Reporting and benchmarking scripts included for verification.

## 9) Reproducible Usage (Minimal)

Base model inference:
- python run_realtime.py --mode high_accuracy --video_path /path/to/video.mp4

LoRA adapter inference:
- python run_realtime.py --mode high_accuracy --video_path /path/to/video.mp4 --model_source lora --lora_adapter_path /path/to/adapter

Repository-local adapter path example:
- python run_realtime.py --mode high_accuracy --video_path /path/to/video.mp4 --model_source lora --lora_adapter_path /data/video_analytics/real-time/finetuned_qwen2vl_lora

Fast mode inference:
- python run_realtime.py --mode fast --video_path /path/to/video.mp4

Targeted crime inference:
- python run_realtime.py --mode fast --crime_target stealing --video_path /path/to/video.mp4

## 10) Known Limitations and Honest Status

- Fast mode still needs per-dataset threshold tuning for best recall/precision balance.
- Live RTSP and LoRA path should be revalidated after each environment/package update.
- Fine-tuning quality depends heavily on annotation quality and class balance.