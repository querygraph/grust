"""Supplemental read-only qualification of completed runs; never reruns tests.

Writes a separate evidence directory. Preserves frozen helpers and raw gate.json,
whose unique-ID assertion incorrectly rejected valid repeated unittest IDs.
"""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import argparse
import ast
import hashlib
import inspect
import json
import subprocess
import sys
import traceback
import unittest
import xml.etree.ElementTree as ET

PUBLIC = Path('/tmp/sail-sdp-orc-public')
BASELINE = Path('/tmp/sail-sdp-time-public/upstream.json')
BASELINE_SHA = 'f1ff78f805018eb13f1d381e55ad4fbf667eb65abcff46b908055981b7e55d2d'
CANDIDATE = Path('/tmp/sail-sdp-orc-public-registration-candidate.json')
COMMIT = '07fa5d5bee4be197c000e9229beef76af1da377e'
SPARK = Path('/Users/alexy/src/spark-sdp-4.2.1')
PIN = '617618396087429b5627a86ce933bb0f5d6645cb'
REPEATED = 'pyspark.testing.connectutils.ReusedConnectTestCase.test_assert_remote_mode'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def stamp():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('/tmp/sail-sdp-orc-public-qualification'))
    args = parser.parse_args()
    out = args.output
    assert not out.exists(), 'preserve any prior supplemental attempt'
    out.mkdir(parents=True)
    result = {'status': 'starting', 'started_at': stamp(), 'sail_commit': COMMIT,
              'script_sha256': sha(__file__), 'tests_rerun': False,
              'scope': 'Supplemental validation of already-completed results and immutable runtime/source receipts.'}

    def save():
        (out / 'qualification.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')

    def retain(source, relative):
        destination = out / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        return sha(destination)

    try:
        candidate = read(CANDIDATE)
        assert candidate['commit'] == COMMIT
        result['candidate_sha256'] = retain(CANDIDATE, 'candidate.json')
        build, gate = read(PUBLIC / 'build.json'), read(PUBLIC / 'gate.json')
        for name, digest in build['helpers_sha256'].items():
            assert sha(PUBLIC / name) == digest
        # Execute only definitions from the unchanged, hash-verified helper.
        # No import cache or other file is written in its frozen directory.
        common = {'__file__': str(PUBLIC / 'common.py'), '__name__': 'qualified_common_definitions'}
        exec(compile((PUBLIC / 'common.py').read_bytes(), str(PUBLIC / 'common.py'), 'exec'), common)
        assert common['candidate']() == candidate
        before = common['snapshot'](candidate)
        assert common['verify_build'](candidate) == build
        server_before = common['verify_server'](candidate, build)
        common['verify_reference']()
        result.update(before=before, cli_sha256=build['cli_sha256'], helpers_sha256=build['helpers_sha256'],
                      server_before=server_before, build_json_sha256=sha(PUBLIC / 'build.json'))
        result['raw_gate_sha256'] = retain(PUBLIC / 'gate.json', 'raw-gate.json')
        retain(PUBLIC / 'server.json', 'server-running.json')
        assert gate['outcome'] == 'failed' and gate['sail_commit'] == COMMIT
        assert "len(set(result['collected'])) == 67" in gate['error']
        assert gate['error'].rstrip().endswith('AssertionError')
        assert [(c['name'], c['exit_code']) for c in gate['checks']] == [('ruff', 0), ('ruff-format', 0), ('pytest', 0), ('upstream', 0)]
        for check in gate['checks']:
            assert sha(PUBLIC / (check['name'] + '.log')) == check['log_sha256']
        assert gate['before'] == build['before'] == build['after'] == before
        assert gate['helpers_sha256'] == build['helpers_sha256']
        selectors = common['selected_nodes']()
        assert read(PUBLIC / 'selected-nodes.json') == selectors
        assert gate['checks'][2]['command'][4:-1] == selectors
        assert gate['checks'][0]['command'][1:] == ['check', common['PIPELINE'], common['PUBLIC']]
        assert gate['checks'][1]['command'][1:] == ['format', '--check', common['PIPELINE'], common['PUBLIC']]
        tree = ET.parse(PUBLIC / 'pytest.xml')
        totals = tuple(sum(int(s.get(key, 0)) for s in tree.iter('testsuite')) for key in ['tests', 'failures', 'errors', 'skipped'])
        assert totals == (296, 0, 0, 0)
        actual = [t.get('classname').replace('.', '/') + '.py::' + t.get('name') for t in tree.iter('testcase')]
        assert len(actual) == len(set(actual)) == 296 and set(selectors[:-1]).issubset(actual)
        new = set(actual) - set(selectors[:-1])
        assert len(new) == 10 and all(node.startswith(common['PUBLIC'] + '::') for node in new)
        upstream = read(PUBLIC / 'upstream.json')
        assert upstream['spark_commit'] == PIN and upstream['remote'] == 'sc://localhost:50088'
        assert upstream['spark_version'] == upstream['server_spark_version'] == '4.2.1'
        assert upstream['tests_run'] == len(upstream['collected']) == len(upstream['outcomes']) == 67
        assert upstream['failures'] == upstream['errors'] == upstream['skipped'] == 0
        assert all(case['outcome'] == 'passed' for case in upstream['outcomes'])
        collected = Counter(upstream['collected'])
        outcomes = Counter(case['id'] for case in upstream['outcomes'])
        assert collected == outcomes and len(collected) == 63
        assert {name: count for name, count in collected.items() if count > 1} == {REPEATED: 5}
        assert sha(BASELINE) == BASELINE_SHA
        baseline = read(BASELINE)
        assert Counter(baseline['collected']) == Counter(case['id'] for case in baseline['outcomes']) == collected
        assert baseline['tests_run'] == 67 and baseline['failures'] == baseline['errors'] == baseline['skipped'] == 0
        assert all(case['outcome'] == 'passed' for case in baseline['outcomes'])
        retain(BASELINE, 'prior-time-upstream.json')
        result['pytest'] = {'tests': 296, 'failures': 0, 'errors': 0, 'skipped': 0, 'sha256': sha(PUBLIC / 'pytest.xml')}
        result['upstream'] = {'executions': 67, 'unique_ids': 63, 'failures': 0, 'errors': 0, 'skipped': 0,
                              'collected_counter': dict(sorted(collected.items())), 'outcome_counter': dict(sorted(outcomes.items())),
                              'repeated_ids': {REPEATED: 5}, 'sha256': sha(PUBLIC / 'upstream.json'), 'prior_baseline_sha256': BASELINE_SHA}
        # Source audit only: no suite collection or test execution is performed.
        source_audit = []
        def source(repo, commit, path, relative):
            data = git(repo, 'show', commit + ':' + path)
            destination = out / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            source_audit.append({'repository': str(repo), 'commit': commit, 'path': path, 'retained': relative,
                'blob': git(repo, 'rev-parse', commit + ':' + path).decode().strip(), 'sha256': sha(destination)})
            return data
        runner_path = 'scripts/spark-pipelines-tests/run.py'
        runner = source(common['ROOT'], COMMIT, runner_path, 'source/runner.py')
        assert runner == (common['ROOT'] / runner_path).read_bytes()
        assert b'loadTestsFromModule(module)' in runner
        paths = git(SPARK, 'ls-tree', '-r', '--name-only', PIN, 'python/pyspark/pipelines/tests').decode().splitlines()
        importers = []
        for path in paths:
            if Path(path).name.startswith('test_') and path.endswith('.py'):
                raw = source(SPARK, PIN, path, 'source/spark/' + Path(path).name)
                assert raw == (SPARK / path).read_bytes()
                module = ast.parse(raw)
                if any(isinstance(node, ast.ImportFrom) and node.module == 'pyspark.testing.connectutils'
                       and any(alias.name == 'ReusedConnectTestCase' and alias.asname in (None, 'ReusedConnectTestCase') for alias in node.names)
                       for node in ast.walk(module)):
                    importers.append(path)
        assert len(importers) == 5
        base = source(SPARK, PIN, 'python/pyspark/testing/connectutils.py', 'source/connectutils.py')
        installed = Path(common['VENV']) / 'lib/python3.12/site-packages/pyspark/testing/connectutils.py'
        assert installed.read_bytes() == base
        assert b'def test_assert_remote_mode(self)' in base
        loader = Path(inspect.getsourcefile(unittest.TestLoader))
        retain(loader, 'source/unittest-loader.py')
        method = inspect.getsource(unittest.TestLoader.loadTestsFromModule)
        assert 'for name in dir(module)' in method and 'issubclass(obj, case.TestCase)' in method
        assert 'obj not in (case.TestCase, case.FunctionTestCase)' in method
        result['source_audit'] = source_audit
        result['duplicate_source_explanation'] = {'importing_modules': importers,
            'installed_connectutils_matches_pinned_source': True, 'unittest_loader_path': str(loader),
            'unittest_loader_sha256': sha(loader), 'python_version': sys.version,
            'interpretation': 'Each of five test modules binds the imported base TestCase; loadTestsFromModule enumerates imported TestCase classes, producing the same base-class remote-mode test ID five times. The reports preserve all executions.'}
        assert common['snapshot'](candidate) == before
        assert common['verify_build'](candidate) == build
        result['after'] = common['snapshot'](candidate)
        result['server_after'] = common['verify_server'](candidate, build)
        assert result['server_after'] == server_before
        assert sha(PUBLIC / 'gate.json') == result['raw_gate_sha256']
        retain(Path(__file__), 'qualify.py')
        result['status'] = 'passed'
    except BaseException:
        result['status'] = 'failed'
        result['error'] = traceback.format_exc()
        raise
    finally:
        result['completed_at'] = stamp()
        result['files'] = [{'path': str(p.relative_to(out)), 'bytes': p.stat().st_size, 'sha256': sha(p)}
                           for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'qualification.json']
        save()
    print('PASS supplemental qualification:296 pytest;67 upstream executions (63 unique IDs), exact multiplicities/source/baseline; no tests rerun; raw gate failure unchanged', flush=True)


if __name__ == '__main__':
    main()
