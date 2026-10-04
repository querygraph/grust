"""Read closed E0 artifacts without starting an engine or changing their source."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

ROOT = Path("/Volumes/Apo/graph-tests/results/sem-completion-20261003/E0-native-cit-active02")
DESTINATION = ROOT / "review"


def pin(path: Path) -> dict[str, object]:
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text())


def inspect() -> None:
    campaign = load(ROOT / "receipt.json")
    wait = load(ROOT / "wait.json")
    if campaign["outcome"] != "passed_two_native_E0_cit_active_cells" or campaign["qualified_cells"] != 2:
        raise ValueError("review needs both qualified closed cells")
    if not all(campaign[key] for key in ("all_child_groups_absent", "source_unchanged", "lock_released")):
        raise ValueError("campaign source or process closure did not qualify")
    if wait["returncode"] != 0 or not wait["actual_wait_completed"] or not wait["owner_group_absent"]:
        raise ValueError("actual supervisor wait did not qualify")
    rows = []
    details = []
    for cell in campaign["cells"]:
        dataset = cell["dataset"]["name"]
        program = cell["program"]
        raw = ROOT / "raw" / f"{dataset}-{program}"
        producer = load(raw / "cell/receipt.json")
        oracle = load(raw / "oracle.json")
        if cell["status"] != "qualified" or cell["errors"]:
            raise ValueError("cell not qualified")
        if producer["status"] != "completed_unvalidated" or not producer["session_stopped"]:
            raise ValueError("producer not closed")
        if oracle["status"] != "passed_full_physical_oracle" or oracle["mismatch_rows"] != 0:
            raise ValueError("oracle not qualified")
        if oracle["before"] != oracle["after"] or cell["input_before"] != cell["input_after"]:
            raise ValueError("input or output content changed")
        processes = {process["role"]: process for process in cell["processes"]}
        if not all(
            process["actual_wait_completed"] and process["group_absent"] and not process["forced_kill"]
            for process in processes.values()
        ):
            raise ValueError("process closure incomplete")
        if processes["oracle"]["started_utc"] <= max(
            processes["server"]["finished_utc"], processes["client"]["finished_utc"]
        ):
            raise ValueError("oracle overlapped an engine/client")
        output_files = sorted((raw / "cell/result").glob("*.parquet"))
        metadata_rows = sum(pq.ParquetFile(path).metadata.num_rows for path in output_files)
        schema = str(pq.ParquetFile(output_files[0]).schema_arrow)
        if metadata_rows != oracle["vertices"] or metadata_rows != oracle["result_rows"]:
            raise ValueError("output footer total differs from full oracle")
        column = {"pagerank": "pagerank", "sssp": "distance", "landmarks": f"dist_{cell['dataset']['source']}"}[program]
        values = pq.read_table(raw / "cell/result", columns=[column])[column].to_numpy(zero_copy_only=False)
        if program == "pagerank":
            reached = None
            depth = None
            numeric_summary = {
                "sum": float(np.sum(values)),
                "minimum": float(np.min(values)),
                "maximum": float(np.max(values)),
                "null_or_nonfinite": int(np.count_nonzero(~np.isfinite(values))),
            }
        elif program == "sssp":
            reached = int(np.count_nonzero(np.isfinite(values)))
            depth = None
            numeric_summary = {
                "reachable": reached,
                "unreachable": len(values) - reached,
                "maximum_distance": float(np.max(values[np.isfinite(values)])),
            }
        else:
            mask = values != np.iinfo(np.int32).max
            reached = int(np.count_nonzero(mask))
            depth = int(np.max(values[mask]))
            numeric_summary = {"reachable": reached, "unreachable": len(values) - reached, "max_hops": depth}
        steps = producer["iterations"]
        plans = []
        total_nodes = {}
        for path in sorted((raw / "cell").glob("pre-write-relation-step-*.txt")):
            text = path.read_text()
            nodes = {}
            for node in re.findall(r"^\s*([A-Za-z]+Exec)(?::|\s|$)", text, re.MULTILINE):
                nodes[node] = nodes.get(node, 0) + 1
                total_nodes[node] = total_nodes.get(node, 0) + 1
            plans.append(
                {
                    "pin": pin(path),
                    "nodes": nodes,
                    "hash_repartition_lines": [
                        line.strip() for line in text.splitlines() if "RepartitionExec: partitioning=Hash" in line
                    ],
                    "aggregate_lines": [line.strip() for line in text.splitlines() if "AggregateExec:" in line],
                }
            )
        if len(plans) != steps:
            raise ValueError("missing a pre-write superstep plan")
        events = load(raw / "cell/events.json")
        starts = [event for event in events if event["kind"] == "iteration_start"]
        ends = [event for event in events if event["kind"] == "iteration_end"]
        if len(starts) != steps or len(ends) != steps:
            raise ValueError("superstep events incomplete")
        frontiers = [event["frontier_size"] for event in ends if "frontier_size" in event]
        if program != "pagerank" and (len(frontiers) != steps or frontiers[-1] != 0):
            raise ValueError("halting frontier record incomplete")
        maxima = {}
        max_server_client_sum = 0
        samples = 0
        for line in (raw / "rss-500ms.jsonl").read_text().splitlines():
            rss = json.loads(line)
            samples += 1
            current_sum = 0
            for observation in rss["observations"]:
                role, value = observation["role"], observation["rss_bytes"]
                maxima[role] = max(maxima.get(role, 0), value)
                if role in ("server", "client"):
                    current_sum += value
            max_server_client_sum = max(max_server_client_sum, current_sum)
        oracle_seconds = (
            datetime.fromisoformat(processes["oracle"]["finished_utc"])
            - datetime.fromisoformat(processes["oracle"]["started_utc"])
        ).total_seconds()
        if dataset == "kgs" and program == "sssp" and not oracle["official_sssp_passed"]:
            raise ValueError("full official weighted kgs SSSP did not pass")
        row = {
            "dataset": dataset,
            "program": program,
            "source": cell["dataset"]["source"],
            "source_basis": cell["dataset"]["source_basis"],
            "vertices": metadata_rows,
            "effective_edges": oracle["edges"],
            "pipeline_seconds": producer["pipeline_seconds"],
            "algorithm_and_export_seconds": producer["algorithm_and_export_seconds"],
            "client_launch_wait_seconds": cell["client_launch_wait_seconds"],
            "oracle_seconds": oracle_seconds,
            "supersteps": steps,
            "converged": producer["converged"],
            "plans": len(plans),
            "snapshot_writes": 0,
            "staging_writes_source_derived": steps + 2,
            "export_writes": 1,
            "halt_count_actions_source_derived": 0 if program == "pagerank" else steps,
            "normalization_aggregate_actions_source_derived": int(program == "pagerank"),
            "keyless_checkpoint_repartitions": 0,
            "output_files": len(output_files),
            "reachable": reached,
            "max_hops": depth,
            "oracle_max_absolute_difference": oracle["max_absolute_difference"],
            "official_sssp_passed": oracle["official_sssp_passed"],
            "rss_samples": samples,
            "server_sampled_max_rss_bytes": maxima.get("server"),
            "client_sampled_max_rss_bytes": maxima.get("client"),
            "server_client_sampled_max_sum_bytes": max_server_client_sum,
            "oracle_sampled_max_rss_bytes": maxima.get("oracle"),
        }
        rows.append(row)
        details.append(
            {
                "row": row,
                "producer_pin": pin(raw / "cell/receipt.json"),
                "oracle_pin": pin(raw / "oracle.json"),
                "events_pin": pin(raw / "cell/events.json"),
                "rss_pin": pin(raw / "rss-500ms.jsonl"),
                "output_schema": schema,
                "numeric_summary": numeric_summary,
                "frontiers": frontiers,
                "plan_nodes_total": total_nodes,
                "plan_details": plans,
                "official_sssp": oracle["official_sssp"],
            }
        )
    record = {
        "observed_utc": datetime.now(timezone.utc).isoformat(),
        "status": "independent_closed_artifact_review_passed",
        "campaign_pin": pin(ROOT / "receipt.json"),
        "supervisor_wait_pin": pin(ROOT / "wait.json"),
        "source_commit": campaign["source_commit"],
        "source_tree": campaign["source_tree"],
        "runtime_commit": campaign["runtime_commit"],
        "cells": details,
        "action_count_basis": "exact program call sites, not observed engine job IDs",
        "plans": "pre-write updated-relation explain; excludes writer sink and execution metrics",
        "rss": "500ms samples of owned process RSS; not a hard peak or memory-fit certificate",
    }
    (DESTINATION / "closed-cells.json").write_text(json.dumps(record, indent=2) + "\n")
    with (DESTINATION / "closed-cells.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(
            {
                key: row[key]
                for key in (
                    "dataset",
                    "program",
                    "pipeline_seconds",
                    "client_launch_wait_seconds",
                    "supersteps",
                    "reachable",
                    "max_hops",
                    "official_sssp_passed",
                    "oracle_max_absolute_difference",
                    "server_sampled_max_rss_bytes",
                )
            }
        )


if __name__ == "__main__":
    inspect()
