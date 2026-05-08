# Realtime Project Plan and Current Status

## Project Objective
Build a standalone realtime CCTV anomaly alert system outside VADTree with:
- very fast low-latency mode
- high-accuracy stable mode
- continuous window-by-window output
- color severity in terminal (red/orange/yellow/green)

## Current State (Done)
1. Project moved outside VADTree to `/data/video_analytics/real-time`.
2. Dual-mode realtime implementation is complete.
3. Fast mode implemented:
- 3s window, 1s step
- frequent alert checks for near-instant updates
4. High-accuracy mode implemented:
- 10s window, 5s step
- stronger temporal smoothing and stability
5. Color severity implemented in terminal output:
- HIGH -> red
- MEDIUM -> orange
- LOW -> yellow
- NORMAL -> green
6. Per-window realtime output line implemented with:
- time range
- status (FLAG/ALERT/ALERT-FAST)
- window score + smoothed score
- severity
- gate reasons
- description
7. Output artifacts implemented:
- per-video `window_flags.jsonl`
- global `alerts_global.log`
- alert snapshots `alert_*.jpg`
8. Docs added for architecture and tuning.
9. Syntax/CLI validation passed.
10. Real VLM fine-tuning pipeline files added (not executed):
- `train_vlm_lora.py`
- `configs_finetune.yaml`
- `scripts/prepare_finetune_data.py`
- `docs/FINETUNE.md`
11. Input source expansion implemented:
- file input
- RTSP stream input
- camera input
- reconnect logic in stream reader
12. Model routing implemented:
- base model inference
- LoRA adapter inference (`--model_source lora --lora_adapter_path ...`)
13. Alert quality hardening implemented:
- short-horizon dedup memory
- false-positive suppression heuristics for benign descriptors
14. UI and supervisor reporting implemented:
- dashboard app in `ui/app.py`
- UI launcher script `scripts/run_ui.sh`
- benchmark extension with elapsed and windows/sec
- report generator `scripts/generate_report.py`
- supervisor brief `docs/SUPERVISOR_BRIEF.md`

## Folder Structure (Implemented)
- `run_realtime.py` -> CLI entrypoint
- `runtime.py` -> main realtime loop + temporal logic
- `vlm_engine.py` -> prompt engine + model scoring
- `configs.py` -> mode presets + validation
- `alerts.py` -> color and level utilities
- `scripts/benchmark_modes.py` -> mode comparison helper
- `docs/ARCHITECTURE.md` -> system architecture
- `docs/TUNING.md` -> threshold tuning guide
- `README.md` -> run instructions
- `results/` -> generated logs and snapshots

## Known Notes
1. TensorFlow startup warnings may appear due to environment libraries; scanner still runs.
2. Model may over-alert on some clips in fast mode; expected tradeoff for low latency.

## Next Steps (Recommended)
1. Tune fast mode to reduce false alerts while keeping 3s cadence.
2. Add scenario profile presets:
- indoor_night
- outdoor_day
- crowded_scene
3. Add optional webhook/REST output for external alert integration.
4. Add service wrapper (tmux/systemd) for persistent deployment.
5. Add ground-truth backed evaluation script for precision/recall/F1.

## Run Commands
Fast mode:
```bash
cd /data/video_analytics/real-time
conda activate VADTree
python run_realtime.py --mode fast --video_path /data/video_analytics/datasets/UCF_Crime_Videos/UCF_Crime_Test/Assault003_x264.mp4
```

High-accuracy mode:
```bash
cd /data/video_analytics/real-time
conda activate VADTree
python run_realtime.py --mode high_accuracy --video_path /data/video_analytics/datasets/UCF_Crime_Videos/UCF_Crime_Test/Assault003_x264.mp4
```

Benchmark both modes:
```bash
cd /data/video_analytics/real-time
conda activate VADTree
python scripts/benchmark_modes.py --video_path /data/video_analytics/datasets/UCF_Crime_Videos/UCF_Crime_Test/Assault003_x264.mp4
```

RTSP run:
```bash
cd /data/video_analytics/real-time
conda activate VADTree
python run_realtime.py --mode fast --input_type rtsp --input_source rtsp://user:pass@camera-ip/stream
```

Camera run:
```bash
cd /data/video_analytics/real-time
conda activate VADTree
python run_realtime.py --mode fast --input_type camera --camera_index 0
```

LoRA inference run:
```bash
cd /data/video_analytics/real-time
conda activate VADTree
python run_realtime.py --mode high_accuracy --video_path /data/video_analytics/datasets/UCF_Crime_Videos/UCF_Crime_Test/Assault003_x264.mp4 --model_source lora --lora_adapter_path /data/video_analytics/real-time/finetuned_qwen2vl_lora
```

UI run (remote server):
```bash
cd /data/video_analytics/real-time
conda activate VADTree
./scripts/run_ui.sh 127.0.0.1 8501
```
