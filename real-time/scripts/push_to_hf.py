#!/usr/bin/env python3
"""Publish the realtime project or LoRA artifacts to Hugging Face Hub.

This script does not change runtime behavior. It only prepares and uploads
the selected local folder to a Hugging Face repository when the user provides
an auth token and repo id.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Push realtime project files to Hugging Face Hub")
    parser.add_argument("--repo_id", required=True, help="Target Hugging Face repo id, e.g. username/realtime-sentinel")
    parser.add_argument(
        "--source",
        choices=["project", "lora"],
        default="project",
        help="Upload the whole realtime project or the LoRA artifact folder",
    )
    parser.add_argument("--token", default=None, help="HF token. If omitted, uses HF_TOKEN env or cached login.")
    parser.add_argument("--private", action="store_true", help="Create the repo as private")
    parser.add_argument("--message", default="Publish realtime sentinel project", help="Commit message")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    try:
        from huggingface_hub import CommitOperationAdd, HfApi
    except Exception as exc:
        raise RuntimeError("huggingface_hub is required. Install it with: pip install huggingface_hub") from exc

    project_root = Path(__file__).resolve().parents[1]
    if args.source == "project":
        upload_root = project_root
        allow_patterns = [
            "alerts.py",
            "commands.md",
            "configs.py",
            "configs_finetune.yaml",
            "docs/**",
            "finetuned_qwen2vl_lora/**",
            "modle.md",
            "plan.md",
            "README.md",
            "run_realtime.py",
            "runtime.py",
            "scripts/**",
            "train_vlm_lora.py",
            "ui/**",
            "vlm_engine.py",
        ]
    else:
        upload_root = project_root / "finetuned_qwen2vl_lora"
        allow_patterns = ["**"]

    if not upload_root.exists():
        raise FileNotFoundError(f"Upload source does not exist: {upload_root}")

    api = HfApi()
    api.create_repo(repo_id=args.repo_id, repo_type="model", private=args.private, exist_ok=True, token=args.token)

    operations = []
    for path in sorted(upload_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(upload_root).as_posix()
        if not any(Path(rel).match(pattern) or rel.startswith(pattern.rstrip("**")) for pattern in allow_patterns):
            continue
        operations.append(CommitOperationAdd(path_in_repo=rel, path_or_fileobj=str(path)))

    if not operations:
        raise RuntimeError(f"No files selected for upload from {upload_root}")

    api.create_commit(
        repo_id=args.repo_id,
        repo_type="model",
        operations=operations,
        commit_message=args.message,
        token=args.token,
    )

    print(f"Uploaded {len(operations)} files to https://huggingface.co/{args.repo_id}")


if __name__ == "__main__":
    main()