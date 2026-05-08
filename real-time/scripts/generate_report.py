#!/usr/bin/env python3
import argparse
import csv
import json
import sys
from pathlib import Path


def load_rows(path: Path):
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


def summarize_rows(rows):
    total = len(rows)
    alerts = [r for r in rows if str(r.get("status", "")).startswith("ALERT")]
    first_alert = alerts[0]["start_s"] if alerts else None
    last_alert = alerts[-1]["end_s"] if alerts else None
    duration = max((rows[-1]["end_s"] - rows[0]["start_s"]), 1e-6) if rows else 1e-6
    alerts_per_hour = len(alerts) / duration * 3600.0

    return {
        "total_windows": total,
        "alerts": len(alerts),
        "first_alert_s": first_alert,
        "last_alert_s": last_alert,
        "alerts_per_hour": round(alerts_per_hour, 3),
    }


def main():
    parser = argparse.ArgumentParser(description="Generate supervisor-ready report from mode benchmark + logs")
    parser.add_argument("--video_name", required=True, help="Video stem name, e.g. Assault003_x264")
    parser.add_argument("--crime_target", default="all")
    parser.add_argument("--annotations_csv", default=None, help="Optional annotations CSV for eval metrics")
    parser.add_argument("--event_type_column", default="event_type")
    parser.add_argument("--video_column", default="video_path")
    parser.add_argument("--class_wise", action="store_true")
    args = parser.parse_args()

    rt_root = Path(__file__).resolve().parent.parent
    results = rt_root / "results"

    suffix = f"_{args.crime_target}" if args.crime_target and args.crime_target != "all" else ""
    fast_log = results / f"{args.video_name}_fast{suffix}" / "window_flags.jsonl"
    acc_log = results / f"{args.video_name}_high_accuracy{suffix}" / "window_flags.jsonl"

    if not fast_log.exists() or not acc_log.exists():
        raise FileNotFoundError("Expected both fast and high_accuracy window logs.")

    fast_rows = load_rows(fast_log)
    acc_rows = load_rows(acc_log)

    fast = summarize_rows(fast_rows)
    acc = summarize_rows(acc_rows)

    report = {
        "video": args.video_name,
        "crime_target": args.crime_target,
        "fast": fast,
        "high_accuracy": acc,
    }

    events = []
    if args.annotations_csv:
        events = load_annotations(
            Path(args.annotations_csv),
            f"{args.video_name}.mp4",
            args.event_type_column,
            args.video_column,
        )

    if events:
        rt_root = Path(__file__).resolve().parent.parent
        if str(rt_root) not in sys.path:
            sys.path.append(str(rt_root))
        from configs import CRIME_PROFILES, normalize_crime_target

        report["fast"]["eval_metrics"] = compute_metrics(
            fast_rows, events, None, normalize_crime_target, CRIME_PROFILES
        )
        report["high_accuracy"]["eval_metrics"] = compute_metrics(
            acc_rows, events, None, normalize_crime_target, CRIME_PROFILES
        )

        if args.class_wise:
            class_metrics_fast = {}
            class_metrics_acc = {}
            for key in CRIME_PROFILES.keys():
                if key == "all":
                    continue
                class_metrics_fast[key] = compute_metrics(
                    fast_rows, events, key, normalize_crime_target, CRIME_PROFILES
                )
                class_metrics_acc[key] = compute_metrics(
                    acc_rows, events, key, normalize_crime_target, CRIME_PROFILES
                )
            report["fast"]["class_metrics"] = class_metrics_fast
            report["high_accuracy"]["class_metrics"] = class_metrics_acc

    out_json = results / f"{args.video_name}_report.json"
    out_csv = results / f"{args.video_name}_report.csv"
    out_md = results / f"{args.video_name}_report.md"

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["mode", "total_windows", "alerts", "first_alert_s", "last_alert_s", "alerts_per_hour"])
        w.writerow(["fast", fast["total_windows"], fast["alerts"], fast["first_alert_s"], fast["last_alert_s"], fast["alerts_per_hour"]])
        w.writerow(["high_accuracy", acc["total_windows"], acc["alerts"], acc["first_alert_s"], acc["last_alert_s"], acc["alerts_per_hour"]])

    md = [
        f"# Realtime Report: {args.video_name}",
        "",
        "## Summary",
        f"- Fast alerts: {fast['alerts']} (first at {fast['first_alert_s']})",
        f"- High accuracy alerts: {acc['alerts']} (first at {acc['first_alert_s']})",
        "",
        "## Metrics",
        "| Mode | Windows | Alerts | First Alert (s) | Last Alert (s) | Alerts/hour |",
        "|---|---:|---:|---:|---:|---:|",
        f"| fast | {fast['total_windows']} | {fast['alerts']} | {fast['first_alert_s']} | {fast['last_alert_s']} | {fast['alerts_per_hour']} |",
        f"| high_accuracy | {acc['total_windows']} | {acc['alerts']} | {acc['first_alert_s']} | {acc['last_alert_s']} | {acc['alerts_per_hour']} |",
    ]
    if events:
        md.extend([
            "",
            "## Eval Metrics (Window-level)",
            "| Mode | Precision | Recall | F1 | False Positive Rate | TP | FP | FN | TN |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            f"| fast | {report['fast']['eval_metrics']['precision']} | {report['fast']['eval_metrics']['recall']} | {report['fast']['eval_metrics']['f1']} | {report['fast']['eval_metrics']['false_positive_rate']} | {report['fast']['eval_metrics']['tp']} | {report['fast']['eval_metrics']['fp']} | {report['fast']['eval_metrics']['fn']} | {report['fast']['eval_metrics']['tn']} |",
            f"| high_accuracy | {report['high_accuracy']['eval_metrics']['precision']} | {report['high_accuracy']['eval_metrics']['recall']} | {report['high_accuracy']['eval_metrics']['f1']} | {report['high_accuracy']['eval_metrics']['false_positive_rate']} | {report['high_accuracy']['eval_metrics']['tp']} | {report['high_accuracy']['eval_metrics']['fp']} | {report['high_accuracy']['eval_metrics']['fn']} | {report['high_accuracy']['eval_metrics']['tn']} |",
        ])
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")

    print(f"Saved: {out_json}")
    print(f"Saved: {out_csv}")
    print(f"Saved: {out_md}")


if __name__ == "__main__":
    main()
