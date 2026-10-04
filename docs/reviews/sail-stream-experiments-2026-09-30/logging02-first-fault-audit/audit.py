"""Read-only, local audit of the closed logging02 capture; no remote commands."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import statistics

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
CELL = ROOT / "logging02"
MONITOR = ROOT / "logging02-monitor"
BOOT = "f5443bfc-c939-491a-a984-b73cc6d1cb20"
CGROUP = "277559b777e04a8bdda5f0cb8931480269de472f0fbf2e2125375496118fab16"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def save(name, value):
    with (OUT / name).open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def numbered(lines, indexes):
    return [{"line_number": i + 1, "value": lines[i]} for i in indexes]


closure_path = ROOT / "logging02-host-closure.json"
closure = load(closure_path)
private_stdout = Path(closure["private_directory"]) / "ssh.stdout"
inputs = sorted(p for p in CELL.rglob("*") if p.is_file()) + [
    ROOT / "logging02-collection.json", closure_path, private_stdout,
    MONITOR / "identity-audit.json",
    MONITOR / "executable-identity-20260930T201136793716Z.json",
    MONITOR / "observation-20260930T215338275713Z.json",
]
before = {str(p): {"bytes": p.stat().st_size, "sha256": digest(p)} for p in inputs}
assert digest(private_stdout) == closure["private_stdout"]["sha256"]
host_raw = load(private_stdout)
guest = json.loads(host_raw["snapshots"]["guest"]["stdout"])
assert guest["boot_id"] == guest["boot_id_after"] == BOOT
kernel = guest["stdout"]
assert hashlib.sha256(kernel.encode()).hexdigest() == closure["guest"]["full_dmesg_decoded_text_sha256"]
kernel_lines = kernel.splitlines()
target_kills = [i for i, line in enumerate(kernel_lines) if "oom-kill:" in line and f"oom_memcg=/docker/{CGROUP}," in line]
assert len(target_kills) == 2
assert "pid=183784," in kernel_lines[target_kills[0]]
assert "pid=183782," in kernel_lines[target_kills[1]]
assert "Killed process 183784 " in kernel_lines[target_kills[0] + 1]
assert "Killed process 183782 " in kernel_lines[target_kills[1] + 1]
kill_times = [float(re.match(r"\[\s*([0-9.]+)\]", kernel_lines[i + 1])[1]) for i in target_kills]
start = max(i for i in range(target_kills[0]) if "invoked oom-killer" in kernel_lines[i])
end = max(i for i, line in enumerate(kernel_lines) if "oom_reaper:" in line and re.search(r"process (183782|183784) ", line))
kernel_target = numbered(kernel_lines, range(start, end + 1))
save("kernel-target-events.json", {
    "boot_id": BOOT, "cgroup": CGROUP,
    "full_decoded_kernel_sha256": hashlib.sha256(kernel.encode()).hexdigest(),
    "full_decoded_kernel_bytes": len(kernel.encode()),
    "private_ssh_stdout_sha256": digest(private_stdout),
    "selection": "Original contiguous kernel lines around the two exact-cgroup OOM events; other cgroups excluded.",
    "lines": kernel_target,
})

receipt = load(CELL / "diagnostics/receipt.json")
orchestration = load(CELL / "cell/orchestration.json")
result = load(CELL / "result.json")
assert orchestration["inspect"]["id"] == CGROUP
assert result["outcome"] == "oom" and receipt["outcome"] == "error"
assert int(receipt["cgroup_after"]["memory.max"]) == 100 * 2**30
events = {k: int(v) for k, v in (line.split() for line in receipt["cgroup_after"]["memory.events"].splitlines())}
assert events["oom_kill"] == 2
rows = [json.loads(line) for line in (CELL / "diagnostics/memory-samples.jsonl").read_text().splitlines()]
assert len(rows) == receipt["memory"]["samples"] == 6836
straddle = next(i for i, row in enumerate(rows) if row["scan_started_seconds"] <= min(kill_times) and row["scan_finished_seconds"] >= max(kill_times))
missing = next(i for i in range(straddle + 1, len(rows)) if not {167, 169} & {p["pid"] for p in rows[i]["processes"]})
first_both = next(i for i, row in enumerate(rows) if {167, 169} <= {p["pid"] for p in row["processes"]})
assert all({167, 169} <= {p["pid"] for p in row["processes"]} for row in rows[first_both:missing])
cleanup = next(i for i, row in enumerate(rows) if row["phase"] == "cleanup")
last_directory = max(i for i, row in enumerate(rows) if row["directories"] is not None)
sample_indexes = sorted(set([straddle - 1, straddle, missing, cleanup, last_directory, len(rows) - 1]))
save("sample-boundaries.json", numbered(rows, sample_indexes))

log_bytes = (CELL / "diagnostics/server.log").read_bytes()
log = log_bytes.decode().splitlines()
fault_re = re.compile(r"(?i)(?<![a-z])(?:error|panic|panicked|OutOfMemory|failed|stream_error|execution_failure)(?![a-z])")
faults = [i for i, line in enumerate(log) if re.match(r"^\[\d{4}-", line) and fault_re.search(line)]
assert len(faults) == 2
assert "connection closed before reading preface" in log[faults[0]]
assert "event=flight_client_error" in log[faults[1]]
assert "peer=http://127.0.0.1:43503" in log[faults[1]]
runtime_error = faults[1]
startup = [i for i, line in enumerate(log) if "extension process worker " in line or "worker 2 is available at 127.0.0.1:43503" in line]
assert len(startup) == 3
selected = sorted(set(startup + faults + list(range(runtime_error, len(log)))))
save("server-target-events.json", {
    "server_sha256": hashlib.sha256(log_bytes).hexdigest(),
    "total_bytes": len(log_bytes), "total_lines": len(log),
    "timestamped_fault_pattern": fault_re.pattern,
    "matching_line_numbers": [i + 1 for i in faults],
    "first_runtime_fault_byte_offset": sum(len(x) for x in log_bytes.splitlines(keepends=True)[:runtime_error]),
    "lines": numbered(log, selected),
})

identity = load(MONITOR / "observation-20260930T215338275713Z.json")
mapped = {x["host_pid"]: x for x in identity["mapping"]["processes"]}
roles = [
    {"role": "driver", "host_pid": 183665, "namespace_pid": 50, "start_ticks": 14376571},
    {"role": "worker 2", "host_pid": 183782, "namespace_pid": 167, "start_ticks": 14376781},
    {"role": "worker 1", "host_pid": 183784, "namespace_pid": 169, "start_ticks": 14376782},
]
for role in roles:
    observed = mapped[role["host_pid"]]
    assert observed["start_ticks"] == role["start_ticks"]
    assert int(observed["status"]["NSpid"].split()[-1]) == role["namespace_pid"]
    assert CGROUP in observed["cgroup"]

uptime = float(guest["uptime"].split()[0])
guest_start = datetime.fromisoformat(guest["started_utc"])
estimated_kill_utc = [(guest_start + timedelta(seconds=t - uptime)).isoformat() for t in kill_times]
spans = [r["scan_finished_seconds"] - r["scan_started_seconds"] for r in rows]
iteration_events = [{k: v for k, v in event.items() if k != "plan"} for event in receipt["iteration_events"]]
assert [(x["kind"], x["iteration"]) for x in iteration_events] == [("iteration_start", 1), ("iteration_end", 1), ("iteration_start", 2)]
findings = {
    "recorded_utc": datetime.now(timezone.utc).isoformat(),
    "outcome": "LOGGING02_EXACT_CGROUP_WORKER_OOM_KILLS_CONFIRMED",
    "boot_id": BOOT, "container_id": CGROUP, "roles": roles,
    "live_executable_sha256": receipt["binary_sha256"],
    "identity_scope": "Worker names/namespace IDs are directly recorded at startup. Prior live executable hashes and repeated host PID/NSpid/start-tick/cgroup mapping establish identity before death. Kernel records exact host PIDs and cgroup, not roles, start ticks or executable hashes. Continuous sampled namespace PID presence supports continuity; it is not continuous process tracing.",
    "kernel_kill_monotonic_seconds": kill_times,
    "kernel_kill_estimated_utc": estimated_kill_utc,
    "utc_conversion_scope": "Approximation from post-closure guest UTC and /proc/uptime in the same boot; not an event UTC recorded by the kernel. Native monotonic coordinates are authoritative. No sub-second cross-clock ordering claim.",
    "clock_anchor": {k: guest[k] for k in ("started_utc", "finished_utc", "uptime", "boot_id", "boot_id_after")},
    "kill_straddling_sample_line": straddle + 1,
    "first_sample_without_workers_line": missing + 1,
    "first_sample_without_workers_interval": [rows[missing]["scan_started_seconds"], rows[missing]["scan_finished_seconds"]],
    "first_runtime_fault": {"line": runtime_error + 1, "text": log[runtime_error]},
    "fault_peer_attribution": "Port 43503 is directly logged as worker 2's advertised endpoint; that worker is one of the kernel victims.",
    "terminal_memory_events": events,
    "terminal_memory_peak_bytes": int(receipt["cgroup_after"]["memory.peak"]),
    "memory_max_bytes": int(receipt["cgroup_after"]["memory.max"]),
    "cgroup_after_current_bytes": int(receipt["cgroup_after"]["memory.current"]),
    "outcomes": {"outer": result["outcome"], "producer": receipt["outcome"], "container_exit": orchestration["inspect"]["state"]["ExitCode"], "container_oom_killed": orchestration["inspect"]["state"]["OOMKilled"], "outer_timeout": orchestration["outer_timeout"]},
    "iteration_events": iteration_events,
    "elapsed_until_error_seconds": receipt["elapsed_until_error_seconds"],
    "cleanup": {"first_sample_line": cleanup + 1, "last_directory_sample_line": last_directory + 1, "last_directory_scan_interval": [rows[last_directory]["scan_started_seconds"], rows[last_directory]["scan_finished_seconds"]], "last_directory_scan_phase": rows[last_directory]["phase"], "last_directory_scan_driver_present": 50 in {p["pid"] for p in rows[last_directory]["processes"]}, "last_sampled_directories": rows[last_directory]["directories"], "post_shutdown_staging_inventory_present": "staging_files_after_shutdown" in receipt, "cleanup_errors": receipt["cleanup_errors"], "write_uncertainty_note": receipt["error"].splitlines()[-1], "container_state": orchestration["inspect"]["state"], "container_remove_returncode": orchestration["remove"]["returncode"]},
    "sampling": {"rows": len(rows), "requested_interval_seconds": receipt["memory"]["interval_seconds"], "actual_scan_span_seconds": {"min": min(spans), "median": statistics.median(spans), "max": max(spans)}, "max_span_line": spans.index(max(spans)) + 1, "peak_straddling_scan_seconds": spans[straddle], "all_step_values_null": all(r["step"] is None for r in rows)},
    "limits": [
        "This closed replay has direct cgroup OOM evidence and its affected peer disappears before the recorded broken-pipe stream failure. It does not identify the allocation site or prove which operator exhausted memory.",
        "The original twelve zero-OOM historical failures remain unexplained; this result must not be retroactively applied to them.",
        "The startup DEBUG preface-close record is preserved separately and is not treated as this terminal runtime failure.",
        "Sample 6805 crosses both kills/reaping and combines sequential process reads; its RSS/PSS peak and post-kill cgroup current are not simultaneous.",
        "No correctness result or completed iteration 2 exists. This shared-host diagnostic is not a performance measurement.",
        "cleanup_errors=[] and successful container removal do not prove staging cleanup. The last directory scan was nonempty while the driver was still sampled, before its later disappearance; it is not a post-shutdown inventory and does not prove retained staging bytes at final exit. No staging_files_after_shutdown field exists in the receipt.",
    ],
}
assert before == {str(p): {"bytes": p.stat().st_size, "sha256": digest(p)} for p in inputs}
save("input-manifest.json", before)
save("analysis.json", findings)
print(json.dumps({"outcome": findings["outcome"], "inputs_unchanged": True, "analysis_sha256": digest(OUT / "analysis.json")}))
