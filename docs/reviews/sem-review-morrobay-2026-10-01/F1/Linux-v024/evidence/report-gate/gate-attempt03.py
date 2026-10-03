"""Exact detached F1 documentation gate over sealed portable metadata only."""

import argparse
import hashlib
import re
import stat
import subprocess
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Literal

import pydantic

SOURCE = "d2668ec7c7dbd7dd728e3976bcfaba3ae51d14ad"
TREE = "2674baf6d93109d5b6d1bf49a77a35b4bc7f115a"
TAG = "309c0ec874dc02ac3e5da0947194d563853b825e"
F1 = "docs/reviews/sem-review-morrobay-2026-10-01/F1/"
REPORT = F1 + "Linux-v024"
RUN = "/Volumes/Apo/graph-tests/results/sem-review-20261001/F1-linux-v024-run02"
SOURCES = {
    "AGENTS.md",
    "Cargo.lock",
    "Cargo.toml",
    "benchmarks/lsqb/fetch-upstream.sh",
    "scripts/ci-local.sh",
    "scripts/gate-linux-container.sh",
    "scripts/verify-package-attribution.sh",
}
STEPS = (
    "start-owned-profile",
    "pull-rust-trixie",
    "build-package-image",
    "verify-toolchain",
    "full-linux-gate",
    "stop-owned-profile",
)


