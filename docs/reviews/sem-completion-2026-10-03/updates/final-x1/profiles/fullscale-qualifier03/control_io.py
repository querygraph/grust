"""Bounded closed metadata identity; no subprocess or native import."""

from __future__ import annotations

import hashlib
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

import owner_models as o


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def utc() -> str:
    return datetime.now(UTC).isoformat()


def pin(path: Path, maximum: int = 1 << 30) -> o.Pin:
    before = path.lstat()
    require(
        stat.S_ISREG(before.st_mode) and before.st_size <= maximum,
        "bounded physical regular metadata/log file required",
    )
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    after = path.lstat()
    require(
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
        "file changed during hash",
    )
    return o.Pin(path=path, bytes=after.st_size, sha256=digest)


def read(expected: o.Pin) -> bytes:
    require(
        expected.bytes <= 16 << 20 and pin(expected.path, 16 << 20) == expected,
        "metadata identity or size differs",
    )
    raw = expected.path.read_bytes()
    require(
        len(raw) == expected.bytes
        and hashlib.sha256(raw).hexdigest() == expected.sha256,
        "metadata changed during read",
    )
    return raw


def save(path: Path, value: o.Model) -> None:
    temporary = path.with_suffix(".writing")
    with temporary.open("x") as stream:
        stream.write(value.model_dump_json(indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def closed(process: o.ProcessProof, *, native: bool = False) -> None:
    require(
        process.pid > 1
        and process.pgid > 1
        and process.wait_completed
        and process.group_absent
        and not process.forced_cleanup
        and process.finished_utc is not None,
        "actual wait/owned group closure absent or forced",
    )
    require(
        process.returncode == 0
        or native
        and process.sigint_shutdown
        and process.returncode == -2,
        "actual waited process failed",
    )
