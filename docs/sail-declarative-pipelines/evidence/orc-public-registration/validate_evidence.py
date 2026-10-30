"""Offline verification of the future ORC public registration evidence packet.

Only reads archived files and local Git objects; starts no build, test, or server.
"""
from collections import Counter
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET

FIRST_SHA = 'a37a2c10067d9cbf8c180af9e07b04f62fa701b4f0eb025b69fa63f9d8e9f6c2'
REFERENCE_SHA = '137d93140b122ce5d7784ee62c58ce8d7883ec9cdfacdfbcc56ead0385d62e22'
BASELINE_SHA = '9ea4f2fbb93bd3121387e306ab49e7b8417e907b6ec778d97ab89a92d0d81b6f'
SPARK_PIN = '617618396087429b5627a86ce933bb0f5d6645cb'
PUBLIC = 'python/pysail/tests/spark/datasource/test_orc.py'
PIPELINE = 'python/pysail/tests/spark/pipelines/test_file_sources.py'
PIPELINE_NODE = PIPELINE + '::test_batch_pipeline_reads_file_source[orc]'
FIRST_COMMIT = '8ea2c075ed2cccb503c99ece60e18db32a32964c'
D_COMMIT = '03e8783f2164b259f17ed0294af6189053240bf4'
D_DOCS = '639ab01e18d3d4fa6f81ddf2647e95c30991f8c2'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def files(root):
    return {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}


def inventory(root, entries, excluded=()):
    assert {entry['path'] for entry in entries} == files(root) - set(excluded)
    for entry in entries:
        path = root / entry['path']
        assert path.resolve().is_relative_to(root.resolve()) and not path.is_symlink()
        assert path.stat().st_size == entry.get('bytes', entry.get('size'))
        assert sha(path) == entry['sha256'], path


def embedded_manifest(root, digest):
    assert sha(root / 'MANIFEST.json') == digest
    inventory(root, read(root / 'MANIFEST.json')['files'], ['MANIFEST.json'])


def pytest_result(path, expected):
    tree = ET.parse(path)
    totals = tuple(sum(int(suite.get(key, 0)) for suite in tree.iter('testsuite'))
                   for key in ['tests', 'failures', 'errors', 'skipped'])
    assert totals == expected, totals
    cases = list(tree.iter('testcase'))
    nodes = [case.get('classname').replace('.', '/') + '.py::' + case.get('name') for case in cases]
    assert len(nodes) == len(set(nodes)) == expected[0]
    return cases, nodes


def library(root, commit, prefix=''):
    gate = read(root / (prefix + 'gate.json'))
    assert gate['sail_commit'] == commit and gate['outcome'] == 'passed'
    assert gate['packages'] == ['sail-session', 'sail-execution']
    assert [c['name'] for c in gate['checks']] == ['fmt', 'clippy', 'rust']
    for check in gate['checks']:
        assert check['exit_code'] == 0
        assert sha(root / (prefix + check['name'] + '.log')) == check['sha256']
    text = (root / (prefix + 'rust.log')).read_text()
    summaries = re.findall(r'^test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored;', text, re.M)
    assert summaries == [('175', '0', '0'), ('26', '0', '0')]
    tests = re.findall(r'^test (.+) \.\.\. ok$', text, re.M)
    assert len(tests) == 201
    assert 'formats::tests::registered_orc_source_rejects_writing' in tests
    assert 'formats::tests::separates_data_sources_from_lake_sources' in tests
    return tests


def lifecycle(public):
    build, server = read(public / 'build.json'), read(public / 'server.json')
    assert build['outcome'] == 'passed' and build['build_exit_code'] == 0
    assert build['before'] == build['after']
    assert build['before']['detached'] and build['before']['status'] == ''
    assert sha(public / 'build.log') == build['build_log_sha256']
    for name, digest in build['helpers_sha256'].items():
        assert sha(public / name) == digest
    assert server['outcome'] == 'stopped' and isinstance(server['exit_code'], int)
    assert server['sail_commit'] == build['sail_commit']
    assert server['cli_sha256'] == build['cli_sha256']
    assert server['build_json_sha256'] == sha(public / 'build.json')
    assert server['terminal_pid_check']['exit_code'] == 1
    assert server['terminal_pid_check']['stdout'] == '' and server['remaining_listener_pids'] == []
    assert sha(public / 'server.log') == server['server_log_sha256']
    assert server['environment_overrides']['PYTHONPATH'].endswith('/.venv/lib/python3.12/site-packages')
    assert server['environment_overrides']['VIRTUAL_ENV'].endswith('/sail-pipelines-proposal/.venv')
    assert server['port'] == 50088 and server['remote'] == 'sc://localhost:50088'
    gate = read(public / 'gate.json')
    assert gate['sail_commit'] == build['sail_commit']
    assert gate['cli_sha256'] == build['cli_sha256']
    assert gate['build_json_sha256'] == sha(public / 'build.json')
    for check in gate['checks']:
        assert sha(public / (check['name'] + '.log')) == check['log_sha256']
    return build, server, gate