class Record(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")


class Identity(Record):
    bytes: int = pydantic.Field(ge=0, le=32 * 2**20)
    sha256: str = pydantic.Field(pattern=r"^[0-9a-f]{64}$")


class Pin(Identity):
    path: str


class Plan(Record):
    parent_commit: str = pydantic.Field(pattern=r"^[0-9a-f]{40}$")
    expected_tree: str = pydantic.Field(pattern=r"^[0-9a-f]{40}$")
    files: dict[str, Identity]
    source_commit: Literal["d2668ec7c7dbd7dd728e3976bcfaba3ae51d14ad"]
    source_tree: Literal["2674baf6d93109d5b6d1bf49a77a35b4bc7f115a"]
    tag_object: Literal["309c0ec874dc02ac3e5da0947194d563853b825e"]
    source_files: dict[str, Identity]
    external_files: dict[str, Identity] = pydantic.Field(default_factory=dict)


class Inventory(Record):
    observed_utc: str
    files: dict[str, Identity]
    count: int
    total_bytes: int


class GatePlan(Record):
    observed_utc: str
    repository: Literal["querygraph/grust"]
    source_commit: Literal["d2668ec7c7dbd7dd728e3976bcfaba3ae51d14ad"]
    source_tree: Literal["2674baf6d93109d5b6d1bf49a77a35b4bc7f115a"]
    release_tag: Literal["v0.24.0"]
    release_source: Literal["1cfd03be315e9b66afb6942c7e25d9a0a951f83a"]
    superseded_requested_commit: Literal["fa49fbb79aa764b742df1334322a3244f4ef18b5"]
    gate_dir: Literal["/Users/alexy/gates-linux-f1-024-run02"]
    result_dir: Literal[
        "/Volumes/Apo/graph-tests/results/sem-review-20261001/F1-linux-v024-run02"
    ]
    profile: Literal["grust-linux-f1-024"]
    socket: Literal["unix:///Users/alexy/.colima/grust-linux-f1-024/docker.sock"]
    vm_cpus: Literal[8]
    vm_memory_gib: Literal[40]
    container_cpus: Literal[8]
    container_memory: Literal["32g"]
    build_jobs: Literal[2]
    rust_version: Literal["1.99.0"]
    production_default_config: Pin
    selected_docker_context: str
    minimum_free_host_bytes: Literal[68719476736]
    scope: str


class Step(Record):
    name: str
    argv: list[str]
    log: str
    started_utc: str
    pid: int = pydantic.Field(gt=0)
    returncode: int
    closed_utc: str


class Receipt(Record):
    observed_utc: str
    started_utc: str
    owner_pid: Literal[50030]
    plan: Pin
    source: Pin
    image_recipe: Pin
    outcome: Literal["failed"]
    active_step: None
    steps: list[Step]
    free_host_bytes: int
    base_image_digest: str
    image_id: str
    event_watcher_returncode: int
    container_inspections: list[Pin]
    exact_verdict: str
    unchanged_detached_sources: Literal[True]
    owned_profile_stopped: Literal[True]
    production_config_and_context_preserved: Literal[False]
    shared_locks_released: Literal[True]
    errors: list[str]
    scope: str


class OwnerExit(Record):
    observed_utc: str
    owner_pid: Literal[50030]
    launcher_pid: Literal[50029]
    returncode: Literal[1]
    wait_completed: Literal[True]


class Launch(Record):
    observed_utc: str
    pid: Literal[50030]
    launcher_pid: Literal[50029]
    command: list[str]
    source: Pin
    scope: str


class LauncherLaunch(Record):
    observed_utc: str
    pid: Literal[50029]
    source: Pin
    scope: str


class FailedReceipt(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="ignore")
    outcome: Literal["failed"]
    observed_utc: str
    steps: list[Step]
    exact_verdict: None
    errors: list[str]


class ManualClosure(Record):
    observed_utc: str
    outcome: Literal["failed_attempt_manually_closed"]
    gate_returncode: Literal[101]
    gate_error: Literal["Missing protobuf standard include google/protobuf/empty.proto"]
    owner_pid_absent: Literal[True]
    owned_runtime_was_empty: Literal[True]
    stop_argv: list[str]
    stop_returncode: Literal[0]
    owned_profile_stopped: Literal[True]
    production_default_config_and_context_preserved: Literal[True]
    original_failed_receipt_unchanged: Literal[True]
    event_cleanup_error_preserved: Literal["PermissionError: Operation not permitted"]


class Profile(Record):
    name: str
    status: Literal["Stopped"]
    arch: Literal["x86_64"]
    cpus: int
    memory: int
    disk: int
    runtime: Literal["docker"]


class ContextBefore(Record):
    observed_utc: str
    selected_context: Literal["default"]
    docker_config_mtime_utc: str
    default_config: Pin


class RestoreAttempt(Record):
    argv: list[str]
    returncode: Literal[1]
    log: Pin
    error: Literal["colima context not found"]


class RepairStep(Record):
    argv: list[str]
    started_utc: str
    returncode: Literal[0]
    closed_utc: str
    log: str


class SourceState(Record):
    path: str
    commit: Literal["d2668ec7c7dbd7dd728e3976bcfaba3ae51d14ad"]
    tree: Literal["2674baf6d93109d5b6d1bf49a77a35b4bc7f115a"]
    clean: Literal[True]
    detached: Literal[True]


class ContextRecovery(Record):
    observed_utc: str
    outcome: Literal[
        "functional_gate_passed_controller_context_cleanup_failed_recovered"
    ]
    original_receipt: Pin
    owner_exit: Pin
    before: ContextBefore
    profiles_before: list[Profile]
    initial_restore_attempt: RestoreAttempt
    restoration_steps: list[RepairStep]
    selected_context_after: Literal["colima"]
    restored_endpoint: Literal["unix:///Users/alexy/.colima/default/docker.sock"]
    profiles_after: list[Profile]
    owned_pids_checked: list[int]
    remaining_owned_processes: list[pydantic.JsonValue]
    sources_after: list[SourceState]
    locks_after: dict[str, bool]
    unchanged_detached_sources: Literal[True]
    owned_profile_stopped: Literal[True]
    production_config_preserved: Literal[True]
    selected_context_restored: Literal[True]
    shared_locks_released: Literal[True]
    owned_processes_absent: Literal[True]
    production_lifecycle_excerpt: Pin
    scope: str


class EventLaunch(Record):
    pid: int
    observed_utc: str
    scope: str


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def utc(text: str) -> datetime:
    value = datetime.fromisoformat(text)
    require(
        value.tzinfo is not None and value.utcoffset() == timedelta(0),
        "aware UTC stamp required",
    )
    return value


def relative(text: str) -> str:
    path = PurePosixPath(text)
    require(
        not path.is_absolute()
        and path.as_posix() == text
        and all(part not in (".", "..") for part in path.parts)
        and bool(path.parts),
        "noncanonical portable path: " + text,
    )
    return text


def read(root: Path, name: str) -> bytes:
    require(
        PurePosixPath(name).suffix
        in {
            ".md",
            ".json",
            ".jsonl",
            ".log",
            ".txt",
            ".py",
            ".sh",
            ".toml",
            ".lock",
        }
        or PurePosixPath(name).name == "Dockerfile",
        "non-metadata path refused before open",
    )
    path = root
    for part in PurePosixPath(relative(name)).parts:
        path /= part
        require(not path.is_symlink(), "symlink in metadata path: " + name)
    require(
        stat.S_ISREG(path.stat().st_mode) and path.stat().st_size <= 32 * 2**20,
        "metadata is not a bounded regular file: " + name,
    )
    return path.read_bytes()


def expected(raw: bytes, identity: Identity, name: str) -> None:
    require(
        len(raw) == identity.bytes
        and hashlib.sha256(raw).hexdigest() == identity.sha256,
        "file identity differs: " + name,
    )


def git(root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, check=True, timeout=30
    ).stdout


def alias(pin: Pin) -> str:
    prefix = RUN + "/"
    require(pin.path.startswith(prefix), "producer pin outside run02")
    return "evidence/attempt-02/" + relative(pin.path[len(prefix) :])


def evidence(root: Path, inventory: Inventory, pin: Pin) -> None:
    name = alias(pin)
    require(
        name in inventory.files
        and inventory.files[name].model_dump()
        == {"bytes": pin.bytes, "sha256": pin.sha256},
        "producer pin absent from inventory",
    )
    expected(read(root, name), pin, name)


def recovered_context(
    root: Path,
    inventory: Inventory,
    receipt: Receipt,
    waited: OwnerExit,
    configuration: GatePlan,
) -> datetime:
    prefix = "evidence/attempt-02/"
    recovery = ContextRecovery.model_validate_json(
        read(root, prefix + "manual-closure02.json")
    )
    for pin in (
        recovery.original_receipt,
        recovery.owner_exit,
        recovery.initial_restore_attempt.log,
        recovery.production_lifecycle_excerpt,
    ):
        evidence(root, inventory, pin)
    require(
        recovery.original_receipt.path == RUN + "/receipt.json"
        and recovery.owner_exit.path == RUN + "/owner-exit01.json"
        and recovery.initial_restore_attempt.log.path
        == RUN + "/manual-context-restore02.log"
        and recovery.production_lifecycle_excerpt.path
        == RUN + "/production-lifecycle-excerpt02.log"
        and recovery.before.default_config == configuration.production_default_config
        and configuration.selected_docker_context == "colima",
        "recovery evidence/default configuration binding differs",
    )
    require(
        recovery.initial_restore_attempt.argv == ["docker", "context", "use", "colima"]
        and len(recovery.restoration_steps) == 2,
        "failed initial recovery or repair count differs",
    )
    commands = (
        [
            "docker",
            "context",
            "create",
            "colima",
            "--docker",
            "host=unix:///Users/alexy/.colima/default/docker.sock",
        ],
        ["docker", "context", "use", "colima"],
    )
    after = utc(recovery.observed_utc)
    before = utc(recovery.before.observed_utc)
    require(
        utc(waited.observed_utc) <= before <= after
        and utc(recovery.before.docker_config_mtime_utc) <= before,
        "recovery observation order differs",
    )
    last = before
    for number, (step, command) in enumerate(
        zip(recovery.restoration_steps, commands, strict=True), 1
    ):
        require(
            step.argv == command
            and step.log == RUN + f"/manual-context-repair02-step{number}.log"
            and last <= utc(step.started_utc) <= utc(step.closed_utc) <= after,
            "context-only repair command/order differs",
        )
        read(root, prefix + f"manual-context-repair02-step{number}.log")
        last = utc(step.closed_utc)
    require(
        recovery.profiles_before == recovery.profiles_after
        and len(recovery.profiles_after) == 2
        and {
            row.name: (row.cpus, row.memory, row.disk)
            for row in recovery.profiles_after
        }
        == {
            "default": (4, 32 * 2**30, 220 * 2**30),
            "grust-linux-f1-024": (8, 40 * 2**30, 60 * 2**30),
        },
        "stopped profile identity/settings differ",
    )
    event = EventLaunch.model_validate_json(read(root, prefix + "event-launch.json"))
    pids = {50029, 50030, event.pid, *(step.pid for step in receipt.steps)}
    require(
        set(recovery.owned_pids_checked) == pids
        and len(recovery.owned_pids_checked) == len(pids)
        and not recovery.remaining_owned_processes,
        "owned process closure evidence differs",
    )
    require(
        len(recovery.sources_after) == 2
        and {source.path for source in recovery.sources_after}
        == {configuration.gate_dir + "/driver", configuration.gate_dir + "/" + SOURCE}
        and recovery.locks_after
        == {
            RUN.rsplit("/", 1)[0] + "/gate.lock": False,
            RUN.rsplit("/", 1)[0] + "/serial-queue.lock": False,
        },
        "final source or shared lock closure differs",
    )
    return after


def closed_run(root: Path, inventory: Inventory, plan: Plan) -> tuple[str, datetime]:
    prefix = "evidence/attempt-02/"
    receipt = Receipt.model_validate_json(read(root, prefix + "receipt.json"))
    waited = OwnerExit.model_validate_json(read(root, prefix + "owner-exit01.json"))
    launch = Launch.model_validate_json(read(root, prefix + "launch01.json"))
    launcher = LauncherLaunch.model_validate_json(
        read(root, prefix + "launcher-launch01.json")
    )
    require(
        receipt.errors == ["cleanup ValueError: production Docker context changed"]
        and tuple(step.name for step in receipt.steps) == STEPS,
        "unexpected failure/incomplete full-gate receipt",
    )
    for pin in (
        receipt.plan,
        receipt.source,
        receipt.image_recipe,
        launch.source,
        launcher.source,
        *receipt.container_inspections,
    ):
        evidence(root, inventory, pin)
    require(
        receipt.source == launch.source
        and receipt.source.path == RUN + "/gate_owner.py"
        and launcher.source.path == RUN + "/gate_launcher.py"
        and receipt.plan.path == RUN + "/plan.json"
        and receipt.image_recipe.path == RUN + "/image/Dockerfile",
        "owner source/config binding differs",
    )
    configuration = GatePlan.model_validate_json(read(root, prefix + "plan.json"))
    require(
        utc(configuration.observed_utc) <= utc(launch.observed_utc),
        "plan timestamp after launch",
    )
    require(
        launch.command[-2:] == ["--plan", RUN + "/plan.json"]
        and RUN in launch.command
        and "--fast" not in launch.command,
        "owner launch differs",
    )
    start = utc(receipt.started_utc)
    finish = utc(receipt.observed_utc)
    require(
        utc(launcher.observed_utc)
        <= utc(launch.observed_utc)
        <= start
        <= finish
        <= utc(waited.observed_utc),
        "owner/launcher timestamp order differs",
    )
    for number, step in enumerate(receipt.steps, 1):
        require(
            step.returncode == 0
            and "--fast" not in step.argv
            and step.log == RUN + f"/{number:02d}-{step.name}.log"
            and start <= utc(step.started_utc) <= utc(step.closed_utc) <= finish,
            "failed or incomplete full-gate step",
        )
        read(root, prefix + relative(step.log.removeprefix(RUN + "/")))
    full = receipt.steps[4]
    require(
        full.argv
        == [
            "bash",
            "/Users/alexy/gates-linux-f1-024-run02/driver/scripts/gate-linux-container.sh",
            SOURCE,
        ],
        "full unmodified release gate command differs",
    )
    require(
        receipt.steps[5].argv == ["colima", "stop", "--profile", "grust-linux-f1-024"],
        "owned-profile shutdown command differs",
    )
    log = read(root, prefix + "05-full-linux-gate.log").decode()
    verdicts = [
        line for line in log.splitlines() if line.startswith("ci-local: PASSED")
    ]
    require(
        verdicts == [receipt.exact_verdict]
        and receipt.exact_verdict
        == "ci-local: PASSED every gate at d2668ec on Linux x86_64 in 3904s",
        "exact clean full Linux verdict missing or duplicated",
    )
    require(
        bool(receipt.container_inspections),
        "actual container resource evidence missing",
    )
    require(set(plan.source_files) == SOURCES, "source contract file set differs")
    for name, identity in plan.source_files.items():
        expected(read(root, prefix + "source/" + name), identity, name)
    return receipt.exact_verdict, recovered_context(
        root, inventory, receipt, waited, configuration
    )


def validate(worktree: Path, commit: str, plan_file: Path) -> None:
    sealed = plan_file.read_bytes()
    plan = Plan.model_validate_json(sealed)
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "exact commit required")
    require(
        "codex-to-codex.md" in plan.files
        and REPORT + "/README.md" in plan.files
        and REPORT + "/inventory.json" in plan.files,
        "documentation proof files missing",
    )
    require(
        all(
            name == "codex-to-codex.md" or relative(name).startswith(F1)
            for name in plan.files
        ),
        "publication path outside F1 documentation",
    )
    for _ in range(2):
        require(
            git(worktree, "rev-parse", "HEAD").decode().strip() == commit
            and git(worktree, "rev-parse", "HEAD^{tree}").decode().strip()
            == plan.expected_tree
            and git(worktree, "rev-parse", "HEAD^").decode().strip()
            == plan.parent_commit
            and not git(worktree, "status", "--porcelain"),
            "exact clean documentation revision differs",
        )
        branch = subprocess.run(
            ["git", "-C", str(worktree), "symbolic-ref", "-q", "HEAD"],
            capture_output=True,
            timeout=30,
            check=False,
        )
        require(branch.returncode == 1, "documentation worktree is not detached")
        changed = git(
            worktree, "diff-tree", "--no-commit-id", "--name-only", "-r", commit
        )
        require(
            set(changed.decode().splitlines()) == set(plan.files),
            "publication path set differs",
        )
        git(worktree, "diff", "--check", plan.parent_commit, commit)
        for name, identity in plan.files.items():
            raw = read(worktree, name)
            expected(raw, identity, name)
            require(
                not re.search(rb"^(<<<<<<<|=======|>>>>>>>)( |$)", raw, re.MULTILINE),
                "conflict marker in publication",
            )
        root = worktree / REPORT
        inventory = Inventory.model_validate_json(read(root, "inventory.json"))
        utc(inventory.observed_utc)
        paths = list(root.rglob("*"))
        require(
            len(paths) <= 4096 and not any(path.is_symlink() for path in paths),
            "unbounded or symlink portable inventory",
        )
        actual = {
            path.relative_to(root).as_posix() for path in paths if not path.is_dir()
        }
        require(
            actual == set(inventory.files) | {"inventory.json", "README.md"}
            and {REPORT + "/" + name for name in actual} <= set(plan.files)
            and inventory.count == len(inventory.files)
            and inventory.total_bytes
            == sum(item.bytes for item in inventory.files.values())
            <= 256 * 2**20,
            "portable inventory set/totals differ",
        )
        require(
            {
                "evidence/attempt-01/" + name
                for name in (
                    "receipt.json",
                    "05-full-linux-gate.log",
                    "failure-traceback.txt",
                    "manual-closure01.json",
                    "manual-stop01.log",
                )
            }
            <= set(inventory.files),
            "failed attempt01 evidence missing",
        )
        for name, identity in inventory.files.items():
            expected(read(root, name), identity, name)
        failed = FailedReceipt.model_validate_json(
            read(root, "evidence/attempt-01/receipt.json")
        )
        manual = ManualClosure.model_validate_json(
            read(root, "evidence/attempt-01/manual-closure01.json")
        )
        failures = [step for step in failed.steps if step.name == "full-linux-gate"]
        require(
            len(failures) == 1
            and failures[0].returncode == 101
            and "ValueError: full-linux-gate failed rc=101" in failed.errors
            and "cleanup PermissionError: [Errno 1] Operation not permitted"
            in failed.errors
            and utc(failed.observed_utc) <= utc(manual.observed_utc)
            and manual.stop_argv
            == ["colima", "stop", "--profile", "grust-linux-f1-024"],
            "failed gate/manual closure history differs",
        )
        verdict, ended = closed_run(root, inventory, plan)
        old = git(worktree, "show", plan.parent_commit + ":codex-to-codex.md")
        current = read(worktree, "codex-to-codex.md")
        require(current.startswith(old), "coordination history prefix changed")
        append = current[len(old) :].decode()
        require(
            len(re.findall(r"\b(?:F1 DONE|DONE F1)\b", append)) == 1
            and append.count(verdict) == 1
            and "F1/Linux-v024/README.md" in append,
            "F1 DONE exact evidence/verdict missing",
        )
        stamps = re.findall(r"^## ([^ ]+) —", append, re.MULTILINE)
        require(
            len(stamps) == 1 and utc(stamps[0]) >= ended,
            "F1 DONE observed UTC stamp differs",
        )
        require(
            git(worktree, "rev-parse", "v0.24.0").decode().strip() == TAG
            and git(worktree, "rev-parse", "v0.24.0^{}").decode().strip() == SOURCE
            and git(worktree, "rev-parse", SOURCE + "^{tree}").decode().strip() == TREE,
            "release source/tag/tree differs",
        )
        for name, identity in plan.source_files.items():
            expected(git(worktree, "show", SOURCE + ":" + name), identity, name)
        for name, identity in plan.external_files.items():
            path = Path(name)
            require(
                path.is_absolute() and not path.is_symlink(),
                "external proof path differs",
            )
            expected(read(path.parent, path.name), identity, name)
        text = read(root, "README.md").decode()
        require(
            text.count(verdict) == 1 and SOURCE in text and TREE in text,
            "README released source/exact verdict missing",
        )
        require(
            "cleanup ValueError: production Docker context changed" in text
            and "cleanup ValueError: production Docker context changed" in append,
            "original controller context cleanup failure disclosure missing",
        )
        for target in re.findall(r"\]\(([^)]+)\)", text):
            if not target.startswith(("https:", "http:", "#")):
                path = (root / target.split("#", 1)[0]).resolve()
                require(
                    not target.startswith("/")
                    and path.is_file()
                    and path.is_relative_to(worktree.resolve()),
                    "README local link missing",
                )
        require(plan_file.read_bytes() == sealed, "documentation gate plan changed")
    print("F1_V024_FINAL_DOCUMENTATION PASSED " + commit)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worktree", required=True, type=Path)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--plan", required=True, type=Path)
    args = parser.parse_args()
    validate(args.worktree, args.expected_commit, args.plan)


if __name__ == "__main__":
    main()
