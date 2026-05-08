# Architecture

## Objective
Realtime CCTV anomaly alerts with minimal latency and color-coded severity output.

## Core Modules
- `run_realtime.py`: CLI entrypoint and argument parsing.
- `configs.py`: mode presets and validation.
- `runtime.py`: window reader, temporal filter, dedup, output writes.
- `vlm_engine.py`: VLM prompts, scoring, and crime-target filtering.
- `alerts.py`: severity buckets and terminal colors.

## Supporting Modules
- `scripts/benchmark_modes.py`: mode comparison runs.
- `scripts/generate_report.py`: JSON/CSV/Markdown summaries.
- `scripts/prepare_finetune_data.py`: training data conversion.
- `train_vlm_lora.py`: LoRA training entrypoint.
- `scripts/push_to_hf.py`: optional Hugging Face publish helper.
- `ui/app.py`: Streamlit dashboard.

## Runtime Flow
1. Resolve input type (file/RTSP/camera).
2. Create sliding windows (`window_sec`, `step_sec`).
3. Sample frames (uniform + motion peaks).
4. Run prompts in `vlm_engine.py` (fast or high_accuracy; optional crime target).
5. Compute `window_score` and `severity`.
6. Apply temporal smoothing + gates (trigger/release/instant/severity).
7. Deduplicate and enforce minimum alert gaps.
8. Emit terminal line, write JSONL, and save alert snapshots when triggered.

## Inputs and Outputs
- Inputs: local video file, RTSP stream, or camera index.
- Output folders: `results/<video_or_stream>_<mode>` plus `_<crime>` when crime_target is not `all`.
