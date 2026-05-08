# Hugging Face Hub Setup

This project can be published to Hugging Face Hub in two ways:

1. Code repository upload
- uploads the realtime runner, configs, docs, UI, and training scripts
- keeps the current fast and high_accuracy modes intact

2. LoRA artifact upload
- uploads only the prepared LoRA adapter folder
- useful for sharing a fine-tuned adapter separately from the code

## What to upload

Recommended code files:
- run_realtime.py
- runtime.py
- vlm_engine.py
- configs.py
- alerts.py
- scripts/
- ui/
- docs/
- README.md
- commands.md

Recommended LoRA files:
- finetuned_qwen2vl_lora/README.md
- finetuned_qwen2vl_lora/adapter_config.json
- finetuned_qwen2vl_lora/training_summary.json
- finetuned_qwen2vl_lora/adapter_model.safetensors when a real trained adapter exists

The helper script only uploads allowlisted files. It does not include:
- results/
- large checkpoints outside the allowlist

## Before uploading

1. Install the Hugging Face client:
```bash
pip install huggingface_hub
```

2. Log in once:
```bash
huggingface-cli login
```

3. Create a repo name on the Hub, for example:
- `username/realtime-sentinel`
- `username/realtime-sentinel-lora`

## Publish the whole project

```bash
cd /data/video_analytics/real-time
python3 scripts/push_to_hf.py \
  --repo_id username/realtime-sentinel \
  --source project \
  --private
```

## Publish only the LoRA adapter

```bash
cd /data/video_analytics/real-time
python3 scripts/push_to_hf.py \
  --repo_id username/realtime-sentinel-lora \
  --source lora \
  --private
```

## Notes

- The realtime code still runs locally the same way after publishing.
- The Hugging Face repo does not replace the local fast/high_accuracy modes.
- If you want a public demo repo later, remove `--private`.