"""One isolated actual-allocation drop control; no workload or timing claim."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

BASE = 'a3462345a6764096024c055dc4d105a3c634e5a4'
ROOT = Path(__file__).resolve().parent
TEST = 'examples/extensions/argentea/tests/pagerank_cursor_lease.rs'
PRODUCTION = 'examples/extensions/argentea/src/pagerank/emission.rs'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=['baseline', 'candidate'])
    args = parser.parse_args()
    repo = Path('/private/tmp/sail-cursor-lease-'+args.kind)
    out = ROOT/args.kind
    out.mkdir(exist_ok=False)
    env = dict(os.environ, GIT_OPTIONAL_LOCKS='0', CARGO_INCREMENTAL='0',
               CARGO_NET_OFFLINE='true', CARGO_BUILD_JOBS='2',
               CARGO_TARGET_DIR='/private/tmp/sail-cursor-lease-target')

    def git(*command):
        return subprocess.check_output(['git', '-C', str(repo), *command], env=env).decode().strip()

    def snapshot():
        assert git('rev-parse', 'HEAD') == BASE
        assert subprocess.run(['git', '-C', str(repo), 'symbolic-ref', '-q', 'HEAD'], env=env, capture_output=True).returncode == 1
        assert not git('diff', '--name-only') and not git('ls-files', '--others', '--exclude-standard')
        changed = git('diff', '--cached', '--name-only').splitlines()
        assert set(changed) == ({TEST} if args.kind == 'baseline' else {TEST, PRODUCTION})
        return dict(head=BASE, tree=git('write-tree'), changed=changed,
                    files={name:sha(repo/name) for name in [TEST, PRODUCTION]})

    before = snapshot()
    command = ['cargo', 'test', '--manifest-path', str(repo/'examples/extensions/argentea/Cargo.toml'),
               '--release', '--locked', '--offline', '--test', 'pagerank_cursor_lease',
               '--', '--nocapture', '--test-threads=1']
    receipt = dict(started_utc=datetime.now(timezone.utc).isoformat(), kind=args.kind,
        source=before, command=command, script_sha256=sha(Path(__file__)),
        environment={key:env[key] for key in ['CARGO_INCREMENTAL','CARGO_NET_OFFLINE','CARGO_BUILD_JOBS','CARGO_TARGET_DIR']},
        rustc=subprocess.check_output(['rustc', '-Vv'], env=env, text=True),
        scope='Thread-local exact-size/pointer lifetime test, one sequence allocation of 2056 bytes. '
              'No graph benchmark, timing/RSS claim, global lease audit or remote operation.')
    try:
        with (out/'stdout').open('x') as stdout, (out/'stderr').open('x') as stderr:
            result = subprocess.run(command, cwd=repo, env=env, stdout=stdout, stderr=stderr, timeout=120)
        receipt['returncode'] = result.returncode
        assert snapshot() == before
        receipt['source_unchanged'] = True
        expected = 101 if args.kind == 'baseline' else 0
        assert result.returncode == expected
        text = (out/'stdout').read_text()
        summary = '2 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out' if args.kind == 'baseline' else '3 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out'
        assert summary in text
        rows = re.findall(r'CURSOR_LEASE mode=(\S+) sequence_bytes=(\d+) matching_allocations=(\d+) '
                          r'sequence_live_at_lease_release=(\d+) admitted_bytes_at_lease_release=(\d+) deallocations=(\d+)', text)
        assert len(rows) == 3 and {row[0] for row in rows} == {'cursor_last_owner','contribution_alias','completed_emission'}
        for mode, size, calls, live, admitted, deallocations in rows:
            assert [int(size),int(calls),int(admitted),int(deallocations)] == [2056,1,0,1]
            assert int(live) == int(args.kind == 'baseline' and mode == 'cursor_last_owner')
        receipt.update(rows=rows, outcome='EXPECTED_BASELINE_FAILURE' if args.kind == 'baseline' else 'PASS_MINIMAL_FIELD_REORDER_CONTROL')
    except BaseException as error:
        receipt.update(outcome='FAIL_CONTROL', error=repr(error))
        raise
    finally:
        receipt['files'] = {p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in out.iterdir() if p.is_file()}
        receipt['finished_utc'] = datetime.now(timezone.utc).isoformat()
        with (out/'receipt.json').open('x') as stream:
            json.dump(receipt,stream,indent=2);stream.write('\n')
    print(receipt['outcome'])


if __name__ == '__main__':
    main()
