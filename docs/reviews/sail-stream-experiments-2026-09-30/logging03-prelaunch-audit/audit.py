"""Local configuration/source audit only; never call Docker or a graph workload."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
EXP = ROOT.parent
SAIL = Path('/private/tmp/sail-stream-diagnostic-harness-gate')
CONTROLLER = '3a9028057c6c6c5034492845926fc4bc18f9626f'
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()

def diff(a, b, path=''):
    rows = []
    if isinstance(a, dict) and isinstance(b, dict):
        assert a.keys() == b.keys()
        for key in sorted(a):
            rows.extend(diff(a[key], b[key], path + '/' + key))
    elif isinstance(a, list) and isinstance(b, list):
        assert len(a) == len(b)
        for index, (x, y) in enumerate(zip(a, b)):
            rows.extend(diff(x, y, path + '/' + str(index)))
    elif a != b:
        rows.append(dict(path=path, logging02=a, logging03=b))
    return rows

assert git(SAIL, 'rev-parse', 'HEAD') == CONTROLLER
assert not git(SAIL, 'status', '--porcelain')
harness = SAIL/'examples/extensions/benchmarks'
sys.path.insert(0, str(harness))
import run_matrix as matrix
names = ['logging02.json', 'logging03-compact.json']
configs = [json.loads((EXP/name).read_text()) for name in names]
before = {name: sha(EXP/name) for name in names + ['run_focused_safe.py', 'preflight_cell.py']}
differences = diff(*configs)
assert {r['path'] for r in differences} == {'/container_root', '/container_sail_binary',
    '/host_output', '/note', '/run_id', '/runtime_source_sha', '/suites/0/name'}
plans = []
for config in configs:
    matrix.validate_config(config)
    cells = matrix.plan_cells(config)
    assert len(cells) == 1
    plans.append(dict(cell=cells[0], command=matrix.cell_command(config, cells[0])))
a, b = (p['command'] for p in plans)
command_differences = [dict(flag=a[i-1], logging02=x, logging03=y)
                       for i, (x, y) in enumerate(zip(a, b)) if x != y]
assert len(a) == len(b)
assert {r['flag'] for r in command_differences} == {'--sail-binary', '--runtime-source-sha', '--dataset', '--output'}
normalized = []
for config in configs:
    c = json.loads(json.dumps(config))
    for key in ('container_root', 'container_sail_binary', 'host_output', 'note', 'run_id', 'runtime_source_sha'):
        del c[key]
    del c['suites'][0]['name']
    normalized.append(c)
assert normalized[0] == normalized[1]
bootstraps = {name: json.loads((EXP/('bootstrap-'+Path(name).stem+'.json')).read_text()) for name in names}
assert all(r['returncode'] == 0 for r in bootstraps.values())
admission = json.loads((EXP/'logging02-admission.json').read_text())
build = json.loads((EXP/'linux-builds/BUILD-HANDOFF.json').read_text())
source_names = ['run_matrix.py', 'runtime.py', 'graph_cell.py', 'traversal_cell.py',
                'traversal_certificate.py', 'measurement.py', 'traversal_methods.py']
receipt = dict(recorded_utc=datetime.now(timezone.utc).isoformat(),
    outcome='PASS_CONFIG_PARITY_WITH_DISCLOSED_BOUNDARIES',
    scope='Local read-only source/configuration audit after repository fetches; no remote workload, admission run, source/config edit or launch authorization.',
    grust_head=git(EXP, 'rev-parse', 'HEAD'), controller_head=CONTROLLER,
    files_sha256=before, controller_files_sha256={n: sha(harness/n) for n in source_names},
    exactly_seven_configuration_differences=differences,
    cell_command_differences=command_differences,
    common_configuration_sha256=hashlib.sha256(json.dumps(normalized[0], sort_keys=True).encode()).hexdigest(),
    unchanged=dict(image=configs[0]['image'], python=configs[0]['container_python'],
        controller=configs[0]['container_repo'], native_source_sha=configs[0]['native_source_sha'],
        limits=configs[0]['limits'], defaults=configs[0]['defaults'], datasets=configs[0]['datasets'],
        environment=configs[0]['environment'], extra_cell_args=configs[0]['extra_cell_args'],
        worker_count=2, worker_task_slots_total=128),
    host_artifacts={k: build[k] for k in ('host289', 'host561')},
    host_source_diff_files=git(SAIL, 'diff', '--name-only', configs[0]['runtime_source_sha'], configs[1]['runtime_source_sha']).splitlines(),
    dataset=dict(bootstrap_returncodes={n: r['returncode'] for n, r in bootstraps.items()},
        bootstrap_shared_target='/targets/gn-capacity-b87fb27a-hub/datasets/scale24',
        logging02_observed=admission['observed']['datasets']['scale24'],
        requirement='Before logging03, compare its fresh preflight manifest SHA/path with logging02; preflight records these but does not assert the expected manifest SHA. The cell checks expected canonical edge digest and checksums every listed Parquet file before timing.'),
    boundaries=[
        dict(id='outer_timeout_can_interrupt_certificate', refs=['graph_cell.py:492-497','run_matrix.py:314-319'],
            finding='Execution alarm14400s is reset to14400s for verification, but the identical15300s outer timeout covers the entire container including pre-timer checksums, startup, execution, verification and cleanup. A completed execution may therefore have certification interrupted.',
            interpretation='Preserve outer_timeout and last observed phase; certification incomplete is not passed, mismatch, or proof of an algorithm failure. Keep the same pinned timeout in both cells.'),
        dict(id='matched_timer_and_validation', refs=['traversal_cell.py:19-27','traversal_cell.py:96-97','graph_cell.py:465-497','traversal_cell.py:110-119','traversal_certificate.py:85-94'],
            finding='Timed boundary is traversal execution through final Parquet write after lazy input handles; excludes input checksum reads, server startup, distributed certificate and cleanup. Certificate checks all-edge inequalities plus rooted tight-edge reachability, cardinality and parent/hop witnesses at1e-12 edge tolerance, with an accumulated absolute error bound.',
            interpretation='Require final passed receipt and certificate/parent fields for success; retain bound/witness rounds. This is not the16k precomputed Dijkstra oracle or a claim of bitwise identical full vectors.'),
        dict(id='memory_and_shared_host_scope', refs=['runtime.py:157-179','graph_cell.py:457-466','graph_cell.py:557-559','measurement.py:130-182'],
            finding='Both use100GiB container cap, swap disabled,32CPU0-31,32partitions/threads,2workers with64slots each,96GiB Sail pool per driver/worker and80GiB native quota setting. The96GiB is not an aggregate cluster/RSS cap. Execution PSS/RSS are sampled; full-cgroup memory includes cache/kernel and verification can set the final peak. Steal spans the whole trial and whole VM.',
            interpretation='Compare execution-phase PSS separately from total cgroup peak; retain memory.events/cpu.stat, observed host pressure, clock evidence and steal scope. One sequential trial each on a shared host is a diagnostic outcome control, not a reliable isolated speedup estimate.'),
        dict(id='separate_admission_and_identity', refs=['preflight_cell.py:78-100','run_focused_safe.py:74-95','run_matrix.py:376-390'],
            finding='The explicit preflight pins config/binary/native and clean controller plus minimum free bytes/idle Docker, but is a separate point-in-time tool, not automatically called by run_focused_safe. Its dataset manifest is observed, not pinned by an argument; standard matrix preflight only checks source and binary existence.',
            interpretation='Use fresh logging03 admission with host561 hash5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec, same manifest8bad1a94c5a37715ce9320f27b3f13097ef50c2a9bfdfa15c25ed0665007c75c, no overlapping build/graph, actual free disk and recorded process image identities. Retained logging02 staging can reduce later disk headroom; prior staging peak is not an upper bound.'),
        dict(id='missing_receipt_or_collection_is_not_algorithm_outcome', refs=['run_focused_safe.py:107-134','run_matrix.py:351-373'],
            finding='The safe runner unconditionally reads diagnostics/receipt.json before classifying and returns0 even for a completed non-pass classification. A missing/invalid receipt or collection timeout can prevent result.json; raw orchestration and VM artifacts remain. Classifier distinguishes OOM, outer timeout, interrupted, orchestration error and missing receipt when invoked with available data.',
            interpretation='Do not use wrapper exit0 as passed. Audit orchestration plus receipt when present and retained last-phase evidence; preserve collection/missing-receipt failures separately. No receipt/final cgroup evidence means no final no-OOM inference merely from Docker driver state.')],
    launch_readiness='Not evaluated here: logging03 fresh admission and actual runtime receipt remain pending. No configuration asymmetry or source-scope blocker found.')
assert before == {name: sha(EXP/name) for name in before}
assert git(SAIL, 'rev-parse', 'HEAD') == CONTROLLER and not git(SAIL, 'status', '--porcelain')
receipt['audit_script_sha256'] = sha(Path(__file__))
with (ROOT/'receipt.json').open('x') as stream:
    json.dump(receipt, stream, indent=2)
    stream.write('\n')
print(json.dumps(dict(outcome=receipt['outcome'], configuration_differences=len(differences),
                     command_differences=len(command_differences), receipt_sha256=sha(ROOT/'receipt.json'))))
