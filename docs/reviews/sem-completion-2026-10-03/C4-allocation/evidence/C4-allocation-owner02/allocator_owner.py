"""Root-only native standalone gate and six fresh allocator processes."""

import argparse
import json
import math
import os
import platform
import shutil
import signal
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import allocator_models as m
import gate_models
import gate_owner as owned

BASE = Path("/Volumes/Apo/graph-tests/results/sem-review-20261001")
OWNERSHIP_HASHES = {
    "gate_models.py": "6a33929b1d4c4d70ef11988b5461deeed9cab66002b0597cc79fb4c3b294f407",
    "gate_owner.py": "6125e36daec091b8619a51b2542728b331406067c19e9743109f245d2a737989",
}
PHASES = [
    "arrow_input_control",
    "first_update",
    "repeat_identical",
    "repeat_improving",
    "sparse_improving",
    "evaluate_all",
    *[name for _ in range(3) for name in ("state_emission", "merge_emitted_state")],
]


def pin(path: Path) -> m.Pin:
    return m.Pin.model_validate(owned.pin(path).model_dump())


def save(path: Path, value: m.Record) -> None:
    temporary = path.with_name(path.name + ".writing")
    with temporary.open("x") as stream:
        stream.write(value.model_dump_json(indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def immutable(plan: m.Plan, configuration: m.Pin) -> None:
    expected = [
        configuration,
        plan.source_freeze,
        *plan.source_files.values(),
        *plan.source_origins,
        *plan.helpers.values(),
        *plan.ownership_helpers.values(),
        *plan.tools.values(),
        *plan.seed_manifests,
    ]
    owned.require(
        all(pin(p.path) == p for p in expected),
        "source/tool/helper/cache admission identity differs",
    )
    for directory, entries in (
        (Path(__file__).parent, plan.helpers),
        (Path(owned.__file__).parent, plan.ownership_helpers),
    ):
        owned.require(
            all(p.path == directory / name for name, p in entries.items()),
            "actual helper origins differ",
        )
    owned.require(
        Path(m.__file__) == plan.helpers["allocator_models.py"].path
        and Path(gate_models.__file__) == plan.ownership_helpers["gate_models.py"].path,
        "imported model origins differ",
    )
    owned.require(
        {name: p.sha256 for name, p in plan.ownership_helpers.items()}
        == OWNERSHIP_HASHES,
        "frozen reused ownership helper identities differ",
    )
    toolchain = Path("/Users/alexy/.rustup/toolchains/1.97.1-x86_64-apple-darwin/bin")
    owned.require(
        all(p.path == toolchain / name for name, p in plan.tools.items()),
        "exact admitted native Rust toolchain origins required",
    )
    freeze = json.loads(plan.source_freeze.path.read_bytes())
    owned.require(
        plan.source_freeze.sha256
        == "82aaef4e7c4689621fd15ef18d54de5f1e68161e141d82a8884d020e73408e9f",
        "frozen standalone source receipt differs",
    )
    preparation = plan.source_freeze.path.parent / "preparation.json"
    origin_receipt = freeze["files"]["preparation.json"]
    owned.require(
        pin(preparation).model_dump(mode="json") == origin_receipt,
        "frozen factory/allocator origin receipt differs",
    )
    origins = json.loads(preparation.read_bytes())
    required_origins = [
        *origins["copied_native_sources"],
        *origins["lowerer_and_registry_sources"],
        origins["df55_factory_source"],
        origins["preserved_historical_meter"],
        origins["dependency_lock_origin"],
    ]
    owned.require(
        [p.model_dump(mode="json") for p in plan.source_origins] == required_origins,
        "complete actual factory/lowering/meter/dependency origins required",
    )
    frozen = {
        name.removeprefix("probe/"): value
        for name, value in freeze["files"].items()
        if name.startswith("probe/")
    }
    owned.require(
        set(frozen) == set(plan.source_files),
        "full frozen standalone source set differs",
    )
    actual_files = {
        p.relative_to(plan.source).as_posix()
        for p in plan.source.rglob("*")
        if p.is_file()
    }
    owned.require(
        actual_files == set(frozen)
        and not any(p.is_symlink() for p in plan.source.rglob("*")),
        "source has extra/symlink members",
    )
    for name, expected_pin in plan.source_files.items():
        observed = frozen[name]
        owned.require(
            expected_pin.path == plan.source / name
            and expected_pin.bytes == observed["bytes"]
            and expected_pin.sha256 == observed["sha256"],
            "source freeze rebasing mismatch",
        )
    owned.require(
        all(
            not (plan.cargo_home / name).exists()
            for name in ("config", "config.toml", "credentials", "credentials.toml")
        ),
        "private cache contains excluded configuration/credentials",
    )


def environment(plan: m.Plan) -> dict[str, str]:
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("CARGO_", "RUST", "SAIL_", "NUTMEG_"))
    }
    env.update(
        CARGO_HOME=str(plan.cargo_home),
        CARGO_TARGET_DIR=str(plan.target),
        CARGO_NET_OFFLINE="true",
        RUSTUP_TOOLCHAIN="1.97.1",
        RUSTC=str(plan.tools["rustc"].path),
        CARGO_BUILD_JOBS="4",
        CARGO_INCREMENTAL="0",
        CARGO_PROFILE_DEV_DEBUG="0",
        CARGO_PROFILE_TEST_DEBUG="0",
        CARGO_PROFILE_RELEASE_OPT_LEVEL="3",
        CARGO_PROFILE_RELEASE_LTO="fat",
        CARGO_PROFILE_RELEASE_CODEGEN_UNITS="1",
        CARGO_PROFILE_RELEASE_DEBUG="0",
        CARGO_PROFILE_RELEASE_STRIP="true",
        TMPDIR=str(plan.root / "tmp"),
    )
    env["PATH"] = (
        str(plan.tools["rustc"].path.parent) + ":/usr/bin:/bin:/usr/sbin:/sbin"
    )
    return env


