"""One root-sealed two-host case; actual host waits are distinct from qualification."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Literal

import x1_io as io
import x1_models as m

STOP = threading.Event()
LOCKS = (
    Path("/Volumes/Apo/graph-tests/results/sem-review-20261001/gate.lock"),
    Path("/Volumes/Apo/graph-tests/results/sem-review-20261001/serial-queue.lock"),
)


@dataclass(slots=True)
class Live:
    process: subprocess.Popen[bytes]
    proof: m.SupervisorProof
    request: m.Request
    heartbeat: threading.Thread
    stop: threading.Event


def interrupted(_signum: int, _frame: FrameType | None) -> None:
    STOP.set()


def journal(receipt: m.OwnerReceipt) -> None:
    receipt.observed_utc = io.utc()
    io.save(receipt.plan.root / "receipt.json", receipt)


def heartbeat(process: subprocess.Popen[bytes], stop: threading.Event) -> None:
    while not stop.wait(2) and process.poll() is None:
        try:
            if process.stdin is not None:
                process.stdin.write(b"\n")
                process.stdin.flush()
        except (BrokenPipeError, OSError):
            break


def finish(live: Live, receipt: m.OwnerReceipt, *, shutdown: bool = False) -> None:
    proof = live.proof.process
    live.stop.set()
    if live.heartbeat.ident is not None:
        live.heartbeat.join(timeout=3)
    if live.process.stdin is not None and not live.process.stdin.closed:
        try:
            live.process.stdin.close()
        except BrokenPipeError:
            pass
    try:
        proof.returncode = live.process.wait(timeout=150 if shutdown else 10)
    except subprocess.TimeoutExpired:
        proof.forced_cleanup = True
        live.process.terminate()
        try:
            proof.returncode = live.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            live.process.kill()
            proof.returncode = live.process.wait(timeout=10)
    proof.wait_completed = True
    proof.group_absent = io.group_absent(proof.pgid)
    proof.finished_utc = io.utc()
    journal(receipt)
    io.require(
        proof.returncode == 0 and proof.group_absent and not proof.forced_cleanup,
        "actual local/SSH supervisor wait/closure failed",
    )


def launch(request: m.Request, receipt: m.OwnerReceipt, role: str) -> Live:
    target = request.target
    directory = receipt.plan.root / "supervisors"
    directory.mkdir(exist_ok=True)
    data = request.model_dump_json().encode() + b"\n"
    io.require(
        len(data) <= io.MAXIMUM_REQUEST, "bounded literal supervisor request exceeded"
    )
    argv = io.command(target, "x1_remote.py")
    with (directory / f"{role}.log").open("xb") as log:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    proof = m.SupervisorProof(
        role=role,
        host=target.name,
        root=request.root,
        process=m.ProcessProof(
            pid=process.pid,
            pgid=process.pid,
            argv=argv,
            started_utc=io.utc(),
        ),
    )
    receipt.supervisors.append(proof)
    stop = threading.Event()
    thread = threading.Thread(target=heartbeat, args=(process, stop), daemon=True)
    live = Live(process, proof, request, thread, stop)
    try:
        journal(receipt)
        io.require(process.stdin is not None, "owned supervisor lease pipe absent")
        if process.stdin is None:
            raise ValueError("lease pipe absent")
        process.stdin.write(data)
        process.stdin.flush()
        thread.start()
    except BaseException:
        finish(live, receipt, shutdown=True)
        raise
    return live


def waited(live: Live, receipt: m.OwnerReceipt, seconds: int) -> None:
    deadline = time.monotonic() + seconds
    while live.process.poll() is None:
        if STOP.is_set():
            raise InterruptedError("root-owned case interrupted")
        if time.monotonic() >= deadline:
            raise TimeoutError("bounded host supervisor lifetime elapsed")
        time.sleep(0.2)
    finish(live, receipt)


def transport_stderr(output: Path) -> Path:
    directory = output.parent / ".transfer-stderr"
    directory.mkdir(exist_ok=True)
    return directory / (output.name + ".stderr.log")


def captured(
    target: m.Target,
    argv: list[str],
    output: Path,
    receipt: m.OwnerReceipt,
    seconds: int = 180,
) -> None:
    process: subprocess.Popen[bytes] | None = None
    proof: m.ProcessProof | None = None
    command = io.command(target, "x1_remote.py", *argv)
    with (
        output.open("xb") as stream,
        transport_stderr(output).open("xb") as log,
    ):
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=log,
                start_new_session=True,
            )
            proof = m.ProcessProof(
                pid=process.pid,
                pgid=process.pid,
                argv=command,
                started_utc=io.utc(),
            )
            receipt.transfers.append(proof)
            journal(receipt)
            result = process.wait(timeout=seconds)
            proof.returncode, proof.wait_completed, proof.finished_utc = (
                result,
                True,
                io.utc(),
            )
            proof.group_absent = io.group_absent(process.pid)
            journal(receipt)
            io.require(
                result == 0 and io.group_absent(process.pid),
                "literal closed-evidence transfer failed or remains",
            )
        finally:
            if process is not None and process.poll() is None:
                if proof is not None:
                    proof.forced_cleanup = True
                process.terminate()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
                if proof is not None:
                    proof.returncode, proof.wait_completed, proof.finished_utc = (
                        process.returncode,
                        True,
                        io.utc(),
                    )
                    proof.group_absent = io.group_absent(process.pid)
                    journal(receipt)


def collect(
    request: m.Request, receipt: m.OwnerReceipt, role: str, *, attach: bool = True
) -> m.Snapshot:
    directory = receipt.plan.root / "closed-evidence" / role
    directory.mkdir(parents=True, exist_ok=False)
    before = directory / "snapshot-before.json"
    captured(
        request.target,
        ["--snapshot-request-json", request.model_dump_json()],
        before,
        receipt,
    )
    observed = m.Snapshot.model_validate_json(io.read(io.pin(before)))
    io.require(
        observed.recording.request == request
        and observed.all_recorded_processes_absent
        and observed.source == observed.recording.source_after
        and observed.pins == observed.recording.pins_after,
        "actual host receipt/current source/process closure differs",
    )
    copies: dict[str, m.Pin] = {}
    for name, expected in {
        "receipt.json": observed.receipt,
        **observed.recording.retained_files,
    }.items():
        destination = directory / name
        captured(
            request.target,
            [
                "--file-request-json",
                request.model_dump_json(),
                "--file-pin-json",
                expected.model_dump_json(),
            ],
            destination,
            receipt,
        )
        actual = io.pin(destination)
        io.require(
            (actual.bytes, actual.sha256) == (expected.bytes, expected.sha256),
            "full copied closed evidence differs",
        )
        copies[name] = actual
    after = directory / "snapshot-after.json"
    captured(
        request.target,
        ["--snapshot-request-json", request.model_dump_json()],
        after,
        receipt,
    )
    closure = m.Snapshot.model_validate_json(io.read(io.pin(after)))
    io.require(
        closure.recording == observed.recording
        and closure.receipt == observed.receipt
        and closure.source == observed.source
        and closure.pins == observed.pins
        and closure.all_recorded_processes_absent,
        "closed evidence changed or actual owned process returned",
    )
    if attach:
        receipt.host_receipts.append(observed.recording)
        for proof in receipt.supervisors:
            if proof.root == request.root and proof.host == request.target.name:
                proof.receipt, proof.fetched = copies["receipt.json"], copies
    journal(receipt)
    return closure


def positive_host(recording: m.RemoteReceipt, outcome: str) -> None:
    io.require(
        recording.outcome == outcome
        and not recording.errors
        and recording.source_before == recording.source_after
        and recording.pins_before == recording.pins_after,
        "closed host admission/run failed",
    )
    proofs = [
        *recording.inspection_steps,
        *([recording.process] if recording.process else []),
    ]
    io.require(
        bool(proofs)
        and all(
            p.wait_completed
            and p.group_absent
            and not p.forced_cleanup
            and p.returncode in (0, -signal.SIGINT)
            for p in proofs
        ),
        "actual native waited closure failed",
    )


def prior_controls(plan: m.Plan) -> None:
    for item in plan.prior_controls:
        producer = m.OwnerReceipt.model_validate_json(io.read(item.producer))
        io.require(
            producer.outcome == "completed_unqualified_closed_twohost_case"
            and not producer.errors
            and producer.plan.kind == item.kind
            and producer.immutable_closure
            and producer.locks_released
            and producer.all_recorded_owned_processes_absent,
            "actual prior case ownership failed",
        )
        io.require(
            producer.plan.driver.binary.sha256 == plan.driver.binary.sha256
            and producer.plan.driver.wheel.sha256 == plan.driver.wheel.sha256
            and producer.plan.native_quota_bytes == plan.native_quota_bytes
            and producer.plan.worker_ports == plan.worker_ports,
            "prior case artifacts/resource/host contract differs",
        )
        raw = json.loads(io.read(item.qualification))
        io.require(
            raw.get("outcome") == item.expected_outcome and raw.get("errors") == [],
            "required prior qualification failed",
        )
        if item.kind == "tiny":
            flags = (
                "full_domain_passed",
                "all_original_edges_examined",
                "parent_paths_and_minimum_parent_passed",
                "all_edge_lower_bound_and_reachability_passed",
                "terminal_empty_expansion_cap_passed",
                "full_physical_certificate_passed",
                "own_identity_closure_passed",
            )
            io.require(
                all(raw.get(flag) is True for flag in flags)
                and all(
                    type(value) is int and value == 0
                    for value in raw["failures"].values()
                ),
                "tiny full signed physical certificate failed",
            )
            io.require(
                producer.native_execution_witness_passed
                and {row.worker_id for row in producer.native_execution_workers}
                == {1, 2},
                "tiny native operation must execute on both actual hosts",
            )
            configuration = m.Pin.model_validate_json(json.dumps(raw["configuration"]))
            config = json.loads(io.read(configuration))
            bindings = [
                m.Pin.model_validate_json(json.dumps(value))
                for value in config["producer_evidence"]
            ]
            io.require(
                item.producer in bindings and config["schema_profile"] == "native13",
                "tiny oracle producer/schema binding differs",
            )
            io.require(
                (
                    config["expected_vertices"],
                    config["expected_edges"],
                    config["source_id"],
                    config["max_levels"],
                    config["partitions"],
                )
                == (13, 14, -5, 8, 32),
                "exact signed/highbit tiny fixture contract required",
            )
        else:
            qualification = m.TypedControlQualification.model_validate_json(
                io.read(item.qualification)
            )
            expected_cause = (
                "bfs_level_cap" if item.kind == "bfs-cap0" else "allocation_refused"
            )
            io.require(
                qualification.producer == item.producer
                and qualification.task_cause == expected_cause,
                "typed negative control actual producer/cause binding differs",
            )
            for witness in qualification.witnesses:
                io.require(
                    io.pin(witness.path) == witness, "typed cause witness changed"
                )


def native_witness(receipt: m.OwnerReceipt) -> None:
    action = receipt.action_receipt
    io.require(action is not None, "actual action receipt required")
    if action is None:
        raise ValueError("action receipt absent")
    native_request = action.native_request
    workers: dict[int, m.RemoteReceipt] = {
        int(record.request.worker_id): record
        for record in receipt.host_receipts
        if record.request.role == "worker" and record.request.worker_id is not None
    }
    io.require(set(workers) == {1, 2}, "both actual closed worker processes required")
    selected: list[dict[str, object]] = []
    for worker in (1, 2):
        recording = workers[worker]
        io.require(recording.process is not None, "actual native worker PID absent")
        path = receipt.plan.root / f"closed-evidence/worker{worker}/native.log"
        with path.open() as stream:
            for line in stream:
                if "ARGENTEA_RECEIPT " not in line:
                    continue
                raw = json.loads(line.split("ARGENTEA_RECEIPT ", 1)[1])
                if raw.get("operation_id") != native_request.get("operation_id"):
                    continue
                io.require(
                    raw.get("worker_id") == worker
                    and recording.process is not None
                    and raw.get("pid") == recording.process.pid,
                    "native operation receipt/PID/physical worker differs",
                )
                io.require(
                    all(
                        raw.get(key) == native_request.get(key)
                        for key in ("snapshot_id", "generation", "algorithm")
                    ),
                    "native operation snapshot/source identity differs",
                )
                selected.append(raw)
    io.require(
        bool(selected) and {raw["worker_id"] for raw in selected} == {1, 2},
        "both physical workers must execute this native operation",
    )
    jobs = {(raw["session_id"], raw["job_id"]) for raw in selected}
    io.require(len(jobs) == 1, "one native operation job/session required")
    session, job = next(iter(jobs))
    if (
        not isinstance(session, str)
        or not isinstance(job, int)
        or isinstance(job, bool)
    ):
        raise TypeError("typed native job/session required")
    stages: set[int] = set()
    for row in action.stages:
        if (
            row["session_id"] == session
            and row["job_id"] == job
            and isinstance(row.get("slot_group"), str)
            and str(row["slot_group"]).startswith("worker-extension:")
        ):
            stage = row["stage"]
            if not isinstance(stage, int) or isinstance(stage, bool):
                raise ValueError("typed native stage identity required")
            io.require(
                row["partitions"] == receipt.plan.partitions
                and row["placement"] == "Worker"
                and row["mode"] == "Pipelined",
                "native stage placement/mode/partition width differs",
            )
            stages.add(stage)
    io.require(
        len(stages) == 2 * receipt.plan.max_levels + 4,
        "actual native stage inventory differs",
    )
    pattern = re.compile(
        r"worker_task_status worker_id=(\d+) job_id=(\d+) stage=(\d+) partition=(\d+) attempt=(\d+) status=([A-Z_]+)\b"
    )
    succeeded: dict[tuple[int, int], int] = {}
    counts: dict[int, int] = {1: 0, 2: 0}
    with (receipt.plan.root / "closed-evidence/driver/native.log").open() as stream:
        for line in stream:
            if "worker_task_status " not in line:
                continue
            match = pattern.search(line)
            io.require(match is not None, "malformed declared task status")
            if match is None:
                raise ValueError("task status parse failed")
            worker, observed_job, stage, partition, attempt = map(
                int, match.groups()[:5]
            )
            status = match[6]
            if observed_job != job or stage not in stages:
                continue
            io.require(
                worker in (1, 2)
                and attempt == 0
                and 0 <= partition < receipt.plan.partitions,
                "actual native task worker/partition/retry differs",
            )
            io.require(
                status in ("RUNNING", "SUCCEEDED"),
                "positive native operation has a failed task",
            )
            if status == "SUCCEEDED":
                key = (stage, partition)
                io.require(key not in succeeded, "duplicate successful native task")
                succeeded[key] = worker
                counts[worker] += 1
    io.require(
        set(succeeded)
        == {
            (int(stage), partition)
            for stage in stages
            for partition in range(receipt.plan.partitions)
        }
        and all(counts.values()),
        "full native stage/partition success on both hosts required",
    )
    for worker in (1, 2):
        process = workers[worker].process
        if process is None:
            raise ValueError("actual native worker proof missing")
        identity: Literal[1, 2] = 1 if worker == 1 else 2
        receipt.native_execution_workers.append(
            m.NativeWorker(
                worker_id=identity,
                pid=process.pid,
                successful_native_tasks=counts[worker],
            )
        )
    receipt.native_execution_session_id, receipt.native_execution_job_id = (
        session,
        job,
    )
    receipt.native_execution_witness_passed = True


def common_environment(plan: m.Plan) -> dict[str, str]:
    return {
        "AWS_ENDPOINT": plan.storage_endpoint,
        "AWS_ENDPOINT_URL": plan.storage_endpoint,
        "AWS_ALLOW_HTTP": "true",
        "AWS_REGION": "us-east-1",
        "AWS_DEFAULT_REGION": "us-east-1",
        "SAIL_EXPERIMENTAL_EXTENSIONS": "1",
        "RUST_LOG": m.LOGGING,
        "SAIL_EXECUTION__CHECKPOINT__PATH": plan.output_uri + "/checkpoints",
        "SAIL_GRAPH_UTILS_ROOT": plan.output_uri + "/graph-utils",
        "SAIL_ARGENTEA_MEMORY_BYTES": str(plan.native_quota_bytes),
        "NUTMEG_WORKERS": str(plan.threads),
        "RAYON_NUM_THREADS": str(plan.threads),
        "TOKIO_WORKER_THREADS": str(plan.threads),
        "SAIL_EXECUTION__DEFAULT_PARALLELISM": str(plan.partitions),
        "SAIL_RUNTIME__MEMORY_POOL__TYPE": "greedy",
        "SAIL_RUNTIME__MEMORY_POOL__GREEDY__MAX_SIZE": str(plan.normal_pool_bytes),
        "SAIL_CLUSTER__TASK_STREAM_CREATION_TIMEOUT_SECS": str(
            plan.stream_creation_timeout_seconds
        ),
        "SAIL_CLUSTER__WORKER_TASK_SLOTS": str(plan.worker_task_slots),
        "SAIL_CLUSTER__WORKER_MAX_IDLE_TIME_SECS": str(plan.worker_idle_seconds),
        "SAIL_CLUSTER__TASK_MAX_ATTEMPTS": "1",
        "SAIL_EXPERIMENTAL_HTTP2_KEEPALIVE_INTERVAL_SECS": str(
            plan.keepalive_interval_seconds
        ),
        "SAIL_EXPERIMENTAL_HTTP2_KEEPALIVE_TIMEOUT_SECS": str(
            plan.keepalive_timeout_seconds
        ),
    }


def execute(plan: m.Plan, receipt: m.OwnerReceipt, lives: list[Live]) -> None:
    common = common_environment(plan)
    for target, root, role in (
        (plan.worker1, plan.root / "inspection-morrobay", "inspect-morrobay"),
        (plan.driver, plan.remote_root / "inspection-capitola", "inspect-capitola"),
    ):
        request = m.Request(
            role="inspect",
            target=target,
            root=root,
            argv=[],
            environment=common,
            timeout_seconds=300,
        )
        live = launch(request, receipt, role)
        lives.append(live)
        waited(live, receipt, 300)
        positive_host(
            collect(request, receipt, role).recording, "passed_native_host_inspection"
        )
    first, second = [
        record.native_inspection["installed_identity"]
        for record in receipt.host_receipts
    ]
    io.require(
        isinstance(first, dict)
        and isinstance(second, dict)
        and first["identities"] == second["identities"],
        "same installed extension manifests/identities/payload counts required",
    )
    configured = m.WorkerConfiguration(plan=plan, common_environment=common)
    driver_env = dict(
        common,
        SAIL_MODE="local-cluster",
        SAIL_EXPERIMENTAL_PROCESS_WORKERS="1",
        SAIL_EXPERIMENTAL_WORKER_COMMAND=json.dumps(
            io.native_command(
                plan.driver,
                "x1_worker.py",
                "--configuration-json",
                configured.model_dump_json(),
            )
        ),
        SAIL_CLUSTER__DRIVER_LISTEN_HOST="0.0.0.0",
        SAIL_CLUSTER__DRIVER_LISTEN_PORT=str(plan.gateway_port),
        SAIL_CLUSTER__DRIVER_EXTERNAL_HOST=plan.driver.advertise,
        SAIL_CLUSTER__DRIVER_EXTERNAL_PORT=str(plan.gateway_port),
        SAIL_CLUSTER__WORKER_INITIAL_COUNT="2",
        SAIL_CLUSTER__WORKER_MAX_COUNT="2",
        SAIL_EXECUTION__CHECKPOINT__PATH=plan.output_uri + "/checkpoints",
        SAIL_GRAPH_UTILS_ROOT=plan.output_uri + "/graph-utils",
        SAIL_NATIVE_RESOURCE_AUDIT=str(plan.remote_root / "driver" / io.NATIVE_AUDIT),
    )
    request = m.Request(
        role="driver",
        target=plan.driver,
        root=plan.remote_root / "driver",
        argv=[
            str(plan.driver.binary.path),
            "spark",
            "server",
            "--ip",
            "0.0.0.0",
            "--port",
            str(plan.connect_port),
        ],
        environment=driver_env,
        timeout_seconds=min(21600, plan.timeout_seconds + 90),
    )
    driver = launch(request, receipt, "driver")
    lives.append(driver)
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        io.require(
            not STOP.is_set() and driver.process.poll() is None,
            "driver supervisor stopped before endpoint readiness",
        )
        try:
            with socket.create_connection(
                (plan.driver.advertise, plan.connect_port), timeout=1
            ):
                break
        except OSError:
            time.sleep(0.2)
    else:
        raise TimeoutError("bounded driver endpoint readiness failed")
    client_request = m.Request(
        role="client",
        target=plan.driver,
        root=plan.remote_root / "client",
        argv=io.native_command(
            plan.driver,
            "x1_actions.py",
            "--plan-json",
            plan.model_dump_json(),
            "--root",
            str(plan.remote_root / "client"),
        ),
        environment=common,
        timeout_seconds=plan.timeout_seconds,
    )
    client = launch(client_request, receipt, "client")
    lives.append(client)
    waited(client, receipt, plan.timeout_seconds + 30)
    finish(driver, receipt, shutdown=True)
    for host_request, role in ((client_request, "client"), (request, "driver")):
        positive_host(
            collect(host_request, receipt, role).recording,
            "completed_closed_supervised_process",
        )
    client_record = receipt.host_receipts[-2]
    action_pin = client_record.retained_files["action-receipt.json"]
    copied = plan.root / "closed-evidence/client/action-receipt.json"
    io.require(
        io.pin(copied).sha256 == action_pin.sha256,
        "retained actual client receipt differs",
    )
    receipt.action_receipt = m.ActionReceipt.model_validate_json(
        io.read(io.pin(copied))
    )
    io.require(
        receipt.action_receipt.plan == plan
        and not receipt.action_receipt.errors
        and receipt.action_receipt.session_closed,
        "actual client plan/error/session closure differs",
    )
    expected = (
        "completed_expected_error_unqualified"
        if plan.kind in ("bfs-cap0", "host-pool-refusal")
        else "completed_unqualified_bfs_export"
    )
    io.require(
        receipt.action_receipt.outcome == expected, "actual client case outcome differs"
    )
    workers: tuple[tuple[Literal[1, 2], m.Target], ...] = (
        (1, plan.worker1),
        (2, plan.worker2),
    )
    for worker, target in workers:
        root = plan.root / "worker1" if worker == 1 else plan.remote_root / "worker2"
        # Actual worker request contains driver-generated session fields; obtain it only from its closed receipt.
        lookup = m.Request(
            role="worker",
            target=target,
            root=root,
            argv=[str(target.binary.path), "worker"],
            environment={},
            timeout_seconds=min(21600, plan.timeout_seconds + 90),
            worker_id=worker,
        )
        directory = plan.root / "worker-discovery"
        directory.mkdir(exist_ok=True)
        path = directory / f"worker{worker}.json"
        captured(
            target,
            ["--discover-worker-request-json", lookup.model_dump_json()],
            path,
            receipt,
        )
        actual = m.Snapshot.model_validate_json(io.read(io.pin(path)))
        worker_request = actual.recording.request
        environment = worker_request.environment
        worker_expected = dict(
            common,
            SAIL_ARGENTEA_MEMORY_BYTES=str(plan.native_quota_bytes),
            SAIL_NATIVE_RESOURCE_AUDIT=str(root / io.NATIVE_AUDIT),
            SAIL_RUNTIME__MEMORY_POOL__GREEDY__MAX_SIZE=str(
                2**20 if plan.kind == "host-pool-refusal" else plan.normal_pool_bytes
            ),
            SAIL_CLUSTER__WORKER_ID=str(worker),
            SAIL_CLUSTER__WORKER_EXTERNAL_HOST=target.advertise,
            SAIL_CLUSTER__WORKER_EXTERNAL_PORT=str(plan.worker_ports[worker - 1]),
        )
        io.require(
            all(environment.get(key) == value for key, value in worker_expected.items())
            and bool(environment.get("SAIL_CLUSTER__SESSION_ID")),
            "actual worker resource/runtime/session settings differ",
        )
        positive_host(
            collect(worker_request, receipt, f"worker{worker}").recording,
            "completed_closed_supervised_process",
        )
    if plan.kind in ("tiny", "scale24"):
        native_witness(receipt)
    io.require(
        len(receipt.host_receipts) == 6,
        "both inspections and driver/client/two worker closures required",
    )


def run(configuration: Path) -> int:
    pin = io.pin(configuration)
    plan = m.Plan.model_validate_json(io.read(pin))
    io.fresh_root(plan.root, plan.worker1)
    plan.root.mkdir(parents=True, exist_ok=False)
    receipt = m.OwnerReceipt(
        observed_utc=io.utc(), pid=os.getpid(), configuration=pin, plan=plan
    )
    token = json.dumps(
        {
            "pid": os.getpid(),
            "configuration": pin.model_dump(mode="json"),
            "run_id": plan.run_id,
        }
    )
    acquired: list[Path] = []
    lives: list[Live] = []
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, interrupted)
    try:
        io.require(
            io.source(plan.worker1)
            == {"head": m.SOURCE, "tree": plan.worker1.tree, "status": ""},
            "controller source differs",
        )
        io.identities(plan.worker1)
        io.read(plan.dataset.admissions["morrobay"])
        io.read(plan.historical_missing_receipt)
        store = json.loads(io.read(plan.storage_admission))
        io.require(
            store.get("outcome") == "ready_owned_store_tiny_probe_only"
            and store.get("endpoint") == plan.storage_endpoint
            and store.get("bucket") == plan.output_uri.split("/")[2]
            and store.get("credential_mode") == "0600"
            and store.get("credential_content_not_logged_or_hashed") is True
            and store.get("allow_http") is True
            and store.get("region") == "us-east-1",
            "actual public fresh-store readiness contract differs",
        )
        prior_controls(plan)
        for lock in LOCKS:
            lock.mkdir(exist_ok=False)
            acquired.append(lock)
            (lock / "owner.json").write_text(token)
        journal(receipt)
        execute(plan, receipt, lives)
        receipt.immutable_closure = all(
            io.pin(item.path) == item
            for item in (
                pin,
                plan.dataset.admissions["morrobay"],
                plan.historical_missing_receipt,
                plan.storage_admission,
            )
        )
        receipt.all_recorded_owned_processes_absent = all(
            proof.wait_completed
            and proof.group_absent
            and proof.returncode == 0
            and not proof.forced_cleanup
            and io.group_absent(proof.pgid)
            for proof in [
                *[value.process for value in receipt.supervisors],
                *receipt.transfers,
            ]
        )
        io.require(
            receipt.immutable_closure and receipt.all_recorded_owned_processes_absent,
            "final owner immutable/process closure failed",
        )
        receipt.outcome = "completed_unqualified_closed_twohost_case"
    except BaseException as error:  # noqa: BLE001 - failed attempt never becomes positive through cleanup
        receipt.errors.append(repr(error))
        receipt.outcome = "error"
    finally:
        for live in reversed(lives):
            if not live.proof.process.wait_completed:
                try:
                    finish(live, receipt, shutdown=True)
                except (OSError, ValueError, subprocess.SubprocessError) as error:
                    receipt.errors.append(f"owned supervisor cleanup: {error!r}")
        if receipt.outcome == "error":
            for live in lives:
                role = live.proof.role
                if (
                    live.proof.process.wait_completed
                    and not (plan.root / "closed-evidence" / role).exists()
                ):
                    try:
                        collect(live.request, receipt, role)
                    except (OSError, ValueError, subprocess.SubprocessError) as error:
                        receipt.errors.append(
                            f"failed case closed evidence {role}: {error!r}"
                        )
        if receipt.outcome != "error":
            try:
                for lock in reversed(acquired):
                    io.require(
                        (lock / "owner.json").read_text() == token,
                        "owned lock changed; refuse release",
                    )
                    (lock / "owner.json").unlink()
                    lock.rmdir()
                receipt.locks_released = True
            except (OSError, ValueError) as error:
                receipt.errors.append(f"owned lock release: {error!r}")
        if receipt.errors:
            receipt.outcome = "error"
        journal(receipt)
    return 0 if receipt.outcome != "error" else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    raise SystemExit(run(parser.parse_args().plan))


if __name__ == "__main__":
    main()
