"""Root-only committed Rust gate; no rerun of previously closed allocator probes."""

import argparse
import json
import os
import platform
import resource
import signal
import time
import uuid
from pathlib import Path

import allocator_models as native
import allocator_owner as reused
import committed_models as m
import gate_owner as owned


def rust_commands(plan: native.Plan) -> list[tuple[str, list[str]]]:
    cargo = str(plan.tools["cargo"].path)
    return [
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


def check_candidate(
    config: m.Config, producer: m.Candidate, waited: m.CandidateWait, plan: native.Plan
) -> None:
    """Pure admission: a completed name alone cannot stand in for controls/waits."""
    owned.require(
        producer.outcome == "passed_native_factory_allocation_controls"
        and not producer.errors
        and producer.finished_utc is not None
        and producer.immutable_source_tool_helper_closure
        and producer.all_owned_groups_absent
        and producer.locks_released,
        "complete immutable candidate controls required",
    )
    owned.require(
        waited.outcome == "passed_waited_native_factory_controls"
        and not waited.errors
        and waited.returncode == 0
        and waited.waited
        and waited.owner_group_absent
        and not waited.forced_cleanup
        and waited.finished_utc is not None
        and waited.owner_pid == producer.owner_pid
        and waited.configuration
        == producer.configuration
        == config.candidate_configuration
        and waited.owner_receipt == config.candidate_receipt,
        "candidate actual owner wait differs",
    )
    owned.require(
        plan.root == config.candidate_receipt.path.parent
        and plan.source == config.repository / config.source_prefix
        and len(plan.source_files) == 8
        and producer.binary == config.candidate_binary,
        "candidate source/artifact attempt differs",
    )
    owned.require(
        tuple(step.name for step in producer.steps) == (*m.RUST_NAMES, *m.PROBE_NAMES),
        "six gates and six complete controls required",
    )
    owned.require(
        all(
            step.returncode == 0
            and step.waited
            and step.group_absent
            and not step.forced_cleanup
            and not step.cleanup_errors
            and step.log is not None
            and step.finished_utc is not None
            for step in producer.steps
        ),
        "candidate control lifecycle unqualified",
    )
    owned.require(
        [step.argv for step in producer.steps[:6]]
        == [argv for _, argv in rust_commands(plan)],
        "candidate exact locked Rust command/profile boundary differs",
    )
    for step, (groups, method) in zip(producer.steps[6:], m.PROBES, strict=True):
        owned.require(
            step.argv == [str(config.candidate_binary.path), str(groups), method],
            "candidate probe binary/arguments differ",
        )


def load_candidate(config: m.Config) -> native.Plan:
    for expected in (
        config.candidate_configuration,
        config.candidate_receipt,
        config.candidate_launch,
        config.candidate_binary,
        config.reused_owner_freeze,
    ):
        owned.require(
            reused.pin(expected.path) == expected,
            "candidate or reused owner pin differs",
        )
    producer = m.Candidate.model_validate_json(
        config.candidate_receipt.path.read_bytes()
    )
    waited = m.CandidateWait.model_validate_json(
        config.candidate_launch.path.read_bytes()
    )
    plan = native.Plan.model_validate_json(
        config.candidate_configuration.path.read_bytes()
    )
    check_candidate(config, producer, waited, plan)
    reused.immutable(plan, config.candidate_configuration)
    frozen = json.loads(config.reused_owner_freeze.path.read_bytes())
    for name, expected in plan.helpers.items():
        original = frozen["files"][name]
        owned.require(
            expected.model_dump(mode="json") == original,
            "reused ownership helper origin differs from freeze",
        )
    for step in producer.steps:
        if step.log is None:
            raise ValueError("closed candidate log missing")
        owned.require(
            reused.pin(step.log.path) == step.log, "closed candidate log changed"
        )
        owned.require(
            not owned.members(step.pgid), "candidate command group still present"
        )
    owned.require(
        not owned.members(producer.owner_pid)
        and not owned.members(waited.launcher_pid),
        "candidate owner/supervisor still present",
    )
    for step, (groups, method) in zip(producer.steps[6:], m.PROBES, strict=True):
        if step.log is None:
            raise ValueError("full prior semantic-control log missing")
        reused.qualify_probe(step.log.path, groups, method)
    return plan


def own_identity(config: m.Config, configuration: native.Pin) -> None:
    owned.require(
        reused.pin(configuration.path) == configuration, "configuration changed"
    )
    for name, expected in config.helpers.items():
        owned.require(
            expected.path == Path(__file__).parent / name
            and reused.pin(expected.path) == expected,
            "new helper source/origin differs",
        )
    owned.require(
        Path(m.__file__) == config.helpers["committed_models.py"].path,
        "new typed model import differs",
    )


def fd_limit() -> tuple[m.Limits, m.Limits]:
    """Set the requested soft limit while retaining the existing hard ceiling."""
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    owned.require(
        hard == resource.RLIM_INFINITY or hard >= 8192, "FD hard ceiling below8192"
    )
    resource.setrlimit(resource.RLIMIT_NOFILE, (8192, hard))
    after = resource.getrlimit(resource.RLIMIT_NOFILE)
    owned.require(after == (8192, hard), "FD limit or hard ceiling differs")
    return m.Limits(soft=soft, hard=hard), m.Limits(soft=after[0], hard=after[1])


def require_git(config: m.Config, proof: m.GitProof, source_names: set[str]) -> None:
    expected = {config.source_prefix + "/" + name for name in source_names}
    owned.require(
        proof.head == config.commit
        and proof.tree == config.tree
        and proof.detached
        and not proof.status
        and set(proof.tracked) == expected
        and len(proof.tracked) == len(expected) == 8,
        "clean detached exact committed eight-file source required",
    )


def git_snapshot(
    config: m.Config,
    plan: native.Plan,
    journal: native.Receipt,
    label: str,
    deadline: float,
) -> m.GitProof:
    queries = {
        "head": ["rev-parse", "HEAD"],
        "tree": ["rev-parse", "HEAD^{tree}"],
        "detached": ["rev-parse", "--abbrev-ref", "HEAD"],
        "status": [
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignored=matching",
        ],
        "tracked": ["ls-files"],
    }
    values: dict[str, str] = {}
    for key, args in queries.items():
        step = reused.step(
            plan,
            journal,
            f"git-{label}-{key}",
            ["/usr/bin/git", "-C", str(config.repository), *args],
            deadline,
            30,
        )
        if step.log is None:
            raise ValueError("Git inspection log missing")
        owned.require(step.log.bytes < 1024**2, "Git metadata inspection exceeds bound")
        values[key] = step.log.path.read_text().strip()
    proof = m.GitProof(
        head=values["head"],
        tree=values["tree"],
        detached=values["detached"] == "HEAD",
        status=values["status"],
        tracked=values["tracked"].splitlines(),
    )
    require_git(config, proof, set(plan.source_files))
    return proof


def run(path: Path) -> int:
    configuration = reused.pin(path)
    config = m.Config.model_validate_json(path.read_bytes())
    startup = {
        "owner.log",
        "wait.json",
        "wait.json.writing",
        "launcher.log",
        "supervisor-launch.json",
    }
    owned.require(
        config.root.is_dir()
        and not config.root.is_symlink()
        and all(
            p.name in startup and not p.is_symlink() and (not p.exists() or p.is_file())
            for p in config.root.iterdir()
        ),
        "fresh prepared result directory required",
    )
    receipt = m.Receipt(
        owner_pid=os.getpid(),
        owner_token=uuid.uuid4().hex,
        configuration=configuration,
        started_utc=owned.utc(),
    )
    destination = config.root / "owner-receipt.json"
    reused.save(destination, receipt)
    journal = native.Receipt(
        owner_pid=receipt.owner_pid,
        owner_token=receipt.owner_token,
        configuration=configuration,
        started_utc=receipt.started_utc,
        scope="Committed Rust command journal only; allocator controls are referenced from a separate closed candidate",
    )
    locks: list[Path] = []
    deadline = time.monotonic() + config.total_seconds
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, owned.interrupted)
    try:
        owned.require(
            platform.system() == "Darwin" and platform.machine() == "x86_64",
            "native x86_64 macOS required",
        )
        owned.require(
            not any(name.startswith("GIT_") for name in os.environ),
            "Git environment overrides are not admitted",
        )
        own_identity(config, configuration)
        original = load_candidate(config)
        receipt.candidate_admitted = receipt.six_prior_semantic_controls_reused = True
        runtime = original.model_dump(mode="json")
        runtime.update(
            root=str(config.root),
            total_seconds=config.total_seconds,
            step_seconds=config.step_seconds,
        )
        plan = native.Plan.model_validate_json(json.dumps(runtime))
        receipt.fd_before, receipt.fd_after = fd_limit()
        for name in ("gate.lock", "serial-queue.lock"):
            lock = reused.BASE / name
            lock.mkdir()
            locks.append(lock)
            reused.save(lock / "owner.json", receipt)
        (config.root / "tmp").mkdir()
        receipt.git_before = git_snapshot(config, plan, journal, "before", deadline)
        for name, argv in rust_commands(plan):
            step = reused.step(plan, journal, name, argv, deadline, config.step_seconds)
            receipt.rust_steps.append(step)
            if name == "rustc-version":
                if step.log is None:
                    raise ValueError("actual compiler observation missing")
                version = step.log.path.read_text()
                owned.require(
                    "release: 1.97.1" in version
                    and "host: x86_64-apple-darwin" in version,
                    "native compiler observation differs",
                )
            reused.save(destination, receipt)
        receipt.git_after = git_snapshot(config, plan, journal, "after", deadline)
        own_identity(config, configuration)
        load_candidate(config)
        receipt.source_and_binary_equal_to_candidate = True
        owned.check_deadline(deadline)
        receipt.immutable_closure = receipt.git_before == receipt.git_after
        receipt.all_owned_groups_absent = all(
            s.waited
            and s.group_absent
            and not s.forced_cleanup
            and not s.cleanup_errors
            and not owned.members(s.pgid)
            for s in journal.steps
        )
        owned.require(
            receipt.immutable_closure and receipt.all_owned_groups_absent,
            "committed gate immutable/lifecycle closure incomplete",
        )
        for lock in reversed(locks):
            marker = m.Receipt.model_validate_json((lock / "owner.json").read_bytes())
            owned.require(
                marker.owner_pid == receipt.owner_pid
                and marker.owner_token == receipt.owner_token
                and marker.configuration == configuration,
                "lock owner differs; preserve",
            )
        for lock in reversed(locks):
            (lock / "owner.json").unlink()
            lock.rmdir()
        receipt.locks_released = True
        receipt.outcome = "passed_committed_native_rust_gates_with_reused_controls"
    except BaseException as error:  # noqa: BLE001 - every failure remains failed with owned locks retained
        receipt.errors.append(repr(error))
        receipt.outcome = "error"
    finally:
        receipt.metadata_steps = [s for s in journal.steps if s.name.startswith("git-")]
        # Include an interrupted Rust step even if reused.step raised before returning.
        receipt.rust_steps = [s for s in journal.steps if s.name in m.RUST_NAMES]
        journal.finished_utc = owned.utc()
        reused.save(config.root / "command-journal.json", journal)
        receipt.command_journal = reused.pin(config.root / "command-journal.json")
        receipt.finished_utc = owned.utc()
        reused.save(destination, receipt)
    return (
        0
        if receipt.outcome == "passed_committed_native_rust_gates_with_reused_controls"
        else 1
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.config))


if __name__ == "__main__":
    main()
