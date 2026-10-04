#!/usr/bin/env python3
"""Bounded controller-only follow-up: weighted64k, warmup AB, measured ABBA.

Reads the completed 16k plan/receipts and reuses its immutable gate3 runtime and
source trees. Creates only a fresh output root and bounded fixture in the VM.
Without --execute this prints a plan and launches no containers.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

import run_pecan_gate3 as shared

ROOT = "/targets/sail-stream-experiments-20260930/pecan64k-controller"
HOST = "/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930/pecan64k-controller"
DATASET = "weighted64k"
VERTICES, DEGREE = 65536, 64


def expected_edges(vertices, degree):
    # Six fixed edges, degree random edges per non-isolate, extra node->0 per third node.
    return 6 + (vertices - 1) * degree + (vertices + 1) // 3


def schedule():
    return [dict(id=f"{kind}-{i+1}-{label}", kind=kind, label=label, mode="process-cluster")
            for kind, labels in (("warmup", ("base", "candidate")),
                                 ("measured", ("base", "candidate", "candidate", "base")))
            for i, label in enumerate(labels)]


def validate_prior(prior):
    fixed = shared.config()
    for key in ("image", "docker_context", "target_volume", "container_python", "container_repo", "harness_source_sha",
                "container_sail_binary", "runtime_source_sha", "native_source_sha",
                "limits", "defaults", "extra_cell_args"):
        if prior[key] != fixed[key]:
            raise ValueError(f"preceding configuration changed fixed {key}")


def cell_config(prior, label, root, output):
    validate_prior(prior)
    cfg = copy.deepcopy(shared.source_config(prior, label))
    cfg.update(run_id="pecan64k-controller", container_root=root, host_output=str(output),
        datasets={DATASET: dict(family="traversal", vertices=VERTICES, degree=DEGREE,
                                seed=42, source=0, directed=True)})
    return cfg


def command(matrix, prior, cell, root, output):
    cfg = cell_config(prior, cell["label"], root, output)
    return matrix.cell_command(cfg, dict(cell_id=cell["id"], dataset=DATASET,
        engine="pecan", algorithm="sssp", variant="frontier", mode=cell["mode"],
        repeat=0, max_iterations=100))


def prior_ready(summary):
    cells = summary.get("cells", [])
    expected = {c["id"] for c in shared.schedule()}
    return (len(cells) == len(expected) and {c.get("id") for c in cells} == expected
        and all(c.get("outcome") and c["outcome"] != "started" for c in cells)
        and all(c["outcome"] == "passed" for c in cells
                if c.get("kind") == "integration" and c.get("label") == "candidate"))


def validate_fixture(fixture):
    assert fixture["family"] == "traversal" and fixture["seed"] == 42
    assert fixture["counts"] == dict(vertices=VERTICES, edges=expected_edges(VERTICES, DEGREE))
    assert fixture["parameters"] == dict(degree=DEGREE, source=0, directed=True)
    assert set(fixture["files"]) == {"vertices.parquet", "edges.parquet", "reference.parquet"}


def identities(summary):
    trials = [c for c in summary["cells"] if c["kind"] != "integration" and c["outcome"] == "passed"]
    values = {}
    for name in ("binary_sha256", "native_identity_sha256"):
        found = {c[name] for c in trials}
        assert len(found) == 1 and None not in found, f"preceding successful trials disagree on {name}"
        values[name] = found.pop()
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--prior-plan", type=Path, required=True)
    parser.add_argument("--root", default=ROOT)
    parser.add_argument("--output", type=Path, default=Path(HOST))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    os.environ["PATH"] = "/usr/local/bin:/opt/homebrew/bin:" + os.environ.get("PATH", "")
    sys.path.insert(0, str(args.matrix.resolve()))
    import run_matrix as matrix
    prior_plan = json.loads(args.prior_plan.read_text())
    prior = prior_plan["configuration"]
    assert args.root != prior["container_root"] and not args.root.startswith(prior["container_root"] + "/")
    assert args.prior_plan.parent.resolve() not in (args.output.resolve(), *args.output.resolve().parents)
    cfg = cell_config(prior, "base", args.root, args.output)
    plan = dict(configuration=cfg, prior_plan=str(args.prior_plan.resolve()),
        prior_plan_sha256=hashlib.sha256(args.prior_plan.read_bytes()).hexdigest(),
        script_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in (Path(__file__).resolve(), Path(shared.__file__).resolve())},
        matrix_files_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in sorted(args.matrix.glob("*.py"))},
        boundary="controller-only comparison; unchanged ffcf runtime/native; shared-host ratios, no absolute performance claim",
        order="two excluded warmups A,B; four measured ABBA; fresh container/server for every cell",
        expected_edges=expected_edges(VERTICES, DEGREE),
        preparation_command=matrix.dataset_command(cfg, DATASET),
        cells=[dict(c, configuration=cell_config(prior, c["label"], args.root, args.output),
                    command=command(matrix, prior, c, args.root, args.output)) for c in schedule()])
    assert plan["matrix_files_sha256"] == prior_plan["matrix_files_sha256"], "matrix harness changed"
    assert plan["script_sha256"]["run_pecan_gate3.py"] == prior_plan["script_sha256"]["run_pecan_gate3.py"], "shared runner changed"
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return 0
    summary = json.loads((args.prior_plan.parent / "summary.json").read_text())
    assert prior_ready(summary), "preceding suite incomplete or candidate integration failed"
    expected_identity = identities(summary)
    assert shutil.disk_usage(args.output.parent).free >= 2 * 1024**3
    args.output.mkdir(parents=True, exist_ok=False)
    plan.update(preceding_outcomes=summary["cells"], expected_identity=expected_identity)
    shared.save(args.output / "plan.json", plan)
    init = "from pathlib import Path; import shutil,sys; assert shutil.disk_usage('/targets').free >= 8*1024**3; Path(sys.argv[1]).mkdir(parents=True,exist_ok=False)"
    setup = matrix.run_container(cfg, "sail-pecan64k-precheck", ["-I", "-c", init, args.root],
        args.output / "precheck", cfg["image"], 120, {})
    assert setup.get("attach_returncode") == 0 and not setup["transport_errors"], "precheck failed"
    for label in ("base", "candidate"):
        matrix.preflight(cell_config(prior, label, args.root, args.output), args.output / ("preflight-" + label))
    prep = matrix.run_container(cfg, "sail-pecan64k-prepare", plan["preparation_command"],
        args.output / "prepare", cfg["image"], 600, {})
    assert prep.get("attach_returncode") == 0 and not prep["transport_errors"], "fixture preparation failed; orchestration retained"
    shared.collect(matrix, cfg, args.root + "/datasets/" + DATASET, args.output / "dataset")
    fixture = json.loads((args.output / "dataset/manifest.json").read_text())
    validate_fixture(fixture)
    records = []
    for cell in schedule():
        cell_cfg = cell_config(prior, cell["label"], args.root, args.output)
        output = args.output / cell["id"]
        record = matrix.run_container(cell_cfg, "sail-pecan64k-" + cell["id"],
            command(matrix, prior, cell, args.root, args.output), output, cfg["image"], 1350, {})
        receipt = None
        try:
            shared.collect(matrix, cell_cfg, args.root + "/cells/" + cell["id"], output / "diagnostics")
            receipt = json.loads((output / "diagnostics/receipt.json").read_text())
        except Exception as error:
            record["receipt_read_error"] = repr(error)
        outcome = matrix.classify(record, receipt, cell_cfg["harness_source_sha"])
        raw = receipt or {}
        actual_identity = dict(binary_sha256=raw.get("binary_sha256"),
            native_identity_sha256=hashlib.sha256(json.dumps(raw.get("native_package_identity"), sort_keys=True).encode()).hexdigest())
        mismatches = []
        if receipt is not None:
            if raw.get("dataset") != fixture:
                mismatches.append("dataset_mismatch")
            mismatches.extend(name + "_mismatch" for name, value in expected_identity.items()
                              if actual_identity[name] != value)
        row = dict(cell, outcome="identity_mismatch" if outcome == "passed" and mismatches else outcome,
            receipt_outcome=raw.get("outcome"), validation_mismatches=mismatches,
            correctness=raw.get("correctness"), **actual_identity,
            execution_seconds=raw.get("end_to_end_seconds"),
            execute_memory=raw.get("memory", {}).get("phase_peaks", {}).get("execute"),
            guest_steal_fraction=raw.get("guest_steal_fraction"))
        records.append(row)
        shared.save(output / "result.json", row)
        shared.save(args.output / "summary.json", dict(utc=shared.utc(), cells=records,
            boundary="all six outcomes retained; warmups excluded from comparisons; shared host"))
        print(json.dumps(row), flush=True)
    return 0 if all(r["outcome"] == "passed" for r in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
