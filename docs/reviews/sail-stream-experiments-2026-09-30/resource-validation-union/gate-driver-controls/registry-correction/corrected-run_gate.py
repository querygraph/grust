"""Gate a frozen detached Sail union; no commit, checkout, push or remote work.

Scope: changed host data-source code, Argentea/Nutmeg release unit tests, local
CLI and Python/SQL controls. Excludes Linux, worker/Flight, a combined rebuilt
native extension, and performance qualification. Evidence is outside Sail.
"""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

PYTHON = Path('/Users/alexy/src/sail-extensions-poc/.venvs/extensions-datafusion/bin/python')
NATIVE_FORMAT = [
    'examples/extensions/nutmeg/src/argentea/bfs/input.rs',
    'examples/extensions/nutmeg/src/argentea/bfs/tests/initialization.rs',
    'examples/extensions/nutmeg/src/argentea/sssp/input.rs',
    'examples/extensions/nutmeg/src/argentea/sssp/tests/initialization.rs',
]
MIN_FREE = 32 * 1024**3
GROUP_TERM_GRACE = 30
GROUP_KILL_GRACE = 10


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            result.update(block)
    return result.hexdigest()


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def stop_group(process):
    """Stop only a group created by this driver, and prove that group is absent.

    Waiting for the leader alone cannot prove that its descendants exited.
    Only direct children are reaped here; group absence is the separate check.
    """
    permission_probes = []

    def exists():
        process.poll()  # Reap an exited leader before asking macOS about its group.
        try:
            os.killpg(process.pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # Darwin can report EPERM while a just-exited group is disappearing.
            # EPERM itself is never absence: require a complete successful ps read.
            process.poll()
            snapshot = subprocess.check_output(['ps', '-axo', 'pid=,pgid='], text=True, timeout=5)
            pairs = [tuple(map(int, line.split())) for line in snapshot.splitlines() if line.strip()]
            check(pairs and all(len(pair) == 2 for pair in pairs), 'empty/malformed process-group inventory')
            check(any(pid == os.getpid() for pid, _ in pairs), 'process inventory omitted driver')
            members = [pid for pid, pgid in pairs if pgid == process.pid]
            permission_probes.append(dict(recorded_utc=utc(), pid=process.pid, member_pids=members,
                                          proof='successful complete ps pid/pgid snapshot'))
            return bool(members)

    result = dict(pid=process.pid, leader_complete_on_entry=process.poll() is not None,
                  group_alive_on_entry=exists(), signals=[], permission_probes=permission_probes)
    for signum in (signal.SIGTERM, signal.SIGKILL):
        if not exists():
            break
        try:
            os.killpg(process.pid, signum)
            result['signals'].append(signum.name)
        except ProcessLookupError:
            break
        except PermissionError:
            if not exists():
                break
            raise
        deadline = time.monotonic() + (GROUP_TERM_GRACE if signum == signal.SIGTERM else GROUP_KILL_GRACE)
        while exists() and time.monotonic() < deadline:
            process.poll()  # Reap the direct child when it exits.
            time.sleep(.05)
    process.wait(timeout=1)
    result.update(leader_returncode=process.returncode, leader_reaped=True,
                  group_absent=not exists())
    check(result['group_absent'], 'owned process group remains: ' + str(result))
    return result


def native_registry(text):
    """Libtest --list output only: no interleaved per-test status parsing."""
    lines = [line for line in text.splitlines() if line.strip()]
    names = [match[1] for line in lines if (match := re.fullmatch(r'(\S+): test', line))]
    check(len(names) == len(set(names)) == 51, 'native registry missing/duplicate tests')
    check(sum(name.startswith('argentea::') for name in names) == 45, 'native Argentea registry differs')
    check(len(lines) == 52 and lines[-1] == '51 tests, 0 benchmarks', 'native registry footer/extra output differs')
    return dict(tests=51, argentea_tests=45, names=sorted(names))


def test_summaries(text, expected):
    rows = re.findall(r'^test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out;', text, re.M)
    values = [tuple(map(int, row)) for row in rows]
    check(values and sum(row[0] for row in values) == expected, 'test inventory differs')
    check(all(row[1:] == (0, 0, 0, 0) for row in values), 'failed/ignored/measured/filtered tests')
    return values


def cargo_artifact(log, name, manifest):
    artifacts = []
    for line in log.read_text().splitlines():
        if not line.startswith('{'):
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get('reason') == 'compiler-artifact' and item.get('target', {}).get('name') == name and item.get('executable'):
            artifacts.append(item)
    check(len(artifacts) == 1, 'Cargo executable artifact inventory differs')
    check(Path(artifacts[0]['manifest_path']).resolve() == manifest.resolve(), 'artifact belongs to another source')
    return artifacts[0]


def native_binary_guard(proof):
    check(sha(Path(proof['binary'])) == proof['binary_sha256'], 'native test executable changed')


def main():
    parser = argparse.ArgumentParser()
    for name in ('repo', 'output', 'target-root', 'sql-helper'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('head', 'tree', 'sql-helper-sha256'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--exact', action='store_true')
    args = parser.parse_args()
    for name in ('repo', 'output', 'target_root', 'sql_helper'):
        setattr(args, name, getattr(args, name).resolve())
    check(not args.output.is_relative_to(args.repo), 'output must be outside source')
    check(not args.target_root.is_relative_to(args.repo), 'targets must be outside source')
    args.output.mkdir(parents=True, exist_ok=False)
    script_hash = sha(Path(__file__))
    receipt = dict(started_utc=utc(), outcome='RUNNING', repository='querygraph/sail',
                   repo=str(args.repo), output=str(args.output), head=args.head, tree=args.tree,
                   exact=args.exact, target_root=str(args.target_root), script_sha256=script_hash,
                   sql_helper=str(args.sql_helper), sql_helper_sha256=args.sql_helper_sha256,
                   scope=__doc__, steps=[], guards=[], saturation=[], cleanup=[])
    processes = []
    lock_fd = None
    lock_path = args.target_root / '.resource-validation-gate.lock'
    baseline = None
    git_env = dict(os.environ, GIT_OPTIONAL_LOCKS='0')

    def save():
        temporary = args.output / 'receipt.tmp'
        temporary.write_text(json.dumps(receipt, indent=2) + '\n')
        temporary.replace(args.output / 'receipt.json')

    def git(*command):
        return subprocess.check_output(['git', *command], cwd=args.repo, env=git_env)

    def state():
        head = git('rev-parse', 'HEAD').decode().strip()
        tree = git('write-tree').decode().strip()
        index = git('ls-files', '--stage', '-z')
        check(subprocess.run(['git', 'symbolic-ref', '-q', 'HEAD'], cwd=args.repo,
                             capture_output=True, env=git_env).returncode == 1, 'source must be detached')
        check(head == args.head and tree == args.tree, 'unexpected HEAD/index tree')
        check(subprocess.run(['git', 'diff', '--quiet'], cwd=args.repo, env=git_env).returncode == 0,
              'unstaged source changes')
        check(not git('ls-files', '--others', '--exclude-standard'), 'untracked source files')
        status = git('status', '--porcelain').decode()
        if args.exact:
            check(not status and git('rev-parse', 'HEAD^{tree}').decode().strip() == args.tree,
                  'exact gate requires a clean matching commit')
        files = {}
        for raw in git('ls-files', '-z').split(b'\0'):
            if not raw:
                continue
            name = os.fsdecode(raw)
            path = args.repo / name
            files[name] = dict(mode=path.lstat().st_mode,
                               sha256=(hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest()
                                       if path.is_symlink() else sha(path)))
        check(git('rev-parse', 'HEAD').decode().strip() == head and
              git('write-tree').decode().strip() == tree and
              git('ls-files', '--stage', '-z') == index, 'source identity changed during snapshot')
        return dict(head=head, tree=tree, status=status, files=files,
                    index_sha256=hashlib.sha256(index).hexdigest())

    def guard(label):
        started = utc()
        current = state()
        check(sha(Path(__file__)) == script_hash, 'gate driver changed')
        check(sha(args.sql_helper) == args.sql_helper_sha256, 'SQL helper changed')
        if current != baseline:
            (args.output / ('source-mismatch-' + label + '.json')).write_text(
                json.dumps(current, indent=2) + '\n')
            raise RuntimeError('frozen source changed: ' + label)
        receipt['guards'].append(dict(label=label, started_utc=started, completed_utc=utc(),
                                       source_sha256=hashlib.sha256(json.dumps(current, sort_keys=True).encode()).hexdigest()))
        save()

    def run(name, command, env, count=None, native_proof=None, loaded=False, separate_stderr=False):
        guard(name + '-before')
        if native_proof is not None:
            native_binary_guard(native_proof)
        free = min(shutil.disk_usage(args.repo).free, shutil.disk_usage(args.target_root).free)
        check(free >= MIN_FREE, 'free disk below 32 GiB before ' + name)
        step = dict(name=name, command=[str(x) for x in command], started_utc=utc(),
                    free_bytes_before=free, outcome='RUNNING', environment=env)
        receipt['steps'].append(step)
        if loaded:
            step['load_alive_before'] = sum(p.poll() is None for p in processes)
            check(step['load_alive_before'] == len(processes) and processes, 'load missing')
        save()
        process = None
        log = args.output / (name + '.log')
        stderr_log = args.output / (name + '.stderr')
        error = None
        try:
            with ExitStack() as stack:
                stream = stack.enter_context(log.open('x'))
                stderr = stack.enter_context(stderr_log.open('x')) if separate_stderr else subprocess.STDOUT
                process = subprocess.Popen(command, cwd=args.repo, env=dict(os.environ, **env),
                                           stdout=stream, stderr=stderr, start_new_session=True)
                step['pid'] = process.pid
                save()
                step['returncode'] = process.wait(timeout=7200)
            check(step['returncode'] == 0, name + ' command failed')
            text = log.read_text()
            if count is not None:
                step['summaries'] = test_summaries(text, count)
                step['tests_passed'] = count
            if native_proof is not None:
                native_binary_guard(native_proof)
                check(native_proof['binary'] in text, 'native command executed another test artifact')
                check(step['summaries'] == [(51, 0, 0, 0, 0)], 'native run must be complete and unfiltered')
                step.update(native_binary_sha256=native_proof['binary_sha256'],
                            native_registry_sha256=native_proof['registry_sha256'],
                            argentea_tests_passed=native_proof['argentea_tests'],
                            argentea_count_evidence='45 registered in pinned executable; all 51 registered tests pass, none ignored/filtered')
            if loaded:
                step['load_alive_after'] = sum(p.poll() is None for p in processes)
                check(step['load_alive_after'] == len(processes), 'load exited during test')
            step['outcome'] = 'PASS'
        except BaseException as caught:
            error = caught
            step.update(outcome='FAIL', error=repr(caught))
        finally:
            if process is not None:
                try:
                    cleanup = stop_group(process)
                    step['process_cleanup'] = cleanup
                    step['final_returncode'] = process.returncode
                    check(not (cleanup['leader_complete_on_entry'] and cleanup['group_alive_on_entry']),
                          'command left background processes')
                except BaseException as caught:
                    step['cleanup_error'] = repr(caught)
                    step['outcome'] = 'FAIL'
                    error = error or caught
            if log.exists():
                step.update(log=log.name, log_bytes=log.stat().st_size, log_sha256=sha(log))
            if stderr_log.exists():
                step.update(stderr_log=stderr_log.name, stderr_log_sha256=sha(stderr_log))
            step.update(finished_utc=utc(), free_bytes_after=shutil.disk_usage(args.target_root).free)
            try:
                guard(name + '-after')
            except BaseException as caught:
                step['source_guard_error'] = repr(caught)
                step['outcome'] = 'FAIL'
                error = error or caught
            save()
        print(name, step['outcome'], flush=True)
        if error:
            raise error

    def reap_load():
        for process in processes:
            try:
                cleanup = stop_group(process)
                receipt['cleanup'].append(dict(kind='saturator', pid=process.pid,
                                               returncode=process.returncode, reaped=process.poll() is not None,
                                               group_cleanup=cleanup))
            except BaseException as error:
                receipt['cleanup'].append(dict(kind='saturator', pid=process.pid, error=repr(error), reaped=False))
        check(all(p.poll() is not None for p in processes), 'unreaped saturator')
        check(all(x.get('reaped') for x in receipt['cleanup']), 'saturator cleanup failed')
        processes.clear()
        save()

    def interrupted(signum, _frame):
        raise InterruptedError('received signal ' + str(signum))

    previous_handlers = {s: signal.signal(s, interrupted) for s in (signal.SIGTERM, signal.SIGINT)}
    save()
    try:
        check(sha(args.sql_helper) == args.sql_helper_sha256, 'SQL helper hash mismatch')
        args.target_root.mkdir(parents=True, exist_ok=True)
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.write(lock_fd, (str(os.getpid()) + '\n').encode())
        baseline = state()
        (args.output / 'source-before.json').write_text(json.dumps(baseline, indent=2) + '\n')
        receipt['source_before_sha256'] = sha(args.output / 'source-before.json')
        for target in ('host', 'core', 'native'):
            (args.target_root / target).mkdir(exist_ok=True)
        probe_env = {key: value for key, value in os.environ.items()
                     if key not in ('PYTHONHOME', 'PYTHONPATH', 'DYLD_LIBRARY_PATH', 'LD_LIBRARY_PATH')}
        probe_env.update(PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', GIT_OPTIONAL_LOCKS='0')
        info = json.loads(subprocess.check_output([str(PYTHON), '-c',
            'import json,sys,sysconfig; print(json.dumps(dict(version=list(sys.version_info[:3]), '
            'base_prefix=sys.base_prefix, purelib=sysconfig.get_path("purelib"), libdir=sysconfig.get_config_var("LIBDIR"))))'], env=probe_env))
        check(info['version'] == [3, 12, 8], 'native/CLI require pinned Python 3.12.8')
        check(Path(info['purelib']).is_dir() and Path(info['libdir']).is_dir(), 'Python paths absent')
        receipt['python'] = dict(path=str(PYTHON), executable_sha256=sha(PYTHON), **info)
        base = dict(CARGO_INCREMENTAL='0', CARGO_NET_OFFLINE='true', CARGO_BUILD_JOBS='6',
                    PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', GIT_OPTIONAL_LOCKS='0')
        python_env = dict(PYO3_PYTHON=str(PYTHON), PYTHONHOME=info['base_prefix'],
                          PYTHONPATH=info['purelib'], DYLD_LIBRARY_PATH=info['libdir'])
        host = dict(base, **python_env, CARGO_TARGET_DIR=str(args.target_root/'host'),
                    CARGO_PROFILE_DEV_DEBUG='0', CARGO_PROFILE_TEST_DEBUG='0')
        core = dict(base, CARGO_TARGET_DIR=str(args.target_root/'core'))
        native = dict(base, **python_env, CARGO_TARGET_DIR=str(args.target_root/'native'))
        environment = dict(host=host, core=core, native=native)
        receipt['environments'] = environment
        receipt['native_format_scope'] = dict(files=NATIVE_FORMAT,
            exclusions='Inherited full Nutmeg format failures; two parent test modules only add declarations.')
        manifest = lambda name: str(args.repo / f'examples/extensions/{name}/Cargo.toml')
        run('diff-check', ['git', 'diff', '--cached', '--check'], host)
        run('host-format', ['cargo', 'fmt', '-p', 'sail-data-source', '--check'], host)
        run('host-clippy', ['cargo', 'clippy', '--locked', '--offline', '-p', 'sail-data-source', '--all-targets', '--', '-D', 'warnings'], host)
        run('host-tests', ['cargo', 'test', '--locked', '--offline', '-p', 'sail-data-source', '--lib'], host, 77)
        run('core-format', ['cargo', 'fmt', '--manifest-path', manifest('argentea'), '--', '--check'], core)
        run('core-clippy', ['cargo', 'clippy', '--manifest-path', manifest('argentea'), '--locked', '--offline', '--all-targets', '--', '-D', 'warnings'], core)
        run('native-changed-format', ['rustfmt', '--edition', '2024', '--check', '--config', 'skip_children=true',
                                     *[str(args.repo / name) for name in NATIVE_FORMAT]], native)
        core_test = ['cargo', 'test', '--manifest-path', manifest('argentea'), '--locked', '--offline', '--release', '--', '--nocapture']
        run('core-release', core_test, core, 120)
        run('native-build', ['cargo', 'test', '--manifest-path', manifest('nutmeg'), '--locked', '--offline',
                             '--release', '--lib', '--no-run', '--message-format=json-render-diagnostics'], native)
        artifact = cargo_artifact(args.output / 'native-build.log', '_native', Path(manifest('nutmeg')))
        native_binary = Path(artifact['executable']).resolve()
        check(artifact['profile']['test'] is True and native_binary.is_relative_to((args.target_root/'native/release').resolve()),
              'native artifact is not this target release test binary')
        native_hash = sha(native_binary)
        native_test = ['cargo', 'test', '--manifest-path', manifest('nutmeg'), '--locked', '--offline', '--release', '--lib']
        run('native-registry', [*native_test, '--', '--list'], native, separate_stderr=True)
        check(str(native_binary) in (args.output / 'native-registry.stderr').read_text(), 'registry executed another test artifact')
        proof = native_registry((args.output / 'native-registry.log').read_text())
        proof.update(binary=str(native_binary), binary_sha256=native_hash,
                     registry_log_sha256=sha(args.output / 'native-registry.log'), cargo_artifact=artifact)
        native_binary_guard(proof)
        (args.output / 'native-registry.json').write_text(json.dumps(proof, indent=2)+'\n')
        proof['registry_sha256'] = sha(args.output / 'native-registry.json')
        receipt['native_registry'] = proof
        save()
        native_test = [*native_test, '--', '--nocapture']
        run('native-release', native_test, native, 51, native_proof=proof)
        count = os.cpu_count()
        check(count is not None and count > 0, 'CPU count unavailable')
        yes = shutil.which('yes')
        check(yes is not None, 'saturator executable absent')
        for _ in range(count):
            process = subprocess.Popen([yes], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            processes.append(process)
            receipt['saturation'].append(dict(pid=process.pid, started_utc=utc()))
            save()
        time.sleep(1)
        run('core-loaded', core_test, core, 120, loaded=True)
        run('native-loaded', native_test, native, 51, native_proof=proof, loaded=True)
        reap_load()
        run('cli-build', ['cargo', 'build', '--locked', '--offline', '-p', 'sail-cli', '--bin', 'sail',
                          '--message-format=json-render-diagnostics'], host)
        binary = args.target_root / 'host/debug/sail'
        artifact = cargo_artifact(args.output / 'cli-build.log', 'sail', args.repo/'crates/sail-cli/Cargo.toml')
        check(Path(artifact['executable']).resolve() == binary.resolve(), 'unexpected new CLI path')
        receipt['cli_cargo_artifact'] = artifact
        binary_hash = sha(binary)
        receipt['binary'] = dict(path=str(binary), sha256=binary_hash, profile='dev debug=0')
        save()
        run('python-sql', [str(PYTHON), str(args.sql_helper), '--repo', str(args.repo),
                          '--output', str(args.output / 'sql'), '--expected-head', args.head,
                          '--expected-tree', args.tree, '--mode', 'exact' if args.exact else 'candidate',
                          '--binary', str(binary),
                          '--binary-sha256', binary_hash], host)
        check(sha(binary) == binary_hash, 'new CLI changed during SQL gate')
        child = json.loads((args.output / 'sql/receipt.json').read_text())
        check(child.get('outcome') == 'passed', 'SQL helper did not report passed')
        check(child.get('unit_tests') == dict(tests=430, failures=0, errors=0, skipped=97),
              'Python unit inventory differs from 333 passed / 97 skipped')
        check(child.get('sql_tests') == dict(tests=58, failures=0, errors=0, skipped=0),
              'SQL inventory differs from 58 passed')
        check(child.get('source_and_runtime_unchanged') is True and child.get('server_reaped') is True,
              'SQL source/runtime or cleanup guard failed')
        control = json.loads((args.output / 'sql/default-statistics.json').read_text())
        check(control.get('outcome') == 'passed' and len(control.get('checks', [])) == 2,
              'default-statistics control did not pass both cases')
        receipt['sql_receipt_sha256'] = sha(args.output / 'sql/receipt.json')
        guard('final')
        receipt['outcome'] = 'PASS'
    except BaseException as error:
        receipt.update(outcome='FAIL', error=repr(error))
    finally:
        for signum in previous_handlers:
            signal.signal(signum, signal.SIG_IGN)
        try:
            reap_load()
        except BaseException as error:
            receipt.update(outcome='FAIL', cleanup_error=repr(error))
        if lock_fd is not None:
            try:
                check(os.fstat(lock_fd).st_ino == lock_path.stat().st_ino, 'target lock replaced')
                lock_path.unlink()
            except BaseException as error:
                receipt.update(outcome='FAIL', lock_cleanup_error=repr(error))
            finally:
                os.close(lock_fd)
        receipt['finished_utc'] = utc()
        receipt['all_saturators_reaped'] = all(x.get('reaped') for x in receipt['cleanup'] if x['kind'] == 'saturator')
        save()
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
    print('RESOURCE_VALIDATION_UNION_GATE', receipt['outcome'], args.head,
          'exact commit' if args.exact else 'staged tree ' + args.tree, flush=True)
    return 0 if receipt['outcome'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
