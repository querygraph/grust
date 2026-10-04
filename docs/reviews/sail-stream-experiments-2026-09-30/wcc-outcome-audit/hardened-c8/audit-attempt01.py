#!/usr/bin/env python3
"""Independent small consumer checks, with no remote or graph execution."""
import ast
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SOURCE_RECEIPT = json.loads((ROOT / 'source-receipt.json').read_text())
SOURCE = Path(SOURCE_RECEIPT['source'])
REPO = SOURCE.parents[2]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def guard():
    assert subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip() == SOURCE_RECEIPT['commit']
    for name, expected in SOURCE_RECEIPT['files_sha256'].items():
        assert digest(SOURCE / name) == expected, name

guard()
sys.path.insert(0, str(SOURCE))
import run_matrix
from run_matrix import cell_command, configuration_fingerprint, plan_cells, classify
from summarize import audited_rows, aggregate
from validation_outcome import effective_outcome

# Unchanged fixture factory only; avoid importing optional pytest machinery.
path = SOURCE / 'test_summarize.py'
factory = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'records')
namespace = dict(json=json, Path=Path, __file__=str(path), plan_cells=plan_cells,
                 cell_command=cell_command, configuration_fingerprint=configuration_fingerprint)
exec(compile(ast.Module(body=[factory], type_ignores=[]), str(path), 'exec'), namespace)

def records(certificate, reported='passed'):
    config, entries = namespace['records']('wcc')
    if certificate:
        config['extra_cell_args'] = ['--ranking-validation=certificate']
    planned = {cell['cell_id']: cell for cell in plan_cells(config)}
    result = []
    for old_cell, _, receipt in entries:
        cell = planned[old_cell['cell_id']]
        receipt['arguments']['ranking_validation'] = 'certificate' if certificate else 'reference'
        receipt['correctness'] = dict(policy='certificate', component_count_verified=False) if certificate else {}
        receipt['outcome'] = reported
        summary = dict(cell, outcome=reported, configuration_sha256=configuration_fingerprint(config))
        result.append((cell, summary, receipt))
    return config, result

checks = []
def note(name, **details):
    checks.append(dict(check=name, outcome='passed', **details))

record = dict(transport_errors=[], attach_returncode=0, inspect={'state': {'OOMKilled': False}})
config, entries = records(True)
for _, summary, receipt in entries:
    summary['outcome'] = classify(record, receipt, config['harness_source_sha'])
original = deepcopy(entries)
rows = audited_rows(entries, config)
assert entries == original
assert {r['outcome'] for r in rows} == {'partially_verified'}
assert aggregate(rows)[0]['passed'] == 0
assert all(not r['integrity_errors'] for r in rows)
note('legacy exit0 receipt -> new partial summary -> audited partial', rows=len(rows))

for reported, code, expected in [('passed', 0, 'partially_verified'), ('passed', 1, 'exit_receipt_mismatch'),
    ('partially_verified', 1, 'partially_verified'), ('partially_verified', 0, 'exit_receipt_mismatch'),
    ('partially_verified', 7, 'exit_receipt_mismatch'), ('partially_verified', None, 'exit_receipt_mismatch')]:
    c, e = records(True, reported)
    assert classify(dict(record, attach_returncode=code), e[0][2], c['harness_source_sha']) == expected
note('new exit1 and legacy exit0 contracts', cases=6)

for marker in ['ABSENT', None, 0, 'false', True]:
    c, e = records(True)
    r = e[0][2]
    if marker == 'ABSENT':
        del r['correctness']['component_count_verified']
    else:
        r['correctness']['component_count_verified'] = marker
    assert effective_outcome(r) == classify(record, r, c['harness_source_sha']) == 'invalid_receipt'
    assert audited_rows(e, c)[0]['outcome'] == 'integrity_error'
for field in ['arguments', 'correctness']:
    for value in [None, [], ['malformed'], False, 'malformed']:
        c, e = records(True)
        r = e[0][2]
        r[field] = value
        assert effective_outcome(r) == classify(record, r, c['harness_source_sha']) == 'invalid_receipt'
        assert audited_rows(e, c)[0]['outcome'] == 'integrity_error'
note('malformed scope and metadata retained as invalid', cases=15)

for planned_certificate in (False, True):
    c, e = records(planned_certificate)
    other, other_entries = records(not planned_certificate)
    for entry, other_entry in zip(e, other_entries):
        entry[2]['arguments']['ranking_validation'] = other_entry[2]['arguments']['ranking_validation']
        entry[2]['correctness'] = other_entry[2]['correctness']
    rows = audited_rows(e, c)
    assert all(r['outcome'] == 'integrity_error' and
               'receipt argument differs: ranking_validation' in r['integrity_errors'] for r in rows)
