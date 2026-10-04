"""Detached exact-source and historical-metadata gate for an incomplete B8 report."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import subprocess
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SHA = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Shape = Literal["adjacency", "representatives", "min-label-initial-round"]
Variant = Literal["union", "array-explode"]
SHAPES: tuple[Shape, ...] = ("adjacency", "representatives", "min-label-initial-round")
VARIANTS: tuple[Variant, ...] = ("union", "array-explode")
SOURCE = "f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a"
RUNTIME = "56194b170155301ba91077f0ba3df31fe2c78b6b"
NATIVE = "ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73"
HARNESS = "6ae2e43a903c2cee02da170465c922c72b76198e"
PREFIX = "docs/reviews/sem-review-morrobay-2026-10-01/B8/"
OOM: Literal["b8-graph500-24-adjacency-01-union"] = "b8-graph500-24-adjacency-01-union"
ENGINE_BOUNDARY = "supervisor perf_counter immediately before engine Popen through completed wait; startup/session/input snapshots/preparation/explain/writes/cleanup included; oracle follows outside"
HOST_BOUNDARY = "queue started_utc immediately before host-driver Popen through finished_utc after host-driver wait; host orchestration, full oracle, archive/copy and closure overhead included"
MAX_METADATA = 32 * 2**20


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Identity(Record):
    bytes: int = Field(ge=0, le=MAX_METADATA)
    sha256: SHA


class Evidence(Identity):
    path: Path
    kind: Literal["json", "text", "source"]
    json_keys: tuple[str, ...] | None = None


class Index(Record):
    schema_version: Literal[1] = 1
    report_kind: Literal["b8_interim_incomplete"] = "b8_interim_incomplete"
    base: Path
    observed_utc: str
    files: dict[str, Evidence]
    payload_scope: Literal["historical metadata/source only; no Parquet, i64, native binary or raw archive rehash"]


class Cell(Record):
    run_id: str
    shape: Shape
    variant: Variant
    role: Literal["warmup", "measured"]
    measured_block: Literal[1, 2] | None
    sequence: int = Field(ge=1, le=10)
    qualified: Literal[True] = True
    rows: int = Field(ge=1)
    engine_child_launch_to_exit_seconds: float = Field(gt=0)
    host_driver_launch_to_exit_seconds: float = Field(gt=0)
    oracle_seconds_outside_engine_boundary: float = Field(ge=0)
    sampled_engine_pss_peak_bytes: int = Field(ge=1)
    guest_steal_fraction: float = Field(ge=0, le=1)
    evidence_keys: tuple[str, ...]


class Summary(Record):
    shape: Shape
    warmups: Literal[2] = 2
    measured_per_variant: Literal[4] = 4
    ratio_definition: Literal["median(array-explode)/median(union), measured cells only"]
    engine_child_ratio_of_medians: float = Field(gt=0)
    host_driver_ratio_of_medians: float = Field(gt=0)
    engine_child_block_ratios_of_geometric_means: tuple[float, float]
    engine_child_block_ratios_of_medians: tuple[float, float]
    engine_child_ratio_of_geometric_means_all_measured: float = Field(gt=0)
    engine_child_geometric_mean_of_block_median_ratios: float = Field(gt=0)


class GraphFailure(Record):
    run_id: Literal["b8-graph500-24-adjacency-01-union"] = OOM
    role: Literal["warmup"] = "warmup"
    qualified: Literal[False] = False
    original_plan_remaining_not_started: Literal[29] = 29
    qualified_timing_cells: Literal[0] = 0
    ratio: None = None
    outcome: Literal["closed_natural_oom"] = "closed_natural_oom"
    certain_closure: Literal[True] = True
    original_receipts_rewritten: Literal[False] = False
    full_collection_rehashed_by_prior_audit: Literal[True] = True
    allocation_cause: Literal["unexplained"] = "unexplained"
    memory_max_bytes: Literal[34359738368] = 34359738368
    memory_peak_bytes: Literal[34359738368] = 34359738368
    oom_events: Literal[8] = 8
    oom_kill_events: Literal[1] = 1
    raw_host_outcome: Literal["error"] = "error"
    raw_producer_outcome: Literal["oom"] = "oom"
    raw_engine_outcome: Literal["error"] = "error"
    raw_bootstrap_outcome: Literal["checking"] = "checking"
    container_exit_code: Literal[1] = 1
    container_oom_killed: Literal[True] = True
    plan_scope: Literal["pre-write relation explain; excludes Parquet sink wrapper"]
    evidence_keys: tuple[str, ...]


class PayloadIdentity(Record):
    bytes: int = Field(ge=0)
    sha256: SHA


class Citation(Identity):
    path: Path


class DatasetContract(Record):
    vertices: PayloadIdentity
    edges: PayloadIdentity
    vertex_rows: int = Field(ge=1)
    edge_rows: int = Field(ge=0)
    evidence: Citation


class Report(Record):
    schema_version: Literal[1] = 1
    report_kind: Literal["b8_interim_incomplete"] = "b8_interim_incomplete"
    incomplete: Literal[True] = True
    all60_done: Literal[False] = False
    comparison_scope: Literal["isolated relational shapes on shared Morrobay host; not full graph algorithms"]
    snapshot_scope: Literal["original generated-queues02 plan and original closed receipts; any later tail campaign is outside this snapshot"]
    engine_boundary: str = ENGINE_BOUNDARY
    host_boundary: str = HOST_BOUNDARY
    units: Literal["ratios dimensionless; raw retained diagnostics in seconds and bytes"]
    source: str = SOURCE
    runtime: str = RUNTIME
    native: str = NATIVE
    harness: str = HARNESS
    cpus: Literal[16] = 16
    memory_bytes: Literal[34359738368] = 34359738368
    swap_bytes: Literal[0] = 0
    execution: Literal["local, 16 partitions, greedy Sail pool 30GiB, configured native quota 256MiB"]
    configured_native_quota_bytes: Literal[268435456]
    native_reservation_observed: Literal[False]
    actual_native_prepaid_bytes: None
    cit_qualified_cells: Literal[30] = 30
    cit_warmups: Literal[6] = 6
    cit_measured_cells: Literal[24] = 24
    cit_cells: tuple[Cell, ...]
    summaries: tuple[Summary, ...]
    graph500: GraphFailure
    evidence_index: Identity
    dataset_contracts: dict[Literal["cit-Patents", "graph500-24"], DatasetContract]
    limitations: tuple[str, ...]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def bounded(path: Path) -> bytes:
    require(path.is_file() and not path.is_symlink(), "regular nonsymlink file required: " + str(path))
    require(path.stat().st_size <= MAX_METADATA, "metadata/source size bound: " + str(path))
    data = path.read_bytes()
    require(len(data) <= MAX_METADATA, "metadata grew beyond bound")
    return data


def identity(data: bytes) -> Identity:
    return Identity(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def load(index: Index, key: str) -> Any:
    evidence = index.files[key]
    require(evidence.path.is_absolute(), "absolute metadata pin required")
    require(evidence.path.suffix in {".json", ".txt", ".py"}, "payload reads prohibited")
    data = bounded(evidence.path)
    require(identity(data) == Identity(bytes=evidence.bytes, sha256=evidence.sha256), "metadata pin changed: " + key)
    if evidence.kind == "json":
        value = json.loads(data)
        require(isinstance(value, dict) and tuple(value) == evidence.json_keys, "historical JSON schema/key order changed: " + key)
        return value
    return data.decode("utf-8")


def counters(text: str) -> dict[str, int]:
    return {key: int(value) for key, value in (line.split() for line in text.splitlines())}


def expected_steps(dataset: str) -> list[dict[str, object]]:
    variants = ("union", "array-explode", "union", "array-explode", "array-explode", "union", "union", "array-explode", "array-explode", "union")
    slug = dataset.lower()
    return [{"dataset": dataset, "shape": shape, "variant": variant,
             "run_id": f"b8-{slug}-{shape}-{position:02d}-{variant}",
             "role": "warmup" if position <= 2 else "measured", "sequence_within_contrast": position,
             "measured_block": None if position <= 2 else 1 if position <= 6 else 2}
            for shape in SHAPES for position, variant in enumerate(variants, start=1)]


def summarize(cells: tuple[Cell, ...], shape: Shape) -> Summary:
    selected = [cell for cell in cells if cell.shape == shape and cell.role == "measured"]
    groups = {variant: [cell for cell in selected if cell.variant == variant] for variant in VARIANTS}
    require(all(len(group) == 4 for group in groups.values()), "four measured cells per form")
    def ratio(attribute: str, block: int | None, geometric: bool) -> float:
        reducer = statistics.geometric_mean if geometric else statistics.median
        values = {variant: reducer([getattr(cell, attribute) for cell in group if block is None or cell.measured_block == block])
                  for variant, group in groups.items()}
        return values["array-explode"] / values["union"]
    engine = "engine_child_launch_to_exit_seconds"
    block_medians = (ratio(engine, 1, False), ratio(engine, 2, False))
    return Summary(shape=shape, ratio_definition="median(array-explode)/median(union), measured cells only",
                   engine_child_ratio_of_medians=ratio(engine, None, False),
                   host_driver_ratio_of_medians=ratio("host_driver_launch_to_exit_seconds", None, False),
                   engine_child_block_ratios_of_geometric_means=(ratio(engine, 1, True), ratio(engine, 2, True)),
                   engine_child_block_ratios_of_medians=block_medians,
                   engine_child_ratio_of_geometric_means_all_measured=ratio(engine, None, True),
                   engine_child_geometric_mean_of_block_median_ratios=statistics.geometric_mean(block_medians))


def derive(index: Index, index_identity: Identity) -> Report:
    require(index.files["oom_audit"].sha256 == "3d54b21d9440d414d9438c6f673432d615ea10c34ae4e94d7f86140f051c3bbe" and index.files["failed_locks"].sha256 == "e273bf60f30fa82180420c164911400b6dea89b19f0e7f20c940526635624d91", "explicit original closure/preservation source pins")
    plan, queue, graph_queue = (load(index, key) for key in ("plan", "cit_queue", "graph_queue"))
    support = load(index, "support_manifest")
    require(support["controller_sha"] == SOURCE and support["harness_sha"] == HARNESS and all(index.files["support:"+name].sha256 == value for name, value in support["files_sha256"].items()), "frozen source helper inventory")
    expected = expected_steps("cit-Patents")
    require(plan["steps"] == expected + expected_steps("graph500-24"), "exact original 60-step plan")
    require((plan["source"], plan["harness"], plan["runtime"], plan["native"]) == (SOURCE, HARNESS, RUNTIME, NATIVE), "plan source pins")
    require((plan["cpus"], plan["memory_bytes"], plan["swap_bytes"]) == (16, 32*2**30, 0), "plan envelope")
    require(queue["outcome"] == "passed" and queue["finished_utc"] and not queue["lock_retained"] and queue["active_child_pid"] is None and queue["error"] is None, "closed cit queue")
    require([cell["step"] for cell in queue["cells"]] == expected, "all exact30 cit cells required")
    cells: list[Cell] = []
    for item in queue["cells"]:
        step, audit, run = item["step"], item["audit"], item["step"]["run_id"]
        require(item["outcome"] == "passed" and item["returncode"] == 0 and audit["qualified"] is True, "qualified original cell: " + run)
        raw = item["raw_receipts"]
        for name in ("host", "producer", "engine", "container", "bootstrap"):
            require(load(index, run+":"+name) == raw[name], "original embedded receipt differs: " + run+":"+name)
        host, producer, engine = raw["host"], raw["producer"], raw["engine"]
        require(host["archive_verified"] and host["certain_container_closure"] and host["payload_removed"] and not host["lock_retained"] and host["outcome"] == "passed", "closed archived host cell")
        require(producer["outcome"] == engine["outcome"] == "passed" and producer["engine_returncode"] == 0 and producer["engine_wait_completed"] and not producer["outer_timeout"], "engine cell success")
        require(producer["engine_receipt"] == engine and (engine["controller_pin"], engine["runtime_pin"], engine["native_pin"]) == (SOURCE, RUNTIME, NATIVE), "engine receipt/source binding")
        require(engine["config"]["shape"] == step["shape"] and engine["config"]["variant"] == step["variant"] and (engine["config"]["mode"], engine["config"]["partitions"], engine["config"]["pool_bytes"], engine["config"]["native_quota"]) == ("local", 16, 30*2**30, 256*2**20), "actual engine config/envelope")
        require(producer["identities_before"] == producer["identities_after"], "unchanged producer identity receipts")
        require(producer["launch_to_exit_seconds"] == audit["launch_to_exit_seconds"], "engine timing audit binding")
        correctness = producer["correctness"]
        require(correctness["outcome"] == "passed" and correctness["full_oracle"] and correctness["mismatches"] == correctness["duplicate_rows"] == 0 and correctness["rows"] == correctness["unique"] == correctness["expected_rows"] == audit["rows"] and correctness["result_files"] == correctness["result_files_after"], "historical full physical oracle")
        require(not producer["remaining_processes"] and not producer["final_processes"] and not producer["finalization_errors"] and producer["observer_error"] is None and not engine["cleanup_errors"] and not engine["staging_payload_after_shutdown"], "cell lifecycle/observer evidence")
        for snapshot in producer["cgroups"].values():
            require(snapshot["memory.max"] == str(32*2**30) and snapshot["memory.swap.max"] == "0" and snapshot["cpu.max"] == "1600000 100000", "actual cgroup limits")
            events = counters(snapshot["memory.events"])
            require(events["oom"] == events["oom_kill"] == 0, "cit cell OOM absent")
        seconds = (datetime.fromisoformat(item["finished_utc"]) - datetime.fromisoformat(item["started_utc"])).total_seconds()
        cells.append(Cell(run_id=run, shape=step["shape"], variant=step["variant"], role=step["role"], measured_block=step["measured_block"], sequence=step["sequence_within_contrast"], rows=audit["rows"], engine_child_launch_to_exit_seconds=audit["launch_to_exit_seconds"], host_driver_launch_to_exit_seconds=seconds, oracle_seconds_outside_engine_boundary=producer["oracle_seconds"], sampled_engine_pss_peak_bytes=audit["sampled_engine_pss_peak_bytes"], guest_steal_fraction=audit["guest_steal_fraction"], evidence_keys=tuple(run+":"+name for name in ("host", "producer", "engine", "container", "bootstrap", "collection", "removal", "plan"))))
    require(graph_queue["outcome"] == "error" and graph_queue["lock_retained"] and graph_queue["active_child_pid"] is None and [cell["step"] for cell in graph_queue["cells"]] == expected_steps("graph500-24"), "original Graph500 queue/plan binding")
    first = graph_queue["cells"][0]
    require(first["outcome"] == "failed_or_unqualified" and first["returncode"] == 1 and first["child_pid"] is not None and first["started_utc"] and first["finished_utc"], "first original Graph500 warmup failed")
    require(all(cell["outcome"] == "pending" and all(cell[name] is None for name in ("child_pid", "returncode", "started_utc", "finished_utc")) for cell in graph_queue["cells"][1:]), "remaining29 original Graph500 cells never started")
    failure, locks = load(index, "oom_audit"), load(index, "failed_locks")
    require(failure["outcome"] == "closed_natural_oom" and not failure["qualified"] and failure["run_id"] == OOM and failure["certain_closure"] and failure["full_collection_rehashed"] and not failure["original_receipts_rewritten"], "closed unqualified historical OOM")
    require(locks["outcome"] == "original_failed_locks_preserved" and not locks["locks_deleted"] and not locks["receipts_rewritten"] and locks["owner_bytes_preserved"], "original owner records preserved")
    for label in ("gate", "serial"):
        owner = load(index, label+"_owner")
        require(identity(bounded(index.files[label+"_owner"].path)).sha256 == locks["archived_"+label+"_owner"]["sha256"], "archived owner pin")
        require(owner["pid" if label == "gate" else "owner_pid"] == locks["original_child_pid" if label == "gate" else "original_serial_pid"], "owned historical lock identity")
    raw = failure["raw_outcomes"]
    require((raw["host"], raw["producer"], raw["engine"], raw["bootstrap"], raw["container_exit"], raw["container_oom_killed"]) == ("error", "oom", "error", "checking", 1, True), "raw OOM outcomes")
    require(failure["oom_events"]["before"]["oom"] == failure["oom_events"]["before"]["oom_kill"] == 0 and failure["oom_events"]["final"]["oom"] == 8 and failure["oom_events"]["final"]["oom_kill"] == 1, "observed OOM event delta")
    failed_producer = load(index, "oom_producer")
    require(failed_producer["cgroups"]["final"]["memory.peak"] == str(32*2**30), "actual failed peak")
    plan_text = load(index, "oom_plan")
    require("mode=Partial" in plan_text and "Hash([#0@0, #1@1], 16)" in plan_text and "UnionExec" in plan_text, "retained pre-write physical plan")
    evidence = ("oom_audit", "failed_locks", "gate_owner", "serial_owner", "oom_producer", "oom_plan", "graph_queue")
    require(all(cell.guest_steal_fraction == 0 for cell in cells), "original cit zero guest-steal observation")
    return Report(comparison_scope="isolated relational shapes on shared Morrobay host; not full graph algorithms", snapshot_scope="original generated-queues02 plan and original closed receipts; any later tail campaign is outside this snapshot", units="ratios dimensionless; raw retained diagnostics in seconds and bytes", execution="local, 16 partitions, greedy Sail pool 30GiB, configured native quota 256MiB", configured_native_quota_bytes=268435456, native_reservation_observed=False, actual_native_prepaid_bytes=None, cit_cells=tuple(cells), summaries=tuple(summarize(tuple(cells), shape) for shape in SHAPES), graph500=GraphFailure(plan_scope="pre-write relation explain; excludes Parquet sink wrapper", evidence_keys=evidence), evidence_index=index_identity, dataset_contracts=queue["prerequisite_observations"]["dataset_contracts"], limitations=("Six warmups qualify correctness and lifecycle but are excluded from summaries; each shape has two UAAU measured blocks.", "Raw diagnostic seconds are retained for reconstruction; shared-host publication reports ratios, not absolute performance.", "Guest steal_fraction was 0.0 for all 30 closed cit cells; this does not establish a dedicated host.", "Representatives is a first contraction-round endpoint map, not a complete WCC partition; min-label is a separately named whole initial-update rewrite.", "No Graph500 qualified timing or ratio; allocation cause unexplained. Partial distinct and 16-way hash exchange are plan observations only.", "Native quota 256MiB is configured; actual native reservation/prepayment and allocated bytes were not observed and remain pending.", "No full-algorithm result, generic 32GiB admission or native retained-memory fit claim follows.", "Historical full payload/oracle/archive qualification is cited, not rerun; this gate rechecks only exact source and metadata.", "Frozen complete-publication helpers do not understand tail mappings/skips; this artifact is explicitly incomplete."))


class SourceManifest(Record):
    schema_version: Literal[1] = 1
    files: dict[str, Identity]
    evidence_index: str
    report: str


class GateReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    started_utc: str
    finished_utc: str | None = None
    outcome: Literal["checking", "passed", "error"] = "checking"
    commit: str
    tree: str
    parent: str
    manifest: Identity
    codex_entry: Identity
    checked_metadata_files: int = 0
    scope: str = "Detached exact report files/codex append and prior historical metadata; no engines, Docker, payload or oracle rerun; interim only."
    error: str | None = None
    traceback: str | None = None


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def git(repo: Path, *args: str) -> bytes:
    process = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    require(process.returncode == 0, "read-only git failed: " + " ".join(args) + ": " + process.stderr.decode("utf-8", errors="replace"))
    return process.stdout


def source_guard(repo: Path, commit: str, tree: str, parent: str) -> None:
    require(git(repo, "rev-parse", "HEAD").decode().strip() == commit, "actual HEAD differs")
    require(git(repo, "rev-parse", "HEAD^{tree}").decode().strip() == tree, "actual tree differs")
    require(git(repo, "rev-list", "--parents", "-n", "1", "HEAD").decode().split() == [commit, parent], "exact single parent required")
    require(not git(repo, "status", "--porcelain", "--untracked-files=all").strip(), "detached gate checkout not clean")
    branch = subprocess.run(["git", "-C", str(repo), "symbolic-ref", "--quiet", "HEAD"], capture_output=True, check=False)
    require(branch.returncode == 1 and not branch.stdout, "gate HEAD must be detached")


def save(path: Path, receipt: GateReceipt) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as stream:
        stream.write(receipt.model_dump_json(indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def verify(args: argparse.Namespace) -> int:
    require(args.repo.is_absolute() and args.repo.is_dir(), "absolute existing detached repository path required")
    for value in (args.commit, args.tree, args.parent):
        require(re.fullmatch(r"[0-9a-f]{40}", value) is not None, "full commit/tree/parent SHA required")
    manifest_data, entry = bounded(args.manifest), bounded(args.codex_entry)
    require(identity(manifest_data).sha256 == args.manifest_sha256 and identity(entry).sha256 == args.codex_entry_sha256, "external gate configuration pins")
    require(args.output.is_absolute() and not args.output.exists() and not args.output.is_relative_to(args.repo), "fresh external gate receipt path required")
    receipt = GateReceipt(started_utc=utc(), commit=args.commit, tree=args.tree, parent=args.parent, manifest=identity(manifest_data), codex_entry=identity(entry))
    save(args.output, receipt)
    try:
        manifest = SourceManifest.model_validate_json(manifest_data)
        require(manifest.evidence_index == PREFIX+"interim-evidence-pins.json" and manifest.report == PREFIX+"interim-findings.json" and {manifest.evidence_index, manifest.report, PREFIX+"sem_b8_interim_gate.py"} <= set(manifest.files), "exact report/index/gate paths bound by source manifest")
        source_guard(args.repo, args.commit, args.tree, args.parent)
        changed = git(args.repo, "diff-tree", "--no-commit-id", "--name-status", "-r", args.parent, args.commit).decode().splitlines()
        actual = {row.split("\t")[1]: row.split("\t")[0] for row in changed}
        require(set(actual) == set(manifest.files) | {"codex-to-codex.md"} and all(status in {"A", "M"} for status in actual.values()), "exact allowed source file delta")
        for relative, expected in manifest.files.items():
            require(relative.startswith(PREFIX) and ".." not in Path(relative).parts, "report path scope")
            path = args.repo / relative
            require(identity(bounded(path)) == expected, "exact staged report/helper file identity: " + relative)
            require(git(args.repo, "show", args.commit+":"+relative) == bounded(path), "source blob differs from checkout")
            require(git(args.repo, "ls-tree", args.commit, "--", relative).decode().startswith("100644 blob "), "regular tracked report/source mode")
        require(Path(__file__).resolve() == (args.repo / (PREFIX+"sem_b8_interim_gate.py")).resolve(), "actual gate module origin")
        codex_before = git(args.repo, "show", args.parent+":codex-to-codex.md")
        require(bounded(args.repo/"codex-to-codex.md") == codex_before + entry and entry.startswith(b"\n## ") and b"B8 interim" in entry, "only exact owned codex append permitted")
        index_data = bounded(args.repo/manifest.evidence_index)
        index = Index.model_validate_json(index_data)
        for key in index.files:
            load(index, key)
        receipt.checked_metadata_files = len(index.files)
        report_data = bounded(args.repo/manifest.report)
        raw_report = json.loads(report_data)
        require(raw_report.get("incomplete") is True and raw_report.get("all60_done") is False and raw_report.get("report_kind") == "b8_interim_incomplete", "explicit interim fields required in machine JSON")
        report = Report.model_validate_json(report_data)
        require(report == derive(index, identity(index_data)), "report differs from exact historical metadata/ratio derivation")
        require(not report.all60_done and report.incomplete and report.report_kind == "b8_interim_incomplete", "interim cannot become complete publication")
        for key in index.files:
            load(index, key)
        source_guard(args.repo, args.commit, args.tree, args.parent)
        require(identity(bounded(args.manifest)) == receipt.manifest and identity(bounded(args.codex_entry)) == receipt.codex_entry, "gate configuration changed")
        receipt.outcome = "passed"
    except (Exception, KeyboardInterrupt, SystemExit) as error:  # noqa: BLE001
        receipt.outcome, receipt.error, receipt.traceback = "error", repr(error), traceback.format_exc()
    finally:
        receipt.finished_utc = utc()
        save(args.output, receipt)
    return 0 if receipt.outcome == "passed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--tree", required=True)
    parser.add_argument("--parent", required=True)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--codex-entry", required=True, type=Path)
    parser.add_argument("--codex-entry-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return verify(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
