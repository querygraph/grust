"""Offline source/schedule-environment controls; no Sail/SQL/server is launched."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import importlib.util
import json
import signal
import subprocess
import tempfile

HELPER_SHA = '0aca81a5819f29095d2592804aea836250d7640de917ce7d959a264ec80f124e'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    helper = Path(__file__).resolve().parent.parent/'sql_gate.py'
    spec = importlib.util.spec_from_file_location('prepared_sql_gate', helper)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    assert gate.sha(helper) == HELPER_SHA
    private = Path(tempfile.mkdtemp(prefix='union-sql-offline-guards-'))
    repo = private/'source'
    repo.mkdir()
    receipt = dict(started_utc=datetime.now(timezone.utc).isoformat(), helper_sha256=HELPER_SHA,
        control_source_sha256=gate.sha(Path(__file__)), private_fixture=str(private), checks=[],
        scope='Private tiny Git fixture and pinned client-interpreter imports only. No Sail binary build, SQL, server, benchmark, remote read or workload.')

    def git(*items):
        return subprocess.check_output(['git', '-C', str(repo), *items],
            stderr=subprocess.STDOUT, timeout=30).decode().strip()

    def rejects(label, function):
        try:
            function()
        except AssertionError:
            receipt['checks'].append(dict(name=label, outcome='expected_rejection'))
        else:
            raise AssertionError(label+' unexpectedly admitted')

    try:
        git('init')
        git('config', 'user.name', 'Offline fixture')
        git('config', 'user.email', 'fixture@example.invalid')
        (repo/'file.py').write_text('print(1)\n')
        git('add', 'file.py')
        git('commit', '-m', 'Private offline control')
        head = git('rev-parse', 'HEAD')
        git('checkout', '--detach', head)
        tree = git('rev-parse', 'HEAD^{tree}')
        first = gate.source_identity(repo, head, tree, 'exact')
        assert first == gate.source_identity(repo, head, tree, 'exact')
        receipt['checks'].append(dict(name='clean exact source/index stable', outcome='passed'))
        (repo/'file.py').write_text('print(2)\n')
        rejects('unstaged source', lambda: gate.source_identity(repo, head, tree, 'exact'))
        git('add', 'file.py')
        candidate = git('write-tree')
        gate.source_identity(repo, head, candidate, 'candidate')
        receipt['checks'].append(dict(name='staged candidate identity', outcome='passed'))
        rejects('candidate claiming exact', lambda: gate.source_identity(repo, head, candidate, 'exact'))
        (repo/'untracked.py').write_text('pass\n')
        rejects('untracked source', lambda: gate.source_identity(repo, head, candidate, 'candidate'))
        env = gate.client_environment(repo/'bench', repo)
        server, settings = gate.server_environment(env)
        assert env['GIT_OPTIONAL_LOCKS'] == server['GIT_OPTIONAL_LOCKS'] == '0'
        assert server['SAIL_EXECUTION__COLLECT_STATISTICS'] == settings['SAIL_EXECUTION__COLLECT_STATISTICS'] == 'true'
        assert 'PYTHONPATH' not in server
        receipt['checks'].append(dict(name='explicit statistics and optional-lock environment', outcome='passed', settings=settings))
        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                gate.interrupted(signum, None)
            except InterruptedError as error:
                assert str(int(signum)) in str(error)
            else:
                raise AssertionError('signal handler did not request controlled unwind')
        receipt['checks'].append(dict(name='both signal handlers request controlled unwind', outcome='passed',
                                     limitation='Direct handler calls; no OS signal or process-group cleanup experiment.'))
        process = subprocess.run([str(gate.PYTHON), '-B', str(helper), '--interpreter-probe'],
            env=env, capture_output=True, text=True, timeout=30)
        (args.output/'client.stdout').write_text(process.stdout)
        (args.output/'client.stderr').write_text(process.stderr)
        receipt['client_returncode'] = process.returncode
        process.check_returncode()
        receipt['client_interpreter'] = json.loads(process.stdout)
        receipt['checks'].append(dict(name='pinned client Python and imports', outcome='passed'))
        assert gate.sha(helper) == HELPER_SHA
        receipt['outcome'] = 'PASS_OFFLINE_PREPARATION_ONLY'
    except BaseException as error:
        receipt.update(outcome='FAIL', error_type=type(error).__name__, error=str(error))
    finally:
        receipt['finished_utc'] = datetime.now(timezone.utc).isoformat()
        receipt['artifact_hashes'] = {p.name: gate.sha(p) for p in args.output.iterdir() if p.is_file()}
        gate.save(args.output/'receipt.json', receipt)
    print(receipt['outcome'])
    return 0 if receipt['outcome'] == 'PASS_OFFLINE_PREPARATION_ONLY' else 1


if __name__ == '__main__':
    raise SystemExit(main())
