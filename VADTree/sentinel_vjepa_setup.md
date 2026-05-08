# Sentinel V-JEPA v1 Setup and Run

## Why setup is needed
Your current `VADTree` env has `transformers==4.45.2`, which does not support `model_type='vjepa2'`.

## Recommended: keep baseline env safe
Use a separate env for V-JEPA tests.

```bash
conda create -n VADTree_vjepa python=3.10 -y
conda activate VADTree_vjepa
pip install --upgrade pip
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install decord pillow numpy
pip install "transformers>=5.5.0" accelerate safetensors sentencepiece
```

## Run V-JEPA scanner
```bash
cd /data/video_analytics/VADTree
python sentinel_vjepa_v1.py \
  --video_path /data/video_analytics/datasets/UCF_Crime_Videos/UCF_Crime_Test/Assault003_x264.mp4
```

## Faster / more sensitive profile
```bash
python sentinel_vjepa_v1.py \
  --video_path /data/video_analytics/datasets/UCF_Crime_Videos/UCF_Crime_Test/Assault003_x264.mp4 \
  --warmup_windows 4 \
  --trigger_ratio 0.50 \
  --release_ratio 0.30 \
  --instant_alert_ratio 0.68 \
  --min_alert_gap_sec 0
```

## Output paths
- `result/<video>_vjepa_alerts/window_scores.jsonl`
- `result/alerts_global.log`
- optional keyframes: `result/<video>_vjepa_alerts/alert_*.jpg` with `--save_alert_frames`
