# Supervisor Brief

## What is implemented
1. Standalone realtime anomaly system in `/data/video_analytics/real-time`.
2. Two operational modes:
- fast (3s/1s)
- high_accuracy (10s/5s)
3. Color-coded realtime terminal severity:
- red (high)
- orange (medium)
- yellow (low)
- green (normal)
4. Prompt-based VLM scoring with temporal smoothing and dedup memory.
5. Stream-ready runtime supporting file, RTSP, and camera inputs.
6. Base model and LoRA adapter inference routing.
7. Optional crime-target mode to focus on one category at runtime.
8. Window-level logging, alert snapshots, benchmark and report scripts.
9. Remote-view UI for continuous monitoring through VS Code port forwarding.

## Core deliverables
- `run_realtime.py`: realtime runner
- `runtime.py`: stream loop + dedup + alerting
- `vlm_engine.py`: VLM prompt/scoring and model loading
- `scripts/benchmark_modes.py`: mode comparison
- `scripts/generate_report.py`: supervisor-ready report outputs
- `ui/app.py`: live dashboard

## KPI outputs
- first alert latency
- alert density
- windows/sec throughput
- per-window evidence trail and alert snapshots

## Deployment model
- Runs on remote GPU server.
- UI viewed locally via VS Code remote port forwarding.
