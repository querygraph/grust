from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

source = Path(__file__).resolve().parent
repository = Path('/Users/alexy/src/grust-sdp')
docs = repository / 'docs/sail-declarative-pipelines'
target = docs / 'evidence/time-semantics/public'
target.mkdir(parents=True, exist_ok=True)
receipt = json.loads((source / 'gate.json').read_text())
assert receipt['outcome'] == 'passed'
for folder in ['', 'spark', 'sail-before', 'spark-initial-port-mismatch', 'sail-initial-missing-python-path']:
    destination = target / folder
    destination.mkdir(exist_ok=True)
    for path in (source / folder).iterdir():
        if path.is_file() and path.suffix in {'.py', '.log', '.json', '.xml', '.txt'}:
            shutil.copyfile(path, destination / path.name)
candidate = Path('/tmp/sail-sdp-time-public-candidate.json')
shutil.copyfile(candidate, target / 'candidate.json')
sail = '/Users/alexy/src/sail-pipelines-proposal'
(target / 'commit.patch').write_bytes(subprocess.check_output(
    ['git','-C',sail,'show','--format=fuller',receipt['sail_commit']]))
stamp = datetime.now(timezone.utc).isoformat()
manifest = {
    'recorded_at':stamp, 'sail_commit':receipt['sail_commit'], 'implementation_commit':receipt['base'],
    'cli_sha256':receipt['cli_sha256'], 'selected_pytest':285, 'selected_upstream_python':67,
    'paired_new_tests':8, 'spark_reference_passed':8, 'previous_sail_passed':1, 'previous_sail_failed':7,
    'previous_sail_implementation_commit':'8d044db3860b4f55e49543c833246af31e986e2e',
    'test_source_sha256':receipt['test_source_sha256'],
    'limitations':[
        'Selected shared-type and SDP regressions only; no original Scala-suite or full SDP qualification.',
        'Spark runtime is installed PySpark4.2.1; it is not asserted to have been built from the source checkout.',
        'An initial Spark runner used a server port inconsistent with PySpark local startup; its source and incomplete report are retained.',
        'The first fresh Sail launch omitted the established PYTHONPATH/VIRTUAL_ENV and selected fallback config defaults. It passed281/failed4 at localRelationSizeLimit lookup. Same binary and unchanged assertions pass after matching the established environment; the focused control and full rerun are retained.',
        'SQL TIME lowering, TIME string parser/configuration and container literal type propagation remain separate work.',
    ],
    'files':[],
}
for path in sorted(target.rglob('*')):
    if path.is_file() and path.name != 'provenance.json':
        data = path.read_bytes()
        manifest['files'].append({'path':str(path.relative_to(target)), 'bytes':len(data), 'sha256':hashlib.sha256(data).hexdigest()})
(target / 'provenance.json').write_text(json.dumps(manifest,indent=2)+'\n')
with (docs / 'TIME-SEMANTICS.md').open('a') as output:
    output.write('\n## Public runtime qualification\n\nRecorded: ' + stamp + '. ')
    output.write('Sail `' + receipt['sail_commit'] + '` passes **285 selected pytest cases and 67 upstream Python executions** on a freshly built CLI. ')
    output.write('The [runtime archive](evidence/time-semantics/public/provenance.json) records the binary hash, exact candidate, commands, environment and raw results. ')
    output.write('Eight new shared TIME checks pass unchanged on installed Spark4.2.1; the previous Sail CLI passes one and fails seven. ')
    output.write('They cover all49 scalar precision pairs, declared schemas, fractional values, null/day boundaries, nested arrays/maps/renamed mixed structs, and a Python TIME literal.\n\n')
    output.write('The first new Sail launch passed281 and failed4 during `createDataFrame` configuration lookup because it lacked the established Python environment. ')
    output.write('Restoring `PYTHONPATH` and `VIRTUAL_ENV` fixed the focused control and full run without changing the binary or assertions. ')
    output.write('The initial failed gate is retained alongside a corrected Spark-runner port setup failure. ')
    output.write('The canonical462 SDP registrations,97 assertion reviews and59 partial ports remain unchanged; these shared-type regressions do not close additional upstream SDP assertions by themselves.\n')
with (docs / 'REVIEW.md').open('a') as output:
    output.write('\nThe [public TIME gate](evidence/time-semantics/public/provenance.json) at `' + receipt['sail_commit'][:10] + '` passes285 selected pytest and67 upstream Python executions, with eight new unchanged checks also passing on Spark4.2.1. ')
    output.write('The previous Sail CLI passes1/fails7 of those eight. Initial runner/server environment failures are retained, including the same-binary control. ')
    output.write('No full SDP, ORC source, streaming/Iggy or CDC qualification is implied.\n')
with (repository / 'codex-to-codex.md').open('a') as output:
    output.write('\n## ' + stamp + ' — DONE TIME cast and Connect activation\n\n')
    output.write('Sail2f5192d50/aacea1ecf/dce4bd751/39e63d686 separately pass detached Rust gates; final public test commit' + receipt['sail_commit'] + ' passes285 selected pytest/67 upstream Python and Ruff with fresh CLI hash' + receipt['cli_sha256'] + '. ')
    output.write('All8 new assertions pass unchanged on installed Spark4.2.1; previous Sail1pass7fail retained. Initial codec import, Spark runner port and Sail Python-path failures retained with corrections; no assertion weakening. ')
    output.write('Shared SQL TIME/configuration/container-literal follow-ups and ORC registration remain open. Streaming/Iggy/CDC unimplemented; full goal active. Documentation integrity gate precedes conditional branch advance.\n')
print('Archived public TIME gate and retained all initial failures')
