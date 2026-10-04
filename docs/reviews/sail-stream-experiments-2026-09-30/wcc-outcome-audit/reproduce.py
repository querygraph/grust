#!/usr/bin/env python3
"""Frozen f63 consumer counterexamples only; never invokes Docker or a server."""
import ast
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'f63-source'
sys.path.insert(0, str(SOURCE))
import run_matrix
from run_matrix import cell_command, configuration_fingerprint, plan_cells, classify
from summarize import audited_rows, aggregate
from validation_outcome import effective_outcome

source_receipt = json.loads((ROOT / 'source-receipt.json').read_text())
for name, expected in source_receipt['files_sha256'].items():
    assert hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected
observed = {'recorded_utc': datetime.now(timezone.utc).isoformat(),
            'source_commit': source_receipt['source_commit'],
            'scope': 'Pure Python consumer reproduction; no server, Docker, graph execution or source edit'}
record = dict(transport_errors=[], attach_returncode=0, inspect={'state': {'OOMKilled': False}})
observed['malformed_metadata'] = []
for marker in ('ABSENT', None, 0, 'false', False, True):
    receipt = dict(outcome='passed', harness_source_sha='a' * 40,
                   arguments={'algorithm': 'wcc', 'ranking_validation': 'certificate'},
                   correctness={'policy': 'certificate', 'verification_scope': 'partial_wcc_partition'})
    if marker != 'ABSENT':
        receipt['correctness']['component_count_verified'] = marker
    observed['malformed_metadata'].append(dict(marker=marker, effective=effective_outcome(receipt),
        classified=classify(record, receipt, 'a' * 40)))
# Extract only the fixture factory, avoiding an optional pytest dependency;
# production modules and the function body are unchanged committed sources.
fixture_path = SOURCE / 'test_summarize.py'
factory = next(n for n in ast.parse(fixture_path.read_text()).body
               if isinstance(n, ast.FunctionDef) and n.name == 'records')
namespace = dict(json=json, Path=Path, __file__=str(fixture_path),
                 plan_cells=plan_cells, cell_command=cell_command,
                 configuration_fingerprint=configuration_fingerprint)
exec(compile(ast.Module(body=[factory], type_ignores=[]), str(fixture_path), 'exec'), namespace)
configuration, entries = namespace['records']('wcc')
for cell, summary, receipt in entries:
    assert '--ranking-validation' not in cell_command(configuration, cell)
    receipt['arguments']['ranking_validation'] = 'certificate'
    receipt['correctness'] = dict(policy='certificate', component_count_verified=False,
                                  verification_scope='partial_wcc_partition')
rows = audited_rows(entries, configuration)
observed['reference_command_certificate_receipt'] = [
    {k: row[k] for k in ('outcome', 'integrity_errors', 'expected_outcome')} for row in rows]
for _, _, receipt in entries:
    del receipt['correctness']['component_count_verified']
rows = audited_rows(entries, configuration)
observed['same_mismatch_without_marker'] = dict(
    rows=[{k: row[k] for k in ('outcome', 'integrity_errors')} for row in rows],
    exact_passes=aggregate(rows)[0]['passed'], exact_metrics=aggregate(rows)[0]['metrics']['seconds'])
# Unit-level resume orchestration: stub only preflight, assert graph launches
# cannot occur, and use fresh local directories. This is not a Docker test.
configuration = json.loads((SOURCE / 'matrix.example.json').read_text())
configuration['host_output'] = str(ROOT / 'resume-missing-receipt')
configuration['suites'] = [dict(name='resume', mode='local', repetitions=1,
    datasets=['sparse-10000'], engines=['pecan'], algorithms=['wcc'], variants=['optimized'])]
configuration['extra_cell_args'] = ['--ranking-validation=certificate']
cell, = plan_cells(configuration)
assert cell['expected_outcome'] == 'partially_verified'
directory = Path(configuration['host_output']) / 'cells' / cell['cell_id']
directory.mkdir(parents=True, exist_ok=False)
legacy = dict(cell, expected_outcome='passed', outcome='passed', expected_outcome_observed=True,
              configuration_sha256=configuration_fingerprint(configuration))
(directory / 'summary.json').write_text(json.dumps(legacy, indent=2) + '\n')
configuration_path = ROOT / 'resume-config.json'
configuration_path.write_text(json.dumps(configuration, indent=2) + '\n')
run_matrix.preflight = lambda config, output: config['image']
def forbid(*args, **kwargs):
    raise AssertionError('No container launch is allowed in this reproduction')
run_matrix.run_container = forbid
sys.argv = ['run_matrix.py', '--config', str(configuration_path), '--resume', '--skip-prepare']
exit_status = run_matrix.main()
result = json.loads((Path(configuration['host_output']) / 'matrix-results.json').read_text())
observed['resume_missing_receipt'] = dict(returncode=exit_status,
    actual_planned_expectation=cell['expected_outcome'],
    results=result['results'], outcome_counts=result['outcome_counts'])
with (ROOT / 'counterexamples.json').open('x') as output:
    json.dump(observed, output, indent=2)
    output.write('\n')
print(json.dumps(observed, indent=2))
