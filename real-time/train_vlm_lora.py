#!/usr/bin/env python3
"""
LoRA fine-tuning pipeline for Qwen2-VL on CCTV anomaly instruction data.

Dataset format (JSONL):
{"image_path": "/abs/or/rel/path.jpg", "prompt": "...", "response": "..."}

This script does not run automatically; execute manually when ready.
"""

import argparse
import json
import os
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import torch
from PIL import Image
from torch.utils.data import Dataset
from transformers import (
    AutoProcessor,
    Qwen2VLForConditionalGeneration,
    Trainer,
    TrainingArguments,
)

from peft import LoraConfig, get_peft_model

# qwen_vl_utils location fallback when real-time is outside VADTree.
THIS_DIR = Path(__file__).resolve().parent
CANDIDATE_ROOTS = [THIS_DIR.parent / "VADTree", THIS_DIR.parent]
for root in CANDIDATE_ROOTS:
    if (root / "qwen_vl_utils.py").exists() and str(root) not in sys.path:
        sys.path.append(str(root))

from qwen_vl_utils import process_vision_info  # noqa: E402


def set_seed(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


class CCTVInstructionDataset(Dataset):
    def __init__(self, jsonl_path: str):
        self.rows: List[Dict] = []
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if "image_path" not in obj or "prompt" not in obj or "response" not in obj:
                    raise ValueError("Each row must contain image_path, prompt, response")
                self.rows.append(obj)
        if not self.rows:
            raise ValueError(f"No samples found in {jsonl_path}")

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, idx: int):
        return self.rows[idx]


@dataclass
class BatchCollator:
    processor: AutoProcessor
    max_length: int

    def __call__(self, features: List[Dict]) -> Dict[str, torch.Tensor]:
        texts = []
        images_batch = []
        videos_batch = []

        for item in features:
            image = Image.open(item["image_path"]).convert("RGB")
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": str(item["prompt"])},
                    ],
                },
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": str(item["response"])}],
                },
            ]
            text = self.processor.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=False,
            )
            img_in, vid_in = process_vision_info(messages)
            texts.append(text)
            images_batch.append(img_in)
            videos_batch.append(vid_in)

        # For Qwen2-VL, processor accepts lists for batched text/images/videos.
        model_inputs = self.processor(
            text=texts,
            images=images_batch,
            videos=videos_batch,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )

        labels = model_inputs["input_ids"].clone()
        pad_id = self.processor.tokenizer.pad_token_id
        if pad_id is not None:
            labels[labels == pad_id] = -100
        model_inputs["labels"] = labels
        return model_inputs


def parse_args():
    parser = argparse.ArgumentParser(description="LoRA fine-tune Qwen2-VL for CCTV alerts")
    parser.add_argument("--train_jsonl", required=True, help="Training JSONL path")
    parser.add_argument("--val_jsonl", required=True, help="Validation JSONL path")
    parser.add_argument("--model_id", default="Qwen/Qwen2-VL-2B-Instruct")
    parser.add_argument("--output_dir", default="./finetuned_qwen2vl_lora")

    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--batch_size", type=int, default=1)
    parser.add_argument("--grad_accum", type=int, default=8)
    parser.add_argument("--max_length", type=int, default=2048)
    parser.add_argument("--warmup_ratio", type=float, default=0.03)
    parser.add_argument("--weight_decay", type=float, default=0.01)

    parser.add_argument("--lora_r", type=int, default=16)
    parser.add_argument("--lora_alpha", type=int, default=32)
    parser.add_argument("--lora_dropout", type=float, default=0.05)

    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--bf16", action="store_true")
    parser.add_argument("--fp16", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    set_seed(args.seed)

    os.makedirs(args.output_dir, exist_ok=True)

    processor = AutoProcessor.from_pretrained(args.model_id)

    model = Qwen2VLForConditionalGeneration.from_pretrained(
        args.model_id,
        torch_dtype=torch.bfloat16 if args.bf16 else (torch.float16 if args.fp16 else torch.float32),
        device_map="auto",
    )

    lora_cfg = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "up_proj", "down_proj", "gate_proj"],
    )
    model = get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()

    train_ds = CCTVInstructionDataset(args.train_jsonl)
    val_ds = CCTVInstructionDataset(args.val_jsonl)
    collator = BatchCollator(processor=processor, max_length=args.max_length)

    train_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        warmup_ratio=args.warmup_ratio,
        weight_decay=args.weight_decay,
        logging_steps=10,
        save_steps=200,
        eval_steps=200,
        evaluation_strategy="steps",
        save_strategy="steps",
        save_total_limit=2,
        bf16=args.bf16,
        fp16=args.fp16,
        report_to="none",
        remove_unused_columns=False,
    )

    trainer = Trainer(
        model=model,
        args=train_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=collator,
    )

    trainer.train()
    trainer.save_model(args.output_dir)
    processor.save_pretrained(args.output_dir)

    print(f"Saved LoRA fine-tuned model to: {args.output_dir}")


if __name__ == "__main__":
    main()
