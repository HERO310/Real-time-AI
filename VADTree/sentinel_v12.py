#!/usr/bin/env python3
"""
VADStream v12 (Sentinel Ultra v14.3)
===============================
- Universal Anomaly Scanner (10s sliding window / 5s step).
- Hardware Optimized: Forced FP16 for max speed on any CUDA device.
- Two-Stage Reasoning: High-accuracy behavioral analysis.
- Clean-Stream: Progressive, unbuffered real-time updates.
- Zero-I/O Path: Skips logs and image saves for all NORMAL results.
- Ultra-Dense Vision: 16 frames per window for high situational awareness.
"""

import sys, os, json, argparse, torch, time, warnings
# Force unbuffered output globally for zero-latency terminal updates
os.environ["PYTHONUNBUFFERED"] = "1"
from pathlib import Path
from PIL import Image

# 1. Environment Alignment
VADTREE_ROOT = Path(__file__).parent.resolve()
sys.path.append(str(VADTREE_ROOT))

import numpy as np
from decord import VideoReader, cpu

# Load VLM
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────
#  SENTINEL ULTRA ENGINE
# ─────────────────────────────────────────────

class SentinelUltra:
    def __init__(self, device="cuda"):
        self.device = device
        print(f"\n🛡️ [Sentinel Ultra] Initializing FP16 Hardware...", flush=True)
        
        # --- Reasoning Engine (Qwen2-VL) ---
        model_path = "Qwen/Qwen2-VL-2B-Instruct"
        # Force FP16 for global compatibility & speed
        self.vlm_model = Qwen2VLForConditionalGeneration.from_pretrained(
            model_path, 
            torch_dtype=torch.float16, 
            device_map="auto"
        )
        self.vlm_processor = AutoProcessor.from_pretrained(model_path)
        
        print(f"✅ [Sentinel Ultra] Speed: 1.0 (FP16). VRAM: {torch.cuda.memory_allocated()/1e9:.2f} GB", flush=True)

    def analyze_anomaly(self, frames_np, callback=None):
        """Two-Stage Behavioral Analysis with Intermediate Feedback."""
        # 16-frame dense sampling for high temporal awareness
        indices = np.linspace(0, len(frames_np)-1, 16, dtype=int)
        pil_images = [Image.fromarray(frames_np[i]) for i in indices]
        
        # --- STAGE 1: Binary Suspicion Filter ---
        prompt_s1 = (
            "Analyze these 16 frames. Compare across frames. Is there ANY possibility of unusual, "
            "aggressive, or suspicious human behavior? (aggressive movement, grabbing, hitting, chasing, "
            "hiding, panic, or unusual interactions). If UNSURE but slightly suspicious, respond YES. "
            "Answer ONLY 'YES' or 'NO'."
        )
        
        messages_s1 = [{"role": "user", "content": [*[{"type": "image", "image": img} for img in pil_images], {"type": "text", "text": prompt_s1}]}]
        text_s1 = self.vlm_processor.apply_chat_template(messages_s1, tokenize=False, add_generation_prompt=True)
        img_in, vid_in = process_vision_info(messages_s1)
        inputs_s1 = self.vlm_processor(text=[text_s1], images=img_in, videos=vid_in, padding=True, return_tensors="pt").to(self.device)
        
        gen_ids_s1 = self.vlm_model.generate(**inputs_s1, max_new_tokens=4)
        output_s1 = self.vlm_processor.batch_decode(gen_ids_s1, skip_special_tokens=True)[0].split("assistant\n")[-1].strip().upper()
        
        if "NO" in output_s1 and "YES" not in output_s1:
            return "NORMAL"
            
        # --- SUSPICION DETECTED! Trigger immediate feedback ---
        if callback: callback()

        # --- STAGE 2: Descriptor ---
        prompt_s2 = "Suspicion detected. Describe the suspicious human behavior or abnormal incident in 5-10 words accurately."
        messages_s2 = [{"role": "user", "content": [*[{"type": "image", "image": img} for img in pil_images], {"type": "text", "text": prompt_s2}]}]
        text_s2 = self.vlm_processor.apply_chat_template(messages_s2, tokenize=False, add_generation_prompt=True)
        # Reuse same vision inputs (img_in, vid_in) but with new text
        inputs_s2 = self.vlm_processor(text=[text_s2], images=img_in, videos=vid_in, padding=True, return_tensors="pt").to(self.device)
        
        gen_ids_s2 = self.vlm_model.generate(**inputs_s2, max_new_tokens=32)
        full_out_s2 = self.vlm_processor.batch_decode(gen_ids_s2, skip_special_tokens=True)[0]
        msg_s2 = full_out_s2.split('assistant\n')[-1].strip()
        return f"ALERT: {msg_s2}"

# ─────────────────────────────────────────────
#  DISPATCHER & LOOP
# ─────────────────────────────────────────────

def run_v12(video_path):
    print(f"\n🚀 [ULTRA SCANNER STARTED] Target: {Path(video_path).name}", flush=True)
    vr = VideoReader(video_path, ctx=cpu(0))
    fps = vr.get_avg_fps()
    engine = SentinelUltra()
    
    out_dir = Path("./result") / f"{Path(video_path).stem}_ultra"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Persistent global alert log
    global_log = Path("./result/alerts_global.log")
    
    print("-" * 75, flush=True)

    win_len_f = int(10.0 * fps)
    step_f = int(5.0 * fps)
    
    for start in range(0, len(vr) - win_len_f, step_f):
        window_frames = vr.get_batch(range(start, start + win_len_f)).asnumpy()
        ts_label = f"| {start/fps:5.1f}s - {(start+win_len_f)/fps:5.1f}s |"
        
        # --- INSTANT FEEDBACK: Show processing start ---
        sys.stdout.write(f"{ts_label} STATUS: \033[94mAnalyzing...\033[0m")
        sys.stdout.flush()

        # Intermediate feedback callback
        def on_suspicion():
            sys.stdout.write(f" -> \033[93mSUSPICION DETECTED!\033[0m")
            sys.stdout.flush()

        # --- Cognitive Analysis ---
        insight = engine.analyze_anomaly(window_frames, callback=on_suspicion)
        
        # Final result on the same line
        if "NORMAL" in insight.upper():
            sys.stdout.write(f" -> \033[92mNORMAL\033[0m\n")
        else:
            # For alerts, move to next line if we already had a suspicion print to avoid clutter
            sys.stdout.write(f"\n{ts_label} STATUS: \033[91mALERT\033[0m | {insight}\n")
            # Only perform I/O for actual alerts
            with open(global_log, "a") as f:
                f.write(f"[{Path(video_path).name}] @ {start/fps:.1f}s: {insight}\n")
            Image.fromarray(window_frames[len(window_frames)//2]).save(out_dir / f"event_{start/fps:.1f}s.jpg")
        
        sys.stdout.flush()

    print(f"\n✅ [SCAN COMPLETED] Alerts (if any) in {out_dir}/")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--video_path", required=True)
    args = parser.parse_args()
    run_v12(args.video_path)
