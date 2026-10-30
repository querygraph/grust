"""Append to the one shared SDP coordination log under its persistent lockfile."""

import argparse
from collections.abc import Sequence
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import re


CANONICAL_LOG = Path("/Users/alexy/src/grust-sdp/codex-to-fable.md")
AUTHORS = ("Codex", "Fable")
ENTRY_HEADER = re.compile(
    r"^## (?P<timestamp>\d{4}-\d{2}-\d{2}T\S+) — (?:Codex|Fable)\r?\n"
    r"(?:Message-ID: (?P<id>CF-[0-9]{4,})\r?\n)?",
    re.MULTILINE,
)


def append_message(
    log: Path,
    author: str,
    body: str,
    *,
    reply_to: Sequence[str] = (),
    seen_through: str | None = None,
) -> str:
    """Append one entry; the path parameter permits isolated temporary-log tests."""
    if author not in AUTHORS:
        raise ValueError(f"unsupported author: {author}")
    if not body.strip():
        raise ValueError("message must not be empty")
    with log.with_suffix(".lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            history = log.read_text(encoding="utf-8")
        except FileNotFoundError:
            history = ""
        references: set[str] = set()
        last_id = 0
        for entry in ENTRY_HEADER.finditer(history):
            timestamp = entry["timestamp"]
            try:
                datetime.fromisoformat(timestamp)
            except ValueError:
                continue
            references.add(f"legacy:{timestamp}")
            if message_id := entry["id"]:
                references.add(message_id)
                last_id = max(last_id, int(message_id.removeprefix("CF-")))
        requested = [*reply_to]
        if seen_through is not None:
            requested.append(seen_through)
        for reference in requested:
            if reference not in references:
                raise ValueError(f"unknown coordination reference: {reference}")

        message_id = f"CF-{last_id + 1:04d}"
        timestamp = datetime.now(timezone.utc).isoformat()
        metadata = [f"Message-ID: {message_id}"]
        metadata.extend(f"Reply-To: {reference}" for reference in reply_to)
        if seen_through is not None:
            metadata.append(f"Seen-Through: {seen_through}")
        entry = f"\n## {timestamp} — {author}\n" + "\n".join(metadata) + "\n\n" + body
        if not body.endswith("\n"):
            entry += "\n"
        with log.open("a", encoding="utf-8", newline="") as output:
            output.write(entry)
            output.flush()
            os.fsync(output.fileno())
        return message_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--author", required=True, choices=AUTHORS)
    parser.add_argument("--body-file", type=Path, required=True)
    parser.add_argument("--reply-to", action="append", default=[], metavar="REFERENCE")
    parser.add_argument("--seen-through", metavar="REFERENCE")
    args = parser.parse_args()
    with args.body_file.open(encoding="utf-8", newline="") as source:
        body = source.read()
    try:
        message_id = append_message(
            CANONICAL_LOG,
            args.author,
            body,
            reply_to=args.reply_to,
            seen_through=args.seen_through,
        )
    except ValueError as error:
        parser.error(str(error))
    print(message_id)


if __name__ == "__main__":
    main()
