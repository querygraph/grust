"""Gate the exact clean detached integration commit; no source mutations."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import sys

ROOT = Path('/private/tmp/sail-stream-review-integrated-gate')
TARGET = Path('/private/tmp/sail-stream-review-integrated-host-target')
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=False)
EXACT = sys.argv[2] if len(sys.argv) == 3 else None
BASE = '56194b170155301ba91077f0ba3df31fe2c78b6b'
PYTHON = '/Users/alexy/src/sail-extensions-poc/.venvs/extensions-datafusion/bin/python'


def utc():
    return datetime.now(timezone.utc).isoformat()


def command(*args):
    return subprocess.check_output(list(args), cwd=ROOT)


def snapshot():
    contents = hashlib.sha256()
    files = command('git', 'ls-files', '-z').split(b'\0')
    for name in files:
        if not name:
            continue
        path = ROOT / os.fsdecode(name)
        contents.update(name + b'\0')
        if path.is_symlink():
            contents.update(b'link\0' + os.fsencode(os.readlink(path)))
        else:
            contents.update(b'file\0')
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1 << 20), b''):
                    contents.update(block)
        contents.update(b'\0')
    detached = subprocess.run(['git', 'symbolic-ref', '-q', 'HEAD'], cwd=ROOT,
                              capture_output=True).returncode == 1
    return dict(head=command('git', 'rev-parse', 'HEAD').decode().strip(), detached=detached,
                branch_head=command('git', 'rev-parse', 'work/stream-review-integrated').decode().strip(),
                tracked_source_sha256=contents.hexdigest(),
                index_sha256=hashlib.sha256(command('git', 'ls-files', '--stage', '-z')).hexdigest(),
                diff_sha256=hashlib.sha256(command('git', 'diff', '--binary', 'HEAD')).hexdigest(),
                status=command('git', 'status', '--porcelain').decode())


def main():
    before = snapshot()
    if not before['detached'] or before['head'] != (EXACT or BASE):
        raise RuntimeError('unexpected commit or attached source')
    if before['branch_head'] != before['head']:
        raise RuntimeError('named branch no longer identifies this commit')
    if EXACT and before['status']:
        raise RuntimeError('exact-commit gate requires a clean working tree and index')
    if not EXACT and command('git', 'diff', '--binary', 'HEAD') != Path('/tmp/stream-review-integrated-evidence/candidate.patch').read_bytes():
        raise RuntimeError('candidate differs from frozen patch')
    env = dict(os.environ, CARGO_TARGET_DIR=str(TARGET), CARGO_INCREMENTAL='0',
               CARGO_PROFILE_DEV_DEBUG='0', CARGO_PROFILE_TEST_DEBUG='0', CARGO_BUILD_JOBS='6',
               PYTHONDONTWRITEBYTECODE='1')
    receipt = dict(started_utc=utc(), outcome='running', identity=('exact clean detached commit ' + EXACT if EXACT else 'detached staged candidate based on ' + BASE),
                   source=str(ROOT), target=str(TARGET), before=before, steps=[],
                   environment={key: env[key] for key in ('CARGO_TARGET_DIR', 'CARGO_INCREMENTAL',
                                'CARGO_PROFILE_DEV_DEBUG', 'CARGO_PROFILE_TEST_DEBUG', 'CARGO_BUILD_JOBS')},
                   free_bytes_before=shutil.disk_usage(ROOT).free,
                   rustc=command('rustc', '--version').decode().strip(),
                   target_seed='APFS clone of idle /private/tmp/sail-compact-struct-min-target; independently owned target')

    def save():
        (OUT / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')

    def step(name, args, process_env):
        record = dict(name=name, command=args, started_utc=utc())
        receipt['steps'].append(record)
        save()
        started = time.monotonic()
        with (OUT / (name + '.log')).open('x') as log:
            result = subprocess.run(args, cwd=ROOT, env=process_env, stdout=log, stderr=subprocess.STDOUT)
        record.update(returncode=result.returncode, finished_utc=utc(), elapsed_seconds=time.monotonic() - started)
        save()
        print(name, result.returncode, flush=True)
        print('\n'.join((OUT / (name + '.log')).read_text().splitlines()[-8:]), flush=True)

    save()
    try:
        step('fmt', ['cargo', 'fmt', '--all', '--check'], env)
        step('clippy', ['cargo', 'clippy', '--locked', '-p', 'sail-function', '-p', 'sail-plan', '-p', 'sail-execution', '--all-targets', '--', '-D', 'warnings'], env)
        step('tests', ['cargo', 'test', '--locked', '-p', 'sail-function', '-p', 'sail-plan', '-p', 'sail-execution', '--lib'], env)
        python_env = dict(env, PYTHONPATH=str(ROOT / 'examples/extensions/graph-algorithms/src'),
                          SPARK_CONNECT_MODE_ENABLED='1')
        python_env.pop('SAIL_GRAPH_TEST_REMOTE', None)
        receipt['python_versions'] = subprocess.check_output([
            PYTHON, '-c', 'import importlib.metadata as m,json;print(json.dumps({p:m.version(p) for p in ("pyspark","protobuf","pytest")}))'
        ], env=python_env, text=True).strip()
        step('pecan-nonintegration', [PYTHON, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                                     '-m', 'not integration', 'examples/extensions/graph-algorithms/tests'], python_env)
        receipt['after'] = snapshot()
        receipt['source_unchanged'] = receipt['after'] == before
        receipt['outcome'] = ('passed' if receipt['source_unchanged'] and
                              all(item['returncode'] == 0 for item in receipt['steps']) else 'failed')
    except BaseException as error:
        receipt.update(outcome='failed', error=repr(error), after=snapshot())
    finally:
        receipt.update(finished_utc=utc(), free_bytes_after=shutil.disk_usage(ROOT).free)
        save()
    print(('EXACT_COMMIT_GATE ' if EXACT else 'CANDIDATE_GATE ') + receipt['outcome'].upper() + ' ' + before['head'] + ' source_sha256=' + before['tracked_source_sha256'], flush=True)
    return 0 if receipt['outcome'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
