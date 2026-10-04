"""Actually wait the committed-source gate owner; forced cleanup never qualifies."""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import allocator_models as native
import allocator_owner as reused
import committed_models as m
import committed_owner as owner
import gate_owner as owned

BOOT = 'import runpy,sys;sys.path[:0]=sys.argv[1:4];sys.argv=sys.argv[4:];runpy.run_path(sys.argv[0],run_name="__main__")'


def require_positive(
    config: m.Config, configuration: native.Pin, pid: int, producer: m.Receipt
) -> None:
    owned.require(
        producer.owner_pid == pid
        and producer.configuration == configuration
        and producer.outcome
        == "passed_committed_native_rust_gates_with_reused_controls"
        and producer.finished_utc is not None
        and not producer.errors
        and producer.candidate_admitted
        and producer.six_prior_semantic_controls_reused
        and producer.source_and_binary_equal_to_candidate
        and producer.immutable_closure
        and producer.all_owned_groups_absent
        and producer.locks_released
        and producer.command_journal is not None
        and not producer.repeated_allocator_probes
        and not producer.graph_or_OS_memory_qualified
        and tuple(step.name for step in producer.rust_steps) == m.RUST_NAMES,
        "closed positive committed Rust gate required",
    )
    if producer.git_before is None or producer.git_after is None:
        raise ValueError("actual committed before/after Git proof missing")
    plan = native.Plan.model_validate_json(
        config.candidate_configuration.path.read_bytes()
    )
    owner.require_git(config, producer.git_before, set(plan.source_files))
    owner.require_git(config, producer.git_after, set(plan.source_files))
    owned.require(
        producer.git_before == producer.git_after
        and producer.fd_after is not None
        and producer.fd_before is not None
        and producer.fd_after.soft == config.fd_soft
        and producer.fd_before.hard == producer.fd_after.hard,
        "source or FD boundary differs",
    )
    owned.require(
        all(
            s.waited
            and s.returncode == 0
            and s.group_absent
            and not s.forced_cleanup
            and not s.cleanup_errors
            for s in [*producer.rust_steps, *producer.metadata_steps]
        ),
        "actual command lifecycle incomplete",
    )


def run(path: Path) -> int:
    configuration = reused.pin(path)
    config = m.Config.model_validate_json(path.read_bytes())
    owner.own_identity(config, configuration)
    candidate = owner.load_candidate(config)
    destination = config.root / "wait.json"
    owned.require(
        config.root.is_dir() and not destination.exists(),
        "fresh prepared wait namespace required",
    )
    argv = [
        sys.executable,
        "-I",
        "-B",
        "-c",
        BOOT,
        str(Path(__file__).parent),
        str(candidate.helpers["allocator_owner.py"].path.parent),
        str(Path(owned.__file__).parent),
        str(Path(__file__).with_name("committed_owner.py")),
        "--config",
        str(path),
    ]
    receipt = m.Wait(configuration=configuration, supervisor_pid=os.getpid())
    reused.save(destination, receipt)
    process: subprocess.Popen[bytes] | None = None
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, owned.interrupted)
    try:
        with (config.root / "owner.log").open("xb") as log:
            process = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            receipt.owner_pid = process.pid
            reused.save(destination, receipt)
            deadline = time.monotonic() + config.total_seconds + 120
            while process.poll() is None:
                owned.check_deadline(deadline)
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
            receipt.returncode = process.wait(timeout=5)
            receipt.waited = True
        receipt.owner_group_absent = not owned.members(process.pid)
        owned.require(
            receipt.returncode == 0 and receipt.owner_group_absent,
            "actual committed owner exit/group closure differs",
        )
        producer_path = config.root / "owner-receipt.json"
        producer = m.Receipt.model_validate_json(producer_path.read_bytes())
        require_positive(config, configuration, process.pid, producer)
        owner.own_identity(config, configuration)
        owner.load_candidate(config)
        if producer.command_journal is None:
            raise ValueError("actual command journal pin missing")
        owned.require(
            reused.pin(producer.command_journal.path) == producer.command_journal,
            "closed command journal changed",
        )
        owned.require(
            all(
                not owned.members(s.pgid)
                for s in [*producer.rust_steps, *producer.metadata_steps]
            ),
            "closed command group still present",
        )
        receipt.owner_receipt = reused.pin(producer_path)
        receipt.outcome = "passed_actual_committed_owner_wait"
    except BaseException as error:  # noqa: BLE001 - errors remain errors despite a subsequent zero wait
        receipt.errors.append(repr(error))
        receipt.outcome = "error"
        try:
            if process is not None and process.poll() is None:
                receipt.forced_cleanup = True
                owned.cleanup(process.pid, process)
            if process is not None:
                receipt.returncode = process.wait(timeout=5)
                receipt.waited = True
                receipt.owner_group_absent = not owned.members(process.pid)
                journal_path = config.root / "command-journal.json"
                if not journal_path.is_file():
                    journal_path = config.root / "receipt.json"
                if journal_path.is_file():
                    journal = native.Receipt.model_validate_json(
                        journal_path.read_bytes()
                    )
                    if (
                        journal.owner_pid == process.pid
                        and journal.configuration == configuration
                    ):
                        for step in journal.steps:
                            if (
                                not step.waited or not step.group_absent
                            ) and owned.members(step.pgid):
                                owned.cleanup(step.pgid)
        except BaseException as cleanup_error:  # noqa: BLE001 - retain incomplete cleanup
            receipt.errors.append("owned cleanup: " + repr(cleanup_error))
    finally:
        receipt.finished_utc = owned.utc()
        reused.save(destination, receipt)
    return 0 if receipt.outcome == "passed_actual_committed_owner_wait" else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.config))


if __name__ == "__main__":
    main()
