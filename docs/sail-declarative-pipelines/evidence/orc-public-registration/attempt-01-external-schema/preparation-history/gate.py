"""Root-executed 296-case public replay and 67 upstream Python executions."""
import os
import subprocess
import traceback
import xml.etree.ElementTree as ET

from common import (
    BASELINE_SHA, LABEL, OUT, PIPELINE, PIPELINE_NODE, PUBLIC, PYTHON, REMOTE, ROOT,
    RUFF, SERVER_ENV, SPARK, SPARK_PIN, VENV, candidate, git, helpers, now,
    read_json, selected_nodes, sha, snapshot, verify_build, verify_reference,
    verify_server, write_json,
)


def check_pytest(selectors):
    tree = ET.parse(OUT / 'pytest.xml')
    suites = list(tree.iter('testsuite'))
    totals = tuple(sum(int(suite.get(key, 0)) for suite in suites)
                   for key in ['tests', 'failures', 'errors', 'skipped'])
    assert totals == (296, 0, 0, 0), totals
    actual = [test.get('classname').replace('.', '/') + '.py::' + test.get('name')
              for test in tree.iter('testcase')]
    assert len(actual) == len(set(actual)) == 296
    assert set(selectors[:-1]).issubset(actual), 'baseline or exact pipeline ORC node omitted'
    new = set(actual) - set(selectors[:-1])
    assert len(new) == 10 and all(node.startswith(PUBLIC + '::') for node in new)
    assert PIPELINE_NODE in actual
    return {'tests': 296, 'failures': 0, 'errors': 0, 'skipped': 0,
            'junit_sha256': sha(OUT / 'pytest.xml'), 'new_orc_nodes': sorted(new)}


def check_upstream():
    result = read_json(OUT / 'upstream.json')
    assert result['spark_commit'] == SPARK_PIN
    assert result['server_spark_version'] == result['spark_version'] == '4.2.1'
    assert result['remote'] == REMOTE
    assert result['tests_run'] == len(result['collected']) == len(result['outcomes']) == 67
    assert len(set(result['collected'])) == 67
    assert result['failures'] == result['errors'] == result['skipped'] == 0
    assert all(case['outcome'] == 'passed' for case in result['outcomes'])
    return {'tests_run': 67, 'failures': 0, 'errors': 0, 'skipped': 0,
            'report_sha256': sha(OUT / 'upstream.json')}


def main():
    assert not (OUT / 'gate.json').exists(), 'archive the prior attempt before rerunning'
    for filename in ['ruff.log', 'ruff-format.log', 'pytest.log', 'pytest.xml', 'upstream.log', 'upstream.json']:
        assert not (OUT / filename).exists(), 'refuse to overwrite ' + filename
    receipt = {'label': LABEL, 'started_at': now(), 'outcome': 'starting', 'checks': [],
               'scope': '296 selected public pytest cases and 67 upstream Python executions; not full SDP qualification.',
               'helpers_sha256': helpers(), 'server_environment': SERVER_ENV,
               'client_environment_overrides': {'PYTHONPATH': 'python', 'VIRTUAL_ENV': VENV,
                                                'SPARK_REMOTE': REMOTE, 'PYTHONDONTWRITEBYTECODE': '1'},
               'baseline_pytest_sha256': BASELINE_SHA}
    try:
        expected = candidate()
        receipt.update(sail_commit=expected['commit'], base=expected['base'])
        receipt['before'] = snapshot(expected)
        build = verify_build(expected)
        receipt['cli_sha256'] = build['cli_sha256']
        receipt['build_json_sha256'] = sha(OUT / 'build.json')
        receipt['spark_reference'] = verify_reference()
        receipt['server_before'] = verify_server(expected, build)
        assert git('rev-parse', 'HEAD', root=SPARK) == SPARK_PIN
        selectors = selected_nodes()
        assert read_json(OUT / 'selected-nodes.json') == selectors
        receipt['selected_nodes_sha256'] = sha(OUT / 'selected-nodes.json')
        write_json(OUT / 'gate.json', receipt)
        commands = [
            ('ruff', [RUFF, 'check', PIPELINE, PUBLIC]),
            ('ruff-format', [RUFF, 'format', '--check', PIPELINE, PUBLIC]),
            ('pytest', [PYTHON, '-m', 'pytest', '-q', *selectors, '--junitxml=' + str(OUT / 'pytest.xml')]),
            ('upstream', [PYTHON, 'scripts/spark-pipelines-tests/run.py', '--spark-source', str(SPARK),
                          '--remote', REMOTE, '--report', str(OUT / 'upstream.json')]),
        ]
        for name, command in commands:
            assert snapshot(expected) == receipt['before']
            verify_build(expected)
            verify_server(expected, build)
            check = {'name': name, 'command': command, 'started_at': now()}
            receipt['checks'].append(check)
            write_json(OUT / 'gate.json', receipt)
            with (OUT / (name + '.log')).open('x') as log:
                result = subprocess.run(command, cwd=ROOT,
                                        env={**os.environ, **receipt['client_environment_overrides']},
                                        stdout=log, stderr=subprocess.STDOUT)
            check.update(exit_code=result.returncode, completed_at=now(),
                         log_sha256=sha(OUT / (name + '.log')))
            write_json(OUT / 'gate.json', receipt)
            assert snapshot(expected) == receipt['before']
            verify_build(expected)
            verify_server(expected, build)
            assert result.returncode == 0, name + ' failed; retain the complete log before retrying'
            if name == 'pytest':
                receipt['pytest_summary'] = check_pytest(selectors)
            if name == 'upstream':
                receipt['upstream_summary'] = check_upstream()
            write_json(OUT / 'gate.json', receipt)
            print('PASS ORC public ' + name, flush=True)
        receipt['after'] = snapshot(expected)
        assert receipt['after'] == receipt['before']
        receipt['server_after'] = verify_server(expected, build)
        assert receipt['server_after'] == receipt['server_before']
        verify_build(expected)
        receipt['outcome'] = 'passed'
    except BaseException:
        receipt['outcome'] = 'failed'
        receipt['error'] = traceback.format_exc()
        raise
    finally:
        receipt['completed_at'] = now()
        write_json(OUT / 'gate.json', receipt)
    print('PASS detached ORC public gate ' + receipt['sail_commit'], flush=True)


if __name__ == '__main__':
    main()
