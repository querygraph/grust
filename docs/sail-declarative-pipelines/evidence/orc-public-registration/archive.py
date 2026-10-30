"""Prepare the final ORC public evidence packet only after root authorizes execution.

Refuses incomplete runtime/lifecycle receipts. Never edits shared docs, sources,
helpers, branches, or commits. Root must fetch/read repository guidance first.
"""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import runpy
import shutil
import subprocess
import xml.etree.ElementTree as ET

PYTHON = '/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python'
VERIFIER = Path('/tmp/sail-sdp-orc-public-validate.py')
D_DOCS = '639ab01e18d3d4fa6f81ddf2647e95c30991f8c2'
CATALOG_PROVENANCE = 'docs/sail-declarative-pipelines/evidence/catalog-empty-schema-read/provenance.json'


def read(path):
    return json.loads(Path(path).read_text())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public', type=Path, default=Path('/tmp/sail-sdp-orc-public'))
    parser.add_argument('--candidate', type=Path, default=Path('/tmp/sail-sdp-orc-public-registration-candidate.json'))
    parser.add_argument('--library-prefix', default='/tmp/sail-sdp-orc-public-registration-')
    parser.add_argument('--first-attempt', type=Path, default=Path('/tmp/sail-sdp-orc-public-attempt-01-external-schema'))
    parser.add_argument('--spark-reference', type=Path, default=Path('/tmp/sail-sdp-orc-public-reference'))
    parser.add_argument('--catalog-docs-commit', required=True, help='Root-confirmed committed generic catalog-fix evidence')
    parser.add_argument('--extra-evidence', type=Path, action='append', default=[])
    parser.add_argument('--qualification', type=Path, default=Path('/tmp/sail-sdp-orc-public-qualification'))
    parser.add_argument('--terminal', type=Path, default=Path('/tmp/sail-sdp-orc-public-terminal.json'))
    parser.add_argument('--sail-repo', type=Path, default=Path('/Users/alexy/src/sail-pipelines-proposal'))
    parser.add_argument('--grust-repo', type=Path, default=Path('/Users/alexy/src/grust-sdp'))
    args = parser.parse_args()
    candidate = read(args.candidate)
    build, gate, server = [read(args.public / (name + '.json')) for name in ['build', 'gate', 'server']]
    qualification = read(args.qualification / 'qualification.json')
    assert build['outcome'] == 'passed' and gate['outcome'] == 'failed'
    assert qualification['status'] == 'passed' and qualification['sail_commit'] == candidate['commit']
    assert qualification['raw_gate_sha256'] == digest((args.public / 'gate.json').read_bytes())
    assert server['outcome'] == 'stopped', 'owned server lifecycle is not terminal'
    assert candidate['commit'] == build['sail_commit'] == gate['sail_commit'] == server['sail_commit']
    assert server['terminal_pid_check']['exit_code'] == 1 and server['remaining_listener_pids'] == []
    assert subprocess.run(['git', '-C', str(args.grust_repo), 'merge-base', '--is-ancestor', D_DOCS, 'HEAD'], capture_output=True).returncode == 0
    assert subprocess.run(['git', '-C', str(args.grust_repo), 'merge-base', '--is-ancestor', args.catalog_docs_commit, 'HEAD'], capture_output=True).returncode == 0
    catalog_provenance = git(args.grust_repo, 'show', args.catalog_docs_commit + ':' + CATALOG_PROVENANCE)
    assert json.loads(catalog_provenance)['sail_commit'] == candidate['base'], 'E parent must be the separately qualified generic catalog fix'
    terminal = []
    for pid in [server['pid'], server['supervisor_pid']]:
        result = subprocess.run(['ps', '-p', str(pid), '-o', 'pid=,ppid=,lstart=,command='], text=True, capture_output=True)
        assert result.returncode == 1 and not result.stdout, 'owned process still exists or PID was reused'
        terminal.append({'pid': pid, 'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
    port = subprocess.run(['/usr/sbin/lsof', '-nP', '-iTCP:50088', '-sTCP:LISTEN', '-Fp'], text=True, capture_output=True)
    assert port.returncode == 1 and not port.stdout, 'port50088 is occupied; do not stop an unrelated process'
    checks = runpy.run_path(str(VERIFIER))
    checks['embedded_manifest'](args.first_attempt, checks['FIRST_SHA'])
    checks['embedded_manifest'](args.spark_reference, checks['REFERENCE_SHA'])
    target = args.grust_repo / 'docs/sail-declarative-pipelines/evidence/orc-public-registration'
    assert not target.exists(), 'never overwrite an evidence packet'
    stage = target.parent / ('.orc-public-registration-staging-' + str(os.getpid()))
    stage.mkdir(parents=True, exist_ok=False)
    mappings, exclusions = [], []

    def copy_file(source, relative):
        assert source.is_file() and not source.is_symlink(), source
        data = source.read_bytes()
        destination = stage / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        assert source.read_bytes() == data, 'input changed while archiving: ' + str(source)
        mappings.append({'original': str(source), 'retained': relative, 'sha256': digest(data)})

    def copy_tree(source, relative):
        for path in sorted(source.rglob('*')):
            if path.is_file():
                if '__pycache__' in path.parts or path.suffix == '.pyc':
                    exclusions.append({'original': str(path), 'reason': 'generated Python bytecode cache'})
                else:
                    copy_file(path, str(Path(relative) / path.relative_to(source)))

    copy_tree(args.public, 'public')
    copy_tree(args.first_attempt, 'attempt-01-external-schema')
    copy_tree(args.spark_reference, 'spark-reference')
    copy_tree(args.qualification, 'supplemental-qualification')
    copy_file(args.terminal, 'terminal.json')
    copy_file(Path('/tmp/sail-sdp-orc-public-qualification-note.md'), 'qualification-note.md')
    copy_file(args.candidate, 'candidate.json')
    copy_file(Path(args.library_prefix + 'gate.json'), 'library/gate.json')
    for name in ['fmt', 'clippy', 'rust']:
        copy_file(Path(args.library_prefix + name + '.log'), 'library/' + name + '.log')
    for index, path in enumerate(args.extra_evidence):
        if path.is_file() and path.name.startswith('sail-sdp-orc-'):
            relative = 'controls/' + path.name
        elif path.is_dir():
            relative = 'diagnostics/' + path.name
        else:
            relative = 'additional-evidence/' + str(index + 1).zfill(2) + '-' + path.name
        copy_tree(path, relative) if path.is_dir() else copy_file(path, relative)
    ctas = read(stage / 'controls/sail-sdp-orc-ctas-original-control.json')
    copy_file(Path(ctas['source_file']), 'controls/input.orc')
    assert digest((stage / 'controls/input.orc').read_bytes()) == ctas['source_sha256']
    scala_path = 'sql/pipelines/src/test/scala/org/apache/spark/sql/pipelines/graph/SqlPipelineSuite.scala'
    (stage / 'controls/SqlPipelineSuite.scala').write_bytes(git(Path('/Users/alexy/src/spark-sdp-4.2.1'), 'show', '617618396087429b5627a86ce933bb0f5d6645cb:' + scala_path))
    copy_file(Path(__file__), 'archive.py')
    copy_file(VERIFIER, 'validate_evidence.py')
    (stage / 'commit.patch').write_bytes(git(args.sail_repo, 'show', '--format=fuller', '--binary', candidate['commit']))
    source_audit = []
    for path in candidate['paths']:
        raw = git(args.sail_repo, 'show', candidate['commit'] + ':' + path)
        destination = stage / 'source' / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        source_audit.append({'path': path, 'commit': candidate['commit'],
            'blob': git(args.sail_repo, 'rev-parse', candidate['commit'] + ':' + path).decode().strip(),
            'sha256': digest(raw)})
    (stage / 'source-audit.json').write_text(json.dumps(source_audit, indent=2) + '\n')
    dependency_path = 'docs/sail-declarative-pipelines/evidence/orc-readformat/provenance.json'
    (stage / 'dependencies').mkdir()
    (stage / 'dependencies/orc-readformat-provenance.json').write_bytes(git(args.grust_repo, 'show', D_DOCS + ':' + dependency_path))
    (stage / 'dependencies/catalog-empty-schema-read-provenance.json').write_bytes(catalog_provenance)
    (stage / 'catalog-read-fix.patch').write_bytes(git(args.sail_repo, 'show', '--format=fuller', '--binary', candidate['base']))
    stamp = datetime.now(timezone.utc).isoformat()
    lifecycle = {'recorded_at': stamp, 'terminal_pid_checks': terminal,
                 'port_check': {'exit_code': port.returncode, 'stdout': port.stdout, 'stderr': port.stderr}}
    (stage / 'archive-terminal-checks.json').write_text(json.dumps(lifecycle, indent=2) + '\n')
    (stage / 'README.md').write_text(f'''# ORC public registration evidence

Recorded {stamp}. Sail `{candidate['commit']}` has completed 296 selected public pytest cases and 67 upstream Python executions, with zero test failures/errors/skips in the final run. The raw enclosing gate remains failed because its summary incorrectly required 67 unique upstream IDs. The separate supplemental qualification passed without rerunning tests: 67 executions / 63 unique IDs, with the imported base remote-mode test legitimately executed five times. Both receipts, the source/baseline multiplicity proof, and the unchanged helpers are retained. Separate Rust library gates cover 175 execution tests and 26 session tests (201 total). The packet records exact source, candidate, CLI/build hash, commands, environment, results, and owned-process cleanup. These are distinct execution counts, not new SDP assertion counts or full SDP qualification.

The unchanged first public attempt at `8ea2c075ed2cccb503c99ece60e18db32a32964c` remains under `attempt-01-external-schema/`: 295 passed and one external catalog-table schema assertion failed; upstream tests did not run. Its complete helper/build/library/server/log evidence, original implementation handoff, preparation correction history, and six same-binary catalog controls are preserved under the original exact manifest. The observed empty schema is retained without rewriting the failure. Its generic named-read correction is the separate parent commit `{candidate['base']}`; `catalog-read-fix.patch` and the committed [catalog schema evidence](../catalog-empty-schema-read/) preserve that unit's own source audit, gates, and controls rather than inferring a cause from the failed assertion alone.

`spark-reference/` retains the fresh ten unchanged public test functions/parameter cases through installed Spark Connect4.2.1. It was direct function/fixture invocation, not pytest. The separately committed [catalog schema evidence](../catalog-empty-schema-read/) contains the additional fresh reference: six ORC/Parquet/JSON schema observations plus one existing-table guard with an embedded expected missing-location failure. These counts are not added to the ten paired public cases. Source and JAR provenance, exact schemas/rows, input hashes, negative-control errors, and owned JVM cleanup are retained. Neither packet claims installed Spark JARs were built from the local source checkout.

Additional controls preserve successful original-call no-USING CTAS and direct batch-MV BIGINT rows 0/1/2. The earlier extra `.collect()` on the CTAS command result failed with UInt64 conversion and remains under `controls/`; command-result collection is not claimed fixed. The six generic reader controls have correct schemas/rows, while omitted-schema `DESCRIBE` remains empty and is an explicit catalog metadata gap. These temporary probes are not additional persistent pytest cases.

The public selection preserves 285 historical node IDs, adds the retained pipeline ORC branch, and adds ten reader cases. It covers the ordinary read registrations and the stated catalog/merge/partition/TIME cases. The session library test separately pins explicit unsupported ORC writing and ordinary-vs-lake registry separation. This does not qualify all ORC schema evolution, Unicode, calendar/rebase modes, distributed execution, native extension packaging, streaming/Iggy, CDC, or the complete original SDP assertion inventory.

`public/` includes raw final execution helpers and their historical inputs; their earlier PREPARATION/README status text is preserved as historical preparation evidence. `source/` is copied from exact candidate Git objects. `dependencies/` identifies the already-committed private ReadFormat evidence at Grust `{D_DOCS}`. `provenance.json` inventories every retained file except itself, maps original files to portable paths, and names exclusions. Only generated Python bytecode caches are omitted. No CLI binary is copied; its immutable SHA256 is retained in build and runtime receipts.

Run `validate_evidence.py <packet>` with the qualified Python for offline content/Git-object/result verification. It does not start Spark, Sail, Cargo, or pytest. The archive writer never edits shared design/review documents or commits changes.
''')
    provenance = {'recorded_at': stamp, 'sail_commit': candidate['commit'], 'base': candidate['base'],
        'd_docs_commit': D_DOCS, 'cli_sha256': build['cli_sha256'],
        'raw_gate_outcome': 'failed', 'supplemental_qualification': 'passed', 'upstream_unique_ids': 63,
        'counts': {'rust_execution': 175, 'rust_session': 26, 'pytest': 296, 'upstream_python': 67, 'spark_direct_reference': 10},
        'separate_catalog_reference': {'generic_cases': 6, 'existing_table_guard': 1, 'embedded_expected_negative_control': 1},
        'first_attempt_manifest_sha256': checks['FIRST_SHA'], 'spark_reference_manifest_sha256': checks['REFERENCE_SHA'],
        'catalog_fix_docs_commit': args.catalog_docs_commit, 'catalog_fix_commit': candidate['base'], 'source_mappings': mappings, 'exclusions': exclusions,
        'full_sdp_qualification': False, 'files': []}
    provenance['files'] = [{'path': str(path.relative_to(stage)), 'bytes': path.stat().st_size, 'sha256': digest(path.read_bytes())}
                           for path in sorted(stage.rglob('*')) if path.is_file()]
    (stage / 'provenance.json').write_text(json.dumps(provenance, indent=2, sort_keys=True) + '\n')
    checks['validate'](stage, args.sail_repo, args.grust_repo)
    stage.rename(target)
    print('Archived terminal public evidence: ' + str(target), flush=True)


if __name__ == '__main__':
    main()
