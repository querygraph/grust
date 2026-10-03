"""Own two serial representative cit-Patents E0 native cells and their separate post-exit full oracles.

Root launches --supervise from a short detached invocation. The supervisor
waits on an independent owner session; the owner waits every engine/client/
oracle, retaining failures, raw payloads, 500ms RSS, identities and closure.
"""

# ruff: noqa: BLE001
# Lifecycle cleanup also records cancellation and waits every owned child.

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

sys.path.insert(0, str(Path(__file__).resolve().parent))
from campaign_models import (
    BINARY,
    BINARY_SHA256,
    COMMIT,
    DATA,
    DATASETS,
    LOCK,
    OFFICIAL,
    PROGRAMS,
    PYHOME,
    ROOT,
    SOURCE,
    TREE,
    VENV,
    Cell,
    Dataset,
    FilePin,
    Process,
    Receipt,
)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def save(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def git(*arguments: str) -> str:
    return subprocess.check_output(["git", "-C", str(SOURCE), *arguments], text=True).strip()


def pin(path: Path) -> FilePin:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return FilePin(str(path.resolve()), path.stat().st_size, digest.hexdigest())


def absent(group: int) -> bool:
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return True
    return False


def source_pins() -> list[FilePin]:
    package = SOURCE / "examples/extensions/graph-algorithms/src/pyspark_pecan"
    paths = [
        *sorted(package.rglob("*.py")),
        SOURCE / "examples/extensions/benchmarks/e0_cell.py",
        SOURCE / "examples/extensions/benchmarks/e0_oracle.py",
        *sorted(Path(__file__).parent.glob("*.py")),
    ]
    return [pin(path) for path in paths]


def check_source() -> None:
    if git("rev-parse", "HEAD") != COMMIT or git("rev-parse", "HEAD^{tree}") != TREE or git("status", "--porcelain"):
        raise ValueError("native campaign source differs or is dirty")
    symbolic = subprocess.run(
        ["git", "-C", str(SOURCE), "symbolic-ref", "-q", "HEAD"], capture_output=True, check=False
    )
    if symbolic.returncode != 1:
        raise ValueError("native campaign needs detached HEAD")


class Sampler:
    """Sample only the observed owned PIDs; never label sampled RSS as hard peak."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.pids: dict[int, str] = {}
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.errors: list[str] = []
        self.thread = threading.Thread(target=self.run, name="owned-rss", daemon=True)

    def add(self, process: Process) -> None:
        with self.lock:
            self.pids[process.pid] = process.role

    def remove(self, process: Process) -> None:
        with self.lock:
            self.pids.pop(process.pid, None)

    def run(self) -> None:
        try:
            with self.path.open("x") as stream:
                while not self.stop.is_set():
                    with self.lock:
                        pids = dict(self.pids)
                    if pids:
                        observed = subprocess.run(
                            ["ps", "-o", "pid=,rss=", "-p", ",".join(map(str, pids))],
                            capture_output=True,
                            text=True,
                            timeout=5,
                            check=False,
                        )
                        if observed.returncode not in (0, 1):
                            raise RuntimeError(f"RSS ps returned {observed.returncode}")
                        rows = []
                        for line in observed.stdout.splitlines():
                            pid, kb = map(int, line.split())
                            rows.append({"pid": pid, "role": pids[pid], "rss_bytes": kb * 1024})
                        stream.write(
                            json.dumps({"utc": utc(), "monotonic_ns": time.monotonic_ns(), "observations": rows}) + "\n"
                        )
                        stream.flush()
                    self.stop.wait(0.5)
        except BaseException:
            self.errors.append(traceback.format_exc())

    def close(self) -> None:
        self.stop.set()
        self.thread.join(timeout=10)
        if self.thread.is_alive() or self.errors:
            raise RuntimeError(f"RSS observer incomplete: {self.errors}")


def launch(
    role: str, argv: list[str], environment: dict[str, str], log: BinaryIO, cell: Cell, sampler: Sampler
) -> tuple[subprocess.Popen[bytes], Process]:
    child = subprocess.Popen(
        argv, cwd=SOURCE, env=environment, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
    )
    observed = Process(role, argv, child.pid, os.getpgid(child.pid), utc())
    if observed.pgid != child.pid:
        child.kill()
        child.wait()
        raise ValueError("child did not enter its own process group")
    cell.processes.append(observed)
    sampler.add(observed)
    return child, observed


def wait(
    child: subprocess.Popen[bytes], record: Process, sampler: Sampler, timeout: int, *, terminate: bool = False
) -> None:
    if terminate and child.poll() is None:
        record.requested_termination = True
        os.killpg(record.pgid, signal.SIGTERM)
    try:
        record.returncode = child.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        record.forced_kill = True
        os.killpg(record.pgid, signal.SIGKILL)
        record.returncode = child.wait(timeout=30)
    record.actual_wait_completed = True
    record.finished_utc = utc()
    record.group_absent = absent(record.pgid)
    sampler.remove(record)
    if record.forced_kill or not record.group_absent:
        raise RuntimeError(f"{record.role} required forced cleanup or leaves its group")


def environment(output: Path, *, client: bool) -> dict[str, str]:
    inherited = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("SAIL_", "NUTMEG_", "TOKIO_", "RAYON_"))
        and key not in ("PYTHONHOME", "PYTHONPATH", "DYLD_LIBRARY_PATH")
    }
    inherited.update(
        {
            "SAIL_MODE": "local",
            "SAIL_EXPERIMENTAL_EXTENSIONS": "1",
            "SAIL_GRAPH_UTILS_ROOT": (output / "staging").as_uri(),
            "SAIL_EXECUTION__DEFAULT_PARALLELISM": "16",
            "TOKIO_WORKER_THREADS": "16",
            "RAYON_NUM_THREADS": "16",
            "SAIL_RUNTIME__MEMORY_POOL__TYPE": "greedy",
            "SAIL_RUNTIME__MEMORY_POOL__GREEDY__MAX_SIZE": str(30 * 1024**3),
            "TMPDIR": str(output / "tmp"),
            "RUST_LOG": "warn",
            "DYLD_LIBRARY_PATH": str(PYHOME / "lib"),
        }
    )
    if client:
        inherited["PYTHONPATH"] = os.pathsep.join(
            (str(SOURCE / "examples/extensions/graph-algorithms/src"), str(SOURCE / "examples/extensions/benchmarks"))
        )
    else:
        inherited.update({"PYTHONHOME": str(PYHOME), "PYTHONPATH": str(VENV / "lib/python3.12/site-packages")})
    return inherited


def paths(dataset: Dataset) -> list[Path]:
    original = [DATA / dataset.name / f"{dataset.name}-v.parquet", DATA / dataset.name / f"{dataset.name}-e.parquet"]
    if dataset.name != "cit-Patents":
        original.append(OFFICIAL / dataset.name / f"{dataset.name}.properties")
    if dataset.name == "kgs":
        original.append(OFFICIAL / "kgs/kgs-SSSP")
    return original


def command(dataset: Dataset, program: str, port: int, output: Path) -> list[str]:
    argv = [
        str(VENV / "bin/python"),
        "-B",
        str(SOURCE / "examples/extensions/benchmarks/e0_cell.py"),
        "--endpoint",
        f"sc://127.0.0.1:{port}",
        "--vertices",
        str(paths(dataset)[0]),
        "--edges",
        str(paths(dataset)[1]),
        "--output",
        str(output / "cell"),
        "--program",
        program,
        "--source",
        str(dataset.source),
        "--landmarks",
        str(dataset.source),
        "--partitions",
        "16",
        "--record-plans",
    ]
    if dataset.undirected:
        argv.append("--undirected")
    if program == "pagerank":
        argv.extend(("--iterations", "10", "--normalized"))
    else:
        argv.extend(("--iterations", "1000", "--vote-to-halt"))
        if program == "sssp" and dataset.weighted:
            argv.append("--input-weights")
    return argv


def run_cell(cell: Cell, record: Receipt) -> None:
    output = ROOT / "raw" / f"{cell.dataset.name}-{cell.program}"
    output.mkdir(parents=True, exist_ok=False)
    (output / "staging").mkdir()
    (output / "tmp").mkdir()
    sampler = Sampler(output / "rss-500ms.jsonl")
    sampler.thread.start()
    owned: list[tuple[subprocess.Popen[bytes], Process]] = []
    cell.status = "running"
    try:
        check_source()
        cell.input_before = [pin(path) for path in paths(cell.dataset)]
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        server_env = environment(output, client=False)
        cell.environment = {
            key: value
            for key, value in server_env.items()
            if key.startswith(("SAIL_", "TOKIO_", "RAYON_"))
            or key in ("PYTHONHOME", "PYTHONPATH", "DYLD_LIBRARY_PATH", "TMPDIR")
        }
        with (output / "server.log").open("xb") as log:
            server, server_record = launch(
                "server",
                [str(BINARY), "spark", "server", "--ip", "127.0.0.1", "--port", str(port)],
                server_env,
                log,
                cell,
                sampler,
            )
        owned.append((server, server_record))
        save(ROOT / "receipt.json", asdict(record))
        ready_by = time.monotonic() + 30
        while True:
            if server.poll() is not None:
                raise RuntimeError("native server exited before readiness")
            with socket.socket() as connection:
                connection.settimeout(0.2)
                if connection.connect_ex(("127.0.0.1", port)) == 0:
                    break
            if time.monotonic() >= ready_by:
                raise TimeoutError("native server readiness expired")
            time.sleep(0.05)
        client_env = environment(output, client=True)
        started = time.perf_counter()
        with (output / "client.log").open("xb") as log:
            client, client_record = launch(
                "client", command(cell.dataset, cell.program, port, output), client_env, log, cell, sampler
            )
        owned.append((client, client_record))
        save(ROOT / "receipt.json", asdict(record))
        wait(client, client_record, sampler, 1200)
        cell.client_launch_wait_seconds = time.perf_counter() - started
        if client_record.returncode != 0:
            raise RuntimeError(f"cell client returned {client_record.returncode}")
        wait(server, server_record, sampler, 30, terminate=True)
        if server_record.returncode not in (0, -signal.SIGTERM):
            raise RuntimeError(f"server returned unexpected {server_record.returncode}")
        oracle_argv = [
            str(VENV / "bin/python"),
            "-B",
            str(SOURCE / "examples/extensions/benchmarks/e0_oracle.py"),
            "--cell",
            str(output / "cell"),
            "--output",
            str(output / "oracle.json"),
        ]
        if cell.dataset.name == "kgs" and cell.program == "sssp":
            oracle_argv.extend(("--official-sssp", str(OFFICIAL / "kgs/kgs-SSSP")))
        with (output / "oracle.log").open("xb") as log:
            oracle, oracle_record = launch("oracle", oracle_argv, client_env, log, cell, sampler)
        owned.append((oracle, oracle_record))
        save(ROOT / "receipt.json", asdict(record))
        wait(oracle, oracle_record, sampler, 1200)
        if oracle_record.returncode != 0:
            raise RuntimeError(f"full physical oracle returned {oracle_record.returncode}")
        oracle_result = json.loads((output / "oracle.json").read_text())
        if oracle_result.get("status") != "passed_full_physical_oracle" or oracle_result.get("mismatch_rows") != 0:
            raise RuntimeError("oracle receipt does not confirm a full physical pass")
        if cell.dataset.name == "kgs" and cell.program == "sssp" and not oracle_result.get("official_sssp_passed"):
            raise RuntimeError("kgs full official weighted SSSP receipt did not pass")
        cell.input_after = [pin(path) for path in paths(cell.dataset)]
        if cell.input_before != cell.input_after:
            raise RuntimeError("an original input or reference changed")
        check_source()
        cell.status = "qualified"
    except BaseException:
        cell.status = "failed"
        cell.errors.append(traceback.format_exc())
        raise
    finally:
        for process, observed in reversed(owned):
            if not observed.actual_wait_completed:
                try:
                    wait(process, observed, sampler, 30, terminate=True)
                except BaseException:
                    cell.errors.append(traceback.format_exc())
        try:
            sampler.close()
        except BaseException:
            cell.errors.append(traceback.format_exc())
        try:
            cell.raw_inventory = [pin(path) for path in sorted(output.rglob("*")) if path.is_file()]
        except BaseException:
            cell.errors.append(traceback.format_exc())
        if cell.errors or any(not item.group_absent or item.forced_kill for item in cell.processes):
            cell.status = "failed"
        save(ROOT / "receipt.json", asdict(record))


def owner() -> int:
    if (ROOT / "receipt.json").exists() or (ROOT / "raw").exists():
        raise ValueError("campaign destination is not fresh; preserve it and choose a new campaign root")
    record = Receipt(
        utc(), os.getpid(), os.getpgrp(), cells=[Cell(dataset, program) for dataset in DATASETS for program in PROGRAMS]
    )
    acquired = False
    try:
        if record.owner_pid != record.owner_pgid:
            raise ValueError("owner was not detached into its own session")
        check_source()
        LOCK.mkdir()
        acquired = True
        (LOCK / "owner").write_text(str(record.owner_pid))
        record.source_before = source_pins()
        record.binary_before = pin(BINARY)
        if record.binary_before.sha256 != BINARY_SHA256:
            raise ValueError("optimized native runtime binary identity changed")
        save(ROOT / "receipt.json", asdict(record))
        for cell in record.cells:
            run_cell(cell, record)
            if cell.status != "qualified":
                raise RuntimeError("cell did not qualify")
            record.qualified_cells += 1
        record.outcome = "passed_two_native_E0_cit_active_cells"
    except BaseException:
        record.outcome = "failed"
        record.errors.append(traceback.format_exc())
        for cell in record.cells:
            if cell.status == "pending":
                cell.status = "skipped_after_failure"
    finally:
        try:
            record.source_after = source_pins()
            record.binary_after = pin(BINARY)
            check_source()
            record.source_unchanged = (
                record.source_before == record.source_after and record.binary_before == record.binary_after
            )
        except BaseException:
            record.errors.append(traceback.format_exc())
        record.all_child_groups_absent = all(
            process.actual_wait_completed and process.group_absent
            for cell in record.cells
            for process in cell.processes
        )
        if acquired and record.all_child_groups_absent:
            try:
                if (LOCK / "owner").read_text() != str(record.owner_pid):
                    raise ValueError("heavy lock owner differs")
                (LOCK / "owner").unlink()
                LOCK.rmdir()
                record.lock_released = True
            except BaseException:
                record.errors.append(traceback.format_exc())
        if (
            record.errors
            or not record.source_unchanged
            or not record.all_child_groups_absent
            or not record.lock_released
        ):
            record.outcome = "failed"
        record.finished_utc = utc()
        save(ROOT / "receipt.json", asdict(record))
    return 0 if record.outcome == "passed_two_native_E0_cit_active_cells" else 1


def interrupted(number: int, _frame: object) -> None:
    raise TimeoutError(f"E0 campaign interrupted by signal {number}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--supervise", action="store_true")
    args = parser.parse_args()
    if args.supervise:
        with (ROOT / "owner.log").open("xb") as log:
            child = subprocess.Popen(
                [sys.executable, "-I", "-B", __file__], stdout=log, stderr=subprocess.STDOUT, start_new_session=True
            )
            result = child.wait()
        save(
            ROOT / "wait.json",
            {
                "observed_utc": utc(),
                "owner_pid": child.pid,
                "returncode": result,
                "actual_wait_completed": True,
                "owner_group_absent": absent(child.pid),
            },
        )
        raise SystemExit(result)
    for number in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM):
        signal.signal(number, interrupted)
    signal.alarm(10800)
    raise SystemExit(owner())


if __name__ == "__main__":
    main()
