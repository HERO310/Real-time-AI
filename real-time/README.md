# Realtime Sentinel (Dual Mode)

Standalone realtime CCTV anomaly alert package.

## Modes
- `fast`: 3s window / 1s step (low latency).
- `high_accuracy`: 10s window / 5s step (stable decisions).

## Severity Colors (Terminal)
- High: red
- Medium: orange
- Low: yellow
- Normal: green

## Run (File Input)
```bash
cd /data/video_analytics/real-time
conda activate VADTree
python run_realtime.py --mode fast --video_path /data/video_analytics/datasets/UCF_Crime_Videos/UCF_Crime_Test/Assault003_x264.mp4
```

```bash
cd /data/video_analytics/real-time
conda activate VADTree
python run_realtime.py --mode high_accuracy --video_path /data/video_analytics/datasets/UCF_Crime_Videos/UCF_Crime_Test/Assault003_x264.mp4
```

## Run (RTSP / Camera)
```bash
python run_realtime.py --mode fast --input_type rtsp --input_source rtsp://user:pass@camera-ip/stream
```

```bash
python run_realtime.py --mode fast --input_type camera --camera_index 0
```

## Run (LoRA Adapter Inference)
```bash
python run_realtime.py \
	--mode high_accuracy \
	--video_path /data/video_analytics/datasets/UCF_Crime_Videos/UCF_Crime_Test/Assault003_x264.mp4 \
	--model_source lora \
	--lora_adapter_path /data/video_analytics/real-time/finetuned_qwen2vl_lora
```

## Optional Overrides
```bash
python run_realtime.py \
	--mode fast \
	--video_path /path/video.mp4 \
	--instant_alert_ratio 0.58 \
	--severity_alert_ratio 0.70 \
	--dedup_window_sec 3.0
```

## Targeted Crime Mode
```bash
python run_realtime.py \
	--mode fast \
	--crime_target stealing \
	--video_path /path/video.mp4
```

Supported targets:
- all
- stealing
- assault
- fire
- intrusion
- accident
- vandalism
- robbery

See Hugging Face publishing instructions in [docs/HUGGINGFACE.md](docs/HUGGINGFACE.md).

## Output
- `results/<video_or_stream>_<mode>/window_flags.jsonl`
- `results/<video_or_stream>_<mode>/alert_*.jpg`
- `results/alerts_global.log`

## Quick Benchmark
```bash
python scripts/benchmark_modes.py --video_path /data/video_analytics/datasets/UCF_Crime_Videos/UCF_Crime_Test/Assault003_x264.mp4
```

## Generate Supervisor Report
```bash
python scripts/generate_report.py --video_name Assault003_x264
```

## UI (Remote Server + Local VS Code)
1. Install UI dependency once:
```bash
pip install streamlit
```

2. Start UI on remote server:
```bash
cd /data/video_analytics/real-time
conda activate VADTree
./scripts/run_ui.sh 127.0.0.1 8501
```

3. In VS Code (connected to remote):
- Open `Ports` panel.
- Forward port `8501`.
- Open forwarded local URL in browser.

4. SSH tunnel fallback (outside VS Code):
```bash
ssh -L 8501:127.0.0.1:8501 user@remote-host
```
