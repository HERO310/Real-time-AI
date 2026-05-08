# V-JEPA World Model Trial Plan

Status: Planning only (no code execution in this phase).
Current baseline to compare against: sentinel_alerts_v1.py.
Constraint: Do not modify sentinel_alerts_v1.py.

## Goal
Evaluate whether a V-JEPA based pipeline can improve CCTV anomaly alert quality while keeping real-time windowed output.

## Target Output Behavior
1. Sliding windows with default 10s window and 5s step.
2. Print one result per window in terminal in real time.
3. Emit alerts only when risk is detected.
4. Keep a global alert log and optional keyframe snapshots.

## Planned New Implementation File
- sentinel_vjepa_v1.py (to be created in implementation phase)

## Phase Plan

### Phase 1: Environment and Model Loading
1. Select a V-JEPA checkpoint compatible with current environment.
2. Add model load path and device handling (CPU/CUDA fallback).
3. Add startup diagnostics (model loaded, device, dtype, fps).

### Phase 2: Windowed Feature Pipeline
1. Keep same windowing API as current baseline (window_sec, step_sec, sample_frames).
2. For each window, sample frames and extract V-JEPA features.
3. Build a compact per-window representation (mean pooled embedding or temporal pooled embedding).

### Phase 3: Anomaly Scoring
1. Build a normal-reference bank using either:
2. Initial warmup windows from current video, or
3. Optional external normal clips.
4. Compute anomaly score with cosine distance / Mahalanobis-style distance to normal bank.
5. Add temporal jump score between adjacent windows.
6. Final window score = alpha * reference_distance + beta * temporal_jump.

### Phase 4: Alert State Logic
1. Reuse current style temporal filtering:
2. Smoothed score over horizon windows.
3. Hysteresis thresholds (trigger_ratio, release_ratio).
4. Cooldown and min_alert_gap_sec.
5. Add instant fast alert for very high raw window score.

### Phase 5: Runtime Output
1. Print per-window status line: FLAG or ALERT.
2. Include fields: raw score, smoothed score, risk level, reason code.
3. Save emitted alerts to result/alerts_global.log.
4. Save optional alert frame image to result/<video>_vjepa_alerts.

### Phase 6: Benchmark Against Current Baseline
1. Run same videos with sentinel_alerts_v1.py and sentinel_vjepa_v1.py.
2. Compare:
3. First-alert latency.
4. Alerts per minute.
5. False-alert rate on known-normal segments.
6. Coverage on known anomaly segments.
7. Throughput (windows/sec).

### Phase 7: Tuning Loop
1. Tune alpha/beta for score fusion.
2. Tune trigger/release/instant thresholds per scenario profile:
3. indoor_night
4. outdoor_day
5. crowded_scene

## CLI Shape (Planned)
python sentinel_vjepa_v1.py \
  --video_path /path/to/video.mp4 \
  --window_sec 10 \
  --step_sec 5 \
  --sample_frames 16 \
  --trigger_ratio 0.62 \
  --release_ratio 0.38 \
  --instant_alert_ratio 0.80 \
  --min_alert_gap_sec 5

## Acceptance Criteria
1. New file runs independently without changing sentinel_alerts_v1.py.
2. Per-window terminal output appears continuously.
3. Alerts are emitted with clear thresholds and reduced false positives.
4. Benchmark report can show whether V-JEPA is better, equal, or worse than baseline.
