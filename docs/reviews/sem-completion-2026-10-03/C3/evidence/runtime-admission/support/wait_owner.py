"""Actually wait a fresh owner session; root detaches this supervisor itself.

Usage: python -I -B wait_owner.py --config /absolute/fresh/config.json
Owner code retains responsibility for its children and heavy lock. A supervisor
timeout is always failure, including when the subsequent owner wait is zero.
"""

# ruff: noqa: BLE001
# A lifecycle supervisor must retain cancellation and still actually wait its owner.

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Config:
    python: Path
    helper_script: Path
    args: list[str]
    wait_path: Path
    log_path: Path
    timeout_seconds: int
    owner_cap_seconds: int
    source_files: list[Path] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class FilePin:
    path: str
    bytes: int
    sha256: str


@dataclass(slots=True)
class WaitReceipt:
    started_utc: str
    supervisor_pid: int
    supervisor_pgid: int
    configuration: Config
    argv: list[str]
    status: str = "running"
    owner_pid: int | None = None
    owner_pgid: int | None = None
    returncode: int | None = None
    actual_wait_completed: bool = False
    owner_group_absent: bool = False
    timed_out: bool = False
    interrupted: bool = False
    requested_sigint: bool = False
    forced_kill: bool = False
    source_before: list[FilePin] = field(default_factory=list)
    source_after: list[FilePin] = field(default_factory=list)
    source_unchanged: bool = False
    finished_utc: str | None = None
    errors: list[str] = field(default_factory=list)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def pin(path: Path) -> FilePin:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return FilePin(str(path.resolve()), path.stat().st_size, digest.hexdigest())


def save(receipt: WaitReceipt) -> None:
    destination = receipt.configuration.wait_path
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(asdict(receipt), default=str, indent=2) + "\n")
    temporary.replace(destination)


def absent(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return True
    return False


def strings(value: object, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be an array of strings")
    return [str(item) for item in value]


def configuration(path: Path) -> Config:
    raw: dict[str, object] = json.loads(path.read_text())
    known = {
        "python",
        "helper_script",
        "args",
        "wait_path",
        "log_path",
        "timeout_seconds",
        "owner_cap_seconds",
        "source_files",
    }
    if set(raw) - known:
        raise ValueError("unknown supervisor configuration fields")
    paths = []
    for name in ("python", "helper_script", "wait_path", "log_path"):
        value = raw[name]
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise ValueError(f"{name} must be an absolute path string")
        paths.append(Path(value))
    timeout, cap = raw["timeout_seconds"], raw["owner_cap_seconds"]
    if type(timeout) is not int or type(cap) is not int or cap <= 0 or timeout <= cap:
        raise ValueError("positive integer supervisor timeout must exceed owner cap")
    result = Config(
        python=paths[0],
        helper_script=paths[1],
        args=strings(raw["args"], "args"),
        wait_path=paths[2],
        log_path=paths[3],
        timeout_seconds=timeout,
        owner_cap_seconds=cap,
        source_files=[Path(item) for item in strings(raw.get("source_files", []), "source_files")],
    )
    if not result.python.is_file() or not result.helper_script.is_file():
        raise ValueError("owner Python and script must exist")
    if any(not item.is_absolute() or not item.is_file() for item in result.source_files):
        raise ValueError("source_files must be existing absolute files")
    if result.wait_path == result.log_path or result.wait_path.exists() or result.log_path.exists():
        raise ValueError("wait and owner-log destinations must be distinct and fresh")
    return result


def supervise(config_path: Path) -> int:
    config = configuration(config_path)
    argv = [str(config.python), "-B", str(config.helper_script), *config.args]
    receipt = WaitReceipt(utc(), os.getpid(), os.getpgrp(), config, argv)
    sources = sorted(
        {
            config_path.resolve(),
            Path(__file__).resolve(),
            config.python.resolve(),
            config.helper_script.resolve(),
            *[path.resolve() for path in config.source_files],
        }
    )
    child: subprocess.Popen[bytes] | None = None
    try:
        receipt.source_before = [pin(path) for path in sources]
        save(receipt)
        with config.log_path.open("xb") as log:
            child = subprocess.Popen(
                argv, cwd=config.helper_script.parent, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
            )
            receipt.owner_pid, receipt.owner_pgid = child.pid, os.getpgid(child.pid)
            if receipt.owner_pgid != child.pid:
                raise ValueError("owner did not enter its own session")
            save(receipt)
            try:
                receipt.returncode = child.wait(timeout=config.timeout_seconds)
            except subprocess.TimeoutExpired:
                receipt.timed_out = True
                raise
            receipt.actual_wait_completed = True
    except BaseException:
        receipt.interrupted = not receipt.timed_out
        receipt.errors.append(traceback.format_exc())
    finally:
        if child is not None and not receipt.actual_wait_completed:
            try:
                if child.poll() is None:
                    receipt.requested_sigint = True
                    os.killpg(child.pid, signal.SIGINT)
                try:
                    receipt.returncode = child.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    receipt.forced_kill = True
                    os.killpg(child.pid, signal.SIGKILL)
                    receipt.returncode = child.wait(timeout=30)
                receipt.actual_wait_completed = True
            except BaseException:
                receipt.errors.append(traceback.format_exc())
        if receipt.owner_pgid is not None:
            receipt.owner_group_absent = absent(receipt.owner_pgid)
        try:
            receipt.source_after = [pin(path) for path in sources]
            receipt.source_unchanged = receipt.source_before == receipt.source_after
        except BaseException:
            receipt.errors.append(traceback.format_exc())
        passed = (
            receipt.returncode == 0
            and receipt.actual_wait_completed
            and receipt.owner_group_absent
            and receipt.source_unchanged
            and not receipt.timed_out
            and not receipt.interrupted
            and not receipt.forced_kill
            and not receipt.errors
        )
        receipt.status = "actual_owner_wait_passed" if passed else "failed"
        receipt.finished_utc = utc()
        save(receipt)
    return 0 if receipt.status == "actual_owner_wait_passed" else 1


def interrupted(number: int, _frame: object) -> None:
    raise InterruptedError(f"supervisor interrupted by signal{number}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    for number in (signal.SIGTERM, signal.SIGINT):
        signal.signal(number, interrupted)
    raise SystemExit(supervise(args.config))


if __name__ == "__main__":
    main()
