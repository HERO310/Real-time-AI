#!/usr/bin/env python3
"""
VADStream v10 (The Sentinel)
=============================
- High-speed, Multi-modal Real-time Alert System.
- Trigger: ImageBind (Visual + Audio) matching against Danger Phrases.
- Verifier: Qwen2-VL-2B (Temporal reasoning + Description).
- Architecture: Modular and Extensible.
"""

import sys, os, json, argparse, torch, time, warnings, collections
from pathlib import Path
from PIL import Image

VADTREE_ROOT = Path(__file__).parent.resolve().parent
import numpy as np
from decord import VideoReader, cpu
import imagebind.data as ib_data
from imagebind.models import imagebind_model
from imagebind.models.imagebind_model import ModalityType
from torchvision import transforms
from torchvision.transforms._transforms_video import NormalizeVideo

# Load VLM Judge
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────
#  MODULAR COMPONENTS
# ─────────────────────────────────────────────

class MultiModalEngine:
    """Tier 1: High-speed Visual/Audio Monitor."""
    def __init__(self, device="cuda"):
        self.device = device
        self.model = imagebind_model.imagebind_huge(pretrained=True).eval().to(device).half()
        self.modality = ModalityType
        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            NormalizeVideo(mean=(0.48145466, 0.4578275, 0.40821073), std=(0.26862954, 0.26130258, 0.27577711)),
        ])
        self.history = collections.deque(maxlen=10) # 5s memory

    @torch.no_grad()
    def get_vision_embedding(self, frames_np):
        idx = [0, len(frames_np)//2, -1] # 3-frame sample
        clip = torch.from_numpy(frames_np[idx]).permute(3, 0, 1, 2).float() / 255.0
        clip = self.transform(clip)
        inp = clip.unsqueeze(0).unsqueeze(1).to(self.device).half()
        emb = self.model({self.modality.VISION: inp})[self.modality.VISION]
        return torch.nn.functional.normalize(emb, dim=-1)

    @torch.no_grad()
    def get_text_anchors(self, phrases):
        """Pre-compute embeddings for danger keywords."""
        from imagebind import data
        tokens = data.load_and_transform_text(phrases, self.device)
        return torch.nn.functional.normalize(self.model({self.modality.TEXT: tokens})[self.modality.TEXT], dim=-1)

class CognitiveJudge:
    """Tier 2: Expert Temporal Analysis."""
    def __init__(self, device="cuda"):
        self.device = device
        model_path = "Qwen/Qwen2-VL-2B-Instruct"
        self.model = Qwen2VLForConditionalGeneration.from_pretrained(model_path, torch_dtype=torch.bfloat16, device_map="auto")
        self.processor = AutoProcessor.from_pretrained(model_path)

    def verify_and_describe(self, frames_np, category_list):
        """Verifies if an event happened and returns a 10-word description."""
        indices = np.linspace(0, len(frames_np)-1, 4, dtype=int)
        pil_images = [Image.fromarray(frames_np[i]) for i in indices]
        
        cats = ", ".join(category_list)
        prompt = f"Analyze this clip. Is any of these happening: {cats}? If YES, describe in 10 words. If NO, say 'NORMAL'."
        
        messages = [{"role": "user", "content": [*[{"type": "image", "image": img} for img in pil_images], {"type": "text", "text": prompt}]}]
        text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        img_in, vid_in = process_vision_info(messages)
        inputs = self.processor(text=[text], images=img_in, videos=vid_in, padding=True, return_tensors="pt").to(self.device)
        
        gen_ids = self.model.generate(**inputs, max_new_tokens=32)
        output = self.processor.batch_decode(gen_ids, skip_special_tokens=True)[0]
        response = output.split("assistant\n")[-1].strip()
        
        is_alert = "NORMAL" not in response.upper()
        return is_alert, response

class AlertDispatcher:
    """Clean Output Dispatcher."""
    @staticmethod
    def dispatch(ts, message, output_folder=None):
        print(f"🚨 [\033[91mALERT\033[0m] {ts:5.1f}s | {message}")
        if output_folder:
            log_path = output_folder / "alerts.log"
            with open(log_path, "a") as f:
                f.write(f"[{ts:.1f}s] {message}\n")

# ─────────────────────────────────────────────
#  THE SENTINEL ORCHESTRATOR
# ─────────────────────────────────────────────

class TheSentinel:
    def __init__(self, categories=["crime", "accident", "fight", "fire", "fall"]):
        self.categories = categories
        print(f"\n[Sentinel v10] Booting System Modules...")
        self.monitor = MultiModalEngine()
        self.judge = CognitiveJudge()
        self.dispatcher = AlertDispatcher()
        
        # Pre-compute text anchors for fast trigger
        self.anchor_embs = self.monitor.get_text_anchors(self.categories)
        self.jump_threshold = 0.08
        self.keyword_threshold = 0.15 # Sensitivity to text phrases

    def run_on_video(self, video_path):
        video_name = Path(video_path).stem
        output_dir = Path("./results") / f"{video_name}_sentinel"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        vr = VideoReader(video_path, ctx=cpu(0))
        fps = vr.get_avg_fps()
        win_f = int(1.0 * fps)
        vlm_win_f = int(10.0 * fps)
        
        print(f"🛡️ [SENTINEL ACTIVE] Monitoring: {video_name}")
        print(f"| Categories: {', '.join(self.categories)} |")
        print("-" * 75)

        for start in range(0, len(vr) - vlm_win_f, int(0.5 * fps)):
            monitor_frames = vr.get_batch(range(start, start + win_f)).asnumpy()
            curr_emb = self.monitor.get_vision_embedding(monitor_frames)
            ts = start / fps

            # --- Pulse 1: Semantic Deviation ---
            drift = 0.0
            if self.monitor.history:
                base = torch.cat(list(self.monitor.history)).mean(0, keepdim=True)
                base = torch.nn.functional.normalize(base, dim=-1)
                drift = 1.0 - (curr_emb @ base.T).item()
            self.monitor.history.append(curr_emb)

            # --- Pulse 2: Keyword Similarity ---
            keyword_sim = (curr_emb @ self.anchor_embs.T).max().item()

            # --- Trigger Check ---
            if drift > self.jump_threshold or keyword_sim > self.keyword_threshold:
                # Wake the Judge
                vlm_frames = vr.get_batch(range(start, start + vlm_win_f)).asnumpy()
                is_alert, report = self.judge.verify_and_describe(vlm_frames, self.categories)
                
                if is_alert:
                    self.dispatcher.dispatch(ts, report, output_dir)
                    # Save proof
                    Image.fromarray(vlm_frames[len(vlm_frames)//2]).save(output_dir / f"event_{ts:.1f}s.jpg")

        print(f"\n✅ [SENTINEL COMPLETE] Final Report at {output_dir}/alerts.log")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--video_path", required=True)
    parser.add_argument("--categories", nargs="+", default=["crime", "accident", "fight", "fire", "fall"])
    args = parser.parse_args()
    
    sentinel = TheSentinel(categories=args.categories)
    sentinel.run_on_video(args.video_path)