def check_step_deadline(deadline: float, limit: float, name: str, seconds: int) -> None:
    """Distinguish the campaign cap from a step's independently bounded budget."""
    owned.check_deadline(deadline)
    owned.require(
        time.monotonic() < limit, f"step timeout expired: {name} ({seconds}s budget)"
    )


def cleanup_step(process: subprocess.Popen[bytes], record: m.Step) -> None:
    """Retain actual cleanup observations while every forced step remains failed."""
    record.forced_cleanup = True
    try:
        owned.cleanup(record.pgid, process)
    except BaseException as error:  # noqa: BLE001 - preserve each failed cleanup observation
        record.cleanup_errors.append("group cleanup: " + repr(error))
    try:
        record.returncode = process.wait(timeout=5)
        record.waited = True
    except BaseException as error:  # noqa: BLE001 - an attempted wait is not a completed wait
        record.cleanup_errors.append("direct child wait: " + repr(error))
    try:
        record.group_absent = not owned.members(record.pgid)
    except BaseException as error:  # noqa: BLE001 - absence must be observed, never inferred
        record.cleanup_errors.append("group observation: " + repr(error))
    if not record.waited or not record.group_absent:
        record.cleanup_errors.append("owned step cleanup remains incomplete")


def step(
    plan: m.Plan,
    receipt: m.Receipt,
    name: str,
    argv: list[str],
    deadline: float,
    seconds: int,
) -> m.Step:
    owned.check_deadline(deadline)
    owned.require(
        shutil.disk_usage(plan.target).free >= plan.minimum_free_bytes,
        "40GiB free admission floor not met",
    )
    record: m.Step | None = None
    with (plan.root / f"{name}.log").open("xb") as log:
        process = subprocess.Popen(
            argv,
            cwd=plan.source,
            env=environment(plan),
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            record = m.Step(
                name=name,
                argv=argv,
                pid=process.pid,
                pgid=process.pid,
                started_utc=owned.utc(),
            )
            receipt.steps.append(record)
            save(plan.root / "receipt.json", receipt)
            limit = min(deadline, time.monotonic() + seconds)
            while process.poll() is None:
                check_step_deadline(deadline, limit, name, seconds)
                owned.require(
                    shutil.disk_usage(plan.target).free >= plan.emergency_free_bytes,
                    "20GiB active disk floor reached",
                )
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
            record.returncode = process.wait(timeout=5)
            record.waited = True
            record.group_absent = not owned.members(process.pid)
            owned.require(
                record.returncode == 0 and record.group_absent,
                "step failed or owned group remains: " + name,
            )
        except BaseException:
            if process.poll() is None or owned.members(process.pid):
                if record is not None:
                    cleanup_step(process, record)
                else:
                    owned.cleanup(process.pid, process)
            raise
        finally:
            if record is not None:
                record.finished_utc = owned.utc()
                record.log = pin(plan.root / f"{name}.log")
                save(plan.root / "receipt.json", receipt)
    owned.require(record is not None, "missing step ownership record")
    return record


def qualify_probe(log: Path, groups: int, method: str) -> None:
    owned.require(log.stat().st_size <= 8 * 1024**2, "bounded JSON probe log exceeded")
    rows: list[dict[str, Any]] = [
        json.loads(line) for line in log.read_text().splitlines()
    ]
    expected_method = (
        "Native9fCompactMin" if method == "tuple-min" else "PlannerOrderedMinBy"
    )
    owned.require(
        len(rows) == 14
        and rows[0]["groups"] == groups
        and rows[0]["method"] == expected_method,
        "probe header/count differs",
    )
    owned.require(
        rows[-1] == {"checks": "passed", "groups": groups, "method": expected_method},
        "full internal semantic controls did not pass",
    )
    owned.require(
        [row["phase"] for row in rows[1:-1]] == PHASES, "all allocator phases required"
    )
    for row in rows[1:-1]:
        seconds = row["seconds_exploratory_shared_host"]
        owned.require(
            type(seconds) in (int, float) and math.isfinite(seconds) and seconds >= 0,
            "invalid phase duration",
        )
        owned.require(
            row["live_requested_change"]
            == row["live_requested_after"] - row["live_requested_before"],
            "allocator change contradicts raw counters",
        )
        for key in (
            "live_requested_before",
            "live_requested_after",
            "peak_requested_above_before",
            "allocations",
            "deallocations",
            "allocated_requested_bytes",
            "accumulator_reported_size",
            "output_array_reported_bytes",
            "process_lifetime_peak_rss_bytes",
        ):
            owned.require(
                type(row[key]) is int and row[key] >= 0,
                "invalid requested allocator/RSS counter",
            )


def run(path: Path) -> int:
    configuration = pin(path)
    plan = m.Plan.model_validate_json(path.read_bytes())
    owned.require(
        plan.root.is_dir()
        and not plan.root.is_symlink()
        and not (plan.root / "receipt.json").exists(),
        "fresh prepared physical attempt required",
    )
    receipt = m.Receipt(
        owner_pid=os.getpid(),
        owner_token=uuid.uuid4().hex,
        configuration=configuration,
        started_utc=owned.utc(),
    )
    save(plan.root / "receipt.json", receipt)
    locks: list[Path] = []
    deadline = time.monotonic() + plan.total_seconds
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, owned.interrupted)
    try:
        owned.require(
            platform.system() == "Darwin" and platform.machine() == "x86_64",
            "native x86_64 macOS required",
        )
        owned.check_deadline(deadline)
        immutable(plan, configuration)
        owned.require(
            all(
                p.is_dir() and not p.is_symlink()
                for p in (plan.source, plan.target, plan.cargo_home)
            ),
            "prepared physical source/target/private cache required",
        )
        for name in ("gate.lock", "serial-queue.lock"):
            lock = BASE / name
            lock.mkdir()
            locks.append(lock)
            save(lock / "owner.json", receipt)
        (plan.root / "tmp").mkdir()
        cargo = str(plan.tools["cargo"].path)
        schedule = [
            ("rustc-version", [str(plan.tools["rustc"].path), "-Vv"]),
            ("cargo-version", [cargo, "-Vv"]),
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
            ("release", [cargo, "build", "--offline", "--locked", "--release"]),
        ]
        for name, argv in schedule:
            result = step(plan, receipt, name, argv, deadline, plan.step_seconds)
            if name == "rustc-version":
                if result.log is None:
                    raise ValueError("actual compiler observation missing")
                version = result.log.path.read_text()
                owned.require(
                    "release: 1.97.1" in version
                    and "host: x86_64-apple-darwin" in version,
                    "actual compiler version/target differs",
                )
        binary = plan.target / "release/current-struct-aggregate-allocation-probe"
        receipt.binary = pin(binary)
        for i, (groups, method) in enumerate(
            [
                (4096, "tuple-min"),
                (4096, "min-by"),
                (100000, "tuple-min"),
                (100000, "min-by"),
                (100000, "min-by"),
                (100000, "tuple-min"),
            ],
            start=1,
        ):
            record = step(
                plan,
                receipt,
                f"probe-{i:02}-{groups}-{method}",
                [str(binary), str(groups), method],
                deadline,
                plan.probe_seconds,
            )
            if record.log is None:
                raise ValueError("probe output log missing")
            qualify_probe(record.log.path, groups, method)
            owned.require(pin(binary) == receipt.binary, "compiled probe changed")
        owned.check_deadline(deadline)
        immutable(plan, configuration)
        receipt.immutable_source_tool_helper_closure = True
        receipt.all_owned_groups_absent = all(
            item.waited
            and item.group_absent
            and not item.forced_cleanup
            and not item.cleanup_errors
            and not owned.members(item.pgid)
            for item in receipt.steps
        )
        owned.require(
            receipt.all_owned_groups_absent, "current owned group closure incomplete"
        )
        for lock in reversed(locks):
            owner = m.Receipt.model_validate_json((lock / "owner.json").read_bytes())
            owned.require(
                owner.owner_pid == receipt.owner_pid
                and owner.owner_token == receipt.owner_token
                and owner.configuration == configuration,
                "lock owner differs; preserve locks",
            )
        for lock in reversed(locks):
            (lock / "owner.json").unlink()
            lock.rmdir()
        receipt.locks_released = True
        receipt.outcome = "passed_native_factory_allocation_controls"
    except BaseException as error:  # noqa: BLE001 - all failures and owned locks remain retained
        receipt.errors.append(repr(error))
        receipt.outcome = "error"
    finally:
        receipt.finished_utc = owned.utc()
        save(plan.root / "receipt.json", receipt)
    return 0 if receipt.outcome == "passed_native_factory_allocation_controls" else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.plan))


if __name__ == "__main__":
    main()
