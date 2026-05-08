# Video Analysis Flow (Window-by-Window)

This document explains how the system analyzes a full video from start to end, using short windows (for example 3 seconds) and producing an anomaly score.

## 1) Windowing the Video

The video is split into short windows:
- Example fast mode: 3 seconds per window.
- Step size can be smaller or larger (overlap or skip).

This means the model never sees the whole video at once. It sees many small windows in sequence.

## 2) Frame Selection per Window

Each window is sampled into a small set of frames:
- uniform sampling across the window
- motion-peak sampling to capture fast changes

This reduces compute while keeping the most informative frames.

## 3) Model Inference per Window

For each window:
1. Selected frames are sent to the VLM.
2. The model answers structured prompts.
3. We convert model outputs into scores:
- window_score (how suspicious the window is)
- severity (how serious the event appears)

## 4) Anomaly Score Formula (per window)

Fast mode window score:
$$
window\_score = 0.55 \cdot vote\_score + 0.25 \cdot severity + 0.20 \cdot keyword\_boost
$$

High-accuracy window score:
$$
window\_score = 0.35 \cdot verdict\_score + 0.25 \cdot guard\_score + 0.20 \cdot conf\_score + 0.20 \cdot severity
$$

Where:
- vote_score is the average of quick YES/NO model votes.
- verdict_score comes from the structured JSON verdict.
- guard_score is from additional safety prompts.
- conf_score is the model confidence normalized to 0-1.
- severity is the risk intensity derived from tags and description.
- keyword_boost is a small bonus when strong danger terms appear.

## 5) Temporal Smoothing

A single window can be noisy. So we smooth scores across recent windows:
$$
smoothed\_score = \frac{1}{N} \sum_{i=t-N+1}^{t} window\_score_i
$$

This prevents rapid alert flicker.

## 6) Alert Thresholds and Gates

The system uses multiple gates:
- trigger_ratio: when to enter alert state.
- release_ratio: when to exit alert state.
- instant_alert_ratio: immediate alert if the current window is very high.
- severity_alert_ratio: alert if severity is very high.

A window can emit an alert if any gate fires and the gap timer allows it.

## 7) Dedup and Cooldown

To reduce repeated spam alerts:
- dedup_window_sec suppresses near-identical alerts.
- cooldown_windows prevents rapid re-entry after release.
- min_alert_gap_sec enforces a minimum time gap.

## 8) Output per Window

For every window, the runtime writes:
- window score and smoothed score
- severity value
- gate reason
- short descriptor text

Output files:
- results/<video>_<mode>_<crime>/window_flags.jsonl
- results/alerts_global.log
- alert_*.jpg snapshot images

## 9) Full Pipeline Summary (Start to End)

1. Load video stream or file.
2. Split into windows.
3. Sample frames from each window.
4. Run model prompts.
5. Compute window score.
6. Smooth scores over time.
7. Apply gates and thresholds.
8. Deduplicate and enforce gaps.
9. Save logs and alert snapshots.

This is repeated for every window until the video ends.
