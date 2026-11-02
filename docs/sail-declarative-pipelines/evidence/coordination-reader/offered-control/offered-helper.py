"""Append to, or read from, the one shared SDP coordination log under its persistent lockfile.

Append: --author X --body-file F [--reply-to REF ...] [--seen-through REF].
Read:   --since REF prints every entry after REF, so a reader resumes from the last
acknowledged point instead of from an arbitrary tail.
"""

import argparse
from collections.abc import Sequence
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import re
import sys


CANONICAL_LOG = Path("/Users/alexy/src/grust-sdp/codex-to-fable.md")
AUTHORS = ("Codex", "Fable")
ENTRY_HEADER = re.compile(
    r"^## (?P<timestamp>\d{4}-\d{2}-\d{2}T\S+) — (?:Codex|Fable)\r?\n"
    r"(?:Message-ID: (?P<id>CF-[0-9]{4,})\r?\n)?",
    re.MULTILINE,
)


def entry_reference(entry: re.Match[str]) -> str | None:
    """The reference other entries may cite: the Message-ID, else the legacy timestamp."""
    try:
        datetime.fromisoformat(entry["timestamp"])
    except ValueError:
        return None
    return entry["id"] or f"legacy:{entry['timestamp']}"


def entries_after(history: str, reference: str) -> tuple[str, str]:
    """Every entry appended after the one carrying `reference`, verbatim and in order,
    with the reference of the last entry returned: the boundary a reader may cite as
    Seen-Through. Nothing new returns ("", reference)."""
    entries = list(ENTRY_HEADER.finditer(history))
    for index, entry in enumerate(entries):
        if entry_reference(entry) == reference:
            later = [candidate for candidate in entries[index + 1 :] if entry_reference(candidate) is not None]
            if not later:
                return "", reference
            boundary = entry_reference(later[-1])
            if boundary is None:  # unreachable after the filter above; keeps the type honest
                raise ValueError("coordination entry without a usable reference")
            return history[later[0].start() :], boundary
    raise ValueError(f"unknown coordination reference: {reference}")


def read_since(log: Path, reference: str) -> tuple[str, str]:
    """Read one consistent snapshot under a shared lock; an append in progress is never seen.
    The boundary refers to that snapshot only, so an entry appended afterwards is not covered."""
    with log.with_suffix(".lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
        history = log.read_text(encoding="utf-8")
    return entries_after(history, reference)


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
            if entry_reference(entry) is None:
                continue
            references.add(f"legacy:{entry['timestamp']}")
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
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--author", choices=AUTHORS)
    parser.add_argument("--body-file", type=Path)
    parser.add_argument("--reply-to", action="append", default=[], metavar="REFERENCE")
    parser.add_argument("--seen-through", metavar="REFERENCE")
    parser.add_argument(
        "--since",
        metavar="REFERENCE",
        help="print every entry after REFERENCE instead of appending (log unchanged); "
        "stderr reports read-through: the last reference printed, to cite as Seen-Through",
    )
    args = parser.parse_args()
    if args.since is not None:
        if args.author or args.body_file or args.reply_to or args.seen_through:
            parser.error("--since reads the log and takes no append options")
        try:
            entries, boundary = read_since(CANONICAL_LOG, args.since)
        except ValueError as error:
            parser.error(str(error))
        print(entries, end="", flush=True)
        print(f"read-through: {boundary}", file=sys.stderr)
        return
    if args.author is None or args.body_file is None:
        parser.error("appending requires --author and --body-file")
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
