#!/usr/bin/env python3
"""Plan/run bounded Pecan gates and paired trials on the existing gate3 VM.

Run on the Docker host. --execute is required to launch any container. Full
artifacts stay in the volume; only flat diagnostics are copied to the host.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

BASE = "ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73"
CANDIDATE = "edc2c7c8cfc17cfc02f4f3a794bd4a3ec86ee3ed"
IMAGE = "sha256:f3518d652fbea8b9b9f9ebf9849277ca3bd39d0c21bb2c6e36fbaeaa2dc2678e"
GATE = "/targets/graph-nuts-ffcfbd569"
ROOT = "/targets/sail-stream-experiments-20260930/pecan-gate3"
HOST = "/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930/pecan-gate3"


def utc():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def config(root=ROOT, output=HOST):
    return dict(run_id="pecan-gate3", docker_context="colima-sail-gate", image=IMAGE,
                target_volume="sail-extension-targets", container_python=GATE + "/venv/bin/python",
                container_repo=GATE + "/source", container_sail_binary=GATE + "/sail-linux-x86_64-ffcfbd5690e3-release",
                runtime_source_sha=BASE, native_source_sha=BASE, harness_source_sha=BASE,
                container_root=root, host_output=output,
                limits=dict(cpus=8, cpuset_cpus="0-7", memory_gib=12, outer_timeout_seconds=1350),
                defaults=dict(partitions=4, threads=4, worker_task_slots=16,
                              sail_pool_bytes=3 * 1024**3, native_quota=256 * 1024**2,
                              tolerance=1e-8, damping=0.85, timeout=600, seed=42, delta=1.0),
                datasets={"weighted16k": dict(family="traversal", vertices=16384, degree=32,
                                               seed=42, source=0, directed=True)},
                extra_cell_args=["--http2-keepalive-timeout", "120"])


def schedule():
    gates = [dict(id=f"gate-{label}-{mode}", kind="integration", label=label, mode=mode)
             for mode in ("local", "process-cluster") for label in ("base", "candidate")]
    # Equal representation in both halves and both positions of adjacent pairs.
    trials = [dict(id=f"warmup-{label}", kind="warmup", label=label, mode="process-cluster")
              for label in ("base", "candidate")]
    trials += [dict(id=f"measured-{i+1}-{label}", kind="measured", label=label, mode="process-cluster")
               for i, label in enumerate(("base", "candidate", "candidate", "base",
                                          "candidate", "base", "base", "candidate"))]
    return gates + trials


def source_config(cfg, label):
    c = dict(cfg)
    c["container_repo"] = GATE + "/source" if label == "base" else cfg["container_root"] + "/source-edc2c7c8"
    c["harness_source_sha"] = BASE if label == "base" else CANDIDATE
    return c


def command(matrix, cfg, cell):
    c = source_config(cfg, cell["label"])
    if cell["kind"] == "integration":
        return [cfg["container_root"] + "/scripts/pecan_gate3_cell.py", "--repo", c["container_repo"],
                "--expected-sha", c["harness_source_sha"], "--sail-binary", c["container_sail_binary"],
                "--output", cfg["container_root"] + "/cells/" + cell["id"],
                "--mode", cell["mode"], "--timeout", "1200"]
    return matrix.cell_command(c, dict(cell_id=cell["id"], dataset="weighted16k", engine="pecan",
        algorithm="sssp", variant="frontier", mode=cell["mode"], repeat=0, max_iterations=100))


BOOTSTRAP = r'''
from pathlib import Path
import hashlib,json,shutil,subprocess,sys
c=json.loads(Path(sys.argv[1]).read_text()); root=Path(c['container_root']); root.mkdir(parents=True,exist_ok=False)
assert shutil.disk_usage('/targets').free >= 12*1024**3, 'less than 12GiB VM disk free'
base=Path(c['container_repo']); candidate=root/'source-edc2c7c8'
subprocess.run(['git','clone','--shared','--no-checkout',str(base),str(candidate)],check=True)
subprocess.run(['git','-C',str(candidate),'fetch','/work/pecan.bundle','refs/heads/work/pecan-single-expansion'],check=True)
subprocess.run(['git','-C',str(candidate),'checkout','--detach',sys.argv[2]],check=True)
for repo,sha in ((base,c['harness_source_sha']),(candidate,sys.argv[2])):
    assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==sha
    assert not subprocess.check_output(['git','-C',str(repo),'status','--porcelain'],text=True).strip()
for name in ('graph_cell.py','measurement.py','runtime.py','traversal_cell.py','traversal_fixture.py','traversal_reference.py'):
    relative=Path('examples/extensions/benchmarks')/name
    assert (base/relative).read_bytes()==(candidate/relative).read_bytes(), name
scripts=root/'scripts'; scripts.mkdir()
shutil.copyfile('/work/pecan_gate3_cell.py',scripts/'pecan_gate3_cell.py')
print(json.dumps(dict(root=str(root),free_bytes=shutil.disk_usage('/targets').free,
    cell_script_sha256=hashlib.sha256((scripts/'pecan_gate3_cell.py').read_bytes()).hexdigest())))
'''


def collect(matrix, cfg, source, destination):
    """Only explicit flat diagnostics; never copy result/staging/dataset trees."""
    destination.mkdir()
    code = r'''
from pathlib import Path
import sys,tarfile
p=Path(sys.argv[1])
allowed={'receipt.json','manifest.json','server.log','pytest.log','junit.xml','graphutils-probe.log','memory-samples.jsonl'}
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as t:
    for name in sorted(allowed):
        f=p/name
        if f.is_file() and not f.is_symlink(): t.add(f,arcname=name,recursive=False)
'''
    cmd = matrix.docker_base(cfg) + ["run", "--rm", "--mount",
        "type=volume,source=sail-extension-targets,target=/targets,readonly",
        "--entrypoint", cfg["container_python"], cfg["image"], "-I", "-c", code, source]
    archive = destination / "diagnostics.tar"
    with archive.open("wb") as stream:
        result = subprocess.run(cmd, stdout=stream, stderr=subprocess.PIPE, timeout=180)
    save(destination / "collection.json", dict(utc=utc(), command=cmd, returncode=result.returncode,
        stderr=result.stderr.decode(), bytes=archive.stat().st_size,
        sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), full_artifacts=source))
    result.check_returncode()
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            assert member.isfile() and Path(member.name).name == member.name
        bundle.extractall(destination)
    archive.unlink()  # diagnostics retained once; do not double host disk use


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, required=True,
                        help="directory containing pinned diagnostic run_matrix.py (3a9028057)")
    parser.add_argument("--root", default=ROOT)
    parser.add_argument("--output", type=Path, default=Path(HOST))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    os.environ["PATH"] = "/usr/local/bin:/opt/homebrew/bin:" + os.environ.get("PATH", "")
    sys.path.insert(0, str(args.matrix.resolve()))
    import run_matrix as matrix
    cfg = config(args.root, str(args.output.resolve()))
    plan = dict(configuration=cfg, cells=[dict(c, command=command(matrix, cfg, c)) for c in schedule()],
                script_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (Path(__file__).resolve(), Path(__file__).with_name("pecan_gate3_cell.py"))},
                matrix_files_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(args.matrix.glob("*.py"))},
                boundary="shared-host paired diagnostic ratios only; no absolute performance claim",
                order="warmup A,B excluded; measured ABBA BAAB; fresh container/server each")
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return 0
    script_dir = Path(__file__).resolve().parent
    assert (script_dir / "pecan.bundle").is_file(), "place candidate git bundle beside runner"
    assert shutil.disk_usage(args.output.parent).free >= 2 * 1024**3, "less than 2GiB host disk free"
    args.output.mkdir(parents=True, exist_ok=False)
    save(args.output / "plan.json", plan)
    # Bootstrap reads only these small files; no dataset copied to/from host.
    save(script_dir / "pecan-gate3-config.json", cfg)
    boot = matrix.docker_base(cfg) + ["run", "--rm", "--mount",
        "type=volume,source=sail-extension-targets,target=/targets", "--mount",
        f"type=bind,source={script_dir},target=/work,readonly", "--workdir", "/targets", "--entrypoint",
        cfg["container_python"], cfg["image"], "-I", "-c", BOOTSTRAP,
        "/work/pecan-gate3-config.json", CANDIDATE]
    result = matrix.capture(boot, timeout=180)
    save(args.output / "bootstrap.json", dict(utc=utc(), command=boot, **result))
    assert result["returncode"] == 0, "bootstrap failed; preserved receipt"
    for label in ("base", "candidate"):
        matrix.preflight(source_config(cfg, label), args.output / ("preflight-" + label))
    prep = matrix.run_container(cfg, "sail-pecan-prepare", matrix.dataset_command(cfg, "weighted16k"),
        args.output / "prepare", cfg["image"], 300, {})
    assert prep.get("attach_returncode") == 0 and not prep["transport_errors"], "fixture preparation failed"
    collect(matrix, cfg, cfg["container_root"] + "/datasets/weighted16k", args.output / "dataset")
    records = []
    for cell in schedule():
        # Preserve all four gates; do not run performance with a failing candidate gate.
        bad_candidate = any(r["kind"] == "integration" and r["label"] == "candidate"
                            and r["outcome"] != "passed" for r in records)
        if cell["kind"] != "integration" and bad_candidate:
            records.append(dict(cell, outcome="not_run_candidate_gate_failed"))
            save(args.output / "summary.json", dict(utc=utc(), cells=records))
            continue
        c = source_config(cfg, cell["label"])
        output = args.output / cell["id"]
        record = matrix.run_container(c, "sail-pecan-" + cell["id"], command(matrix, cfg, cell),
                                      output, cfg["image"], 1350, {})
        receipt = None
        try:
            collect(matrix, cfg, cfg["container_root"] + "/cells/" + cell["id"], output / "diagnostics")
            receipt = json.loads((output / "diagnostics/receipt.json").read_text())
        except Exception as error:
            record["receipt_read_error"] = repr(error)
        outcome = matrix.classify(record, receipt, c["harness_source_sha"])
        row = dict(cell, outcome=outcome, receipt_outcome=(receipt or {}).get("outcome"),
                   binary_sha256=(receipt or {}).get("binary_sha256"),
                   native_identity_sha256=hashlib.sha256(json.dumps(
                       (receipt or {}).get("native_package_identity"), sort_keys=True).encode()).hexdigest(),
                   execution_seconds=(receipt or {}).get("end_to_end_seconds"),
                   execute_memory=(receipt or {}).get("memory", {}).get("phase_peaks", {}).get("execute"),
                   guest_steal_fraction=(receipt or {}).get("guest_steal_fraction"))
        records.append(row)
        save(output / "result.json", row)
        save(args.output / "summary.json", dict(utc=utc(), cells=records))
        print(json.dumps(row), flush=True)
    # Baseline known failures remain failures, never converted to expected passes.
    return 0 if all(r["outcome"] == "passed" for r in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
