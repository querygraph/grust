"""Frozen detached source gate; writes receipts outside the Sail checkout."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--head', required=True)
    parser.add_argument('--tree', required=True)
    parser.add_argument('--exact', action='store_true')
    args = parser.parse_args()
    args.out.mkdir(exist_ok=False)

    def git(*command):
        return subprocess.check_output(['git', *command], cwd=args.root)

    def state():
        source = {}
        for name in git('ls-files', '-z').split(b'\0'):
            if not name:
                continue
            path = args.root / os.fsdecode(name)
            if path.is_symlink():
                data = os.fsencode(os.readlink(path))
            else:
                data = path.read_bytes()
            source[os.fsdecode(name)] = digest(data)
        return dict(head=git('rev-parse', 'HEAD').decode().strip(),
                    tree=git('write-tree').decode().strip(),
                    index=digest(git('ls-files', '--stage', '-z')),
                    status=git('status', '--porcelain').decode(),
                    diff=digest(git('diff', '--binary', 'HEAD')),
                    source=source,
                    detached=subprocess.run(['git', 'symbolic-ref', '-q', 'HEAD'], cwd=args.root,
                                            capture_output=True).returncode == 1)

    before = state()
    assert before['detached'] and before['head'] == args.head and before['tree'] == args.tree
    assert not git('diff', '--name-only')
    assert not git('ls-files', '--others', '--exclude-standard')
    if args.exact:
        assert before['status'] == ''
    free = shutil.disk_usage(args.root).free
    assert free >= 30 * 1024**3, free
    env = dict(os.environ, CARGO_TARGET_DIR=str(args.target), CARGO_INCREMENTAL='0',
               CARGO_PROFILE_DEV_DEBUG='0', CARGO_PROFILE_TEST_DEBUG='0', CARGO_BUILD_JOBS='6')
    receipt = dict(started_utc=utc(), outcome='RUNNING', source=str(args.root), target=str(args.target),
                   before=before, free_bytes_before=free, exact_commit=args.exact, steps=[],
                   environment={k: env[k] for k in ('CARGO_TARGET_DIR', 'CARGO_INCREMENTAL',
                       'CARGO_PROFILE_DEV_DEBUG', 'CARGO_PROFILE_TEST_DEBUG', 'CARGO_BUILD_JOBS')})
    def save():
        (args.out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    save()
    try:
        for name, command in [
            ('fmt', ['cargo', 'fmt', '-p', 'sail-data-source', '--check']),
            ('clippy', ['cargo', 'clippy', '--locked', '-p', 'sail-data-source', '--all-targets', '--', '-D', 'warnings']),
            ('tests', ['cargo', 'test', '--locked', '-p', 'sail-data-source', '--lib']),
        ]:
            step = dict(name=name, command=command, started_utc=utc())
            receipt['steps'].append(step)
            save()
            started = time.monotonic()
            with (args.out / (name + '.log')).open('x') as stream:
                result = subprocess.run(command, cwd=args.root, env=env, stdout=stream, stderr=subprocess.STDOUT)
            step.update(returncode=result.returncode, finished_utc=utc(), elapsed_seconds=time.monotonic()-started)
            save()
            print(name, result.returncode, flush=True)
            print('\n'.join((args.out / (name + '.log')).read_text().splitlines()[-10:]), flush=True)
            assert result.returncode == 0, name
        receipt['after'] = state()
        assert receipt['after'] == before, 'source changed during gate'
        receipt['outcome'] = 'PASS'
    except BaseException as error:
        receipt['outcome'] = 'FAIL'
        receipt['error'] = repr(error)
        raise
    finally:
        receipt['finished_utc'] = utc()
        receipt['free_bytes_after'] = shutil.disk_usage(args.root).free
        save()
    print(f"PARQUET_FLOAT_STATISTICS_GATE PASS {args.head} {'exact commit' if args.exact else 'staged tree '+args.tree}", flush=True)


if __name__ == '__main__':
    main()
