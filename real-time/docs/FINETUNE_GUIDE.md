# Fine-tuning Guide (LoRA)

This guide explains how to fine-tune the Qwen2-VL model specifically for CCTV anomaly detection using the provided LoRA pipeline.

---

## 1. Training Parameters
The following configuration is optimized for high-quality instruction following on surveillance data while fitting within a 24GB VRAM budget.

### Core Configuration
| Parameter | Value |
| :--- | :--- |
| **Base Model** | Qwen2-VL-2B-Instruct |
| **Training Dataset** | 5,000 annotated CCTV instruction pairs |
| **Hardware** | 1x NVIDIA RTX 4090 (24 GB) |
| **Mixed Precision** | FP16 |
| **Training Script** | `train_vlm_lora.py` |
| **Adapter Output** | `finetuned_qwen2vl_lora/` |

### Hyperparameters (LoRA)
| Parameter | Value | Description |
| :--- | :--- | :--- |
| **Epochs** | 2 | Total passes over the dataset |
| **Learning Rate** | 2e-4 | Peak learning rate for AdamW |
| **Batch Size** | 1 | Samples per GPU per step |
| **Grad Accumulation** | 8 | Effective batch size of 8 |
| **LoRA Rank (R)** | 16 | Dimension of the low-rank matrices |
| **LoRA Alpha** | 32 | Scaling factor for LoRA weights |
| **LoRA Dropout** | 0.05 | Dropout probability for LoRA layers |
| **Max Length** | 2048 | Maximum token sequence length |

---

## 2. How to Run Fine-tuning

### Step 1: Prepare Data
Ensure your training data is in JSONL format, where each line contains an image path, a prompt, and the expected AI response.
```json
{"image_path": "path/to/frame.jpg", "prompt": "Describe this CCTV scene.", "response": "Normal traffic flow."}
```

### Step 2: Execute Training
Run the training script with the following command. This will initialize the model and start the LoRA weight adjustment.

```bash
cd /data/video_analytics/real-time
conda activate VADTree

python train_vlm_lora.py \
    --train_jsonl /path/to/train.jsonl \
    --val_jsonl /path/to/val.jsonl \
    --epochs 2 \
    --lr 2e-4 \
    --fp16 \
    --output_dir ./finetuned_qwen2vl_lora
```

---

## 3. Using the Fine-tuned Adapter
Once training is complete, the adapter will be saved in `./finetuned_qwen2vl_lora`. You can run the real-time scanner using this new "brain" by adding the `--model_source lora` flag.

### Command:
```bash
python run_realtime.py \
    --mode high_accuracy \
    --model_source lora \
    --lora_adapter_path ./finetuned_qwen2vl_lora \
    --video_path /path/to/test_video.mp4
```

### Expected Improvements:
- **Higher Precision**: Significant reduction in false alerts for common movements.
- **Better Description**: The AI will use more technical "surveillance-style" language.
- **Target Alignment**: Improved ability to follow the `--crime_target` instructions.
