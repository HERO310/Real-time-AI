import json
import re
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

from configs import resolve_crime_target

# qwen_vl_utils may live in VADTree root when this folder is outside VADTree.
THIS_DIR = Path(__file__).resolve().parent
candidate_roots = [
    THIS_DIR.parent / "VADTree",    # /data/video_analytics/VADTree
    THIS_DIR.parent,                  # legacy case when file was under VADTree
]
for root in candidate_roots:
    if (root / "qwen_vl_utils.py").exists() and str(root) not in sys.path:
        sys.path.append(str(root))

from qwen_vl_utils import process_vision_info


class SentinelVLMEngine:
    def __init__(
        self,
        device: str = "cuda",
        model_path: str = "Qwen/Qwen2-VL-2B-Instruct",
        model_source: str = "base",
        lora_adapter_path: str = None,
        crime_target: str = "all",
    ):
        self.device = device
        self.model_path = model_path
        self.model_source = model_source
        self.lora_adapter_path = lora_adapter_path
        self.crime_profile = resolve_crime_target(crime_target)
        dtype = torch.float16 if device == "cuda" else torch.float32

        base_model = Qwen2VLForConditionalGeneration.from_pretrained(
            model_path,
            torch_dtype=dtype,
            device_map="auto" if device == "cuda" else None,
        )

        if model_source == "lora":
            if not lora_adapter_path:
                raise ValueError("model_source=lora requires --lora_adapter_path")
            try:
                from peft import PeftModel
            except Exception as exc:
                raise RuntimeError("PEFT is required for LoRA inference: pip install peft") from exc
            if not Path(lora_adapter_path).exists():
                raise FileNotFoundError(f"LoRA adapter path not found: {lora_adapter_path}")
            self.model = PeftModel.from_pretrained(base_model, lora_adapter_path)
        else:
            self.model = base_model

        if device != "cuda":
            self.model.to(device)
        self.model.eval()
        self.processor = AutoProcessor.from_pretrained(model_path)

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"\s+", " ", text.strip())

    @staticmethod
    def _clip01(x: float) -> float:
        return max(0.0, min(1.0, float(x)))

    @staticmethod
    def _extract_json(text: str):
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None

    @staticmethod
    def _yes_vote(text: str) -> int:
        up = text.upper().strip()
        if up.startswith("YES"):
            return 1
        if up.startswith("NO"):
            return 0
        if "YES" in up and "NO" not in up:
            return 1
        if "NO" in up and "YES" not in up:
            return 0
        return 0

    @staticmethod
    def _risk_level_score(level: str) -> float:
        mp = {"NONE": 0.00, "LOW": 0.35, "MEDIUM": 0.60, "HIGH": 0.85, "CRITICAL": 1.00}
        return mp.get(level.upper().strip(), 0.35)

    # @staticmethod
    # def _keyword_severity(desc: str) -> float:
    #     tags = {
    #         "fight": 0.95,
    #         "attack": 0.95,
    #         "assault": 0.95,
    #         "weapon": 1.00,
    #         "gun": 1.00,
    #         "knife": 1.00,
    #         "fire": 1.00,
    #         "smoke": 0.85,
    #         "explosion": 1.00,
    #         "crash": 0.95,
    #         "collision": 0.95,
    #         "accident": 0.85,
    #         "theft": 0.80,
    #         "steal": 0.80,
    #         "intruder": 0.85,
    #         "break-in": 0.85,
    #         "panic": 0.75,
    #         "chase": 0.75,
    #         "fall": 0.70,
    #         "injury": 0.85,
    #         "vandalism": 0.75,
    #     }
    @staticmethod
    def _keyword_severity(desc: str) -> float:
        tags = {
            "fight": 0.95,
            "attack": 0.95,
            "assault": 0.95,
            "weapon": 1.00,
            "gun": 1.00,
            "knife": 1.00,
            "fire": 1.00,
            "smoke": 0.85,
            "explosion": 1.00,
            "crash": 0.95,
            "collision": 0.95,
            "accident": 0.85,
            "theft": 0.80,
            "steal": 0.80,
            "intruder": 0.85,
            "break-in": 0.85,
            "panic": 0.75,
            "chase": 0.75,
            "fall": 0.70,
            "injury": 0.85,
            "vandalism": 0.75,

            # New additions
            "robbery": 0.90,
            "looting": 0.90,
            "arson": 1.00,
            "riot": 0.95,
            "crowd": 0.60,
            "suspicious": 0.65,
            "trespassing": 0.75,
            "unauthorized": 0.70,
            "bleeding": 0.90,
            "unconscious": 0.95,
            "collapse": 0.85,
            "scream": 0.80,
            "running": 0.60,
            "speeding": 0.70,
        }
        low = desc.lower()
        mx = 0.0
        for k, v in tags.items():
            if k in low:
                mx = max(mx, v)
        return 0.45 if mx == 0.0 else mx

    @staticmethod
    def _contains_danger_terms(text: str) -> bool:
        low = text.lower()
        terms = [
            "fire",
            "smoke",
            "flame",
            "burn",
            "explosion",
            "attack",
            "fight",
            "weapon",
            "theft",
            "intrusion",
            "crash",
            "collision",
            "fall",
            "injury",
        ]
        return any(t in low for t in terms)

    def _target_terms(self) -> tuple:
        return self.crime_profile.keywords

    def _target_match(self, text: str, tags) -> bool:
        if self.crime_profile.key == "all":
            return True
        haystack = f"{text or ''} {' '.join(str(t) for t in (tags or []))}".lower()
        for term in self._target_terms():
            if term in haystack:
                return True
        return False

    def _target_prompt_clause(self) -> str:
        if self.crime_profile.key == "all":
            return "any suspicious or harmful event"
        return f"ONLY this target crime: {self.crime_profile.prompt_focus}. Ignore unrelated events."

    @staticmethod
    def _sample_uniform(num_frames: int, n: int) -> np.ndarray:
        n = max(1, min(n, num_frames))
        return np.linspace(0, num_frames - 1, n, dtype=int)

    @staticmethod
    def _sample_motion_peaks(frames_np: np.ndarray, n: int) -> np.ndarray:
        if len(frames_np) <= 1 or n <= 0:
            return np.array([], dtype=int)
        gray = 0.299 * frames_np[..., 0] + 0.587 * frames_np[..., 1] + 0.114 * frames_np[..., 2]
        diffs = np.mean(np.abs(gray[1:] - gray[:-1]), axis=(1, 2))
        if len(diffs) == 0:
            return np.array([], dtype=int)
        top = np.argsort(diffs)[-min(n, len(diffs)):]
        return np.unique(top + 1)

    def _select_indices(self, frames_np: np.ndarray, sample_frames: int) -> np.ndarray:
        num_frames = len(frames_np)
        sample_frames = max(1, min(sample_frames, num_frames))
        n_uniform = max(1, sample_frames // 2)
        n_motion = sample_frames - n_uniform
        u = self._sample_uniform(num_frames, n_uniform)
        m = self._sample_motion_peaks(frames_np, n_motion)
        idx = np.unique(np.concatenate([u, m]))
        if len(idx) < sample_frames:
            fill = self._sample_uniform(num_frames, sample_frames)
            idx = np.unique(np.concatenate([idx, fill]))
        if len(idx) > sample_frames:
            pick = np.linspace(0, len(idx) - 1, sample_frames, dtype=int)
            idx = idx[pick]
        return idx

    def _run_prompt(self, pil_images, prompt: str, max_new_tokens: int) -> str:
        messages = [{
            "role": "user",
            "content": [
                *[{"type": "image", "image": img, "resized_height": 270, "resized_width": 480} for img in pil_images],
                {"type": "text", "text": prompt},
            ],
        }]
        text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        img_in, vid_in = process_vision_info(messages)
        inputs = self.processor(text=[text], images=img_in, videos=vid_in, padding=True, return_tensors="pt").to(self.device)
        with torch.no_grad():
            gen_ids = self.model.generate(**inputs, max_new_tokens=max_new_tokens)
        raw = self.processor.batch_decode(gen_ids, skip_special_tokens=True)[0]
        return self._normalize_text(raw.split("assistant\n")[-1])

    def _parse_screen_json(self, txt: str) -> dict:
        obj = self._extract_json(txt)
        if not isinstance(obj, dict):
            y = self._yes_vote(txt)
            return {
                "verdict": "YES" if y else "NO",
                "confidence": 70.0 if y else 30.0,
                "risk_level": "MEDIUM" if y else "NONE",
                "event_tags": [],
                "short_reason": txt[:140] if txt else "none",
            }
        verdict = str(obj.get("verdict", "UNSURE")).upper()
        if verdict not in {"YES", "NO", "UNSURE"}:
            verdict = "UNSURE"
        conf = float(obj.get("confidence", 50.0))
        conf = max(0.0, min(100.0, conf))
        risk = str(obj.get("risk_level", "LOW")).upper()
        if risk not in {"NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            risk = "LOW"
        tags = obj.get("event_tags", [])
        if not isinstance(tags, list):
            tags = []
        tags = [str(x).strip().lower() for x in tags if str(x).strip()]
        reason = str(obj.get("short_reason", "uncertain")).strip() or "uncertain"
        return {
            "verdict": verdict,
            "confidence": conf,
            "risk_level": risk,
            "event_tags": tags,
            "short_reason": reason,
        }

    def _apply_false_positive_suppression(self, descriptor: str, severity: float, critical_vote: int, event_tags):
        """Lower score for common benign descriptions when no critical signals are present."""
        if critical_vote == 1:
            return severity, False

        benign_patterns = [
            "walking",
            "standing",
            "talking",
            "sitting",
            "crowd moving",
            "normal traffic",
            "people passing",
            "store activity",
            "no unusual",
            "normal",
        ]
        text = descriptor.lower()
        hit = any(p in text for p in benign_patterns)
        tag_hit = any(str(t).lower() in {"other", "normal"} for t in (event_tags or []))

        if (hit or tag_hit) and severity < 0.85:
            return max(0.0, severity - 0.20), True
        return severity, False

    def analyze_window(self, frames_np: np.ndarray, sample_frames: int, mode: str, crime_target: str = "all") -> dict:
        if crime_target != self.crime_profile.key:
            self.crime_profile = resolve_crime_target(crime_target)
        idx = self._select_indices(frames_np, sample_frames)
        pil_images = [Image.fromarray(frames_np[i]) for i in idx]

        if mode == "fast":
            p_main = (
                f"Real-time CCTV safety check. {self._target_prompt_clause()} Across all frames, is there any sign of it? Reply ONLY YES or NO."
            )
            p_guard = f"Any brief but important moment of {self.crime_profile.prompt_focus} in this clip? Reply ONLY YES or NO."
            p_fire = f"Do you see any visible sign of {self.crime_profile.prompt_focus} in any frame? Reply ONLY YES or NO."
            o1 = self._run_prompt(pil_images, p_main, max_new_tokens=6)
            o2 = self._run_prompt(pil_images, p_guard, max_new_tokens=6)
            o3 = self._run_prompt(pil_images, p_fire, max_new_tokens=6)

            y1, y2, y3 = self._yes_vote(o1), self._yes_vote(o2), self._yes_vote(o3)
            vote_score = (y1 + y2 + y3) / 3.0
            keyword_boost = 1.0 if (
                self._contains_danger_terms(o1) or
                self._contains_danger_terms(o2) or
                self._contains_danger_terms(o3)
            ) else 0.0

            if y1 == 0 and y2 == 0 and y3 == 0 and keyword_boost == 0.0:
                return {
                    "window_score": 0.0,
                    "severity": 0.0,
                    "critical_vote": 0,
                    "descriptor": "normal",
                    "event_tags": [],
                    "suppressed_fp": False,
                }

            p_desc = (
                "Describe suspicious event in <=8 words. "
                "If fire/smoke is visible, explicitly mention fire or smoke."
            )
            desc = self._run_prompt(pil_images, p_desc, max_new_tokens=24)
            sev = self._keyword_severity(desc)

            if self.crime_profile.key != "all" and not self._target_match(desc, []) and not self._target_match(o1 + " " + o2 + " " + o3, []):
                return {
                    "window_score": 0.0,
                    "severity": 0.0,
                    "critical_vote": 0,
                    "descriptor": "normal",
                    "event_tags": [self.crime_profile.key],
                    "suppressed_fp": True,
                }

            if self._contains_danger_terms(desc) or self._contains_danger_terms(o3):
                sev = max(sev, 0.90)

            critical_vote = 1 if (sev >= 0.85 or y3 == 1) else 0
            sev, suppressed = self._apply_false_positive_suppression(desc, sev, critical_vote, [])
            window_score = self._clip01(0.55 * vote_score + 0.25 * sev + 0.20 * keyword_boost)
            return {
                "window_score": window_score,
                "severity": sev,
                "critical_vote": critical_vote,
                "descriptor": desc,
                "event_tags": [],
                "suppressed_fp": suppressed,
            }

        p_screen = (
            f"You are CCTV anomaly analyst. {self._target_prompt_clause()} Detect if it appears at any moment. "
            "Output ONLY valid JSON: "
            "{\"verdict\":\"YES|NO|UNSURE\",\"confidence\":0-100,\"risk_level\":\"NONE|LOW|MEDIUM|HIGH|CRITICAL\","
            "\"event_tags\":[\"violence|theft|intrusion|fire|crash|fall|medical|vandalism|other\"],\"short_reason\":\"...\"}."
        )
        p_guard_1 = (
            f"Does any frame show direct harm/threat for {self.crime_profile.prompt_focus}? Reply ONLY YES or NO."
        )
        p_guard_2 = (
            f"Do actions indicate suspicious intent escalation for {self.crime_profile.prompt_focus}? Reply ONLY YES or NO."
        )

        o_screen = self._run_prompt(pil_images, p_screen, max_new_tokens=120)
        o_g1 = self._run_prompt(pil_images, p_guard_1, max_new_tokens=6)
        o_g2 = self._run_prompt(pil_images, p_guard_2, max_new_tokens=6)

        screen = self._parse_screen_json(o_screen)
        verdict_score = {"YES": 1.0, "UNSURE": 0.5, "NO": 0.0}.get(screen["verdict"], 0.5)
        guard_score = (self._yes_vote(o_g1) + self._yes_vote(o_g2)) / 2.0
        conf_score = screen["confidence"] / 100.0
        risk_score = self._risk_level_score(screen["risk_level"])

        suspicious = (screen["verdict"] != "NO") or guard_score > 0.0
        desc = "normal"
        sev_desc = 0.0
        if suspicious:
            p_desc = (
                f"Output ONLY JSON for {self.crime_profile.prompt_focus}: {{\"event_type\":\"violence|theft|intrusion|fire|crash|fall|medical|vandalism|other\","
                "\"severity_score\":0.0-1.0,\"description\":\"short factual description\"}."
            )
            o_desc = self._run_prompt(pil_images, p_desc, max_new_tokens=80)
            obj = self._extract_json(o_desc)
            if isinstance(obj, dict):
                desc = str(obj.get("description", "possible anomaly")).strip() or "possible anomaly"
                try:
                    sev_desc = self._clip01(float(obj.get("severity_score", 0.45)))
                except Exception:
                    sev_desc = 0.45
            else:
                desc = o_desc[:160] if o_desc else "possible anomaly"
                sev_desc = 0.45

        keyword_sev = self._keyword_severity(desc)
        severity = max(risk_score, sev_desc, keyword_sev if suspicious else 0.0)

        critical_tags = {
            "violence", "assault", "weapon", "fire", "explosion", "crash", "collision",
            "severe_fall", "medical_distress", "intrusion", "theft"
        }
        target_match = self._target_match(desc, screen["event_tags"]) or self._target_match(screen["short_reason"], screen["event_tags"])
        if self.crime_profile.key != "all" and not target_match:
            suspicious = False
            verdict_score = 0.0
            guard_score = 0.0
            conf_score = 0.0
            risk_score = 0.0
            severity = 0.0
            desc = "normal"

        critical_vote = int(
            suspicious and (
                any(t in critical_tags for t in screen["event_tags"]) or
                screen["risk_level"] in {"HIGH", "CRITICAL"} or
                severity >= 0.85
            )
        )

        severity, suppressed = self._apply_false_positive_suppression(desc, severity, critical_vote, screen["event_tags"])
        window_score = self._clip01(0.35 * verdict_score + 0.25 * guard_score + 0.20 * conf_score + 0.20 * severity)

        return {
            "window_score": window_score,
            "severity": severity,
            "critical_vote": critical_vote,
            "descriptor": desc if suspicious else "normal",
            "event_tags": screen["event_tags"],
            "suppressed_fp": suppressed,
        }
