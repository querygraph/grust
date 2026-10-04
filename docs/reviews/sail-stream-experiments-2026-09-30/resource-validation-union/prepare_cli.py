"""Build the frozen detached union CLI; this is preparation, not a gate verdict."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

OUT = Path(__file__).resolve().parent
REPO = Path('/private/tmp/sail-resource-validation-union-gate')
TARGET = Path('/private/tmp/sail-resource-validation-union-target/host')
PYTHON = '/Users/alexy/src/sail-extensions-poc/.venvs/extensions-datafusion/bin/python'
PYTHON_ROOT = '/Users/alexy/.local/share/uv/python/cpython-3.12.8-macos-aarch64-none'


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(['git', '-C', str(REPO), *args])


def state():
    files = {}
    for name in git('ls-files', '-z').split(b'\0'):
        if name:
            p = REPO / os.fsdecode(name)
            files[os.fsdecode(name)] = sha(os.fsencode(os.readlink(p)) if p.is_symlink() else p.read_bytes())
    return dict(head=git('rev-parse', 'HEAD').decode().strip(),
                tree=git('write-tree').decode().strip(),
                index=sha(git('ls-files', '--stage', '-z')), files=files)


def main():
    output = OUT / 'cli-preparation'
    output.mkdir(exist_ok=False)
    prep = json.loads((OUT / 'source-preparation.json').read_text())
    targets = json.loads((OUT / 'target-preparation.json').read_text())
    assert targets['outcome'] == 'PASS_PRIVATE_TARGET_PREPARATION'
    assert subprocess.run(['git', '-C', str(REPO), 'symbolic-ref', '-q', 'HEAD'], capture_output=True).returncode == 1
    assert not git('diff', '--name-only') and not git('ls-files', '--others', '--exclude-standard')
    before = state()
    assert before['head'] == prep['base'] and before['tree'] == prep['tree']
    free = shutil.disk_usage(REPO).free
    assert free >= 32 * 1024**3
    overrides = dict(CARGO_TARGET_DIR=str(TARGET), CARGO_INCREMENTAL='0', CARGO_NET_OFFLINE='true',
                     CARGO_PROFILE_DEV_DEBUG='0', CARGO_PROFILE_TEST_DEBUG='0', CARGO_BUILD_JOBS='6',
                     PYO3_PYTHON=PYTHON, PYTHONHOME=PYTHON_ROOT,
                     DYLD_LIBRARY_PATH=PYTHON_ROOT + '/lib')
    env = {k: v for k, v in os.environ.items() if not k.startswith('SAIL_') and k != 'PYTHONPATH'}
    env.update(overrides)
    command = ['cargo', 'build', '--locked', '--offline', '-p', 'sail-cli', '--bin', 'sail']
    receipt = dict(started_utc=utc(), before=before, free_bytes_before=free,
                   environment=overrides, command=command, driver_sha256=sha(Path(__file__).read_bytes()),
                   interpreter_sha256=sha(Path(PYTHON).resolve().read_bytes()),
                   scope='Preliminary CLI compilation from frozen detached staged union; no test/runtime/performance verdict.')
    path = output / 'receipt.json'

    def save():
        path.write_text(json.dumps(receipt, indent=2) + '\n')

    save()
    try:
        with (output / 'build.log').open('x') as log:
            process = subprocess.run(command, cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT)
        receipt['returncode'] = process.returncode
        process.check_returncode()
        receipt['after'] = state()
        assert receipt['after'] == before
        assert not git('diff', '--name-only') and not git('ls-files', '--others', '--exclude-standard')
        binary = TARGET / 'debug/sail'
        receipt['binary'] = dict(path=str(binary), bytes=binary.stat().st_size, sha256=sha(binary.read_bytes()))
        version = subprocess.run([str(binary), '--version'], cwd=REPO, env=env, capture_output=True, text=True, timeout=15)
        receipt['version'] = dict(returncode=version.returncode, stdout=version.stdout, stderr=version.stderr)
        version.check_returncode()
        receipt['outcome'] = 'BUILT_FROZEN_CANDIDATE_CLI'
    except BaseException as error:
        receipt.update(outcome='PREPARATION_FAILED', error=repr(error))
        raise
    finally:
        receipt.update(finished_utc=utc(), free_bytes_after=shutil.disk_usage(REPO).free,
                       log_sha256=sha((output / 'build.log').read_bytes()))
        save()
    print(json.dumps(dict(outcome=receipt['outcome'], binary=receipt['binary'])), flush=True)


if __name__ == '__main__':
    main()
