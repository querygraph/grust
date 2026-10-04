"""Run a frozen detached test-only baseline or candidate SSSP control."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-code', type=int, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    env = dict(os.environ, CARGO_INCREMENTAL='0', CARGO_NET_OFFLINE='true', CARGO_BUILD_JOBS='6',
               CARGO_TARGET_DIR='/private/tmp/sail-sssp-candidate-target/core', GIT_OPTIONAL_LOCKS='0')

    def git(*cmd):
        return subprocess.check_output(['git', *cmd], cwd=args.repo, env=env)

    def state():
        assert subprocess.run(['git', 'symbolic-ref', '-q', 'HEAD'], cwd=args.repo,
                              env=env, capture_output=True).returncode == 1
        assert not git('diff', '--name-only') and not git('ls-files', '--others', '--exclude-standard')
        files = {}
        for name in git('ls-files', '-z').split(b'\0'):
            if name:
                path = args.repo / os.fsdecode(name)
                data = os.fsencode(os.readlink(path)) if path.is_symlink() else path.read_bytes()
                files[os.fsdecode(name)] = [path.lstat().st_mode, hashlib.sha256(data).hexdigest()]
        return dict(head=git('rev-parse', 'HEAD').decode().strip(), tree=git('write-tree').decode().strip(),
                    index_sha256=hashlib.sha256(git('ls-files', '--stage', '-z')).hexdigest(), files=files)

    receipt = dict(started_utc=utc(), outcome='RUNNING', repo=str(args.repo),
                   driver_sha256=sha(Path(__file__)), expected_code=args.expected_code,
                   environment={k: env[k] for k in ('CARGO_INCREMENTAL', 'CARGO_NET_OFFLINE',
                                'CARGO_BUILD_JOBS', 'CARGO_TARGET_DIR', 'GIT_OPTIONAL_LOCKS')})
    try:
        before = state()
        (args.output / 'source-before.json').write_text(json.dumps(before, indent=2)+'\n')
        (args.output / 'source.patch').write_bytes(git('diff', '--cached', '--binary'))
        receipt['free_bytes'] = shutil.disk_usage(args.repo).free
        assert receipt['free_bytes'] >= 32 * 1024**3
        cmd = ['cargo', 'test', '--manifest-path', 'examples/extensions/argentea/Cargo.toml',
               '--release', '--locked', '--offline', '--lib', 'reuse_tests', '--', '--nocapture']
        receipt['command'] = cmd
        with (args.output / 'tests.log').open('x') as log:
            result = subprocess.run(cmd, cwd=args.repo, env=env, stdout=log, stderr=subprocess.STDOUT)
        receipt['returncode'] = result.returncode
        after = state()
        (args.output / 'source-after.json').write_text(json.dumps(after, indent=2)+'\n')
        assert before == after, 'source changed'
        assert result.returncode == args.expected_code
        receipt['outcome'] = 'PASS' if args.expected_code == 0 else 'EXPECTED_BASELINE_FAILURE_RETAINED'
    except BaseException as error:
        receipt.update(outcome='FAIL', error=repr(error))
    finally:
        receipt.update(finished_utc=utc(), files={p.name: sha(p) for p in args.output.iterdir() if p.is_file()})
        (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(receipt['outcome'], flush=True)
    return int(receipt['outcome'] == 'FAIL')


if __name__ == '__main__':
    sys.exit(main())
