"""Prepare catalog/statistics and oracle requests from the pinned SNB checkout."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from snb_complex import request as complex_request
from snb_dataset import PIN, load, request
from snb_scale import replicate


def verify_checkout(root: Path) -> None:
    environment = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    head = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], env=environment, text=True
    ).strip()
    dirty = subprocess.check_output(
        ["git", "-C", str(root), "status", "--porcelain"], env=environment, text=True
    ).strip()
    if head != PIN or dirty:
        raise ValueError("SNB checkout must be clean at the pinned commit")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--track", choices=("short", "complex"), default="short")
    parser.add_argument("--replicas", type=int, default=1)
    args = parser.parse_args()
    root = args.checkout.resolve()
    verify_checkout(root)
    dataset = load(root)
    record = (complex_request if args.track == "complex" else request)(dataset, root)
    scaled = replicate(dataset, args.replicas)
    record["tables"] = [table.metadata() for table in scaled.tables]
    record["dataset_sha256"] = scaled.sha256
    args.output.write_text(json.dumps(record, indent=2) + "\n")


if __name__ == "__main__":
    main()
