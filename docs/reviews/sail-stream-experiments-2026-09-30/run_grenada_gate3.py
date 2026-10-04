#!/usr/bin/env python3
"""Two Grenada weighted crosschecks after the existing Pecan suite; no new dataset."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

import run_pecan_gate3 as shared

ROOT = "/targets/sail-stream-experiments-20260930/grenada-gate3"
HOST = "/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930/grenada-gate3"


def schedule():
    return [dict(id="grenada-" + label, label=label, kind="crosscheck", mode="process-cluster")
            for label in ("base", "candidate")]


def cell_config(prior, cell, root, output):
    # Resolve the candidate source before assigning this experiment's output root.
    cfg = copy.deepcopy(shared.source_config(prior, cell["label"]))
    cfg.update(run_id="grenada-gate3", container_root=root, host_output=str(output))
    return cfg


def command(matrix, prior, cell, root, output):
    cfg = cell_config(prior, cell, root, output)
    cmd = matrix.cell_command(cfg, dict(cell_id=cell["id"], dataset="weighted16k",
        engine="nutmeg-datafusion", algorithm="sssp", variant="frontier",
        mode=cell["mode"], repeat=0, max_iterations=100))
    cmd[cmd.index("--dataset") + 1] = prior["container_root"] + "/datasets/weighted16k"
    return cmd


def completed_suite(summary):
    cells = summary.get("cells", [])
    expected = {c["id"] for c in shared.schedule()}
    return (len(cells) == len(expected) and {c.get("id") for c in cells} == expected
            and all(c.get("outcome") and c["outcome"] != "started" for c in cells))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--prior-plan", type=Path, required=True,
                        help="completed Pecan host output's plan.json; read only")
    parser.add_argument("--root", default=ROOT)
    parser.add_argument("--output", type=Path, default=Path(HOST))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    os.environ["PATH"] = "/usr/local/bin:/opt/homebrew/bin:" + os.environ.get("PATH", "")
    sys.path.insert(0, str(args.matrix.resolve()))
    import run_matrix as matrix
    prior = json.loads(args.prior_plan.read_text())["configuration"]
    plan = dict(prior_plan=str(args.prior_plan.resolve()),
        prior_plan_sha256=hashlib.sha256(args.prior_plan.read_bytes()).hexdigest(),
        script_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in (Path(__file__).resolve(), Path(shared.__file__).resolve())},
        matrix_files_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in sorted(args.matrix.glob("*.py"))},
        boundary="one base/candidate Grenada output/memory crosscheck on shared host; no statistical timing claim",
        order="base then candidate, no extra warmups; each a fresh container/server",
        fixture="same manifest and Parquet paths as preceding Pecan suite; no preparation or copy",
        cells=[dict(c, configuration=cell_config(prior, c, args.root, args.output),
                    command=command(matrix, prior, c, args.root, args.output)) for c in schedule()])
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return 0
    preceding = args.prior_plan.parent
    summary = json.loads((preceding / "summary.json").read_text())
    assert completed_suite(summary), "preceding Pecan suite has not recorded all terminal outcomes"
    fixture = json.loads((preceding / "dataset/manifest.json").read_text())
    assert fixture["counts"] == dict(vertices=16384, edges=529723)
    assert shutil.disk_usage(args.output.parent).free >= 2 * 1024**3
    args.output.mkdir(parents=True, exist_ok=False)
    plan["preceding_outcomes"] = summary["cells"]
    plan["fixture_manifest"] = fixture
    shared.save(args.output / "plan.json", plan)
    # No new source, scripts, datasets, wheels or builds are staged in the VM.
    init = r'''
from pathlib import Path
import json,shutil,sys
root=Path(sys.argv[1]); assert not root.exists()
assert shutil.disk_usage('/targets').free >= 4*1024**3
assert json.loads(Path(sys.argv[2]).read_text()) == json.loads(sys.argv[3]), 'fixture manifest changed'
root.mkdir(parents=True)
'''
    setup = matrix.run_container(prior, "sail-grenada-precheck",
        ["-I", "-c", init, args.root, prior["container_root"] + "/datasets/weighted16k/manifest.json",
         json.dumps(fixture, sort_keys=True)], args.output / "precheck", prior["image"], 120, {})
    assert setup.get("attach_returncode") == 0 and not setup["transport_errors"], "precheck failed"
    records = []
    for cell in schedule():
        cfg = cell_config(prior, cell, args.root, args.output)
        matrix.preflight(cfg, args.output / ("preflight-" + cell["label"]))
        output = args.output / cell["id"]
        orchestration = matrix.run_container(cfg, "sail-" + cell["id"],
            command(matrix, prior, cell, args.root, args.output), output, cfg["image"], 1350, {})
        receipt = None
        try:
            shared.collect(matrix, cfg, args.root + "/cells/" + cell["id"], output / "diagnostics")
            receipt = json.loads((output / "diagnostics/receipt.json").read_text())
        except Exception as error:
            orchestration["receipt_read_error"] = repr(error)
        outcome = matrix.classify(orchestration, receipt, cfg["harness_source_sha"])
        if receipt is not None and receipt.get("dataset") != fixture:
            outcome = "dataset_mismatch"
        row = dict(cell, outcome=outcome, receipt_outcome=(receipt or {}).get("outcome"),
            correctness=(receipt or {}).get("correctness"),
            binary_sha256=(receipt or {}).get("binary_sha256"),
            native_identity_sha256=hashlib.sha256(json.dumps(
                (receipt or {}).get("native_package_identity"), sort_keys=True).encode()).hexdigest(),
            execution_seconds=(receipt or {}).get("end_to_end_seconds"),
            execute_memory=(receipt or {}).get("memory", {}).get("phase_peaks", {}).get("execute"),
            guest_steal_fraction=(receipt or {}).get("guest_steal_fraction"))
        records.append(row)
        shared.save(output / "result.json", row)
        shared.save(args.output / "summary.json", dict(utc=shared.utc(), cells=records,
            boundary="single pair, no timing inference; retain all outcomes"))
        print(json.dumps(row), flush=True)
    return 0 if all(r["outcome"] == "passed" for r in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
