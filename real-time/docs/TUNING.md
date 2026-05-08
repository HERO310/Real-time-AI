# Tuning Guide

## Fast mode (lower latency)
- Lower `instant_alert_ratio` for earlier alerts.
- Lower `severity_alert_ratio` to catch subtle events.
- Keep `cooldown_windows=0` for continuous firing.
- If using `crime_target`, consider lowering `trigger_ratio` slightly for better recall.

## High-accuracy mode (stability)
- Increase `vote_horizon_windows` for stronger smoothing.
- Increase `trigger_ratio` to suppress noisy alerts.
- Keep non-zero `min_alert_gap_sec` to avoid duplicates.
- Use a larger `step_sec` only if you can tolerate missed short events.

## Common Fixes
- Too many alerts: increase `instant_alert_ratio` and `trigger_ratio`.
- Missed events: lower `severity_alert_ratio`, lower `trigger_ratio`.
- Too sparse: reduce `step_sec` so more windows are analyzed.
