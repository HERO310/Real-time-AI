#!/usr/bin/env python3
"""
VADStream v11 (Universal Scanner)
==================================
- Sliding Window Scanner (10.0s window / 5.0s step).
- Fast Monitor (ImageBind) -> Checks for any semantic change to skip static scenes.
- Expert Judge (Qwen2-VL)  -> Provides situational analysis for active scenes.
- Resides in main VADTree directory for direct execution.
"""

import sys, os, json, argparse, torch, time, warnings
from pathlib import Path
from PIL import Image

# 1. Setup Environment
VADTREE_ROOT = Path(__file__).parent.resolve()
sys.path.append(str(VADTREE_ROOT))
sys.path.append(str(VADTREE_ROOT / "ImageBind"))

import numpy as np
from decord import VideoReader, cpu
from imagebind.models import imagebind_model
from imagebind.models.imagebind_model import ModalityType
from torchvision import transforms
from torchvision.transforms._transforms_video import NormalizeVideo

# Load VLM
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────
#  V11 Scanner Engine
# ─────────────────────────────────────────────

class ScannerV11:
    def __init__(self, device="cuda"):
        self.device = device
        print(f"\n[Scanner v11] Booting Real-Time Modules...")
        
        # --- Tier 1 (Motion Monitor) ---
        self.ib_model = imagebind_model.imagebind_huge(pretrained=True).eval().to(device).half()
        self.ib_modality = ModalityType
        self.ib_transform = transforms.Compose([
            transforms.Resize((224, 224)),
            NormalizeVideo(mean=(0.48145466, 0.4578275, 0.40821073), std=(0.26862954, 0.26130258, 0.27577711)),
        ])

        # --- Tier 2 (Expert Judge) ---
        model_path = "Qwen/Qwen2-VL-2B-Instruct"
        self.vlm_model = Qwen2VLForConditionalGeneration.from_pretrained(model_path, torch_dtype=torch.bfloat16, device_map="auto")
        self.vlm_processor = AutoProcessor.from_pretrained(model_path)
        
        print(f"[Scanner v11] Modules Ready. Speed: Max. VRAM: {torch.cuda.memory_allocated()/1e9:.2f} GB")

    @torch.no_grad()
    def get_semantic_pulse(self, frames_np):
        """Quickly check if the scene has changed."""
        idx = [0, -1]
        clip = torch.from_numpy(frames_np[idx]).permute(3, 0, 1, 2).float() / 255.0
        clip = self.ib_transform(clip)
        inp = clip.unsqueeze(0).unsqueeze(1).to(self.device).half()
        return torch.nn.functional.normalize(self.ib_model({self.ib_modality.VISION: inp})[self.ib_modality.VISION], dim=-1)

    def analyze_situation(self, frames_np):
        """VLM high-precision situational analysis."""
        # 16 frames for 10s context (High spatial-temporal awareness)
        indices = np.linspace(0, len(frames_np)-1, 16, dtype=int)
        pil_images = [Image.fromarray(frames_np[i]) for i in indices]
        
        prompt = (
            "Look at these 16 frames from a 10s clip. Is there any crime, fire, crash, or accident? "
            "First word must be YES or NO. If YES, add a 5-word description."
        )
        
        messages = [{"role": "user", "content": [*[{"type": "image", "image": img} for img in pil_images], {"type": "text", "text": prompt}]}]
        text = self.vlm_processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        img_in, vid_in = process_vision_info(messages)
        inputs = self.vlm_processor(text=[text], images=img_in, videos=vid_in, padding=True, return_tensors="pt").to(self.device)
        
        gen_ids = self.vlm_model.generate(**inputs, max_new_tokens=32)
        output = self.vlm_processor.batch_decode(gen_ids, skip_special_tokens=True)[0]
        return output.split("assistant\n")[-1].strip()

class AlertDispatcher:
    """Clean Output Dispatcher for persistent logging."""
    @staticmethod
    def dispatch(ts, message, output_folder=None):
        print(f"🚨 [\033[91mALERT\033[0m] {ts:5.1f}s | {message}")
        if output_folder:
            log_path = output_folder / "/data/video_analytics/VADTree/result/alerts.log" # Global log
            with open(log_path, "a") as f:
                f.write(f"[{ts:.1f}s] {message}\n")

# ─────────────────────────────────────────────
#  SCANNER ORCHESTRATION
# ─────────────────────────────────────────────

def run_v11(video_path):
    print(f"\n🚀 [SCANNER v11 STARTED] Video: {Path(video_path).stem}")
    vr = VideoReader(video_path, ctx=cpu(0))
    fps = vr.get_avg_fps()
    engine = ScannerV11()
    dispatcher = AlertDispatcher()
    
    out_dir = Path("./result") / f"{Path(video_path).stem}_v11"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    DANGER_WORDS = ["grab", "steal", "hit", "run", "fall", "smoke", "fire", "fight", "accident", "damage", "attack", "altercation", "thief", "explosion", "flame", "ignite", "burning", "crash", "collision", "smash"]
    
    print("-" * 65)

    win_len_f = int(10.0 * fps)
    step_f = int(5.0 * fps)
    
    for start in range(0, len(vr) - win_len_f, step_f):
        window_frames = vr.get_batch(range(start, start + win_len_f)).asnumpy()
        ts_label = f"[{start/fps:5.1f}s - {(start+win_len_f)/fps:5.1f}s]"
        
        # Analyze EVERY window (No skip for max reliability in security)
        report = engine.analyze_situation(window_frames)
        
        # Strict Trigger: Check if response starts with YES
        is_yes = report.strip().upper().startswith("YES")
        
        if is_yes:
             dispatcher.dispatch(start/fps, report, out_dir)
             Image.fromarray(window_frames[len(window_frames)//2]).save(out_dir / f"event_{start/fps:.1f}s.jpg")
        else:
             print(f"{ts_label} -> NORMAL")

    print(f"\n✅ [SCANNER COMPLETE] Total alerts found in {out_dir}/alerts.log")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--video_path", required=True)
    args = parser.parse_args()
    run_v11(args.video_path)
