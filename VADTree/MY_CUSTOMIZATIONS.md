# 🛡️ VADTree — My Customizations & Sentinel Ultra System

> **Author:** Umesh  
> **Base Repo:** [VADTree (NeurIPS 2025)](https://arxiv.org/abs/2510.22693) — Explainable Training-Free Video Anomaly Detection  
> **Custom Work:** Real-Time CCTV Sentinel Alert System built on top of VADTree  

---

## 📌 What This File Is

This document tracks **everything I built and changed** on top of the original VADTree repository — from the first alert script to the final production-grade Sentinel Ultra v14 system. The original VADTree pipeline is a research system that requires multi-step offline processing. I extended it with a **zero-config, real-time alert engine** that works directly on any video file.

---

## 🗂️ What Was Already Here (Original VADTree)

The base repository (`github.com/wenlongli10/VADTree`) contains an offline research pipeline:

| Component | Role |
|---|---|
| `EfficientGEBD/` | Generic Event Boundary Detection model (GEBD) — splits video into scene segments |
| `LLaVA-NeXT/infer_VAD.py` | VLM captioning — describes each scene segment using LLaVA-Video-7B-Qwen2 |
| `DeepSeek-R1/deepseek_batch_infer.py` | LLM reasoning — scores anomaly level per segment using DeepSeek-R1-Distill-Qwen-14B |
| `ImageBind/imagebind_sim.py` | Feature similarity — computes audio-visual embeddings per segment |
| `HGTree_generation.py` | Builds the Hierarchical Granularity-Aware Tree from GEBD boundaries |
| `refinement_eval.py` | Intra-cluster refinement and AUC evaluation |
| `correlation_eval.py` | Inter-cluster correlation for final VADTree score |

This pipeline achieves state-of-the-art on UCF-Crime, XD-Violence, and MSAD benchmarks — but it requires multiple conda environments, pre-downloaded model weights, and processes entire datasets offline.

---

## 🚀 What I Built — The Sentinel Ultra System

I built a **completely different, real-time alert engine** that runs on a single video file with one command, no pre-processing required.

### Design Philosophy

> *"Give me one video. Tell me what happened. Right now."*

- **Zero config** — just `--video_path`
- **No prior data or training** — pure VLM inference
- **Real-time streaming output** — see results as each 10s window finishes
- **FP16 hardware acceleration** — lean on VRAM (~4.4 GB)
- **Two-stage behavioral reasoning** — high accuracy, low false positives

---

## 📜 Development History (From Start to End)

### Phase 1 — First Alert Scripts (`sentinel_alerts_v1.py`, `sentinel_alerts_v2.py`)

**Goal:** Quick alert system using existing VADTree models.

- Used `ImageBind` for multimodal (visual + audio) embeddings
- Used keyword-based detection (`fight`, `fire`, `gun`, etc.)
- Fixed category list — missed anything not in the list
- Results were category-restricted and not flexible
- **Problem:** Could not catch new/unseen event types

---

### Phase 2 — Sliding Window Architecture (`sentinel_v11.py`)

**Goal:** Process video in sliding windows for temporal awareness.

**Key Design:**
- **10-second sliding window** with 5-second step (50% overlap)
- Each window → sampled frames → VLM analysis
- Used `decord` for fast video reading
- ImageBind embeddings computed per window for "semantic drift" detection
- Motion-skipper: skipped windows with no movement (based on embedding similarity)

**Problems:**
- Still used keyword matching (`DANGER_WORDS` list)
- VLM behaved like a captioner, not a detector
- Motion-skipper too aggressive — missed slow-onset crimes

---

### Phase 3 — Sentinel Ultra v12 (`sentinel_v12.py` initial)

**Goal:** Universal anomaly scanner — no fixed categories.

**Key Changes:**
- **Removed ImageBind** from the critical path entirely (saves ~2.5 GB VRAM)
- **Inverse-logic prompt:** "Is everything NORMAL?" → if VLM hesitates, flag it
- Strict output format: `ANSWER: NORMAL` or `ANSWER: ALERT - <description>`
- **Zero-I/O fast path:** NORMAL results skip all disk writes
- **Dense 16-frame sampling** per window for high temporal coverage
- **FP16 forced** for both models (`torch_dtype=torch.float16`)
- Real-time console feedback with `flush=True`

**VRAM Usage:** ~4.4 GB (down from ~9 GB with ImageBind)

---

### Phase 4 — Two-Stage Reasoning Engine (v14)

**Goal:** Fix VLM hallucination — it was treating every window as ALERT.

**Root Cause:** Single-prompt approach made the VLM behave as a narrator, not a security guard.

**Solution — Two-Stage Pipeline:**

```
Window Frames (16 frames)
        │
        ▼
┌──────────────────────────────────────────────────────┐
│  STAGE 1: Binary Suspicion Filter  (max_new_tokens=4) │
│                                                       │
│  Prompt: "Is there ANY possibility of suspicious,     │
│  aggressive behavior? (grabbing, hitting, hiding,     │
│  panic, chasing). If UNSURE → YES. Answer YES/NO."   │
│                                                       │
│  Output: YES / NO                                     │
└──────────────────────────────────────────────────────┘
        │
   NO ──┼──► NORMAL  (done, zero I/O)
        │
   YES  │
        ▼
┌──────────────────────────────────────────────────────┐
│  STAGE 2: Situational Descriptor  (max_new_tokens=32)│
│                                                       │
│  Prompt: "Suspicion detected. Describe the behavior  │
│  in 5-10 words accurately."                          │
│                                                       │
│  Output: "man being attacked by group in stairwell"  │
└──────────────────────────────────────────────────────┘
        │
        ▼
   ALERT logged + keyframe saved
```

**Why This Works:**
- Stage 1 is a fast, constrained binary classifier (4 tokens max)
- Stage 2 only runs when Stage 1 confirms suspicion → lower cost
- Behavioral focus (not keyword-based): aggression, panic, unusual movement
- Soft detection: "If unsure → YES" ensures no missed events
- Temporal awareness: "Compare across frames to detect changes in behavior"

---

### Phase 5 — Real-Time Streaming Feedback (v14.1 → v14.3)

**Goal:** See results immediately — not after the full video finishes.

**Problem:** `tail -n 100` was buffering output. Results appeared only at the end.

**Fixes applied (in order):**

| Version | Fix |
|---|---|
| v14.1 | Added `callback=on_suspicion()` — prints `SUSPICION DETECTED!` the moment Stage 1 fires |
| v14.2 | Added `PROCESSING...` indicator printed before Stage 1 runs; `os.environ["PYTHONUNBUFFERED"] = "1"` |
| v14.3 | Fixed `NORMALSING...` glitch (caused by `\r` carriage return overwriting `NORMAL` + `PROCESSING`). Switched to progressive inline format: `Analyzing... -> NORMAL` |

**Final output format:**
```
|   0.0s -  10.0s | STATUS: Analyzing... -> NORMAL
|   5.0s -  15.0s | STATUS: Analyzing... -> SUSPICION DETECTED!
|   5.0s -  15.0s | STATUS: ALERT | ALERT: man pushing another man down stairs
|  10.0s -  20.0s | STATUS: Analyzing... -> NORMAL
```

---

## 📁 Files I Added / Modified

| File | Status | Description |
|---|---|---|
| `sentinel_v12.py` | ✅ **MY MAIN SCRIPT** | Final Sentinel Ultra v14.3 — the complete real-time CCTV alert system |
| `sentinel_v11.py` | ✅ Created | Earlier version with ImageBind + motion-skipper + keyword matching |
| `sentinel_alerts_v1.py` | ✅ Created | First alert prototype — category-based with ImageBind |
| `sentinel_alerts_v2.py` | ✅ Created | Extended alert script — more categories, batch processing |
| `realtime_guardian.py` | ✅ Created | Experimental real-time guardian with threading |
| `sentinel_vjepa_v1.py` | ✅ Created | Experimental V-JEPA based anomaly scoring |
| `sentinel_vjepa_plan.md` | ✅ Created | Planning doc for V-JEPA integration |
| `sentinel_vjepa_setup.md` | ✅ Created | Setup guide for V-JEPA models |
| `result/alerts_global.log` | ✅ Auto-generated | Persistent log of all alerts across all videos |
| `result/<video>_ultra/` | ✅ Auto-generated | Per-video folder with keyframe snapshots of alerts |

---

## ⚙️ How to Run My System

### Prerequisites
```bash
conda activate VADTree
```

### Run on any video
```bash
python -u sentinel_v12.py --video_path /path/to/your/video.mp4
```

> The `-u` flag forces Python unbuffered mode — essential for real-time terminal updates.

### Example
```bash
python -u sentinel_v12.py \
    --video_path /data/video_analytics/datasets/UCF_Crime_Videos/UCF_Crime_Test/Assault003_x264.mp4
```

### Output
- **Terminal:** Live window-by-window status as each 10s clip is analyzed
- **`result/alerts_global.log`:** Persistent log of all alerts
- **`result/<video_name>_ultra/`:** Keyframe `.jpg` snapshots for each alert event

---

## 🔬 Verified Results

### Assault003_x264.mp4
```
|   0.0s -  10.0s | STATUS: Analyzing... -> NORMAL
|   5.0s -  15.0s | STATUS: Analyzing... -> SUSPICION DETECTED!
|   5.0s -  15.0s | STATUS: ALERT | ALERT: man walking towards woman in bathroom
|  10.0s -  20.0s | STATUS: Analyzing... -> SUSPICION DETECTED!
|  10.0s -  20.0s | STATUS: ALERT | ALERT: man pushing another man down flight of stairs
|  30.0s -  40.0s | STATUS: Analyzing... -> SUSPICION DETECTED!
|  30.0s -  40.0s | STATUS: ALERT | ALERT: group engaging in suspicious behavior
| 110.0s - 120.0s | STATUS: Analyzing... -> SUSPICION DETECTED!
| 110.0s - 120.0s | STATUS: ALERT | ALERT: individual being pushed and kicked by others
| 125.0s - 135.0s | STATUS: Analyzing... -> SUSPICION DETECTED!
| 125.0s - 135.0s | STATUS: ALERT | ALERT: man being attacked by another man in stairwell
```

### Shoplifting036_x264.mp4
```
|  30.0s -  40.0s | STATUS: ALERT | ALERT: suspect seen holding knife, threatening someone
|  40.0s -  50.0s | STATUS: ALERT | ALERT: man in green shirt holding knife threatening another
|  45.0s -  55.0s | STATUS: ALERT | ALERT: suspect walking towards camera holding knife
```

---

## 📊 Technical Specs

| Property | Value |
|---|---|
| Model | Qwen2-VL-2B-Instruct |
| Precision | FP16 |
| VRAM Required | ~4.4 GB |
| Window Size | 10 seconds |
| Window Step | 5 seconds (50% overlap) |
| Frames per Window | 16 (dense sampling) |
| Stage 1 Max Tokens | 4 (YES/NO only) |
| Stage 2 Max Tokens | 32 (short description) |
| Video Input | Any `.mp4` / `.avi` / `.mkv` via `decord` |
| Output Latency | Instant (per window, unbuffered) |

---

## 🔮 Planned Next Steps

- [ ] **RTSP Live Stream Support** — plug into actual CCTV cameras via `cv2.VideoCapture("rtsp://...")`
- [ ] **Web Dashboard** — real-time UI showing keyframes and alert timeline
- [ ] **TensorRT / vLLM** — further reduce VLM inference time for high-traffic deployments
- [ ] **Local Model Caching** — pre-download Qwen2-VL weights to `/data/video_analytics/models/` for offline use
- [ ] **Multi-Camera Support** — parallel processing of multiple RTSP feeds

---

## 🙏 Credits

- **Original VADTree Paper & Code:** [Wenlong Li et al., NeurIPS 2025](https://arxiv.org/abs/2510.22693)
- **VLM:** [Qwen2-VL-2B-Instruct](https://huggingface.co/Qwen/Qwen2-VL-2B-Instruct) by Alibaba
- **Video Decoding:** [decord](https://github.com/dmlc/decord)
- **Dataset:** [UCF-Crime](https://www.crcv.ucf.edu/projects/real-world/)
- **Custom Engineering:** Umesh — Real-Time Sentinel Ultra System (v14.3)
