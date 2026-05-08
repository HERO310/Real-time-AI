#!/usr/bin/env python3
import sys, os, json, argparse, torch, time, warnings, collections, traceback
from pathlib import Path
from PIL import Image

# 1. Setup Paths
VADTREE_ROOT = Path(__file__).parent.resolve().parent
sys.path.append(str(VADTREE_ROOT))
sys.path.append(str(VADTREE_ROOT / "ImageBind"))

print("[v9] Initializing Imports...")
try:
    import numpy as np
    from decord import VideoReader, cpu
    from imagebind.models import imagebind_model
    from imagebind.models.imagebind_model import ModalityType
    from torchvision import transforms
    from torchvision.transforms._transforms_video import NormalizeVideo
    from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
    from qwen_vl_utils import process_vision_info
    warnings.filterwarnings("ignore")
    print("[v9] Imports Successful.")
except Exception as e:
    print(f"[v9] CRITICAL IMPORT ERROR: {e}")
    traceback.print_exc()
    sys.exit(1)

class GuardianV9:
    def __init__(self, device="cuda"):
        self.device = device
        print(f"[v9] Loading Models on {device}...")
        try:
            self.ib_model = imagebind_model.imagebind_huge(pretrained=True).eval().to(device).half()
            self.ib_modality = ModalityType
            self.ib_transform = transforms.Compose([
                transforms.Resize((224, 224)),
                NormalizeVideo(mean=(0.48145466, 0.4578275, 0.40821073), std=(0.26862954, 0.26130258, 0.27577711)),
            ])
            model_path = "Qwen/Qwen2-VL-2B-Instruct"
            self.vlm_model = Qwen2VLForConditionalGeneration.from_pretrained(model_path, torch_dtype=torch.bfloat16, device_map="auto")
            self.vlm_processor = AutoProcessor.from_pretrained(model_path)
            self.buffer = collections.deque(maxlen=20)
            print("[v9] Models Loaded Successfully.")
        except Exception as e:
            print(f"[v9] MODEL LOAD ERROR: {e}")
            traceback.print_exc()
            sys.exit(1)

    @torch.no_grad()
    def get_jump_score(self, frames_np):
        idx = [0, -1]
        clip = torch.from_numpy(frames_np[idx]).permute(3, 0, 1, 2).float() / 255.0
        clip = self.ib_transform(clip)
        inp = clip.unsqueeze(0).unsqueeze(1).to(self.device).half()
        curr_emb = torch.nn.functional.normalize(self.ib_model({self.ib_modality.VISION: inp})[self.ib_modality.VISION], dim=-1)
        score = 0.0
        if self.buffer:
            baseline = torch.cat(list(self.buffer)).mean(0, keepdim=True)
            baseline = torch.nn.functional.normalize(baseline, dim=-1)
            score = 1.0 - (curr_emb @ baseline.T).squeeze().item()
        self.buffer.append(curr_emb)
        return score

    def verify_alert(self, frames_np):
        indices = np.linspace(0, len(frames_np)-1, 4, dtype=int)
        pil_images = [Image.fromarray(frames_np[i]) for i in indices]
        messages = [{"role": "user", "content": [*[{"type": "image", "image": img} for img in pil_images], {"type": "text", "text": "Is there any crime, accident, or fight? Answer YES or NO."}]}]
        text = self.vlm_processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        img_in, vid_in = process_vision_info(messages)
        inputs = self.vlm_processor(text=[text], images=img_in, videos=vid_in, padding=True, return_tensors="pt").to(self.device)
        gen_ids = self.vlm_model.generate(**inputs, max_new_tokens=4)
        output = self.vlm_processor.batch_decode(gen_ids, skip_special_tokens=True)[0]
        return "YES" in output.split("assistant\n")[-1].strip().upper()

def run_v9(video_path, sensitivity=0.07):
    print(f"[v9] Opening Video: {video_path}")
    vr = VideoReader(video_path, ctx=cpu(0))
    fps = vr.get_avg_fps()
    engine = GuardianV9()
    
    script_dir = Path(__file__).parent.resolve()
    res_dir = script_dir / "results" / f"{Path(video_path).stem}_v9"
    res_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n📢 [REAL-TIME MONITORING STARTED]")
    print("-" * 50)
    for start in range(0, len(vr) - int(10 * fps), int(0.5 * fps)):
        monitor_frames = vr.get_batch(range(start, start + int(1.0 * fps))).asnumpy()
        jump = engine.get_jump_score(monitor_frames)
        if jump > sensitivity:
            vlm_frames = vr.get_batch(range(start, start + int(10 * fps))).asnumpy()
            if engine.verify_alert(vlm_frames):
                print(f"🚨 [ALERT] HAPPENING AT {start/fps:5.1f}s")
                Image.fromarray(vlm_frames[len(vlm_frames)//2]).save(res_dir / f"event_{start/fps:.1f}s.jpg")
    print(f"\n✅ [MONITORING COMPLETE]")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--video_path", required=True)
    parser.add_argument("--sensitivity", type=float, default=0.07)
    args = parser.parse_args()
    run_v9(args.video_path, args.sensitivity)
