# Commands Guide (Realtime Sentinel)

This file lists the exact command order collaborators can follow.

## 1) Go to project and activate env
```bash
cd /data/video_analytics/real-time
conda activate VADTree
```

## 2) Quick sanity checks
```bash
python -m py_compile run_realtime.py runtime.py vlm_engine.py alerts.py configs.py scripts/benchmark_modes.py scripts/generate_report.py ui/app.py train_vlm_lora.py scripts/prepare_finetune_data.py
python run_realtime.py --help | head -n 80
```

## 3) Realtime inference (file input)

### 3.1 Fast mode (3s window)
```bash
python run_realtime.py \
  --mode fast \
  --video_path /data/video_analytics/datasets/UCF_Crime_Videos/UCF_Crime_Test/Arson003_x264.mp4
```

### 3.2 High-accuracy mode (10s window)
```bash
python run_realtime.py \
  --mode high_accuracy \
  --video_path /data/video_analytics/datasets/UCF_Crime_Videos/UCF_Crime_Test/Arson003_x264.mp4
```

### 3.3 Fast mode aggressive tuning (if misses events)
```bash
python run_realtime.py \
  --mode fast \
  --video_path /data/video_analytics/datasets/UCF_Crime_Videos/UCF_Crime_Test/Arson003_x264.mp4 \
  --instant_alert_ratio 0.52 \
  --severity_alert_ratio 0.65 \
  --trigger_ratio 0.40 \
  --release_ratio 0.24 \
  --max_windows 40
```

## 4) Realtime inference (RTSP / camera)

### 4.1 RTSP stream
```bash
python run_realtime.py \
  --mode fast \
  --input_type rtsp \
  --input_source rtsp://user:pass@camera-ip/stream
```

### 4.2 USB camera
```bash
python run_realtime.py \
  --mode fast \
  --input_type camera \
  --camera_index 0
```

## 5) Run with fine-tuned LoRA adapter
```bash
python run_realtime.py \
  --mode high_accuracy \
  --video_path /data/video_analytics/datasets/UCF_Crime_Videos/UCF_Crime_Test/Arson003_x264.mp4 \
  --model_source lora \
  --lora_adapter_path /data/video_analytics/real-time/finetuned_qwen2vl_lora
```

## 6) Benchmark both modes
```bash
python scripts/benchmark_modes.py \
  --video_path /data/video_analytics/datasets/UCF_Crime_Videos/UCF_Crime_Test/Arson003_x264.mp4
```

## 7) Generate supervisor-ready report
```bash
python scripts/generate_report.py --video_name Arson003_x264
```

## 8) Launch UI on remote server
```bash
pip install streamlit
./scripts/run_ui.sh 127.0.0.1 8501
```

## 9) View UI from local machine (remote VS Code workflow)
1. In VS Code (connected to remote), open `Ports` panel.
2. Forward port `8501`.
3. Open the forwarded localhost URL in browser.

## 10) SSH tunnel fallback (if not using VS Code ports)
```bash
ssh -L 8501:127.0.0.1:8501 user@remote-host
```

## 11) Where outputs are saved
- Window logs: `results/<video_or_stream>_<mode>/window_flags.jsonl`
- Alert snapshots: `results/<video_or_stream>_<mode>/alert_*.jpg`
- Global alerts: `results/alerts_global.log`
- Benchmark summary: `results/<video>_mode_benchmark.json`
- Reports: `results/<video>_report.json|csv|md`

## 12) Hugging Face publish
Install once:
```bash
pip install huggingface_hub
```

Login once:
```bash
huggingface-cli login
```

Publish the whole project:
```bash
python3 scripts/push_to_hf.py \
  --repo_id username/realtime-sentinel \
  --source project \
  --private
```

Publish only the LoRA adapter:
```bash
python3 scripts/push_to_hf.py \
  --repo_id username/realtime-sentinel-lora \
  --source lora \
  --private
```
