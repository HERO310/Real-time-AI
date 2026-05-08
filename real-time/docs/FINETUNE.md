# VLM Fine-Tuning (LoRA)

This folder includes a real LoRA fine-tuning pipeline for Qwen2-VL.

## Files
- `train_vlm_lora.py` -> training script
- `configs_finetune.yaml` -> parameter template
- `scripts/prepare_finetune_data.py` -> dataset conversion utility

## Status
- Training is manual and optional.
- The repository includes a presentation-safe adapter folder at `finetuned_qwen2vl_lora`.
- Adapter weights (`adapter_model.safetensors`) are created only after real training.

## 1) Prepare annotations CSV
Expected columns:
- `video_path,start_s,end_s,event_type,description`

## 2) Create training JSONL
```bash
cd /data/video_analytics/real-time
conda activate VADTree
python scripts/prepare_finetune_data.py \
  --annotations_csv ./data/finetune/annotations.csv \
  --output_jsonl ./data/finetune/train.jsonl \
  --frames_dir ./data/finetune/frames
```

Create validation JSONL similarly (recommended separate CSV split).

## 3) Run LoRA training (manual)
```bash
cd /data/video_analytics/real-time
conda activate VADTree
python train_vlm_lora.py \
  --train_jsonl ./data/finetune/train.jsonl \
  --val_jsonl ./data/finetune/val.jsonl \
  --output_dir ./finetuned_qwen2vl_lora \
  --fp16
```

## 4) Output
- Training writes adapter artifacts to the `--output_dir` you provide.
- After training, the folder typically contains adapter weights (commonly `adapter_model.safetensors`) and config files.
- This repo already includes `./finetuned_qwen2vl_lora` with metadata/config placeholders for presentation.

## 5) Use fine-tuned adapter in realtime
```bash
cd /data/video_analytics/real-time
conda activate VADTree
python run_realtime.py \
  --mode high_accuracy \
  --video_path /data/video_analytics/datasets/UCF_Crime_Videos/UCF_Crime_Test/Assault003_x264.mp4 \
  --model_source lora \
  --lora_adapter_path /data/video_analytics/real-time/finetuned_qwen2vl_lora
```

## Notes
- Training is not triggered automatically.
- You can keep realtime inference on base model until trained model is validated.
