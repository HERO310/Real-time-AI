#!/usr/bin/env python3
import json
from pathlib import Path

import streamlit as st


def read_jsonl(path: Path):
    rows = []
    if not path.exists():
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def find_latest_runs(results_dir: Path, limit: int = 20):
    candidates = [p for p in results_dir.iterdir() if p.is_dir()]
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[:limit]


def main():
    st.set_page_config(page_title="Realtime Sentinel UI", layout="wide")
    st.title("Realtime Sentinel Dashboard")

    rt_root = Path(__file__).resolve().parent.parent
    results_dir = rt_root / "results"

    st.sidebar.header("Controls")
    refresh = st.sidebar.button("Refresh")
    runs = find_latest_runs(results_dir)
    run_names = [p.name for p in runs]

    if not run_names:
        st.warning("No runs found in results folder yet.")
        return

    selected = st.sidebar.selectbox("Run", run_names, index=0)
    run_dir = results_dir / selected

    window_log = run_dir / "window_flags.jsonl"
    rows = read_jsonl(window_log)

    if refresh:
        st.rerun()

    col1, col2, col3, col4 = st.columns(4)
    total = len(rows)
    alerts = [r for r in rows if str(r.get("status", "")).startswith("ALERT")]
    last = rows[-1] if rows else {}

    col1.metric("Total Windows", total)
    col2.metric("Alerts", len(alerts))
    col3.metric("Last Status", str(last.get("status", "N/A")))
    col4.metric("Last Level", str(last.get("level", "N/A")))

    st.subheader("Latest Event")
    if last:
        st.json(last)
    else:
        st.info("No window records yet.")

    st.subheader("Latest Snapshots")
    images = sorted(run_dir.glob("alert_*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)[:6]
    if images:
        cols = st.columns(min(3, len(images)))
        for i, img in enumerate(images):
            cols[i % len(cols)].image(str(img), caption=img.name, use_container_width=True)
    else:
        st.info("No alert snapshots for this run yet.")

    st.subheader("Recent Window Records")
    if rows:
        st.dataframe(rows[-200:], use_container_width=True)


if __name__ == "__main__":
    main()
