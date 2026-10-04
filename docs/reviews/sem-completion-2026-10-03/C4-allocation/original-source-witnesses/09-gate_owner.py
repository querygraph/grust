"""Root-launched native Rust gate owner; commits and publication are separate."""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import signal
import stat
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import FrameType

from gate_models import (
    LOCK_BASE,
    NamespaceAdmission,
    Owner,
    Pin,
    Plan,
    Receipt,
    Record,
    Source,
    Step,
)

HELPERS = Path(__file__).parent
STOP_SIGNAL: int | None = None


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def pin(path: Path) -> Pin:
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode), "regular non-symlink file required: " + str(path))
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    after = path.lstat()
    require(
        (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        == (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ),
        "file changed while hashing",
    )
    return Pin(path=path, bytes=after.st_size, sha256=digest)


def write(path: Path, record: Record) -> None:
    temporary = path.with_name(path.name + ".writing")
    with temporary.open("x") as stream:
        stream.write(record.model_dump_json(indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def git(plan: Plan, *argv: str, code: int = 0) -> str:
    done = subprocess.run(
        ["/usr/bin/git", *argv],
        cwd=plan.repo,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    require(
        done.returncode == code and len(done.stdout) <= 2**20,
        "source metadata command failed: " + " ".join(argv),
    )
    return done.stdout.strip()


def source(plan: Plan) -> Source:
    git(plan, "symbolic-ref", "--quiet", "HEAD", code=1)
    head = git(plan, "rev-parse", "HEAD")
    head_tree = git(plan, "rev-parse", "HEAD^{tree}")
    require(head == plan.commit, "detached source HEAD differs")
    require(git(plan, "cat-file", "-t", plan.tree) == "tree", "admitted tree object missing")
    git(plan, "diff", "--quiet", plan.tree, "--")
    git(plan, "diff", "--cached", "--quiet", plan.tree, "--")
    require(
        not git(plan, "ls-files", "--others", "--exclude-standard"),
        "untracked source would escape exact tree admission",
    )
    status = git(plan, "status", "--porcelain=v1")
    if plan.mode == "committed":
        require(
            head_tree == plan.tree and not status,
            "final gate requires exact clean committed tree",
        )
    else:
        require(
            head_tree != plan.tree and bool(status),
            "candidate tree must contain the admitted observer changes",
        )
    return Source(
        head=head,
        head_tree=head_tree,
        admitted_tree=plan.tree,
        status=status,
        detached=True,
    )


def immutable(plan: Plan, configuration: Pin) -> None:
    require(pin(configuration.path) == configuration, "configuration changed")
    for expected in (
        *plan.tools.values(),
        plan.python,
        plan.libpython,
        plan.namespace_admission,
    ):
        require(
            pin(expected.path) == expected,
            "admitted tool/Python/namespace identity changed: " + str(expected.path),
        )
    admission = NamespaceAdmission.model_validate_json(plan.namespace_admission.path.read_bytes())
    require(
        admission.target == plan.target and admission.cargo_home == plan.cargo_home,
        "namespace seed admission does not bind actual target/cache",
    )
    for manifest in admission.seed_manifests:
        require(pin(manifest.path) == manifest, "root seed-copy manifest changed")
    require(
        all(
            not (plan.cargo_home / n).exists() and not (plan.cargo_home / n).is_symlink()
            for n in ("config", "config.toml", "credentials", "credentials.toml")
        ),
        "private Cargo-home contains excluded configuration/credentials",
    )
    for directory, entries in ((plan.repo, plan.source_files), (HELPERS, plan.helpers)):
        for name, expected_identity in entries.items():
            actual = pin(directory / name)
            require(
                (actual.bytes, actual.sha256) == (expected_identity.bytes, expected_identity.sha256),
                "source/helper identity changed: " + name,
            )
    source(plan)


def members(pgid: int) -> list[int]:
    done = subprocess.run(
        ["/bin/ps", "-axo", "pid=,pgid=,uid="],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    result: list[int] = []
    for line in done.stdout.splitlines():
        fields = line.split()
        require(len(fields) == 3, "unexpected process identity row")
        pid, group, uid = map(int, fields)
        if group == pgid:
            require(uid == os.getuid(), "owned group contains another user; refuse signals")
            result.append(pid)
    return result


def cleanup(pgid: int, process: subprocess.Popen[bytes] | None = None) -> None:
    require(pgid > 1 and pgid != os.getpgrp(), "refuse unrelated/self process group")
    if process is not None and process.poll() is None:
        process.terminate()  # Reap the known direct child before considering descendant group signals.
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    for signum, seconds in ((signal.SIGTERM, 10.0), (signal.SIGKILL, 5.0)):
        if process is not None:
            process.poll()
        if not members(pgid):
            return
        try:
            os.killpg(pgid, signum)
        except ProcessLookupError:
            pass
        limit = time.monotonic() + seconds
        while time.monotonic() < limit:
            if not members(pgid):
                return
            time.sleep(0.05)
    require(not members(pgid), "owned build group remains after cleanup")


def interrupted(signum: int, _frame: FrameType | None) -> None:
    global STOP_SIGNAL
    STOP_SIGNAL = signum  # Defer exceptions until Popen and its ownership journal are complete.


def check_deadline(deadline: float) -> None:
    require(STOP_SIGNAL is None, "gate interrupted by signal " + str(STOP_SIGNAL))
    require(time.monotonic() < deadline, "gate total timeout expired")


def directory_bytes(path: Path) -> int:
    total = 0
    for directory, directories, files in os.walk(path, followlinks=False):
        base = Path(directory)
        require(
            not any((base / n).is_symlink() for n in directories),
            "private target contains a symlink directory",
        )
        for name in files:
            entry = (base / name).lstat()
            require(
                stat.S_ISREG(entry.st_mode),
                "private target contains a nonregular member",
            )
            total += entry.st_size
    return total


def guard_disk(plan: Plan) -> dict[str, int]:
    observed = {str(p): shutil.disk_usage(p).free for p in (plan.root, plan.target, plan.cargo_home)}
    require(
        all(n >= plan.minimum_free_bytes for n in observed.values()),
        "insufficient free disk before Rust gate step",
    )
    require(
        directory_bytes(plan.target) <= plan.maximum_target_bytes,
        "private target exceeds declared 200 GiB maximum",
    )
    return observed


def environment(plan: Plan) -> dict[str, str]:
    env = dict(os.environ)
    for name in tuple(env):
        if name.startswith("CARGO_") or name in {
            "PYTHONHOME",
            "PYTHONPATH",
            "RUSTFLAGS",
            "CARGO_ENCODED_RUSTFLAGS",
            "RUSTC_WRAPPER",
            "RUSTC_WORKSPACE_WRAPPER",
            "RUSTC",
            "RUSTDOC",
            "RUSTUP_TOOLCHAIN",
        }:
            del env[name]
    env.update(
        RUSTUP_TOOLCHAIN="1.97.1",
        CARGO_BUILD_JOBS="4",
        CARGO_INCREMENTAL="0",
        CARGO_HOME=str(plan.cargo_home),
        CARGO_TARGET_DIR=str(plan.target),
        CARGO_NET_OFFLINE="true",
        CARGO_PROFILE_RELEASE_OPT_LEVEL="3",
        CARGO_PROFILE_DEV_DEBUG="0",
        CARGO_PROFILE_TEST_DEBUG="0",
        CARGO_PROFILE_RELEASE_LTO="fat",
        CARGO_PROFILE_RELEASE_CODEGEN_UNITS="1",
        CARGO_PROFILE_RELEASE_DEBUG="0",
        CARGO_PROFILE_RELEASE_STRIP="true",
        RUSTC=str(plan.tools["rustc"].path),
        PYO3_PYTHON=str(plan.python.path),
        DYLD_LIBRARY_PATH=str(plan.libpython.path.parent),
        PROTOC=str(plan.tools["protoc"].path),
        PYTHONDONTWRITEBYTECODE="1",
        TMPDIR=str(plan.root / "tmp"),
    )
    env["PATH"] = (
        str(plan.tools["rustc"].path.parent)
        + ":"
        + str(plan.tools["protoc"].path.parent)
        + ":/usr/bin:/bin:/usr/sbin:/sbin"
    )
    return env


def step(
    plan: Plan,
    receipt: Receipt,
    name: str,
    argv: list[str],
    env: dict[str, str],
    deadline: float,
) -> None:
    check_deadline(deadline)
    guard_disk(plan)
    limit = min(deadline, time.monotonic() + plan.step_seconds)
    with (
        (plan.root / (name + ".log")).open("xb") as log,
        (plan.root / (name + ".disk.csv")).open("x") as disk,
    ):
        disk.write("observed_utc,target_filesystem_free_bytes\n")
        process = subprocess.Popen(
            argv,
            cwd=plan.repo,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        record = Step(
            name=name,
            argv=argv,
            started_utc=utc(),
            pid=process.pid,
            pgid=process.pid,
            log=plan.root / (name + ".log"),
        )
        try:
            receipt.steps.append(record)
            write(plan.root / "receipt.json", receipt)
            while process.poll() is None:
                check_deadline(limit)
                free = shutil.disk_usage(plan.target).free
                disk.write(utc() + "," + str(free) + "\n")
                disk.flush()
                require(
                    free >= plan.emergency_free_bytes,
                    "20 GiB emergency free-disk floor reached",
                )
                try:
                    process.wait(timeout=min(1.0, max(0.01, limit - time.monotonic())))
                except subprocess.TimeoutExpired:
                    pass
            record.returncode = process.wait(timeout=5)
            record.wait_completed = True
            record.remaining_owned_pids = members(record.pgid)
            require(
                record.returncode == 0 and not record.remaining_owned_pids,
                "failed step or live child group: " + name,
            )
        except BaseException as error:  # Retain every actual failed gate and close only its owned group.
            receipt.errors.append(f"{name} {type(error).__name__}: {error}")
            record.forced_cleanup = process.poll() is None or bool(members(record.pgid))
            cleanup(record.pgid, process)
            record.returncode = process.wait(timeout=5)
            record.wait_completed = True
            record.remaining_owned_pids = members(record.pgid)
            raise
        finally:
            record.finished_utc = utc()
            write(plan.root / "receipt.json", receipt)


def run(configuration: Path) -> int:
    configuration_pin = pin(configuration)
    plan = Plan.model_validate_json(configuration.read_bytes())
    require(configuration.parent == HELPERS, "configuration must be beside frozen helpers")
    require(
        plan.root.is_dir() and not plan.root.is_symlink(),
        "root must prepare a fresh physical result directory",
    )
    require(
        not (plan.root / "receipt.json").exists(),
        "fresh attempt required; preserve failed attempts",
    )
    owner = Owner(pid=os.getpid(), token=uuid.uuid4().hex, plan_sha256=configuration_pin.sha256)
    receipt = Receipt(
        started_utc=utc(),
        owner=owner,
        configuration=configuration_pin,
        mode=plan.mode,
        namespace_admission=plan.namespace_admission,
    )
    write(plan.root / "receipt.json", receipt)
    locks: list[Path] = []
    deadline = time.monotonic() + plan.total_seconds
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, interrupted)
    try:
        require(
            platform.system() == "Darwin" and platform.machine() == "x86_64",
            "native x86_64 macOS required",
        )
        require(
            all(p.is_dir() and not p.is_symlink() for p in (plan.target, plan.cargo_home)),
            "root-prepared private target/cache directories required",
        )
        immutable(plan, configuration_pin)
        receipt.source_before = source(plan)
        receipt.free_bytes_before = guard_disk(plan)
        receipt.target_bytes_before = directory_bytes(plan.target)
        for name in ("gate.lock", "serial-queue.lock"):
            lock = LOCK_BASE / name
            lock.mkdir()
            locks.append(lock)
            write(lock / "owner.json", owner)
        (plan.root / "tmp").mkdir()
        env = environment(plan)
        receipt.release_environment = {
            n: env[n]
            for n in (
                "RUSTUP_TOOLCHAIN",
                "CARGO_BUILD_JOBS",
                "CARGO_INCREMENTAL",
                "CARGO_HOME",
                "CARGO_TARGET_DIR",
                "CARGO_NET_OFFLINE",
                "CARGO_PROFILE_RELEASE_OPT_LEVEL",
                "CARGO_PROFILE_RELEASE_LTO",
                "CARGO_PROFILE_DEV_DEBUG",
                "CARGO_PROFILE_TEST_DEBUG",
                "CARGO_PROFILE_RELEASE_CODEGEN_UNITS",
                "CARGO_PROFILE_RELEASE_DEBUG",
                "CARGO_PROFILE_RELEASE_STRIP",
                "RUSTC",
                "PYO3_PYTHON",
                "DYLD_LIBRARY_PATH",
                "PROTOC",
                "PATH",
                "TMPDIR",
            )
        }
        cargo = str(plan.tools["cargo"].path)
        schedule = [
            ("rustc-version", [str(plan.tools["rustc"].path), "-Vv"]),
            ("cargo-version", [cargo, "-Vv"]),
            ("protoc-version", [str(plan.tools["protoc"].path), "--version"]),
            ("python-version", [str(plan.python.path), "--version"]),
            ("fmt", [cargo, "fmt", "--all", "--", "--check"]),
            (
                "clippy",
                [
                    cargo,
                    "clippy",
                    "--offline",
                    "--locked",
                    "--all-targets",
                    "--",
                    "-D",
                    "warnings",
                ],
            ),
            ("test", [cargo, "test", "--offline", "--locked", "--all-targets"]),
            (
                "release",
                [
                    cargo,
                    "build",
                    "--offline",
                    "--locked",
                    "--release",
                    "-p",
                    "sail-cli",
                ],
            ),
        ]
        for name, argv in schedule:  # Any failed gate raises before the next command.
            step(plan, receipt, name, argv, env, deadline)
            if name in {"rustc-version", "cargo-version", "python-version"}:
                expected = {
                    "rustc-version": "rustc 1.97.1",
                    "cargo-version": "cargo 1.97.1",
                    "python-version": "Python 3.12.6",
                }[name]
                require(
                    expected in (plan.root / (name + ".log")).read_text(),
                    "selected tool version differs: " + name,
                )
        receipt.binary = pin(plan.target / "release/sail")
        immutable(plan, configuration_pin)
        receipt.source_after = source(plan)
        require(receipt.source_before == receipt.source_after, "source changed during gates")
        receipt.immutable_pins_before_after_equal = True
        receipt.target_bytes_after = directory_bytes(plan.target)
        require(
            receipt.target_bytes_after <= plan.maximum_target_bytes,
            "final target exceeds maximum",
        )
        receipt.all_owned_groups_absent = all(not members(s.pgid) and not s.forced_cleanup for s in receipt.steps)
        require(
            receipt.all_owned_groups_absent,
            "owned groups remain or forced cleanup prevents qualification",
        )
        for lock in locks:
            require(
                Owner.model_validate_json((lock / "owner.json").read_bytes()) == owner
                and {p.name for p in lock.iterdir()} == {"owner.json"},
                "lock ownership changed",
            )
        for lock in reversed(locks):
            (lock / "owner.json").unlink()
            lock.rmdir()
        locks.clear()
        receipt.locks_released = True
        receipt.outcome = "passed_candidate_native_gate" if plan.mode == "candidate" else "passed_committed_native_gate"
    except BaseException as error:  # noqa: BLE001 - all failed gates and closure errors are retained.
        receipt.outcome = "error"
        receipt.errors.append(f"{type(error).__name__}: {error}")
        if locks:
            receipt.errors.append("Failed owned locks retained for root closure review: " + ", ".join(map(str, locks)))
    receipt.finished_utc = utc()
    write(plan.root / "receipt.json", receipt)
    print(receipt.outcome + " " + str(plan.root / "receipt.json"))
    return 0 if receipt.outcome.startswith("passed_") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    return run(parser.parse_args().plan)


if __name__ == "__main__":
    raise SystemExit(main())
