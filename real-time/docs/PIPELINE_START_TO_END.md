# Start-to-End Pipeline

This document explains the full realtime anomaly detection pipeline in this project from initial setup to final outputs.

## 1) Goal

Build a practical CCTV anomaly pipeline that can:
- ingest video file, RTSP stream, or camera,
- detect suspicious events in sliding windows,
- emit stable realtime alerts,
- store logs for audit,
- optionally use LoRA-adapted model weights.

## 2) Project Entry Points

Main files used in the pipeline:
- run_realtime.py: command-line entrypoint.
- configs.py: mode presets and threshold validation.
- runtime.py: window reader, temporal filter, dedup, final alert emission.
- vlm_engine.py: VLM prompts, scoring, severity extraction.
- alerts.py: severity bucket and terminal color mapping.

Optional training path:
- train_vlm_lora.py
- scripts/prepare_finetune_data.py
- configs_finetune.yaml

## 3) Setup Stage

1. Move to project folder.
2. Activate environment.
3. Ensure runtime dependencies are installed (torch, transformers, decord, opencv, peft for LoRA inference).

Example:
```bash
cd /data/video_analytics/real-time
conda activate VADTree
```

## 4) Runtime Configuration Stage

The run starts in run_realtime.py and reads:
- mode: fast or high_accuracy.
- input source and input type.
- optional threshold overrides.
- model source: base or lora.
- optional crime_target: limit detection to one category.

Mode presets come from configs.py:
- fast: quicker reaction, lower thresholds.
- high_accuracy: more stable and stricter thresholds.

Overrides are validated to avoid invalid states, for example:
- all ratio values in [0, 1],
- trigger_ratio must be greater than release_ratio.

## 5) Input Ingestion Stage

runtime.py resolves source type:
- file: uses FileWindowReader,
- rtsp/camera: uses StreamWindowReader with reconnect logic.

Then it creates sliding windows using:
- window_sec: window duration,
- step_sec: slide step.

Each window yields:
- start time t0,
- end time t1,
- frame tensor (numpy array).

## 6) Frame Selection Stage

vlm_engine.py selects representative frames from each window by combining:
- uniform temporal sampling,
- motion-peak sampling (frame difference based).

This gives a compact but informative frame set for model prompts.

## 7) VLM Inference Stage

For each window:
- the selected frames are converted to PIL images,
- prompt set is sent to Qwen2-VL,
- textual outputs are parsed into structured signals.

Fast mode:
- quick yes/no prompts and target-focused guard prompt,
- computes window_score from votes + severity + keyword boost.

High-accuracy mode:
- structured JSON prompt for verdict/confidence/risk/tags,
- guard prompts for direct threat and suspicious escalation,
- computes window_score from verdict, guard, confidence, severity.

## 8) Scoring and Alert Decision Stage

runtime.py applies a TemporalFilter:
- smooth recent window scores over vote_horizon_windows,
- turn alert state on at trigger_ratio,
- turn alert state off at release_ratio,
- optional cooldown after release.

Additional gates:
- critical gate from severe tags/risk,
- severity gate using severity_alert_ratio,
- instant gate using instant_alert_ratio.

Final emission logic:
- emit alert if any gate is active,
- enforce min_alert_gap_sec,
- suppress near-duplicate events with EventDeduplicator.

## 9) Output Stage

For every window:
- print color-coded line in terminal,
- include window score, smoothed score, severity, gate reason, descriptor.

Saved artifacts:
- results/<video_or_stream>_<mode>[_<crime>]/window_flags.jsonl
- results/alerts_global.log
- optional debug records when --save_debug_jsonl is enabled.

## 10) Evaluation and Reporting Stage

Use scripts for comparison and reporting:
- scripts/benchmark_modes.py: compare modes (speed and behavior).
- scripts/generate_report.py: produce JSON/CSV/Markdown summaries.

This stage is used to verify threshold changes and model behavior before deployment.

## 11) Optional Fine-Tuning Stage (LoRA)

Pipeline:
1. Create annotation CSV with event segments.
2. Convert CSV to training JSONL + frames using prepare_finetune_data.py.
3. Run train_vlm_lora.py to generate adapter output.
4. Run inference with:
   - --model_source lora
   - --lora_adapter_path <adapter_dir>

Current repository also contains a presentation-safe adapter artifact folder:
- finetuned_qwen2vl_lora/

Important:
- Inference does not auto-load LoRA.
- Base model remains default unless lora flags are explicitly passed.

## 12) Typical End-to-End Run Examples

High-accuracy file run:
```bash
python run_realtime.py \
  --mode high_accuracy \
  --input_source /path/to/video.mp4 \
  --input_type file
```

Fast file run:
```bash
python run_realtime.py \
  --mode fast \
  --input_source /path/to/video.mp4 \
  --input_type file
```

LoRA inference run:
```bash
python run_realtime.py \
  --mode high_accuracy \
  --input_source /path/to/video.mp4 \
  --model_source lora \
  --lora_adapter_path /data/video_analytics/real-time/finetuned_qwen2vl_lora
```

Targeted crime run:
```bash
python run_realtime.py \
  --mode high_accuracy \
  --crime_target stealing \
  --input_source /path/to/video.mp4
```

Other supported targets:
- all
- stealing
- assault
- fire
- intrusion
- accident
- vandalism
- robbery

## 13) Why This Pipeline Design

- Sliding windows: capture temporal context, not single-frame noise.
- Temporal hysteresis (trigger/release): prevents alert oscillation.
- Instant and severity gates: preserve fast reaction for critical events.
- Dedup + gap control: reduces alert spam.
- Dual mode profiles: supports low-latency operations and stable auditing.
- Optional LoRA route: allows adaptation without breaking default inference.

## 14) Final Operational Checklist

Before sharing results:
1. Confirm selected mode and threshold overrides.
2. Run on representative videos.
3. Inspect window_flags.jsonl and alerts_global.log.
4. Compare fast vs high_accuracy outputs.
5. If using LoRA, verify adapter path and environment compatibility.
