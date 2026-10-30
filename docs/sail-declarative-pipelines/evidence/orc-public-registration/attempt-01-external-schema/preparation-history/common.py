"""Read-only provenance checks shared by root-executed public gate helpers."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path('/Users/alexy/src/sail-sdp-gate')
OUT = Path(__file__).resolve().parent
LABEL = 'orc-public-registration'
CANDIDATE = Path('/tmp/sail-sdp-orc-public-registration-candidate.json')
PYTHON = '/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python'
VENV = '/Users/alexy/src/sail-pipelines-proposal/.venv'
RUFF = '/Users/alexy/.cache/uv/archive-v0/Mi-CiNT8OaLEq_dG/ruff-0.16.9.data/scripts/ruff'
CLI = ROOT / 'target/debug/sail'
SPARK = Path('/Users/alexy/src/spark-sdp-4.2.1')
SPARK_PIN = '617618396087429b5627a86ce933bb0f5d6645cb'
PORT = 50088
REMOTE = 'sc://localhost:50088'
REFERENCE = Path('/tmp/sail-sdp-orc-public-reference')
REFERENCE_MANIFEST_SHA = '137d93140b122ce5d7784ee62c58ce8d7883ec9cdfacdfbcc56ead0385d62e22'
BASELINE_SHA = '9ea4f2fbb93bd3121387e306ab49e7b8417e907b6ec778d97ab89a92d0d81b6f'
PUBLIC = 'python/pysail/tests/spark/datasource/test_orc.py'
PIPELINE = 'python/pysail/tests/spark/pipelines/test_file_sources.py'
PIPELINE_NODE = PIPELINE + '::test_batch_pipeline_reads_file_source[orc]'
FROZEN = {
    'crates/sail-session/src/formats.rs': '537d22b659c4ca6fbfa01e11cd97052ff4244b292acd959e524c6c2ab235a57f',
    PIPELINE: 'd860e9406a069261de11f9ad541b744cb50aa3902c7d5bc58a242057ee019cd0',
    PUBLIC: 'c8e73063a7aeb9085b7e801ac67561747cb67d545f60974d092f9f982e879f2c',
    'python/pysail/tests/spark/datasource/orc_data/time_precisions.orc': '7504f8007af001893ccd60b873ded01bffae4b4cf4af95b1e054e7b07ff92986',
    'python/pysail/tests/spark/datasource/orc_data/spark-reference.json': '2a7a1e2e295fad6b2728538f227a9237c4796b86ae67d6813c27893ef1b13fbc',
}
SERVER_ENV = {
    'PYTHONPATH': VENV + '/lib/python3.12/site-packages',
    'VIRTUAL_ENV': VENV,
    'PYTHONDONTWRITEBYTECODE': '1',
}
BUILD_ENV = {
    'CARGO_PROFILE_DEV_DEBUG': '0',
    'CARGO_PROFILE_DEV_INCREMENTAL': 'false',
    'CARGO_INCREMENTAL': '0',
    'PYO3_PYTHON': PYTHON,
    'CARGO_TARGET_DIR': str(ROOT / 'target'),
}


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def git(*arguments, root=ROOT):
    return subprocess.check_output(['git', '-C', str(root), *arguments], text=True).strip()


def candidate():
    result = read_json(CANDIDATE)
    assert result.get('label', LABEL) == LABEL, 'wrong candidate label'
    assert set(result['paths']) == set(FROZEN), 'candidate must contain the five frozen E paths'
    assert len(result['paths']) == len(FROZEN)
    assert git('rev-parse', result['commit'] + '^') == result['base']
    return result


def snapshot(expected):
    head = git('rev-parse', 'HEAD')
    assert head == expected['commit'], (head, expected['commit'])
    status = git('status', '--porcelain', '--untracked-files=all')
    assert not status, status
    detached = subprocess.run(['git', '-C', str(ROOT), 'symbolic-ref', '-q', 'HEAD'], capture_output=True)
    assert detached.returncode == 1, 'gate checkout must be detached'
    sources = {path: sha(ROOT / path) for path in FROZEN}
    assert sources == FROZEN, 'frozen E source or fixture changed'
    return {'head': head, 'tree': git('rev-parse', 'HEAD^{tree}'), 'status': status,
            'detached': True, 'sources': sources, 'cargo_lock_sha256': sha(ROOT / 'Cargo.lock'),
            'candidate_sha256': sha(CANDIDATE)}


def helpers():
    return {path.name: sha(path) for path in sorted(OUT.glob('*.py'))}


def verify_reference():
    assert sha(REFERENCE / 'MANIFEST.json') == REFERENCE_MANIFEST_SHA
    manifest = read_json(REFERENCE / 'MANIFEST.json')
    for entry in manifest['files']:
        file = REFERENCE / entry['path']
        assert file.stat().st_size == entry['size'] and sha(file) == entry['sha256'], entry['path']
    result = read_json(REFERENCE / 'results.json')
    assert result['summary'] == {'passed': 10, 'failed': 0} and result['status'] == 'completed'
    assert result['spark_version'] == result['pyspark_version'] == '4.2.1'
    assert result['session_class'] == 'pyspark.sql.connect.session.SparkSession'
    assert result['owned_gateway_exit_code'] == 0
    assert sha(REFERENCE / 'source/test_orc.py') == FROZEN[PUBLIC]
    for filename in ['time_precisions.orc', 'spark-reference.json']:
        assert sha(REFERENCE / 'source/orc_data' / filename) == FROZEN[PUBLIC.replace('test_orc.py', 'orc_data/' + filename)]
    return {'manifest_sha256': REFERENCE_MANIFEST_SHA, 'results_sha256': sha(REFERENCE / 'results.json'),
            'scope': 'Ten unchanged functions/parameter cases through Spark Connect; direct fixture invocation, not pytest.'}


def selected_nodes():
    baseline = OUT / 'inputs/baseline-pytest.xml'
    assert sha(baseline) == BASELINE_SHA
    tree = ET.parse(baseline)
    suite = tree.getroot().find('testsuite')
    assert tuple(suite.get(k) for k in ['tests', 'failures', 'errors', 'skipped']) == ('285', '0', '0', '0')
    nodes = [test.get('classname').replace('.', '/') + '.py::' + test.get('name')
             for test in tree.iter('testcase')]
    assert len(nodes) == len(set(nodes)) == 285
    assert PIPELINE_NODE not in nodes and not any(node.startswith(PUBLIC + '::') for node in nodes)
    return nodes + [PIPELINE_NODE, PUBLIC]


def verify_build(expected):
    build = read_json(OUT / 'build.json')
    assert build['outcome'] == 'passed' and build['build_exit_code'] == 0
    assert build['sail_commit'] == expected['commit'] and build['base'] == expected['base']
    assert build['command'] == ['cargo', '+1.98.1', 'build', '-p', 'sail-cli', '--locked']
    assert build['environment_overrides'] == BUILD_ENV
    assert build['before'] == build['after'] == snapshot(expected)
    assert build['helpers_sha256'] == helpers(), 'gate helpers changed after the build receipt'
    assert build['build_log_sha256'] == sha(OUT / 'build.log')
    assert build['cli_path'] == str(CLI) and build['cli_sha256'] == sha(CLI)
    return build


def listener_pids():
    result = subprocess.run(['/usr/sbin/lsof', '-nP', '-iTCP:' + str(PORT), '-sTCP:LISTEN', '-Fp'], text=True, capture_output=True)
    assert result.returncode in (0, 1), result.stderr
    return {int(line[1:]) for line in result.stdout.splitlines() if line.startswith('p')}


def verify_server(expected, build):
    server = read_json(OUT / 'server.json')
    assert server['outcome'] == 'running' and server['sail_commit'] == expected['commit']
    assert server['cli_sha256'] == build['cli_sha256'] == sha(CLI)
    assert server['build_json_sha256'] == sha(OUT / 'build.json')
    assert server['environment_overrides'] == SERVER_ENV
    assert server['remote'] == REMOTE and server['port'] == PORT
    assert listener_pids() == {server['pid']}, 'wrong or missing port owner'
    command = subprocess.check_output(['ps', '-p', str(server['pid']), '-o', 'command='], text=True).strip()
    assert command == ' '.join(server['command'])
    return {key: server[key] for key in ['pid', 'command', 'cli_sha256', 'remote', 'started_at']}