def validate(packet, sail, grust):
    provenance = read(packet / 'provenance.json')
    inventory(packet, provenance['files'], ['provenance.json'])
    candidate = read(packet / 'candidate.json')
    commit = candidate['commit']
    assert provenance['sail_commit'] == commit
    first = packet / 'attempt-01-external-schema'
    embedded_manifest(first, FIRST_SHA)
    first_candidate = read(first / 'library-candidate.json')
    assert first_candidate['commit'] == FIRST_COMMIT
    frozen = {entry['path']: entry['sha256'] for entry in read(first / 'implementation/source-state.json')['files']}
    assert len(frozen) == 5 and set(candidate['paths']) == set(frozen)
    assert git(sail, 'rev-parse', commit + '^').decode().strip() == candidate['base']
    assert set(git(sail, 'diff', '--name-only', candidate['base'], commit).decode().splitlines()) == set(frozen)
    assert (packet / 'commit.patch').read_bytes() == git(sail, 'show', '--format=fuller', '--binary', commit)
    assert (first / 'commit.patch').read_bytes() == git(sail, 'show', '--format=fuller', '--binary', FIRST_COMMIT)
    for path, digest in frozen.items():
        raw = git(sail, 'show', commit + ':' + path)
        assert hashlib.sha256(raw).hexdigest() == digest
        assert (packet / 'source' / path).read_bytes() == raw
        assert (first / 'implementation/source' / path).read_bytes() == raw
    audit = read(packet / 'source-audit.json')
    assert {entry['path'] for entry in audit} == set(frozen)
    for entry in audit:
        assert entry['commit'] == commit and entry['sha256'] == frozen[entry['path']]
        assert entry['blob'] == git(sail, 'rev-parse', commit + ':' + entry['path']).decode().strip()
    catalog_path = 'docs/sail-declarative-pipelines/evidence/catalog-empty-schema-read/provenance.json'
    assert (packet / 'dependencies/catalog-empty-schema-read-provenance.json').read_bytes() == git(grust, 'show', provenance['catalog_fix_docs_commit'] + ':' + catalog_path)
    assert read(packet / 'dependencies/catalog-empty-schema-read-provenance.json')['sail_commit'] == provenance['catalog_fix_commit'] == candidate['base']
    assert (packet / 'catalog-read-fix.patch').read_bytes() == git(sail, 'show', '--format=fuller', '--binary', candidate['base'])
    assert provenance['d_docs_commit'] == D_DOCS
    dependency_path = 'docs/sail-declarative-pipelines/evidence/orc-readformat/provenance.json'
    assert (packet / 'dependencies/orc-readformat-provenance.json').read_bytes() == git(grust, 'show', D_DOCS + ':' + dependency_path)
    assert read(packet / 'dependencies/orc-readformat-provenance.json')['sail_commit'] == D_COMMIT
    assert subprocess.run(['git', '-C', str(sail), 'merge-base', '--is-ancestor', D_COMMIT, commit], capture_output=True).returncode == 0

    first_build, _, first_gate = lifecycle(first / 'public')
    assert first_gate['outcome'] == 'failed'
    assert [(c['name'], c['exit_code']) for c in first_gate['checks']] == [('ruff', 0), ('ruff-format', 0), ('pytest', 1)]
    assert not (first / 'public/upstream.json').exists()
    cases, _ = pytest_result(first / 'public/pytest.xml', (296, 1, 0, 0))
    failures = [case for case in cases if case.find('failure') is not None]
    assert len(failures) == 1
    assert failures[0].get('name') == 'test_orc_external_catalog_table_reads_existing_files'
    assert 'StructType([])' in ET.tostring(failures[0], encoding='unicode')
    assert library(first, FIRST_COMMIT, 'library-')
    control = read(first / 'catalog-control.json')
    assert control['script_sha256'] == sha(first / 'catalog-control.py')
    assert control['server']['cli_sha256'] == first_build['cli_sha256']
    assert len(control['cases']) == 6 and control['spark_version'] == '4.2.1'
    observation = read(first / 'observation.json')
    assert observation['passed'] == 295 and observation['failed'] == 1 and observation['upstream_executed'] is False
    for check in observation['terminal_pid_checks'] + [observation['port_check']]:
        assert check['exit_code'] == 1 and check['stdout'] == ''

    public = packet / 'public'
    build, server, gate = lifecycle(public)
    assert build['sail_commit'] == gate['sail_commit'] == commit
    assert build['before']['sources'] == frozen
    assert build['before']['candidate_sha256'] == sha(packet / 'candidate.json')
    assert gate['outcome'] == 'failed' and gate['before'] == build['before']
    assert "len(set(result['collected'])) == 67" in gate['error']
    assert gate['server_before']['pid'] == server['pid']
    supplement = packet / 'supplemental-qualification'
    qualification = read(supplement / 'qualification.json')
    inventory(supplement, qualification['files'], ['qualification.json'])
    assert qualification['status'] == 'passed' and qualification['tests_rerun'] is False
    assert qualification['sail_commit'] == commit and qualification['before'] == qualification['after'] == build['before']
    assert qualification['raw_gate_sha256'] == sha(public / 'gate.json') == sha(supplement / 'raw-gate.json')
    assert qualification['cli_sha256'] == build['cli_sha256']
    assert qualification['build_json_sha256'] == sha(public / 'build.json')
    assert qualification['helpers_sha256'] == build['helpers_sha256']
    assert qualification['server_before'] == qualification['server_after'] == gate['server_before']
    assert qualification['script_sha256'] == sha(supplement / 'qualify.py')
    for entry in qualification['source_audit']:
        raw = git(Path(entry['repository']), 'show', entry['commit'] + ':' + entry['path'])
        assert raw == (supplement / entry['retained']).read_bytes()
        assert entry['sha256'] == sha(supplement / entry['retained'])
        assert entry['blob'] == git(Path(entry['repository']), 'rev-parse', entry['commit'] + ':' + entry['path']).decode().strip()
    assert qualification['duplicate_source_explanation']['unittest_loader_sha256'] == sha(supplement / 'source/unittest-loader.py')
    assert len(qualification['duplicate_source_explanation']['importing_modules']) == 5
    terminal = read(packet / 'terminal.json')
    assert terminal['qualification_sha256'] == sha(supplement / 'qualification.json')
    assert terminal['server_receipt_sha256'] == sha(public / 'server.json')
    for check in terminal['checks'] + [terminal['port_check']]:
        assert check['exit_code'] == 1 and check['stdout'] == ''
    assert [(c['name'], c['exit_code']) for c in gate['checks']] == [('ruff', 0), ('ruff-format', 0), ('pytest', 0), ('upstream', 0)]
    assert gate['checks'][0]['command'][1:] == ['check', PIPELINE, PUBLIC]
    assert gate['checks'][1]['command'][1:] == ['format', '--check', PIPELINE, PUBLIC]
    assert sha(public / 'inputs/baseline-pytest.xml') == BASELINE_SHA
    _, baseline = pytest_result(public / 'inputs/baseline-pytest.xml', (285, 0, 0, 0))
    selected = read(public / 'selected-nodes.json')
    assert selected == baseline + [PIPELINE_NODE, PUBLIC]
    _, actual = pytest_result(public / 'pytest.xml', (296, 0, 0, 0))
    assert set(selected[:-1]).issubset(actual)
    added = set(actual) - set(selected[:-1])
    assert len(added) == 10 and all(node.startswith(PUBLIC + '::') for node in added)
    assert gate['checks'][2]['command'][4:-1] == selected
    upstream = read(public / 'upstream.json')
    assert upstream['tests_run'] == len(upstream['collected']) == len(upstream['outcomes']) == 67
    repeated = 'pyspark.testing.connectutils.ReusedConnectTestCase.test_assert_remote_mode'
    collected = Counter(upstream['collected'])
    outcomes = Counter(case['id'] for case in upstream['outcomes'])
    assert collected == outcomes and len(collected) == 63
    assert {name: count for name, count in collected.items() if count > 1} == {repeated: 5}
    baseline_upstream = read(supplement / 'prior-time-upstream.json')
    assert collected == Counter(baseline_upstream['collected']) == Counter(case['id'] for case in baseline_upstream['outcomes'])
    assert dict(collected) == qualification['upstream']['collected_counter'] == qualification['upstream']['outcome_counter']
    assert qualification['upstream']['sha256'] == sha(public / 'upstream.json')
    assert qualification['upstream']['prior_baseline_sha256'] == sha(supplement / 'prior-time-upstream.json')
    assert upstream['failures'] == upstream['errors'] == upstream['skipped'] == 0
    assert upstream['spark_commit'] == SPARK_PIN and upstream['server_spark_version'] == '4.2.1'
    assert {case['id'] for case in upstream['outcomes']} == set(upstream['collected'])
    assert all(case['outcome'] == 'passed' for case in upstream['outcomes'])
    assert library(packet / 'library', commit)
    assert provenance['raw_gate_outcome'] == 'failed' and provenance['supplemental_qualification'] == 'passed'
    assert provenance['upstream_unique_ids'] == 63
    assert provenance['counts'] == {'rust_execution': 175, 'rust_session': 26, 'pytest': 296, 'upstream_python': 67, 'spark_direct_reference': 10}

    reference = packet / 'spark-reference'
    embedded_manifest(reference, REFERENCE_SHA)
    result = read(reference / 'results.json')
    assert result['status'] == 'completed' and result['summary'] == {'passed': 10, 'failed': 0}
    assert len(result['cases']) == 10 and all(case['status'] == 'passed' for case in result['cases'])
    assert result['spark_version'] == '4.2.1' and result['spark_source_pin'] == SPARK_PIN
    assert result['session_class'] == 'pyspark.sql.connect.session.SparkSession'
    assert sha(reference / 'source/test_orc.py') == frozen[PUBLIC]
    assert result['owned_gateway_exit_code'] == 0
    assert result['terminal_pid_check']['exit_code'] == 1 and result['terminal_pid_check']['stdout'] == ''
    assert result['initial_config']['spark.sql.timeType.enabled'] == 'false'
    assert all(case['config']['spark.sql.timeType.enabled'] == 'true' for case in result['cases'])
    for name in ['time_precisions.orc', 'spark-reference.json']:
        assert sha(reference / 'source/orc_data' / name) == frozen[PUBLIC.replace('test_orc.py', 'orc_data/' + name)]
    controls = packet / 'controls'
    for stem in ['sail-sdp-orc-followup-controls', 'sail-sdp-orc-original-followup']:
        wrapper = read(controls / (stem + '.json'))
        assert wrapper['completed'] is True and wrapper['before'] == wrapper['after'] == build['before']
        assert wrapper['server_before'] == wrapper['server_after'] == qualification['server_before']
        for check in wrapper['checks']:
            assert check['exit_code'] == (1 if Path(check['script']).name == 'sail-sdp-orc-ctas-control.py' else 0)
            assert sha(controls / Path(check['script']).name) == check['script_sha256']
            assert sha(controls / Path(check['log']).name) == check['log_sha256']
    original = read(controls / 'sail-sdp-orc-ctas-original-control.json')
    failed = read(controls / 'sail-sdp-orc-ctas-control.json')
    for stem, value in [('sail-sdp-orc-ctas-original-control', original), ('sail-sdp-orc-ctas-control', failed)]:
        assert value['script_sha256'] == sha(controls / (stem + '.py'))
        assert value['server']['cli_sha256'] == build['cli_sha256']
        assert value['source_sha256'] == sha(controls / 'input.orc')
        assert value['tables_absent'] and value['source_unchanged'] and value['cleanup_errors'] == []
    assert original['outcome'] == 'passed' and [case['name'] for case in original['cases']] == ['ctas', 'batch_mv']
    for case in original['cases']:
        assert case['schema'] == {'type': 'struct', 'fields': [{'name': 'id', 'type': 'long', 'nullable': True, 'metadata': {}}]}
        assert sorted(case['rows']) == [[0], [1], [2]]
    assert failed['outcome'] == 'failed' and 'uint64' in failed['error'] and 'spark.sql(sql).collect()' in failed['error']
    generic = read(controls / 'sail-sdp-orc-catalog-control-after.json')
    assert len(generic['cases']) == 6
    for case in generic['cases']:
        assert case['file_unchanged'] and sorted(case['table_rows']) == [[1], [3]]
        assert case['table_schema']['fields'][0]['type'] == ('long' if case['format'] == 'json' and not case['explicit_schema'] else 'integer')
        if not case['explicit_schema']:
            assert case['describe'] == [], 'retained omitted-schema DESCRIBE gap changed'
    scala = 'sql/pipelines/src/test/scala/org/apache/spark/sql/pipelines/graph/SqlPipelineSuite.scala'
    assert (controls / 'SqlPipelineSuite.scala').read_bytes() == git(Path('/Users/alexy/src/spark-sdp-4.2.1'), 'show', SPARK_PIN + ':' + scala)
    print('PASS exact ORC public packet: 201 Rust library tests;296 pytest;67 upstream;10 direct Spark reference cases; unchanged295/1 failed attempt and six same-binary controls retained')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packet', type=Path)
    parser.add_argument('--sail-repo', type=Path, default=Path('/Users/alexy/src/sail-pipelines-proposal'))
    parser.add_argument('--grust-repo', type=Path, default=Path('/Users/alexy/src/grust-sdp'))
    args = parser.parse_args()
    validate(args.packet.resolve(), args.sail_repo, args.grust_repo)


if __name__ == '__main__':
    main()
