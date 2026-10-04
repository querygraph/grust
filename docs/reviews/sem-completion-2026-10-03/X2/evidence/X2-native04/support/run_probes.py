"""Serial waited X2 owner; only complete post-exit control oracles qualify."""

import argparse
import hashlib
import os
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import probe_models as m
from pydantic import Field

BASE = Path("/Volumes/Apo/graph-tests/results/sem-review-20261001")
LOCKS = (
    Path("/tmp/morrobay-sem-completion-heavy.lock"),
    BASE / "gate.lock",
    BASE / "serial-queue.lock",
)
BOOT = "import runpy,sys;sys.path.insert(0,sys.argv[1]);sys.argv=sys.argv[2:];runpy.run_path(sys.argv[0],run_name='__main__')"


class Config(m.Model):
    root: Path
    python: Path
    worker: m.Pin
    oracle: m.Pin
    helpers: list[m.Pin]
    plans: list[m.Pin]
    timeout_seconds: int = Field(default=14400, ge=300, le=21600)


class Call(m.Model):
    run_id: str
    plan: m.Pin
    pid: int | None = None
    pgid: int | None = None
    launched_utc: str | None = None
    finished_utc: str | None = None
    launch_to_wait_seconds: float | None = None
    returncode: int | None = None
    wait_completed: bool = False
    child_group_absent: bool = False
    forced_cleanup: bool = False
    producer: m.Pin | None = None
    oracle: m.Pin | None = None
    oracle_returncode: int | None = None
    oracle_pid: int | None = None
    oracle_pgid: int | None = None
    oracle_wait_completed: bool = False
    oracle_group_absent: bool = False


class Receipt(m.Model):
    outcome: Literal["checking", "completed_scoped_native_probe_queue", "error"] = (
        "checking"
    )
    started_utc: str
    finished_utc: str | None = None
    owner_pid: int
    configuration: m.Pin
    configuration_value: Config
    calls: list[Call] = Field(default_factory=list)
    owned_locks_released: bool = False
    errors: list[str] = Field(default_factory=list)


