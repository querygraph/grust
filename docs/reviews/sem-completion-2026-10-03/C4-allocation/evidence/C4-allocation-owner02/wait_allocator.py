"""Waited root launcher; a detached wrapper is not an owner-exit observation."""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import allocator_models as m
import allocator_owner as owner
import gate_owner as owned

BOOT = 'import runpy,sys;sys.path[:0]=sys.argv[1:3];sys.argv=sys.argv[3:];runpy.run_path(sys.argv[0],run_name="__main__")'


def run(path: Path) -> int:
    configuration = owner.pin(path)
    plan = m.Plan.model_validate_json(path.read_bytes())
    owner.immutable(plan, configuration)
    destination = plan.root / "launch-receipt.json"
    owned.require(
        plan.root.is_dir() and not destination.exists(),
        "fresh prepared launch namespace required",
    )
    argv = [
        sys.executable,
        "-I",
        "-B",
        "-c",
        BOOT,
        str(Path(__file__).parent),
        str(Path(owned.__file__).parent),
        str(Path(__file__).with_name("allocator_owner.py")),
        "--plan",
        str(path),
    ]
    receipt = m.Launch(configuration=configuration, launcher_pid=os.getpid(), argv=argv)
    owner.save(destination, receipt)
    process: subprocess.Popen[bytes] | None = None
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, owned.interrupted)
    try:
        with (plan.root / "owner.log").open("xb") as log:
            process = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            receipt.owner_pid = process.pid
            owner.save(destination, receipt)
            deadline = time.monotonic() + plan.total_seconds + 120
            while process.poll() is None:
                owned.check_deadline(deadline)
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
            receipt.returncode = process.wait(timeout=5)
            receipt.waited = True
        receipt.owner_group_absent = not owned.members(process.pid)
        producer = m.Receipt.model_validate_json(
            (plan.root / "receipt.json").read_bytes()
        )
        owned.require(
            receipt.returncode == 0
            and receipt.owner_group_absent
            and producer.owner_pid == process.pid
            and producer.configuration == configuration
            and producer.outcome == "passed_native_factory_allocation_controls"
            and not producer.errors
            and producer.finished_utc is not None
            and producer.locks_released
            and producer.all_owned_groups_absent
            and producer.immutable_source_tool_helper_closure
            and producer.binary is not None,
            "closed positive allocator owner required",
        )
        owner.immutable(plan, configuration)
        receipt.owner_receipt = owner.pin(plan.root / "receipt.json")
        receipt.outcome = "passed_waited_native_factory_controls"
    except BaseException as error:  # noqa: BLE001 - failure stays failed; close only live direct ownership
        receipt.errors.append(repr(error))
        receipt.outcome = "error"
        try:
            if process is not None and process.poll() is None:
                receipt.forced_cleanup = True
                process.terminate()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)
            if process is not None:
                receipt.returncode = process.wait(timeout=5)
                receipt.waited = True
                receipt.owner_group_absent = not owned.members(process.pid)
                producer_path = plan.root / "receipt.json"
                if producer_path.is_file():
                    producer = m.Receipt.model_validate_json(producer_path.read_bytes())
                    if (
                        producer.owner_pid == process.pid
                        and producer.configuration == configuration
                    ):
                        for step in producer.steps:
                            if (
                                not step.waited or not step.group_absent
                            ) and owned.members(step.pgid):
                                owned.cleanup(step.pgid)
        except BaseException as cleanup_error:  # noqa: BLE001 - preserve failed cleanup without discarding owner failure
            receipt.errors.append("owned cleanup: " + repr(cleanup_error))
    finally:
        receipt.finished_utc = owned.utc()
        owner.save(destination, receipt)
    return 0 if receipt.outcome == "passed_waited_native_factory_controls" else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.plan))


if __name__ == "__main__":
    main()