note('planned reference/certificate protocol mismatch rejected both directions')

for identity in ('binary', 'native', 'dataset'):
    c, e = records(True, 'partially_verified')
    r = e[1][2]
    if identity == 'binary':
        r['binary_sha256'] = '1' * 64
    elif identity == 'native':
        r['native_package_identity']['files_sha256']['extension.so'] = '2' * 64
    else:
        r['dataset']['files']['edges.parquet']['sha256'] = '3' * 64
    assert all(row['outcome'] == 'integrity_error' for row in audited_rows(e, c))
note('explicit partial identity conflicts rejected symmetrically', identities=3)

for outcome in ('mismatch', 'error', 'timeout', 'nonconverged'):
    c, e = records(True, outcome)
    e[0][2]['correctness'] = ['malformed']
    assert classify(record, e[0][2], c['harness_source_sha']) == outcome
c, e = records(True)
assert classify(dict(record, outer_timeout=True), e[0][2], c['harness_source_sha']) == 'outer_timeout'
assert classify(dict(record, inspect={'state': {'OOMKilled': True}}), e[0][2], c['harness_source_sha']) == 'oom'
note('failure precedence retained', cases=6)

# Unit-level resume control. Preflight is stubbed; any graph/container call fails.
run_matrix.preflight = lambda config, output: config['image']
def forbid(*args, **kwargs):
    raise AssertionError('No graph or container execution is permitted')
run_matrix.run_container = forbid
for evidence, expected in [('valid', 'partially_verified'), ('missing', 'missing_receipt'),
    ('invalid_json', 'invalid_receipt'), ('nonobject', 'invalid_receipt'),
    ('missing_exit', 'exit_receipt_mismatch'), ('wrong_exit', 'exit_receipt_mismatch')]:
    c, e = records(True)
    c['suites'] = [dict(name='resume', mode='local', repetitions=1, datasets=['sparse-10000'],
        engines=['pecan'], algorithms=['wcc'], variants=['optimized'])]
    c['host_output'] = str(ROOT / ('resume-' + evidence))
    cell, = plan_cells(c)
    directory = Path(c['host_output']) / 'cells' / cell['cell_id']
    (directory / 'artifacts').mkdir(parents=True, exist_ok=False)
    summary = dict(cell, expected_outcome='passed', outcome='passed', expected_outcome_observed=True,
                   configuration_sha256=configuration_fingerprint(c))
    summary_path = directory / 'summary.json'
    summary_path.write_text(json.dumps(summary) + '\n')
    before = digest(summary_path)
    receipt_path = directory / 'artifacts/receipt.json'
    r = e[0][2]
    if evidence != 'missing':
        receipt_path.write_text('{invalid' if evidence == 'invalid_json' else json.dumps([] if evidence == 'nonobject' else r))
    orchestration = dict(transport_errors=[])
    if evidence != 'missing_exit':
        orchestration['attach_returncode'] = 7 if evidence == 'wrong_exit' else 0
    (directory / 'orchestration.json').write_text(json.dumps(orchestration))
    receipt_before = digest(receipt_path) if receipt_path.exists() else None
    config_path = ROOT / ('resume-' + evidence + '.json')
    config_path.write_text(json.dumps(c))
    sys.argv = ['run_matrix.py', '--config', str(config_path), '--resume', '--skip-prepare']
    code = run_matrix.main()
    result = json.loads((Path(c['host_output']) / 'matrix-results.json').read_text())['results'][0]
    assert result['outcome'] == expected and code == (0 if evidence == 'valid' else 1)
    assert result['original_outcome'] == 'passed' and result['expected_outcome'] == 'partially_verified'
    assert digest(summary_path) == before
    assert (digest(receipt_path) if receipt_path.exists() else None) == receipt_before
note('resumed missing/invalid receipts and exit mismatches retained without source-evidence rewrites', cases=6)
guard()
receipt = dict(recorded_utc=datetime.now(timezone.utc).isoformat(), outcome='passed',
               commit=SOURCE_RECEIPT['commit'], tree=SOURCE_RECEIPT['tree'], checks=checks,
               source_hashes_unchanged=True, no_remote_or_graph_execution=True,
               source_receipt_sha256=digest(ROOT / 'source-receipt.json'), audit_sha256=digest(Path(__file__)),
               scope='Independent Python consumer controls only; separate from owner full tests and SQL integration')
with (ROOT / 'audit-receipt.json').open('x') as out:
    json.dump(receipt, out, indent=2)
    out.write('\n')
print(json.dumps(receipt, indent=2))
