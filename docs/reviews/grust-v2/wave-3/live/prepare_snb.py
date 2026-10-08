"""Prepare catalog/statistics and oracle requests from the pinned SNB checkout."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from snb_dataset import PIN, load, request


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
    args = parser.parse_args()
    root = args.checkout.resolve()
    verify_checkout(root)
    dataset = load(root)
    args.output.write_text(json.dumps(request(dataset, root), indent=2) + "\n")


if __name__ == "__main__":
    main()
