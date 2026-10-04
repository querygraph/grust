"""Host-local literal stdin lease supervisor with actual native child wait/closure."""

from __future__ import annotations

import argparse
import json
import os
import platform
import select
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import FrameType
from typing import cast

from pydantic import JsonValue

import x1_io as io
import x1_models as m

STOP = False


def interrupted(_signum: int, _frame: FrameType | None) -> None:
    global STOP
    STOP = True  # Never interrupt Popen before its live handle is owned.


def event(name: str, request: m.Request, receipt: m.RemoteReceipt) -> None:
    print(
        json.dumps(
            {
                "event": name,
                "role": request.role,
                "root": str(request.root),
                "hostname": receipt.host,
                "supervisor_pid": receipt.supervisor_pid,
                "native_pid": receipt.process.pid if receipt.process else None,
                "worker_id": request.worker_id,
                "outcome": receipt.outcome,
            }
        ),
        flush=True,
    )


def close(process: subprocess.Popen[bytes], proof: m.ProcessProof) -> None:
    if process.poll() is None:
        proof.sigint_shutdown = True
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            proof.forced_cleanup = True
            process.kill()
            process.wait(timeout=10)
    proof.returncode = process.wait(timeout=5)
    proof.wait_completed = True
    # A live direct child is reaped before same-UID descendant groups are considered.
    if io.same_uid_group(process.pid):
        for signum, seconds in ((signal.SIGINT, 30), (signal.SIGKILL, 10)):
            if not io.same_uid_group(process.pid):
                break
            if signum == signal.SIGKILL:
                proof.forced_cleanup = True
            try:
                os.killpg(process.pid, signum)
            except ProcessLookupError:
                pass
            deadline = time.monotonic() + seconds
            while io.same_uid_group(process.pid) and time.monotonic() < deadline:
                time.sleep(0.1)
    proof.group_absent = io.group_absent(process.pid)
    proof.finished_utc = io.utc()


