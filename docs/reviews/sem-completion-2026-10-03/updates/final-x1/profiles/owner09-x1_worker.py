"""Two-target router: explicit native controls survive the foreground lease."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import threading
from types import FrameType
from typing import Literal

import x1_io as io
import x1_models as m

STOP = threading.Event()


def interrupted(_signum: int, _frame: FrameType | None) -> None:
    STOP.set()


def run(value: str) -> int:
    configured = m.WorkerConfiguration.model_validate_json(value)
    plan = configured.plan
    raw_worker = int(os.environ["SAIL_CLUSTER__WORKER_ID"])
    worker: Literal[1, 2]
    if raw_worker == 1:
        worker = 1
    elif raw_worker == 2:
        worker = 2
    else:
        raise ValueError("only the two admitted worker identities are allowed")
    target = plan.worker1 if worker == 1 else plan.worker2
    root = plan.root / "worker1" if worker == 1 else plan.remote_root / "worker2"
    environment = dict(configured.common_environment)
    environment.update(
        {
            key: value
            for key, value in os.environ.items()
            if key.startswith(("SAIL_CLUSTER__", "SAIL_EXECUTION__", "SAIL_RUNTIME__"))
        }
    )
    environment.update(
        SAIL_ARGENTEA_MEMORY_BYTES=str(plan.native_quota_bytes),
        SAIL_NATIVE_RESOURCE_AUDIT=str(root / io.NATIVE_AUDIT),
        SAIL_RUNTIME__MEMORY_POOL__GREEDY__MAX_SIZE=str(
            2**20 if plan.kind == "host-pool-refusal" else plan.normal_pool_bytes
        ),
        SAIL_CLUSTER__WORKER_ID=str(worker),
        SAIL_CLUSTER__WORKER_LISTEN_HOST="0.0.0.0",
        SAIL_CLUSTER__WORKER_EXTERNAL_HOST=target.advertise,
        SAIL_CLUSTER__WORKER_LISTEN_PORT=str(plan.worker_ports[worker - 1]),
        SAIL_CLUSTER__WORKER_EXTERNAL_PORT=str(plan.worker_ports[worker - 1]),
    )
    request = m.Request(
        role="worker",
        target=target,
        root=root,
        argv=[str(target.binary.path), "worker"],
        environment=environment,
        timeout_seconds=min(21600, plan.timeout_seconds + 90),
        worker_id=worker,
    )
    data = request.model_dump_json().encode() + b"\n"
    io.require(
        len(data) <= io.MAXIMUM_REQUEST, "bounded worker protocol request exceeded"
    )
    process: subprocess.Popen[bytes] | None = None
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, interrupted)
    try:
        process = subprocess.Popen(
            io.command(target, "x1_remote.py"), stdin=subprocess.PIPE
        )
        if process.stdin is None:
            raise ValueError("owned lease pipe absent")
        process.stdin.write(data)
        process.stdin.flush()
        while process.poll() is None and not STOP.wait(2):
            process.stdin.write(b"\n")
            process.stdin.flush()
    finally:
        if process is not None:
            if process.stdin is not None:
                try:
                    process.stdin.close()
                except BrokenPipeError:
                    pass
            try:
                process.wait(timeout=100)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
    if process is None:
        raise ValueError("worker supervisor never launched")
    return process.returncode


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configuration-json", required=True)
    raise SystemExit(run(parser.parse_args().configuration_json))


if __name__ == "__main__":
    main()