def pin(path: Path) -> m.Pin:
    if path.is_symlink() or not path.is_file():
        raise ValueError("regular owner input required")
    return m.Pin(
        path=path,
        bytes=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def save(path: Path, receipt: Receipt) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as stream:
        stream.write(receipt.model_dump_json(indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def absent(pgid: int) -> bool:
    raw = subprocess.check_output(["ps", "-axo", "pid=,pgid="], text=True, timeout=5)
    return not any(
        int(values[1]) == pgid
        for line in raw.splitlines()
        if len(values := line.split()) == 2
    )


def command(config: Config, helper: Path, *arguments: str) -> list[str]:
    return [
        str(config.python),
        "-I",
        "-B",
        "-c",
        BOOT,
        str(helper.parent),
        str(helper),
        *arguments,
    ]


def execute(path: Path) -> int:
    config = Config.model_validate_json(path.read_bytes())
    config.root.mkdir(parents=True, exist_ok=False)
    receipt = Receipt(
        started_utc=datetime.now(UTC).isoformat(),
        owner_pid=os.getpid(),
        configuration=pin(path),
        configuration_value=config,
    )
    locks: list[Path] = []
    process: subprocess.Popen[str] | None = None
    active: Call | None = None
    before = {
        item.path: item
        for item in [config.worker, config.oracle, *config.helpers, *config.plans]
    }
    deadline = time.monotonic() + config.timeout_seconds
    try:
        if not config.plans or len(before) != 2 + len(config.helpers) + len(
            config.plans
        ):
            raise ValueError("owner pins empty or duplicated")
        if not {Path(__file__), Path(m.__file__)}.issubset(before):
            raise ValueError("loaded owner and models must be pinned")
        if any(pin(item.path) != item for item in before.values()):
            raise ValueError("owner helper/plan origin changed")
        for lock in LOCKS:
            lock.mkdir()
            locks.append(lock)
            (lock / "owner.json").write_text(receipt.model_dump_json() + "\n")
        plans = [
            m.Plan.model_validate_json(item.path.read_bytes()) for item in config.plans
        ]
        if len({plan.run_id for plan in plans}) != len(plans) or len(
            {plan.output for plan in plans}
        ) != len(plans):
            raise ValueError("fresh unique run IDs/outputs required")
        save(config.root / "receipt.json", receipt)
        for item, plan in zip(config.plans, plans, strict=True):
            if plan.output.exists():
                raise ValueError("planned output already exists")
            active = Call(run_id=plan.run_id, plan=item)
            receipt.calls.append(active)
            with (config.root / f"{plan.run_id}.log").open("x") as log:
                started = time.monotonic()
                process = subprocess.Popen(
                    command(config, config.worker.path, "--plan", str(item.path)),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    text=True,
                )
                active.pid = process.pid
                active.pgid = process.pid
                active.launched_utc = datetime.now(UTC).isoformat()
                save(config.root / "receipt.json", receipt)
                active.returncode = process.wait(
                    timeout=min(plan.timeout_seconds + 120, deadline - time.monotonic())
                )
                active.launch_to_wait_seconds = time.monotonic() - started
                active.finished_utc = datetime.now(UTC).isoformat()
                active.wait_completed = True
                active.child_group_absent = absent(process.pid)
            if active.returncode != 0 or not active.child_group_absent:
                raise ValueError("native probe child failed or group remains")
            child = m.Receipt.model_validate_json(
                (plan.output / "receipt.json").read_bytes()
            )
            if (
                child.configuration != plan
                or child.owner_pid != process.pid
                or child.outcome != "completed_unqualified"
            ):
                raise ValueError("producer receipt does not bind waited child")
            active.producer = pin(plan.output / "receipt.json")
            oracle_output = config.root / f"{plan.run_id}-oracle.json"
            with (config.root / f"{plan.run_id}-oracle.log").open("x") as log:
                process = subprocess.Popen(
                    command(
                        config,
                        config.oracle.path,
                        "--receipt",
                        str(active.producer.path),
                        "--output",
                        str(oracle_output),
                    ),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    text=True,
                )
                active.oracle_pid = process.pid
                active.oracle_pgid = process.pid
                active.oracle_returncode = process.wait(
                    timeout=min(60, deadline - time.monotonic())
                )
                active.oracle_wait_completed = True
                active.oracle_group_absent = absent(process.pid)
            if active.oracle_returncode != 0 or not active.oracle_group_absent:
                raise ValueError("outside-timer answer/log oracle failed or remains")
            active.oracle = pin(oracle_output)
            save(config.root / "receipt.json", receipt)
        if (
            any(pin(item.path) != item for item in before.values())
            or pin(path) != receipt.configuration
        ):
            raise ValueError("owner identity closure differs")
        receipt.outcome = "completed_scoped_native_probe_queue"
    except BaseException as error:  # noqa: BLE001 - preserve interruption/failed locks and only clean live direct child
        receipt.errors.append(repr(error))
        receipt.outcome = "error"
        if process is not None and process.poll() is None:
            if active is not None:
                active.forced_cleanup = True
            try:
                os.killpg(process.pid, signal.SIGINT)
                process.wait(timeout=90)
            except subprocess.TimeoutExpired:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            except OSError as cleanup_error:
                receipt.errors.append(f"direct child cleanup: {cleanup_error!r}")
    finally:
        if receipt.outcome == "completed_scoped_native_probe_queue":
            try:
                for lock in reversed(locks):
                    owner = json_receipt(lock / "owner.json")
                    if (
                        owner.owner_pid != os.getpid()
                        or owner.configuration != receipt.configuration
                    ):
                        raise ValueError("lock owner changed; lock retained")
                for lock in reversed(locks):
                    (lock / "owner.json").unlink()
                    lock.rmdir()
                receipt.owned_locks_released = True
            except Exception as error:  # noqa: BLE001 - failed lock release never becomes a pass
                receipt.errors.append(f"owned lock release: {error!r}")
                receipt.outcome = "error"
        receipt.finished_utc = datetime.now(UTC).isoformat()
        save(config.root / "receipt.json", receipt)
    return 0 if receipt.outcome == "completed_scoped_native_probe_queue" else 1


def json_receipt(path: Path) -> Receipt:
    return Receipt.model_validate_json(path.read_bytes())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(execute(args.config))


if __name__ == "__main__":
    main()
