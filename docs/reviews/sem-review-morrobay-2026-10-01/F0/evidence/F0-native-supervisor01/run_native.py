"""Root-controlled native build or four cold process F0 cells; never retries."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import stat
import subprocess
import time
from pathlib import Path
from types import FrameType

import models


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def utc() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def identity(path: Path) -> models.Identity:
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode), "regular pinned file required")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(2**20):
            digest.update(block)
    after = path.lstat()
    require((before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_ino, after.st_size, after.st_mtime_ns), "file changed while hashing")
    return models.Identity(bytes=after.st_size, sha256=digest.hexdigest())


def file_pin(path: Path) -> models.FilePin:
    return models.FilePin(path=path, **identity(path).model_dump())


def inventory(pins: tuple[models.FilePin, ...]) -> dict[str, models.Identity]:
    result: dict[str, models.Identity] = {}
    for pin in pins:
        actual = identity(pin.path)
        require(actual == models.Identity(bytes=pin.bytes, sha256=pin.sha256), "pinned bytes changed: " + str(pin.path))
        key = pin.path.as_posix()
        require(key not in result or result[key] == actual, "conflicting file identities")
        result[key] = actual
    return result


def save(receipt: models.Receipt) -> None:
    path = receipt.config.output / "receipt.json"
    temporary = path.with_suffix(".partial")
    with temporary.open("w") as stream:
        stream.write(receipt.model_dump_json(indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def group_members(pid: int, ps: Path) -> tuple[str, ...]:
    result = subprocess.run([str(ps), "-axo", "pid=,ppid=,pgid=,stat=,command="],
                            capture_output=True, text=True, check=True, timeout=5)
    require(len(result.stdout) <= 4 * 2**20, "bounded process observation exceeded")
    lines = []
    for line in result.stdout.splitlines():
        fields = line.strip().split(maxsplit=4)
        if len(fields) == 5 and fields[2].isdigit() and int(fields[2]) == pid:
            lines.append(line.strip())
    return tuple(lines)


def terminate(child: subprocess.Popen[bytes], seconds: int) -> None:
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        child.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait(timeout=seconds)


def stop(_signal: int, _frame: FrameType | None) -> None:
    raise InterruptedError("native F0 supervision interrupted")


def parse_time(text: str) -> int:
    matches = re.findall(r"^\s*(\d+)\s+maximum resident set size\s*$", text, re.MULTILINE)
    require(len(matches) == 1 and int(matches[0]) > 0, "one positive macOS /usr/bin/time peak RSS required")
    return int(matches[0])


def execute(receipt: models.Receipt, record: models.Child, timeout: int,
            environment: dict[str, str]) -> None:
    config = receipt.config
    output = config.output / record.id
    output.mkdir()
    out, err = output / "stdout.txt", output / "stderr.txt"
    process: subprocess.Popen[bytes] | None = None
    record.started_utc = utc()
    started = time.monotonic()
    try:
        with out.open("xb") as stdout, err.open("xb") as stderr:
            started = time.monotonic()
            process = subprocess.Popen(record.command, cwd=config.source_root / "csr-floor",
                                       env=environment, stdout=stdout, stderr=stderr,
                                       start_new_session=True)
            record.pid = process.pid
            save(receipt)
            try:
                record.returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                record.timed_out = True
                raise
            finally:
                record.launch_to_wait_seconds = time.monotonic() - started
        require(record.returncode == 0, "native child exit was nonzero")
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        record.error = repr(error)
    finally:
        if process is not None:
            try:
                remaining = group_members(process.pid, config.ps.path)
                if process.poll() is None or remaining:
                    record.forced_cleanup = True
                    terminate(process, config.closure_seconds)
                    record.returncode = process.returncode
                record.group_remaining = group_members(process.pid, config.ps.path)
                require(not record.group_remaining, "owned child process group remains")
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                record.error = (record.error or "") + "; closure: " + repr(error)
            require(process.poll() is not None or record.error is not None, "child wait is uncertain")
        record.finished_utc = utc()
        record.stdout, record.stderr = identity(out), identity(err)
        if record.error is None and not record.forced_cleanup and not record.timed_out:
            record.outcome = "passed_internal_guard"
        else:
            record.outcome = "error"
        save(receipt)


def validate_result(result: models.NativeResult, data: models.Dataset, undirected: bool) -> None:
    arcs = data.edge_rows * (2 if undirected else 1)
    require(result.vertices == data.vertex_rows and result.edges == data.edge_rows and
            result.arcs == arcs and result.undirected is undirected, "F0 exact count/form contract differs")
    require(result.csr_bytes == (data.vertex_rows + 1) * 8 + arcs * 4 + data.vertex_rows * 8,
            "F0 declared CSR byte formula differs")
    require(max(result.read_seconds, result.map_seconds, result.build_seconds) <= result.total_seconds + 0.001,
            "F0 internal timer bounds differ beyond printed millisecond rounding")


def environment(config: models.Config) -> dict[str, str]:
    env = dict(os.environ)
    env.update(RAYON_NUM_THREADS="4", LC_ALL="C")
    return env


def cells(receipt: models.Receipt) -> None:
    config = receipt.config
    if config.build_receipt is None or config.binary is None:
        raise ValueError("sealed native build required")
    built = models.RootBuild.model_validate_json(config.build_receipt.path.read_bytes())
    validate_build(built, config)
    stopped = False
    for index, name in enumerate(models.ORDER):
        data, undirected = config.datasets[index // 2], bool(index % 2)
        output = config.output / name
        command: tuple[str, ...] = (str(config.time.path), "-l", "-o", str(output / "time.txt"), str(config.binary.path),
                   "--vertices", str(data.vertices.path), "--edges", str(data.edges.path),
                   "--src", "source", "--dst", "target", "--threads", "4")
        if undirected:
            command += ("--undirected",)
        child = models.Child(id=name, command=command, outcome="skipped" if stopped else "running")
        receipt.children.append(child)
        save(receipt)
        if stopped:
            child.error = "earlier one-shot cell failed; no retry or cleanup override"
            continue
        execute(receipt, child, config.cell_seconds, environment(config))
        try:
            require(child.outcome == "passed_internal_guard", "F0 cell execution failed")
            require((output / "stdout.txt").stat().st_size <= 2**20, "bounded one-record output required")
            child.result = models.NativeResult.model_validate_json((output / "stdout.txt").read_bytes())
            validate_result(child.result, data, undirected)
            child.maxrss_bytes = parse_time((output / "time.txt").read_text())
            child.time_record = identity(output / "time.txt")
        except (OSError, ValueError) as error:
            child.outcome, child.error, stopped = "error", repr(error), True
        save(receipt)
    require(not stopped, "one or more native F0 one-shot outcomes did not pass")
    receipt.outcome = "completed_internal_guards"


def validate_build(built: models.RootBuild, config: models.Config) -> None:
    require(built.errors == [] and built.source_before == built.source_after and built.binary == config.binary,
            "successful immutable root build/source/binary binding failed")
    expected = {pin.path.relative_to(config.source_root / "csr-floor").as_posix(): pin
                for pin in config.source_files if pin.path.is_relative_to(config.source_root / "csr-floor")}
    require(built.source_before == expected, "root build must bind all three exact borrowed crate files")
    require(built.command[1:] == ("build", "--locked", "--release", "--manifest-path",
                                 str(config.source_root / "csr-floor/Cargo.toml")), "exact locked release build command required")
    required = {"CARGO_INCREMENTAL": "0", "CARGO_PROFILE_RELEASE_OPT_LEVEL": "3",
                "CARGO_PROFILE_RELEASE_DEBUG": "0", "CARGO_PROFILE_RELEASE_STRIP": "true",
                "CARGO_PROFILE_RELEASE_CODEGEN_UNITS": "1", "CARGO_PROFILE_RELEASE_LTO": "thin"}
    require(all(built.environment.get(key) == value for key, value in required.items()), "native optimized flags differ")
    require(built.cargo_version.startswith("cargo 1.98.1 ") and built.rustc_verbose.startswith("rustc 1.98.1 ") and
            "host: x86_64-apple-darwin" in built.rustc_verbose and "Mach-O 64-bit executable x86_64" in built.file_type,
            "root-observed compiler/native executable identity differs")


def run(path: Path) -> int:
    config = models.Config.model_validate_json(path.read_bytes())
    require(platform.system() == "Darwin", "native macOS protocol only")
    helper_paths = {pin.path.resolve() for pin in config.helper_files}
    require(Path(models.__file__).resolve() in helper_paths and Path(__file__).resolve() in helper_paths,
            "actual imported sibling models and runner bytes must be pinned")
    require(not config.output.exists() and not config.output.is_symlink(), "fresh output required; no resume")
    require(not any(lock.exists() or lock.is_symlink() for lock in config.refuse_locks), "another declared serial job is active")
    require(not config.lock.exists() and not config.lock.is_symlink(), "serial owner lock already exists")
    require(shutil.disk_usage(config.output.parent).free >= config.disk_free_bytes, "disk admission failed")
    config.output.mkdir()
    config.lock.mkdir()
    receipt = models.Receipt(config=config, config_pin=file_pin(path), helper_pin=file_pin(Path(__file__).resolve()),
                             started_utc=utc(), parent_pid=os.getpid())
    with (config.lock / "owner.json").open("x") as stream:
        stream.write(json.dumps({"pid": os.getpid(), "started_utc": receipt.started_utc,
                                 "output": str(config.output), "config_sha256": receipt.config_pin.sha256}) + "\n")
    save(receipt)
    try:
        receipt.before = inventory((*config.pins(), receipt.config_pin, receipt.helper_pin))
        receipt.observations = {"platform": platform.platform(), "machine": platform.machine(),
                                "cpu_count": os.cpu_count(), "host_memory_bytes": int(subprocess.run(
                                    ["/usr/sbin/sysctl", "-n", "hw.memsize"], capture_output=True,
                                    text=True, check=True, timeout=5).stdout),
                                "maxrss_scope": "macOS /usr/bin/time -l child maximum RSS in bytes; no PSS or cgroup data",
                                "cache_policy": "not flushed; one fresh process per cell; shared host",
                                "internal_timer": "borrowed source first Parquet open through adjacency/checksum; printed milliseconds",
                                "outer_timer": "parent immediately before Popen through waited wrapper child exit; excludes input hashes",
                                "correctness": "counts plus unchanged source target-sum assertion; no full topology oracle"}
        save(receipt)
        cells(receipt)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        receipt.outcome = "error"
        receipt.errors.append(repr(error))
    finally:
        try:
            receipt.after = inventory((*config.pins(), receipt.config_pin, receipt.helper_pin))
            require(receipt.before == receipt.after, "all original identities must close")
        except (OSError, ValueError) as error:
            receipt.outcome = "error"
            receipt.errors.append("identity closure: " + repr(error))
        closed = all(child.pid is None or (child.returncode is not None and not child.group_remaining)
                     for child in receipt.children)
        if closed and receipt.outcome != "error":
            (config.lock / "owner.json").unlink()
            config.lock.rmdir()
            receipt.locks_released = True
        receipt.finished_utc = utc()
        save(receipt)
    return 0 if receipt.outcome in ("built", "completed_internal_guards") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    return run(args.config)


if __name__ == "__main__":
    raise SystemExit(main())