def run_probe(
    root: Path,
    name: str,
    argv: list[str],
    environment: dict[str, str],
    receipt: m.RemoteReceipt,
) -> str:
    process: subprocess.Popen[bytes] | None = None
    proof: m.ProcessProof | None = None
    with (root / f"{name}.log").open("xb") as log:
        try:
            process = subprocess.Popen(
                argv,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
            proof = m.ProcessProof(
                pid=process.pid, pgid=process.pid, argv=argv, started_utc=io.utc()
            )
            receipt.inspection_steps.append(proof)
            io.save(root / "receipt.json", receipt)
            result = process.wait(timeout=60)
            proof.returncode, proof.wait_completed, proof.finished_utc = (
                result,
                True,
                io.utc(),
            )
            proof.group_absent = io.group_absent(process.pid)
            io.require(
                result == 0 and io.group_absent(process.pid),
                "native admission subprocess failed or remains",
            )
        finally:
            if process is not None and proof is not None and not proof.wait_completed:
                proof.forced_cleanup = True
                close(process, proof)
    data = (root / f"{name}.log").read_bytes()
    io.require(len(data) <= 2**20, "bounded native admission log exceeded")
    return data.decode()


def native_identity(
    arm: subprocess.CompletedProcess[str],
    translated: subprocess.CompletedProcess[str],
    vendor: str | None,
    system: str,
    machine: str,
    target: str,
) -> str:
    """Admit explicit zero, or an absent key only on proved native Intel."""
    io.require(
        arm.args == ["/usr/sbin/sysctl", "-n", "hw.optional.arm64"]
        and arm.returncode in (0, 1),
        "hardware architecture probe unresolved",
    )
    hardware = (
        "arm64" if arm.returncode == 0 and arm.stdout.strip() == "1" else "x86_64"
    )
    io.require(
        system == "Darwin" and machine == hardware == target,
        "native Python and actual physical hardware architecture differ",
    )
    if hardware == "x86_64":
        io.require(
            arm.stdout.strip() in ("", "0") and vendor == "GenuineIntel",
            "native Intel hardware architecture probe unresolved",
        )
    io.require(
        translated.args == ["/usr/sbin/sysctl", "-n", "sysctl.proc_translated"]
        and (
            (translated.returncode == 0 and translated.stdout.strip() == "0")
            or (
                hardware == "x86_64"
                and vendor == "GenuineIntel"
                and translated.returncode == 1
                and translated.stdout == ""
                and translated.stderr.strip()
                == "sysctl: unknown oid 'sysctl.proc_translated'"
            )
        ),
        "translated or unresolved current Python process",
    )
    return hardware


def inspect(
    request: m.Request, receipt: m.RemoteReceipt, environment: dict[str, str]
) -> None:
    io.assembly(request.target)
    arm = subprocess.run(
        ["/usr/sbin/sysctl", "-n", "hw.optional.arm64"],
        capture_output=True,
        check=False,
        text=True,
        timeout=5,
    )
    translated = subprocess.run(
        ["/usr/sbin/sysctl", "-n", "sysctl.proc_translated"],
        capture_output=True,
        check=False,
        text=True,
        timeout=5,
    )
    hardware = (
        "arm64" if arm.returncode == 0 and arm.stdout.strip() == "1" else "x86_64"
    )
    vendor = None
    if hardware == "x86_64":
        vendor = subprocess.check_output(
            ["/usr/sbin/sysctl", "-n", "machdep.cpu.vendor"], text=True, timeout=5
        ).strip()
    hardware = native_identity(
        arm,
        translated,
        vendor,
        platform.system(),
        platform.machine(),
        request.target.architecture,
    )
    receipt.host_architecture = hardware
    receipt.translated = False
    version = run_probe(
        request.root,
        "native-version",
        [str(request.target.binary.path), "--version"],
        environment,
        receipt,
    )
    io.require(version.strip() == "sail 0.7.1", "native fat CLI version differs")
    loader = "import json,platform,sys;import sail_nutmeg._native as n;print(json.dumps({'architecture':platform.machine(),'python':sys.version,'module':n.__file__}))"
    loaded = json.loads(
        run_probe(
            request.root,
            "native-loader",
            [str(request.target.python), "-I", "-B", "-c", loader],
            environment,
            receipt,
        )
    )
    io.require(
        loaded["architecture"] == hardware
        and str(loaded["python"]).startswith(request.target.python_version + " "),
        "native fat library CP312/version differs",
    )
    identity_path = request.root / "installed-identity.json"
    run_probe(
        request.root,
        "installed-identity",
        [
            str(request.target.python),
            "-I",
            "-B",
            str(request.target.identity_helper.path),
            "--output",
            str(identity_path),
        ],
        environment,
        receipt,
    )
    identity = json.loads(io.read(io.pin(identity_path)))
    io.require(
        identity["architecture"] == hardware
        and identity["native_import_occurred"] is False
        and {p["entry_name"] for p in identity["identities"]} == {"nutmeg", "argentea"},
        "installed package metadata admission differs",
    )
    receipt.native_inspection = cast(
        dict[str, JsonValue],
        {
            "cli_version": version.strip(),
            "loader": loaded,
            "installed_identity": identity,
            "sysctl_arm64": {
                "returncode": arm.returncode,
                "stdout": arm.stdout.strip(),
            },
            "sysctl_cpu_vendor": vendor,
            "sysctl_translated": {
                "argv": translated.args,
                "returncode": translated.returncode,
                "stdout": translated.stdout.strip(),
                "stderr": translated.stderr.strip(),
            },
            "no_translation_basis": "hardware and current native interpreter architecture agree; translated status is zero, or its exact unknown-oid failure is admitted only on independently proved native GenuineIntel x86_64",
        },
    )


def run() -> int:
    line = sys.stdin.buffer.readline(io.MAXIMUM_REQUEST + 1)
    io.require(len(line) <= io.MAXIMUM_REQUEST, "bounded versioned request required")
    request = m.Request.model_validate_json(line)
    io.fresh_root(request.root, request.target)
    request.root.mkdir(parents=True, exist_ok=False)
    receipt = m.RemoteReceipt(
        observed_utc=io.utc(),
        supervisor_pid=os.getpid(),
        request=request,
        host=platform.node(),
        architecture=platform.machine(),
    )
    process: subprocess.Popen[bytes] | None = None
    normal_stop = False
    try:
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(signum, interrupted)
        receipt.source_before = io.source(request.target)
        receipt.pins_before = io.identities(request.target)
        io.prepare_native_audit(request)
        environment = io.environment(request.target, request.environment)
        if request.role == "inspect":
            inspect(request, receipt, environment)
            io.require(
                all(
                    step.wait_completed
                    and step.returncode == 0
                    and step.group_absent
                    and not step.forced_cleanup
                    for step in receipt.inspection_steps
                ),
                "inspection actual waited closure differs",
            )
            receipt.outcome = "passed_native_host_inspection"
        else:
            io.require(
                bool(request.argv)
                and request.argv[0]
                in (str(request.target.binary.path), str(request.target.python)),
                "only admitted native executable or client interpreter is allowed",
            )
            with (request.root / "native.log").open("xb") as log:
                process = subprocess.Popen(
                    request.argv,
                    cwd=request.root,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                receipt.process = m.ProcessProof(
                    pid=process.pid,
                    pgid=process.pid,
                    argv=request.argv,
                    started_utc=io.utc(),
                )
                io.save(request.root / "receipt.json", receipt)
                event("x1_native_started", request, receipt)
                heartbeat = time.monotonic()
                deadline = heartbeat + request.timeout_seconds
                while process.poll() is None:
                    if STOP:
                        normal_stop = True
                        break
                    readable, _, _ = select.select([sys.stdin.buffer], [], [], 0.2)
                    if readable:
                        data = os.read(sys.stdin.fileno(), 4096)
                        if not data:
                            normal_stop = True
                            break
                        heartbeat = time.monotonic()
                    if time.monotonic() - heartbeat > request.lease_seconds:
                        raise TimeoutError("owning lease expired")
                    if time.monotonic() >= deadline:
                        raise TimeoutError("bounded native child lifetime elapsed")
                close(process, receipt.process)
                io.require(
                    receipt.process.group_absent
                    and not receipt.process.forced_cleanup
                    and receipt.process.returncode
                    in ((0, -signal.SIGINT) if normal_stop else (0,)),
                    "actual native exit/group closure differs",
                )
                receipt.outcome = "completed_closed_supervised_process"
    except BaseException as error:  # noqa: BLE001 - retain every failure and close only owned live subprocess
        receipt.errors.append(repr(error))
        receipt.outcome = "error"
    finally:
        if (
            process is not None
            and receipt.process is not None
            and not receipt.process.wait_completed
        ):
            try:
                close(process, receipt.process)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                receipt.errors.append(f"owned native cleanup: {error!r}")
        try:
            receipt.source_after = io.source(request.target)
            receipt.pins_after = io.identities(request.target)
            io.require(
                receipt.source_before == receipt.source_after
                and receipt.pins_before == receipt.pins_after,
                "final host source/artifact/helper closure differs",
            )
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            receipt.errors.append(f"host immutable closure: {error!r}")
        if receipt.errors:
            receipt.outcome = "error"
        try:
            if receipt.process is not None:
                io.check_native_audit(request)
            permitted = {
                "native-version.log",
                "native-loader.log",
                "installed-identity.log",
                "installed-identity.json",
                "native.log",
                "action-receipt.json",
            }
            if request.role in ("driver", "worker"):
                permitted.add(io.NATIVE_AUDIT)
            receipt.retained_files = {
                p.name: io.pin(p)
                for p in sorted(request.root.iterdir())
                if p.is_file() and p.name in permitted
            }
        except (OSError, ValueError) as error:
            receipt.errors.append(f"retained host files: {error!r}")
            receipt.outcome = "error"
        receipt.observed_utc = io.utc()
        io.save(request.root / "receipt.json", receipt)
        event("x1_native_closed", request, receipt)
    return 0 if receipt.outcome != "error" else 1


def snapshot(value: str, *, discover: bool = False) -> int:
    request = m.Request.model_validate_json(value)
    receipt_pin = io.pin(request.root / "receipt.json")
    recording = m.RemoteReceipt.model_validate_json(io.read(receipt_pin))
    actual = recording.request
    if discover:
        io.require(
            request.role == actual.role == "worker"
            and request.worker_id == actual.worker_id
            and request.target == actual.target
            and request.root == actual.root
            and request.argv == actual.argv,
            "actual worker request discovery identity differs",
        )
    else:
        io.require(actual == request, "exact closed host request required")
    io.require(recording.outcome != "running", "closed host receipt required")
    proofs = [
        *recording.inspection_steps,
        *([recording.process] if recording.process else []),
    ]
    pids = {recording.supervisor_pid, *(proof.pid for proof in proofs)}
    pgids = {proof.pgid for proof in proofs}
    remaining = [
        list(row) for row in io.process_rows() if row[0] in pids or row[1] in pgids
    ]
    result = m.Snapshot(
        observed_utc=io.utc(),
        recording=recording,
        receipt=receipt_pin,
        source=io.source(request.target),
        pins=io.identities(request.target),
        processes_remaining=remaining,
        all_recorded_processes_absent=not remaining,
    )
    io.require(
        io.pin(receipt_pin.path) == receipt_pin,
        "closed receipt changed during current observation",
    )
    print(result.model_dump_json(), flush=True)
    return 0


def fetch(value: str, expected: str) -> int:
    request = m.Request.model_validate_json(value)
    item = m.Pin.model_validate_json(expected)
    allowed = {
        "receipt.json",
        "native-version.log",
        "native-loader.log",
        "installed-identity.log",
        "installed-identity.json",
        "native.log",
        "action-receipt.json",
        io.NATIVE_AUDIT,
    }
    io.require(
        item.path.parent == request.root and item.path.name in allowed,
        "only literal closed evidence files may be fetched",
    )
    if item.path.name == io.NATIVE_AUDIT:
        io.require(
            io.native_audit_path(request) == item.path,
            "only the exact owned native audit may be fetched",
        )
        io.check_native_audit(request)
    io.require(
        io.pin(item.path) == item, "closed evidence identity changed before copy"
    )
    with item.path.open("rb") as source:
        while block := source.read(4 * 2**20):
            sys.stdout.buffer.write(block)
    sys.stdout.buffer.flush()
    io.require(
        io.pin(item.path) == item, "closed evidence identity changed during copy"
    )
    if item.path.name == io.NATIVE_AUDIT:
        io.check_native_audit(request)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-request-json")
    parser.add_argument("--discover-worker-request-json")
    parser.add_argument("--file-request-json")
    parser.add_argument("--file-pin-json")
    args = parser.parse_args()
    if args.discover_worker_request_json is not None:
        io.require(
            args.snapshot_request_json is None
            and args.file_request_json is None
            and args.file_pin_json is None,
            "one literal command required",
        )
        return snapshot(args.discover_worker_request_json, discover=True)
    if args.snapshot_request_json is not None:
        io.require(
            args.file_request_json is None and args.file_pin_json is None,
            "one literal command required",
        )
        return snapshot(args.snapshot_request_json)
    if args.file_request_json is not None:
        io.require(args.file_pin_json is not None, "exact file pin required")
        return fetch(args.file_request_json, args.file_pin_json)
    io.require(args.file_pin_json is None, "unexpected file pin")
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
