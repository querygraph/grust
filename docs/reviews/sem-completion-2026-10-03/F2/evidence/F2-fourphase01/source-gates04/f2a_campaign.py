"""Serial four-phase Arrow bridge owner; full output qualification remains external."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import signal
import subprocess
import threading
import time
from itertools import pairwise
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

import f2a_models as models

BASE = Path("/Volumes/Apo/graph-tests/results/sem-completion-20261003")
LOCK_BASE = Path("/Volumes/Apo/graph-tests/results/sem-review-20261001")
BOOT = 'import runpy,sys;r=sys.argv[1];sys.path.insert(0,r);sys.argv=[r+"/f2a_worker.py"]+sys.argv[2:];runpy.run_path(sys.argv[0],run_name="__main__")'


class Config(models.Record):
    root: Path
    worker: Path
    python: Path
    repo: Path
    tree: str = Field(pattern=r"^[0-9a-f]{40}$")
    plans: list[Path] = Field(min_length=1, max_length=4)
    expected_plans: list[models.FilePin]
    expected_source: list[models.FilePin]
    expected_helpers: list[models.FilePin]
    expected_inputs: list[models.FilePin]
    expected_client: list[models.FilePin]
    binary: models.FilePin
    wheel: models.FilePin
    timeout_seconds: int = Field(ge=300, le=21600)
    series_seconds: int = Field(default=2050, ge=2010, le=2400)
    minimum_free_bytes: int = Field(default=68719476736, ge=68719476736)

    @model_validator(mode="after")
    def paths(self) -> Self:
        pins = self.pins()
        for path in (
            self.root,
            self.worker,
            self.python,
            self.repo,
            *self.plans,
            *(p.path for p in pins),
        ):
            if not path.is_absolute() or ".." in path.parts:
                raise ValueError("absolute paths without parent traversal required")
        if (
            not self.root.is_relative_to(BASE)
            or self.root == BASE
            or self.root == self.worker.parent
            or self.worker.is_relative_to(self.root)
        ):
            raise ValueError(
                "fresh campaign metadata namespace under sem-completion BASE required"
            )
        if len(self.plans) not in (1, 4) or len(set(self.plans)) != len(self.plans):
            raise ValueError("one smoke plan or four distinct main plans required")
        if {p.path for p in self.expected_plans} != set(self.plans):
            raise ValueError("every plan must have exactly one admitted pin")
        if len({p.path for p in pins}) != len(pins):
            raise ValueError("pin paths must be unique across declared categories")
        for category in (
            self.expected_source,
            self.expected_helpers,
            self.expected_inputs,
            self.expected_client,
        ):
            if not category:
                raise ValueError(
                    "source/helper/input/client categories must be nonempty"
                )
        return self

    def pins(self) -> list[models.FilePin]:
        return [
            *self.expected_plans,
            *self.expected_source,
            *self.expected_helpers,
            *self.expected_inputs,
            *self.expected_client,
            self.binary,
            self.wheel,
        ]


class Series(models.Record):
    plan: models.FilePin
    argv: list[str]
    outcome: Literal["running", "completed_unvalidated", "error"] = "running"
    launched_utc: str
    closed_utc: str | None = None
    pid: int
    pgid: int
    wait_completed: bool = False
    returncode: int | None = None
    launch_to_wait: models.Span | None = None
    driver_group_absent: bool = False
    server_group_absent: bool = False
    server_pid: int | None = None
    server_pgid: int | None = None
    worker_receipt: models.FilePin | None = None
    forced_cleanup: bool = False
    rss_samples: int = 0
    observed_worker_peak_rss_kib: int | None = None
    observed_server_peak_rss_kib: int | None = None
    rss_errors: list[str] = Field(default_factory=list)
    rss_sampler_closed: bool = False
    rss_file: models.FilePin | None = None


class Receipt(models.Record):
    outcome: Literal["running", "completed_unvalidated_campaign", "error"] = "running"
    started_utc: str
    finished_utc: str | None = None
    owner_pid: int
    configuration: models.FilePin
    series: list[Series] = Field(default_factory=list)
    skipped_plans: list[Path] = Field(default_factory=list)
    before: list[models.FilePin] = Field(default_factory=list)
    after: list[models.FilePin] = Field(default_factory=list)
    source_before: dict[str, str] = Field(default_factory=dict)
    source_after: dict[str, str] = Field(default_factory=dict)
    all_owned_groups_absent: bool = False
    locks_released: bool = False
    errors: list[str] = Field(default_factory=list)
    scope: str = "Serial unvalidated materialized Arrow bridge WCC execution; full original-domain/partition oracles and raw-output retention qualification are external. Parent launch_to_wait includes interpreter/setup/diagnostics/cleanup. Worker pipeline has its separately declared boundary. RSS is 500ms observed native/driver RSS, not an OS peak, limit or allocation proof."


def utc() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def pin(path: Path) -> models.FilePin:
    require(
        path.is_file() and not path.is_symlink(),
        f"regular immutable file required: {path}",
    )
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return models.FilePin(path=path, bytes=size, sha256=digest.hexdigest())


def save(path: Path, value: models.Record) -> None:
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("w") as stream:
        stream.write(value.model_dump_json(indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def source(config: Config) -> dict[str, str]:
    commands = {
        "head": ["rev-parse", "HEAD"],
        "tree": ["rev-parse", "HEAD^{tree}"],
        "status": ["status", "--porcelain", "--untracked-files=all"],
        "branch": ["symbolic-ref", "-q", "HEAD"],
    }
    result: dict[str, str] = {}
    for key, arguments in commands.items():
        observed = subprocess.run(
            ["git", "-C", str(config.repo), *arguments],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        require(
            observed.returncode == (1 if key == "branch" else 0),
            "clean detached source observation failed",
        )
        result[key] = observed.stdout.strip()
    require(
        result
        == {
            "head": models.EXTENSION_SOURCE,
            "tree": config.tree,
            "status": "",
            "branch": "",
        },
        "exact clean detached source required",
    )
    return result


def members(pgid: int) -> list[int]:
    observed = subprocess.run(
        ["/bin/ps", "-axo", "pid=,pgid="],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    require(observed.returncode == 0, "process group observation failed")
    return [
        int(row.split()[0])
        for row in observed.stdout.splitlines()
        if len(row.split()) == 2 and int(row.split()[1]) == pgid
    ]


def admitted(config: Config) -> list[models.Plan]:
    helpers = {p.path for p in config.expected_helpers}
    own = Path(__file__).resolve()
    require(
        {
            own,
            own.with_name("f2a_campaign_launch.py"),
            config.worker,
            config.worker.with_name("f2a_models.py"),
        }
        <= helpers,
        "all owner/launcher/worker/model helpers must be pinned",
    )
    require(
        config.worker.name == "f2a_worker.py"
        and Path(models.__file__).resolve() == config.worker.with_name("f2a_models.py"),
        "actual imported worker models must have the pinned origin",
    )
    plans = [
        models.Plan.model_validate_json(path.read_bytes()) for path in config.plans
    ]
    inputs = {p.path for p in config.expected_inputs}
    client = {p.path for p in config.expected_client}
    require(
        config.python.resolve() in client,
        "actual Python executable must be client-pinned",
    )
    outputs: set[Path] = set()
    receipts: set[Path] = set()
    for plan in plans:
        require(
            {plan.vertices, plan.edges} <= inputs and plan.binary == config.binary.path,
            "original inputs/binary must match admitted pins",
        )
        require(
            config.python == plan.venv / "bin/python",
            "one admitted new extension venv required",
        )
        require(
            {
                plan.python_purelib / "pyspark/sql/connect/plan.py",
                plan.python_purelib / "pyspark/sql/connect/session.py",
            }
            <= client,
            "source-pinned client plan/cache/session modules required",
        )
        require(
            not plan.output_root.exists() and not plan.receipt.exists(),
            "fresh series output and receipt required",
        )
        require(
            (
                plan.receipt.is_relative_to(config.root)
                or plan.receipt.parent == config.worker.parent / "series"
            )
            and plan.receipt != config.root / "receipt.json",
            "series receipt must belong to declared campaign or worker series namespace",
        )
        require(
            plan.output_root not in outputs and plan.receipt not in receipts,
            "series paths cannot be reused",
        )
        outputs.add(plan.output_root)
        receipts.add(plan.receipt)
        parent = next(p for p in plan.output_root.parents if p.exists())
        require(
            shutil.disk_usage(parent).free >= config.minimum_free_bytes,
            "64GiB timed-output disk reserve required",
        )
    if len(plans) == 4:
        require(
            {(p.dataset, p.ids, p.calls) for p in plans}
            == {
                (d, ids, n)
                for d in ("cit-Patents", "graph500-24")
                for ids in ("int64",)
                for n in (1, 3)
            },
            "main bridge campaign needs both datasets at one and three calls",
        )
    else:
        require(
            plans[0].dataset == "tiny"
            and plans[0].calls == 3
            and plans[0].chunk_rows == 2,
            "one-plan campaign is the three-call, two-row-chunk tiny qualification",
        )
    return plans


class Sampler:
    def __init__(self, series: Series, receipt_path: Path, destination: Path) -> None:
        self.series, self.receipt_path, self.destination = (
            series,
            receipt_path,
            destination,
        )
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self) -> None:
        try:
            with self.destination.open("x") as log:
                while not self.stop.is_set():
                    try:
                        server: int | None = None
                        if (
                            self.receipt_path.is_file()
                            and self.receipt_path.stat().st_size
                        ):
                            observed = models.Receipt.model_validate_json(
                                self.receipt_path.read_bytes()
                            )
                            require(
                                observed.owner_pid == self.series.pid,
                                "sampler refuses foreign worker receipt",
                            )
                            server = observed.server.pid if observed.server else None
                        pids = [self.series.pid, *([server] if server else [])]
                        rows = subprocess.run(
                            [
                                "/bin/ps",
                                "-o",
                                "pid=,rss=",
                                "-p",
                                ",".join(map(str, pids)),
                            ],
                            capture_output=True,
                            text=True,
                            timeout=2,
                            check=False,
                        )
                        require(
                            rows.returncode in (0, 1) and not rows.stderr.strip(),
                            "RSS observation failed",
                        )
                        rss = {
                            int(a): int(b)
                            for a, b in (
                                row.split() for row in rows.stdout.splitlines()
                            )
                        }
                        log.write(
                            json.dumps(
                                {
                                    "observed_utc": utc(),
                                    "monotonic_ns": time.monotonic_ns(),
                                    "worker_pid": self.series.pid,
                                    "server_pid": server,
                                    "rss_kib": rss,
                                }
                            )
                            + "\n"
                        )
                        log.flush()
                        self.series.rss_samples += 1
                        for pid, field in (
                            (self.series.pid, "observed_worker_peak_rss_kib"),
                            (server, "observed_server_peak_rss_kib"),
                        ):
                            if pid in rss:
                                current = getattr(self.series, field)
                                setattr(self.series, field, max(current or 0, rss[pid]))
                    except Exception as error:  # noqa: BLE001 - RSS observations remain explicitly unavailable on error.
                        self.series.rss_errors.append(
                            f"{type(error).__name__}: {error}"
                        )
                    self.stop.wait(0.5)
                os.fsync(log.fileno())
        except Exception as error:  # noqa: BLE001 - retain sampler startup/fsync failures explicitly.
            self.series.rss_errors.append(f"{type(error).__name__}: {error}")
        finally:
            self.series.rss_sampler_closed = True


def accept(config: Config, plan: models.Plan, series: Series) -> None:
    result = models.Receipt.model_validate_json(plan.receipt.read_bytes())
    require(
        series.returncode == 0 and series.wait_completed and not series.forced_cleanup,
        "worker did not naturally complete",
    )
    require(
        result.owner_pid == series.pid
        and result.configuration == plan
        and result.configuration_pin == series.plan,
        "worker/configuration binding failed",
    )
    by_path = {p.path: p for p in config.expected_helpers}
    client_by_path = {p.path: p for p in config.expected_client}
    require(
        result.pyspark_version == "4.0.1"
        and result.client_plan_source
        == client_by_path[plan.python_purelib / "pyspark/sql/connect/plan.py"]
        and result.client_session_source
        == client_by_path[plan.python_purelib / "pyspark/sql/connect/session.py"],
        "actual loaded 4.0.1 client source/cache contract differs from admission",
    )
    require(
        result.worker_source == by_path[config.worker]
        and result.models_source == by_path[config.worker.with_name("f2a_models.py")],
        "worker source binding failed",
    )
    require(
        result.outcome == "completed_unvalidated"
        and result.execution_profile == "materialized_arrow_client_four_phase"
        and not result.errors
        and result.pipeline_completed
        and result.projection_reused is True
        and result.graph_dropped
        and result.spark_stopped,
        "worker execution/cache/cleanup failed",
    )
    require(
        result.pipeline is not None
        and result.pipeline_seconds == result.pipeline.seconds
        and result.pipeline_seconds > 0,
        "continuous pipeline clock missing",
    )
    require(
        len(result.phases) == 4
        and [phase.name for phase in result.phases]
        == ["read_parquet", "csr_and_graph", "algorithm_materialize", "write_parquet"]
        and all(phase.completed and phase.call is None for phase in result.phases),
        "four sequential materialized bridge phases missing",
    )
    spans = [phase.span for phase in result.phases]
    require(
        result.pipeline is not None
        and result.pipeline.started_ns <= spans[0].started_ns
        and all(
            first.ended_ns <= second.started_ns for first, second in pairwise(spans)
        )
        and result.pipeline.ended_ns == spans[-1].ended_ns,
        "bridge phase boundaries overlap or exceed the continuous clock",
    )
    exclusive = result.exclusive_sem_phases
    require(
        exclusive.availability == "observed_materialized_arrow_bridge"
        and [
            exclusive.read_seconds,
            exclusive.csr_and_graph_build_seconds,
            exclusive.algorithm_seconds,
            exclusive.write_seconds,
        ]
        == [span.seconds for span in spans],
        "reported materialized four-phase clocks differ from raw spans",
    )
    require(
        len(result.arrow_handoffs) == 2
        and [handoff.input_name for handoff in result.arrow_handoffs]
        == ["vertices", "edges"]
        and all(
            handoff.chunk_rows == plan.chunk_rows
            and handoff.cached_chunks == handoff.chunks
            and handoff.maximum_ipc_bytes <= 33554432
            and handoff.cache_threshold_bytes == 1
            and handoff.chunks
            == max(1, (handoff.rows + plan.chunk_rows - 1) // plan.chunk_rows)
            and handoff.balanced_union_depth == (handoff.chunks - 1).bit_length()
            for handoff in result.arrow_handoffs
        ),
        "bounded cached Arrow handoff proof missing",
    )
    if plan.dataset == "tiny":
        require(
            any(handoff.chunks > 1 for handoff in result.arrow_handoffs),
            "tiny must exercise a multi-chunk balanced union",
        )
    require(
        [(o.call, o.path, o.completed) for o in result.outputs]
        == [
            (n, plan.output_root / f"result-call{n}", True)
            for n in range(1, plan.calls + 1)
        ],
        "full write attempts missing",
    )
    if result.server is None:
        raise ValueError("owned native server proof missing")
    server = result.server
    require(
        server.pid == server.pgid
        and server.wait_completed
        and server.closed_utc is not None
        and not server.forced_kill
        and (
            server.returncode == 0
            or (server.termination_requested and server.returncode == -15)
        ),
        "native server exit failed or forced",
    )
    require(
        len(server.argv) == 7
        and server.argv[:6]
        == [str(plan.binary), "spark", "server", "--ip", "127.0.0.1", "--port"]
        and server.argv[6].isdigit(),
        "native argv binding failed",
    )
    series.server_pid, series.server_pgid = server.pid, server.pgid
    series.driver_group_absent = not members(series.pgid)
    series.server_group_absent = not members(server.pgid)
    require(
        series.driver_group_absent and series.server_group_absent,
        "owned driver/server process group remains live",
    )
    series.worker_receipt = pin(plan.receipt)
    series.outcome = "completed_unvalidated"


def interrupted(number: int, _frame: object) -> None:
    raise TimeoutError(f"campaign interrupted by signal {number}")


def run(path: Path) -> int:
    configuration = pin(path)
    config = Config.model_validate_json(path.read_bytes())
    require(
        path.parent in (config.root, config.worker.parent)
        and not (config.root / "receipt.json").exists(),
        "fresh owner/configuration namespace required",
    )
    config.root.mkdir(parents=True, exist_ok=True)
    receipt = Receipt(
        started_utc=utc(), owner_pid=os.getpid(), configuration=configuration
    )
    destination = config.root / "receipt.json"
    save(destination, receipt)
    locks: list[Path] = []
    process: subprocess.Popen[bytes] | None = None
    sampler: Sampler | None = None
    try:
        for number in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM):
            signal.signal(number, interrupted)
        signal.alarm(config.timeout_seconds)
        for name in ("gate.lock", "serial-queue.lock"):
            lock = LOCK_BASE / name
            lock.mkdir()
            locks.append(lock)
            (lock / "owner.json").write_text(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "configuration": configuration.model_dump(mode="json"),
                    }
                )
                + "\n"
            )
        require(
            shutil.disk_usage(config.root).free >= config.minimum_free_bytes,
            "64GiB metadata/retention disk reserve required",
        )
        receipt.before = [pin(p.path) for p in config.pins()]
        require(
            receipt.before == config.pins(), "declared immutable admission pin mismatch"
        )
        receipt.source_before = source(config)
        plans = admitted(config)
        for index, plan in enumerate(plans):
            parent = next(p for p in plan.output_root.parents if p.exists())
            require(
                min(shutil.disk_usage(config.root).free, shutil.disk_usage(parent).free)
                >= config.minimum_free_bytes,
                "64GiB per-series disk reserve required",
            )
            argv = [
                str(config.python),
                "-I",
                "-B",
                "-c",
                BOOT,
                str(config.worker.parent),
                "--plan",
                str(config.plans[index]),
            ]
            with (config.root / f"series-{index + 1}.log").open("xb") as log:
                start = time.monotonic_ns()
                launched = utc()
                process = subprocess.Popen(
                    argv,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                series = Series(
                    plan=pin(config.plans[index]),
                    argv=argv,
                    launched_utc=launched,
                    pid=process.pid,
                    pgid=process.pid,
                )
                receipt.series.append(series)
                require(
                    os.getpgid(process.pid) == process.pid,
                    "driver fresh process group missing",
                )
                save(destination, receipt)
                sampler = Sampler(
                    series, plan.receipt, config.root / f"series-{index + 1}-rss.jsonl"
                )
                sampler.thread.start()
                series.returncode = process.wait(timeout=config.series_seconds)
                series.launch_to_wait = models.Span(
                    started_ns=start, ended_ns=time.monotonic_ns()
                )
                series.wait_completed = True
                series.closed_utc = utc()
                sampler.stop.set()
                sampler.thread.join(timeout=5)
                require(
                    not sampler.thread.is_alive() and series.rss_sampler_closed,
                    "RSS sampler remains live or lacks closure",
                )
                if sampler.destination.is_file():
                    series.rss_file = pin(sampler.destination)
                accept(config, plan, series)
                process = None
                sampler = None
                save(destination, receipt)
        receipt.after = [pin(p.path) for p in config.pins()]
        receipt.source_after = source(config)
        require(
            pin(path) == configuration
            and receipt.before == receipt.after
            and receipt.source_before == receipt.source_after,
            "immutable source/configuration/pins changed",
        )
        receipt.all_owned_groups_absent = all(
            s.driver_group_absent
            and s.server_group_absent
            and not members(s.pgid)
            and s.server_pgid is not None
            and not members(s.server_pgid)
            for s in receipt.series
        )
        require(
            receipt.all_owned_groups_absent,
            "owned groups must remain absent at final closure",
        )
        for lock in reversed(locks):
            owner = json.loads((lock / "owner.json").read_bytes())
            require(
                owner["pid"] == os.getpid()
                and owner["configuration"] == configuration.model_dump(mode="json"),
                "lock ownership changed",
            )
            (lock / "owner.json").unlink()
            lock.rmdir()
        receipt.locks_released = True
        receipt.outcome = "completed_unvalidated_campaign"
    except BaseException as error:  # noqa: BLE001 - all attempted execution/cleanup failures and locks are retained.
        receipt.outcome = "error"
        receipt.errors.append(f"{type(error).__name__}: {error}")
        if receipt.series:
            receipt.series[-1].outcome = "error"
        signal.alarm(300)
        if process is not None and process.poll() is None:
            try:
                require(
                    os.getpgid(process.pid) == process.pid,
                    "live driver ownership cannot be established",
                )
                owned = (
                    receipt.series[-1]
                    if receipt.series and receipt.series[-1].pid == process.pid
                    else None
                )
                if owned is not None:
                    owned.forced_cleanup = True
                else:
                    receipt.errors.append(
                        f"launched direct child {process.pid} lacks a completed launch record"
                    )
                process.terminate()
                process.wait(timeout=240)
                if owned is not None:
                    owned.wait_completed = True
                    owned.returncode = process.returncode
            except Exception as cleanup:  # noqa: BLE001 - retain live direct-child cleanup failure; no historical signals.
                receipt.errors.append(
                    f"owned cleanup {type(cleanup).__name__}: {cleanup}"
                )
        if sampler is not None:
            sampler.stop.set()
            sampler.thread.join(timeout=5)
            if sampler.thread.is_alive():
                receipt.errors.append("RSS sampler remains live")
        receipt.skipped_plans = config.plans[len(receipt.series) :]
        try:
            if receipt.before:
                receipt.after = [pin(p.path) for p in config.pins()]
            if receipt.source_before:
                receipt.source_after = source(config)
        except Exception as final_error:  # noqa: BLE001 - preserve independent closure errors on failed attempt.
            receipt.errors.append(
                f"final identity closure {type(final_error).__name__}: {final_error}"
            )
    finally:
        signal.alarm(0)
        receipt.finished_utc = utc()
        save(destination, receipt)
    print(receipt.outcome + " " + str(destination), flush=True)
    return 0 if receipt.outcome == "completed_unvalidated_campaign" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    return run(parser.parse_args().config.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
