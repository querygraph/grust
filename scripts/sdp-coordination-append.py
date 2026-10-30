"""Append to the one shared SDP coordination log under its persistent lockfile."""
import argparse
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--author", required=True, choices=("Codex", "Fable"))
    parser.add_argument("--body-file", type=Path, required=True)
    args = parser.parse_args()
    body = args.body_file.read_text().strip()
    if not body:
        parser.error("message must not be empty")
    log = Path("/Users/alexy/src/grust-sdp/codex-to-fable.md")
    with log.with_suffix(".lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        with log.open("a") as output:
            output.write(f"\n## {datetime.now(timezone.utc).isoformat()} — {args.author}\n\n{body}\n")
            output.flush()
            os.fsync(output.fileno())


if __name__ == "__main__":
    main()
