#!/usr/bin/env python3
import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path


def run_mode(rt_root: Path, video_path: str, mode: str, crime_target: str) -> tuple:
    cmd = [
        sys.executable,
        str(rt_root / "run_realtime.py"),
        "--mode",
        mode,
        "--video_path",
        video_path,
    ]
    if crime_target and crime_target != "all":
        cmd.extend(["--crime_target", crime_target])

    t0 = time.time()
    subprocess.run(cmd, check=True)
    elapsed = time.time() - t0
    stem = Path(video_path).stem
    suffix = f"_{crime_target}" if crime_target and crime_target != "all" else ""
    log_path = rt_root / "results" / f"{stem}_{mode}{suffix}" / "window_flags.jsonl"
    return log_path, elapsed


def load_rows(path: Path) -> list:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def load_annotations(csv_path: Path, video_name: str, event_type_col: str, video_col: str) -> list:
    events = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if video_col not in row or event_type_col not in row:
                raise ValueError("annotations_csv missing required columns")
            row_video = Path(row[video_col]).name
            if video_name and row_video != video_name:
                continue
            start_s = float(row["start_s"])
            end_s = float(row["end_s"])
            event_type = str(row[event_type_col]).strip().lower()
            events.append({"start_s": start_s, "end_s": end_s, "event_type": event_type})
    return events


def overlaps(t0: float, t1: float, ev: dict) -> bool:
    return not (t1 <= ev["start_s"] or t0 >= ev["end_s"])


def derive_predicted_labels(row: dict, normalize_label, crime_profiles: dict) -> set:
    target = normalize_label(row.get("crime_target", "all"))
    if target and target != "all" and target in crime_profiles:
        return {target}

    labels = set()
    tags = row.get("event_tags", []) or []
    for tag in tags:
        norm = normalize_label(tag)
        if norm in crime_profiles and norm != "all":
            labels.add(norm)

    desc = str(row.get("descriptor", ""))
    desc_low = desc.lower()
    for key, profile in crime_profiles.items():
        if key == "all":
            continue
        for kw in profile.keywords:
            if kw in desc_low:
                labels.add(key)
                break
    return labels


def compute_metrics(rows: list, events: list, target_class: str, normalize_label, crime_profiles: dict) -> dict:
    tp = fp = fn = tn = 0
    for row in rows:
        t0 = float(row.get("start_s", 0.0))
        t1 = float(row.get("end_s", 0.0))
        gt_pos = False
        for ev in events:
            ev_type = normalize_label(ev["event_type"])
            if target_class and ev_type != target_class:
                continue
            if overlaps(t0, t1, ev):
                gt_pos = True
                break

        status = str(row.get("status", ""))
        pred_alert = status.startswith("ALERT")
        if target_class:
            pred_labels = derive_predicted_labels(row, normalize_label, crime_profiles)
            pred_pos = pred_alert and target_class in pred_labels
        else:
            pred_pos = pred_alert

        if pred_pos and gt_pos:
            tp += 1
        elif pred_pos and not gt_pos:
            fp += 1
        elif (not pred_pos) and gt_pos:
            fn += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "false_positive_rate": round(fpr, 4),
    }


def summarize(rows: list, elapsed_sec: float, events: list, class_wise: bool, rt_root: Path) -> dict:
    alerts = [r for r in rows if str(r.get("status", "")).startswith("ALERT")]
    total = len(rows)
    first_alert = alerts[0]["start_s"] if alerts else None
    alerts_per_100_windows = (len(alerts) / total * 100.0) if total else 0.0
    windows_per_sec = (total / elapsed_sec) if elapsed_sec > 0 else 0.0

    summary = {
        "total_windows": total,
        "alerts": len(alerts),
        "alerts_per_100_windows": round(alerts_per_100_windows, 3),
        "first_alert_s": first_alert,
        "elapsed_sec": round(elapsed_sec, 3),
        "windows_per_sec": round(windows_per_sec, 3),
    }

    if events:
        if str(rt_root) not in sys.path:
            sys.path.append(str(rt_root))
        from configs import CRIME_PROFILES, normalize_crime_target

        summary["eval_metrics"] = compute_metrics(rows, events, None, normalize_crime_target, CRIME_PROFILES)
        if class_wise:
            class_metrics = {}
            for key in CRIME_PROFILES.keys():
                if key == "all":
                    continue
                class_metrics[key] = compute_metrics(rows, events, key, normalize_crime_target, CRIME_PROFILES)
            summary["class_metrics"] = class_metrics

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run fast/high_accuracy and compare quick metrics")
    parser.add_argument("--video_path", required=True)
    parser.add_argument("--crime_target", default="all")
    parser.add_argument("--annotations_csv", default=None, help="Optional annotations CSV for eval metrics")
    parser.add_argument("--event_type_column", default="event_type")
    parser.add_argument("--video_column", default="video_path")
    parser.add_argument("--class_wise", action="store_true")
    args = parser.parse_args()

    rt_root = Path(__file__).resolve().parent.parent

    fast_log, fast_elapsed = run_mode(rt_root, args.video_path, "fast", args.crime_target)
    acc_log, acc_elapsed = run_mode(rt_root, args.video_path, "high_accuracy", args.crime_target)

    events = []
    if args.annotations_csv:
        events = load_annotations(
            Path(args.annotations_csv),
            Path(args.video_path).name,
            args.event_type_column,
            args.video_column,
        )

    fast_rows = load_rows(fast_log)
    acc_rows = load_rows(acc_log)

    fast = summarize(fast_rows, fast_elapsed, events, args.class_wise, rt_root)
    acc = summarize(acc_rows, acc_elapsed, events, args.class_wise, rt_root)

    out = {
        "video": Path(args.video_path).name,
        "crime_target": args.crime_target,
        "fast": fast,
        "high_accuracy": acc,
    }
    out_path = rt_root / "results" / f"{Path(args.video_path).stem}_mode_benchmark.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    print(json.dumps(out, indent=2))
    print(f"Saved benchmark: {out_path}")


if __name__ == "__main__":
    main()
