"""Summarize the frozen queue only after its complete, passing closure.

Reads retained evidence without changing it or contacting Docker. Raw timing
cells are diagnostic evidence; the comparison is ratios on a shared host.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import cast

type Json = None | bool | int | float | str | list[Json] | dict[str, Json]
HERE = Path(__file__).resolve().parent
HOST = Path("/Users/alexy/src/sail-extensions-gates/pecan-typed-tests-20261001")
REPORT = HERE / "morrobay-20261001"
SUPPORT = "0f378b86d2feaa93413d1fe573eef524c110f1c019f2dace955c22d1a8f5dc39"
RUNTIME = "56194b170155301ba91077f0ba3df31fe2c78b6b"
NATIVE = "ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73"
BINARY = "5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec"
IMAGE = "sha256:f3518d652fbea8b9b9f9ebf9849277ca3bd39d0c21bb2c6e36fbaeaa2dc2678e"
GIB = 2**30


@dataclass(frozen=True, slots=True)
class Step:
    run_id: str
    kind: str
    mode: str
    revision: str
    role: str


@dataclass(frozen=True, slots=True)
class Cell:
    step: Step
    outcome: str
    source: str
    timings: dict[str, Json]
    execute_pss_peak_bytes: int | None
    lifetime_cgroup_peak_bytes: int | None
    guest_steal_fraction: float | None
    rounds: dict[str, Json]
    oracle: dict[str, Json]
    resources: dict[str, Json]
    boundaries: dict[str, Json]
    host_pressure: dict[str, Json]
    evidence: dict[str, Json]


@dataclass(frozen=True, slots=True)
class Comparison:
    mode: str
    metric: str
    baseline_values: list[float]
    candidate_values: list[float]
    baseline_median: float
    candidate_median: float
    candidate_over_baseline: float


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def obj(value: Json) -> dict[str, Json]:
    require(isinstance(value, dict), "expected JSON object")
    return cast(dict[str, Json], value)


def array(value: Json) -> list[Json]:
    require(isinstance(value, list), "expected JSON array")
    return cast(list[Json], value)


def string(value: Json) -> str:
    require(isinstance(value, str), "expected JSON string")
    return cast(str, value)


def number(value: Json) -> float:
    require(type(value) in (int, float), "expected JSON number")
    result = float(cast(int | float, value))
    require(math.isfinite(result), "nonfinite measurement")
    return result


def read(path: Path) -> dict[str, Json]:
    require(path.is_file() and not path.is_symlink(), f"missing/unsafe evidence: {path}")
    return obj(cast(Json, json.loads(path.read_text())))


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def pressure(before: dict[str, Json], after: dict[str, Json],
             orchestration: dict[str, Json]) -> dict[str, Json]:
    """Keep raw host pressure records and a small factual presentation."""
    summary: dict[str, Json] = {"host_load_before": orchestration["host_load_before"]}
    for phase, record in (("before", before), ("after", after)):
        swap = obj(record["swap"])
        vm = obj(record["vm_stat"])
        require(swap["returncode"] == vm["returncode"] == 0, "host pressure probe failed")
        used = re.search(r"used\s*=\s*([0-9.]+)M", string(swap["stdout"]))
        free = re.search(r"Pages free:\s*([0-9]+)\.", string(vm["stdout"]))
        page = re.search(r"page size of ([0-9]+) bytes", string(vm["stdout"]))
        require(used is not None and free is not None and page is not None,
                "unrecognized host pressure record")
        if used is not None and free is not None and page is not None:
            summary[f"swap_used_mib_{phase}"] = float(used.group(1))
            summary[f"free_page_bytes_{phase}"] = int(free.group(1)) * int(page.group(1))
    return {"summary": summary, "before": before, "after": after}


def read_cell(step: Step, heads: dict[str, Json]) -> Cell:
    output = HOST / step.run_id
    names = ("result.json", "diagnostics/receipt.json", "collection.json",
             "container/orchestration.json", "admission.json", "host-before.json", "host-after.json")
    records = {name: read(output / name) for name in names}
    result, producer = records["result.json"], records["diagnostics/receipt.json"]
    orchestration, collection = records["container/orchestration.json"], records["collection.json"]
    args = obj(producer["arguments" if step.kind == "wcc" else "options"])
    require(result["run_id"] == step.run_id and args["mode"] == step.mode,
            f"run identity mismatch: {step.run_id}")
    require(args["controller_sha"] == result["source"] == heads[step.revision],
            f"controller mismatch: {step.run_id}")
    require(args["repo"] == f"/targets/pecan-typed-tests-20261001/{step.revision}"
            and args["output"] == f"/targets/pecan-typed-tests-20261001/cells/{step.run_id}",
            f"source/output boundary mismatch: {step.run_id}")
    require(result["outcome"] == producer["outcome"] == "passed"
            and result["producer_outcome"] == "passed" and result["lock_retained"] is False,
            f"non-pass or retained lock: {step.run_id}")
    state = obj(result["container_state"])
    inspection = obj(orchestration["inspect"])
    require(state["ExitCode"] == 0 and state["Running"] is False and state["OOMKilled"] is False
            and inspection["state"] == state, f"uncertain container closure: {step.run_id}")
    require(orchestration["attach_returncode"] == 0 and obj(orchestration["remove"])["returncode"] == 0
            and orchestration["outer_timeout"] is False and not orchestration["transport_errors"]
            and not producer["cleanup_errors"], f"incomplete shutdown: {step.run_id}")
    require(inspection["image"] == IMAGE and collection["returncode"] == 0
            and sha(output / "diagnostics.tar") == collection["sha256"],
            f"collection/image mismatch: {step.run_id}")
    admission = records["admission.json"]
    require(admission["returncode"] == 0, f"admission failed: {step.run_id}")
    require(result["no_absolute_performance_claim"] is True, "missing shared-host restriction")
    audit = read(REPORT / f"{step.run_id}-audit.json")
    require(audit["step"] == asdict(step) and audit["outcome"] == "passed"
            and audit["container_removed"] is True and audit["lock_cleared"] is True,
            f"driver audit mismatch: {step.run_id}")
    bundle = read(REPORT / f"{step.run_id}-bundle.json")
    require(bundle["step"] == asdict(step)
            and sha(REPORT / string(bundle["bundle"])) == bundle["bundle_sha256"],
            f"retained bundle mismatch: {step.run_id}")
    evidence: dict[str, Json] = {
        "host_directory": str(output), "retained_archive": bundle["archive"],
        "bundle": bundle["bundle"], "bundle_sha256": bundle["bundle_sha256"],
        "diagnostics_tar_sha256": collection["sha256"],
        "records_sha256": {name: sha(output / name) for name in names},
        "admission": admission, "container_state": state,
        "container_removed": True, "lock_cleared": True,
    }
    host = pressure(records["host-before.json"], records["host-after.json"], orchestration)
    if step.kind == "smoke":
        return Cell(step, "passed", string(result["source"]), {}, None, None, None,
                    {}, {name: producer[name] for name in ("sssp", "bfs", "wcc")}, {}, {}, host, evidence)
    pins, identities = obj(producer["source_pins"]), obj(producer["identities"])
    identity = obj(identities["before"])
    require(pins["runtime"] == RUNTIME and pins["native"] == NATIVE
            and pins["controller"] == heads[step.revision]
            and identity["binary_sha256"] == BINARY and identities["before"] == identities["after"]
            and producer["inputs_before"] == producer["inputs_after"],
            f"changed source/input/runtime: {step.run_id}")
    oracle, timings = obj(producer["correctness"]), obj(producer["timings"])
    require(oracle["rows"] == oracle["unique"] == 3774768
            and oracle["membership_mismatches"] == 0 and oracle["components"] == 3627
            and oracle["largest_component_vertices"] == 3764117,
            f"physical oracle failed: {step.run_id}")
    rounds, memory, cgroups = obj(producer["rounds"]), obj(producer["memory"]), obj(producer["cgroups"])
    require(not rounds["incomplete_rounds"] and timings["converged"] is True
            and len(array(rounds["completed_round_durations"])) == timings["iterations"],
            f"incomplete rounds: {step.run_id}")
    require(memory["error"] is None and memory["execution_sampled"] is True
            and memory["thread_alive"] is False and producer["error"] is None
            and producer["integrity_error"] is None and not producer["staging_files_after_shutdown"],
            f"incomplete diagnostics: {step.run_id}")
    final_cgroup = obj(cgroups["after"])
    events = dict(line.split() for line in string(final_cgroup["memory.events"]).splitlines())
    require(int(events["oom"]) == int(events["oom_kill"]) == 0, f"OOM: {step.run_id}")
    pss = int(number(obj(obj(memory["phase_peaks"])["execute"])["pss_bytes"]))
    lifetime = int(string(final_cgroup["memory.peak"]))
    steal = number(producer["guest_steal_fraction"])
    require(0 <= steal <= 1 and pss > 0 and lifetime > 0, "invalid memory/steal measurement")
    evidence.update(source_pins=pins, inputs_sha256=producer["inputs_before"],
                    identities=identity, packages=producer["packages"], memory=memory, cgroups=cgroups)
    return Cell(step, "passed", string(result["source"]), timings, pss, lifetime, steal,
                rounds, oracle, obj(producer["resources"]), obj(producer["boundaries"]), host, evidence)


def metric(cell: Cell, name: str) -> float:
    if name == "execute_pss_peak_bytes":
        require(cell.execute_pss_peak_bytes is not None, "missing sampled PSS")
        return float(cast(int, cell.execute_pss_peak_bytes))
    if name == "lifetime_cgroup_peak_bytes":
        require(cell.lifetime_cgroup_peak_bytes is not None, "missing lifetime cgroup peak")
        return float(cast(int, cell.lifetime_cgroup_peak_bytes))
    return number(cell.timings[name])


def comparisons(cells: list[Cell]) -> list[Comparison]:
    result: list[Comparison] = []
    for mode in ("local", "process-cluster"):
        measured = [cell for cell in cells if cell.step.mode == mode and cell.step.role == "measured"]
        for name in ("end_to_end_seconds", "input_snapshot_seconds",
                     "execute_pss_peak_bytes", "lifetime_cgroup_peak_bytes"):
            baseline = [metric(cell, name) for cell in measured if cell.step.revision == "baseline"]
            candidate = [metric(cell, name) for cell in measured if cell.step.revision == "candidate"]
            require(len(baseline) == len(candidate) == 2, f"incomplete measured class: {mode}")
            a, b = median(baseline), median(candidate)
            require(a > 0 and b > 0, f"invalid ratio inputs: {mode}/{name}")
            result.append(Comparison(mode, name, baseline, candidate, a, b, b / a))
    return result


def audit_queue() -> tuple[dict[str, Json], list[Cell], list[Comparison]]:
    plan, closure = read(HERE / "plan.json"), read(REPORT / "receipt.json")
    require(closure["outcome"] == "passed" and closure["failure"] is None
            and closure["remaining"] == [] and closure["host"] == "morrobay"
            and closure["shared_host_ratios_only"] is True, "driver queue is not completely passed")
    require(closure["plan_sha256"] == sha(HERE / "plan.json")
            and closure["support_sha256"] == plan["support_sha256"] == SUPPORT
            and closure["driver_sha256"] == sha(HERE / "execute_morrobay.py"), "driver/plan pin mismatch")
    steps = [Step(**{key: string(value) for key, value in obj(raw).items()})
             for raw in array(plan["steps"])]
    require(len(steps) == 14 and len({step.run_id for step in steps}) == 14, "unexpected frozen plan")
    completed = array(closure["completed"])
    require(len(completed) == len(steps), "driver did not close every step")
    for step, raw in zip(steps, completed, strict=True):
        record = obj(raw)
        require(record["step"] == asdict(step) and record["outcome"] == "passed"
                and record["container_removed"] is True and record["lock_cleared"] is True,
                f"non-pass driver step: {step.run_id}")
    cells = [read_cell(step, obj(plan["controller_commits"])) for step in steps]
    wcc = [cell for cell in cells if cell.step.kind == "wcc"]
    require(len(wcc) == 12 and len([cell for cell in cells if cell.step.role == "warmup"]) == 4,
            "missing smoke/warmup/WCC evidence")
    for cell in wcc:
        require(cell.boundaries == wcc[0].boundaries, "unequal timing boundary")
        require(cell.evidence["inputs_sha256"] == wcc[0].evidence["inputs_sha256"], "unequal input hashes")
        for key in ("cpus", "memory_bytes", "partitions", "log_filter", "sampler_interval_seconds"):
            require(cell.resources[key] == wcc[0].resources[key], f"unequal common envelope: {key}")
    return closure, cells, comparisons(cells)


def format_metric(value: float, name: str) -> str:
    return f"{value / GIB:.2f} GiB" if name.endswith("_bytes") else f"{value:.2f} s"


def cell_table(cells: list[Cell]) -> list[str]:
    lines = ["| Run | Revision | Public/export s | Snapshot s | Execute PSS GiB | Lifetime cgroup GiB | Rounds | Guest steal |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for cell in cells:
        lines.append(f"| `{cell.step.run_id}` | {cell.step.revision} | "
                     f"{number(cell.timings['end_to_end_seconds']):.2f} | "
                     f"{number(cell.timings['input_snapshot_seconds']):.2f} | "
                     f"{cast(int, cell.execute_pss_peak_bytes) / GIB:.2f} | "
                     f"{cast(int, cell.lifetime_cgroup_peak_bytes) / GIB:.2f} | "
                     f"{cell.timings['iterations']} | {cast(float, cell.guest_steal_fraction) * 100:.2f}% |")
    return lines


def markdown(cells: list[Cell], ratios: list[Comparison], recorded: str) -> str:
    lines = ["# Typed Pecan comparison on Morrobay", "", f"Recorded: {recorded}.", "",
             "All 14 frozen steps passed: two compatibility smokes, four warmups and eight measured cells. "
             "Their producer receipts, physical oracle and container closure were checked before this summary.", "",
             "These are **candidate/baseline ratios on a shared host**, with two samples per revision "
             "in each execution class. The medians describe this queue; they do not establish statistical "
             "confidence or isolate the contribution of individual controller changes.", "",
             "The process cluster uses three Sail processes inside one container on one host. "
             "This queue tests the two pinned Python controllers with the same existing Linux runtime binary. "
             "It does not test a runtime rebuilt from the candidate commit, multi-host scaling or maximum scale.", "",
             "## Pins and boundaries", "",
             f"- Baseline controller: `{next(cell.source for cell in cells if cell.step.revision == 'baseline')}`.",
             f"- Candidate controller: `{cells[0].source}`.",
             f"- Runtime source: `{RUNTIME}`; binary SHA-256: `{BINARY}`.",
             f"- Native source: `{NATIVE}`; Docker image: `{IMAGE}`.",
             "- cit-Patents: 3,774,768 vertices, 16,518,947 edges; WCC `randomized_fused`.",
             "- Each cell: 16 CPUs, 32 GiB container memory, no swap, 16 partitions. "
             "Local pool 24 GiB; process cluster three 8 GiB nominal pools.", "",
             "The public timer begins after creation of lazy input handles and includes public WCC plus "
             "complete result export and observer overhead. Startup, input hashing and physical verification "
             "are outside that timer. Snapshot time is a subset of public time, not an extra phase to add.", "",
             "Execute PSS is the sampled sum of proportional process memory during execute, with a one-second "
             "delay after each scan. The cgroup peak is a container lifetime peak including page cache and "
             "allocator overhead; it is not the same scope or phase as execute PSS. Guest steal covers the "
             "whole Linux VM during the server lifecycle and does not prove an idle host.", "",
             "## Measured comparison", "",
             "A ratio below 1 means the candidate's median is lower for that metric; above 1 means higher. "
             "Raw seconds and GiB below are retained diagnostic cells, not dedicated-host performance ratings.", "",
             "| Execution class | Metric | Baseline median | Candidate median | Candidate / baseline |",
             "| --- | --- | ---: | ---: | ---: |"]
    for ratio in ratios:
        lines.append(f"| {ratio.mode} | `{ratio.metric}` | "
                     f"{format_metric(ratio.baseline_median, ratio.metric)} | "
                     f"{format_metric(ratio.candidate_median, ratio.metric)} | "
                     f"{ratio.candidate_over_baseline:.2f} |")
    for mode in ("local", "process-cluster"):
        lines.extend(["", f"### Every measured {mode} cell", ""])
        lines.extend(cell_table([cell for cell in cells if cell.step.role == "measured" and cell.step.mode == mode]))
    lines.extend(["", "## Warmups", "", "Warmups are retained and excluded from the ratios.", ""])
    lines.extend(cell_table([cell for cell in cells if cell.step.role == "warmup"]))
    lines.extend(["", "## Exact physical result and closure", "",
                  "All 12 cit-Patents WCC cells delivered exactly 3,774,768 unique vertices, "
                  "zero membership mismatches and 3,627 components; the largest component has 3,764,117 vertices. "
                  "The frozen independent PyArrow oracle requires exactly `id:int64, component:int64`, "
                  "non-null values and the exact minimum original vertex ID for every component. "
                  "The two smokes also passed SSSP, BFS and WCC on sparse signed IDs, an isolate and zero-weight ties.", "",
                  "Every container exited with status 0, without OOM, and was removed; every cell lock was cleared. "
                  "Input, controller, runtime and native identity checks passed. Round durations, hashes, "
                  "raw host pressure before/after, guest admission and phase memory details are in "
                  "[comparison-summary.json](comparison-summary.json).", "",
                  "### Host pressure observed", "",
                  "Mac host swap use and free pages are observations, not proof of active paging or "
                  "a dedicated host. Full `vm_stat`, swap and uptime output remains in each evidence bundle.", "",
                  "| Run | Load before (1/5/15 min) | Swap used before / after MiB | Free pages before / after GiB |",
                  "| --- | --- | ---: | ---: |"])
    for cell in cells:
        host = obj(cell.host_pressure["summary"])
        load = "/".join(f"{number(value):.2f}" for value in array(host["host_load_before"]))
        lines.append(f"| `{cell.step.run_id}` | {load} | "
                     f"{number(host['swap_used_mib_before']):.0f} / {number(host['swap_used_mib_after']):.0f} | "
                     f"{number(host['free_page_bytes_before']) / GIB:.2f} / "
                     f"{number(host['free_page_bytes_after']) / GIB:.2f} |")
    lines.extend(["", "## All frozen outcomes and retained evidence", "",
                  "The lossless repository bundles include raw logs, memory samples, receipts and closure "
                  "records. The duplicate diagnostics tar is retained separately in the Apo archive.", "",
                  "| Run | Role | Class | Outcome | Evidence |", "| --- | --- | --- | --- | --- |"])
    for cell in cells:
        bundle = string(cell.evidence["bundle"])
        lines.append(f"| `{cell.step.run_id}` | {cell.step.role} | {cell.step.mode} | passed | "
                     f"[bundle]({bundle}), [audit]({cell.step.run_id}-audit.json) |")
    lines.extend(["", "Driver closure: [receipt.json](receipt.json). Summarizer: "
                  "[summarize_morrobay.py](../summarize_morrobay.py).", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="audit complete evidence without writing reports")
    options = parser.parse_args()
    closure, cells, ratios = audit_queue()
    if options.check:
        print("PASS: all 14 frozen outcomes and retained closures; no report written")
        return 0
    json_path, markdown_path = REPORT / "comparison-summary.json", REPORT / "COMPARISON.md"
    require(not json_path.exists() and not markdown_path.exists(), "summary output already exists")
    recorded = datetime.now(timezone.utc).isoformat()
    report = dict(recorded_utc=recorded, outcome="passed", host="morrobay", shared_host_ratios_only=True,
                  sample_count_per_revision_per_class=2, driver_closure=closure,
                  summarizer_sha256=sha(Path(__file__)),
                  cells=[asdict(cell) for cell in cells], comparisons=[asdict(ratio) for ratio in ratios])
    rendered = markdown(cells, ratios, recorded)
    with json_path.open("x") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    with markdown_path.open("x") as stream:
        stream.write(rendered)
    print(f"PASS: wrote {json_path} and {markdown_path}; 14 outcomes, 8 measured cells")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
