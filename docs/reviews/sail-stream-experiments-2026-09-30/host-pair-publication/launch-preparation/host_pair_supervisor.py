"""Host-only durable supervision of the frozen six-cell pair; no Docker calls.

The frozen runner owns admission, execution, stopping and outcome classification.
This helper only launches it once, retains its exit and collects host metadata.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

PYTHON = Path('/usr/local/bin/python3')
ROOT = Path('/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930')
NS = 'pair16k-20260930201356'
PLAN_SHA = 'd51e9f4d5a1d16fb18c36e93fcb3d641c017610a7319ee56a203676800dbe1ab'
RUNNER_SHA = '8220b9951c51420bd34ca5e32ba20c2304a1b863aa5f2fa1fa9467e74d60a7f1'
PLAN = ROOT/(NS+'-plan.json')
RUNNER = ROOT/(NS+'-runner.py')
STUDY = ROOT/NS
LAUNCH = ROOT/(NS+'-launch-evidence')
MAX_JSON = 8 << 20
MAX_COLLECTION = 2 << 30


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    need(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_JSON,
         'missing, linked or oversized JSON: '+str(path))
    value = json.loads(path.read_text())
    need(isinstance(value, dict), 'JSON is not an object')
    return value


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def absent(path):
    need(not path.exists() and not path.is_symlink(), 'existing namespace; no retries: '+str(path))


def interpreter():
    need(sys.version_info[:3] == (3, 14, 7), 'host Python must be 3.14.7')
    need(Path(sys.executable).resolve() == PYTHON.resolve(), 'host Python path differs')
    return dict(executable=str(PYTHON), resolved=str(PYTHON.resolve()), version=sys.version,
                sha256=sha(PYTHON))


def inputs():
    need(ROOT.is_dir() and not ROOT.is_symlink(), 'host root unavailable')
    need(sha(PLAN) == PLAN_SHA and sha(RUNNER) == RUNNER_SHA, 'plan/runner differs')
    plan = read(PLAN)
    need(plan['namespace'] == NS and plan['remote_root'] == str(ROOT), 'plan namespace differs')
    need([(r['order'], r['phase'], r['host']) for r in plan['runs']] ==
         [(1,'warmup','A'),(2,'warmup','B'),(3,'measurement','A'),(4,'measurement','B'),
          (5,'measurement','B'),(6,'measurement','A')], 'six-cell order differs')
    files = {str(PLAN): PLAN_SHA, str(RUNNER): RUNNER_SHA}
    for name, digest in plan['scripts'].items():
        if name != 'run_host_pair.py':
            files[str(ROOT/name)] = digest
    for name, digest in plan['harness_files_sha256'].items():
        files[str(ROOT/'harness'/name)] = digest
    for entry in plan['runs']:
        files[str(ROOT/entry['configuration'])] = entry['configuration_sha256']
    for name, digest in files.items():
        path = Path(name)
        need(path.is_file() and not path.is_symlink() and path.is_relative_to(ROOT)
             and sha(path) == digest, 'pinned support/configuration differs: '+name)
    return plan, files


def physical_closure(path, digest, request_sha):
    need(path.is_absolute() and path.resolve().is_relative_to(ROOT.resolve())
         and '..' not in path.parts and path.name == 'outer-receipt.json',
         'closure path is outside host evidence')
    need(sha(path) == digest, 'physical03 closure hash differs')
    closure = read(path)
    state = closure.get('container_state') or {}
    need(closure.get('request_sha256') == request_sha and closure.get('finished_utc')
         and closure.get('cleanup') == 'removed_after_state_capture'
         and state.get('Running') is False and state.get('Status') == 'exited'
         and type(state.get('ExitCode')) is int and closure.get('bundle_unchanged') is True,
         'physical checker is not demonstrably closed/removed')
    need(closure.get('physical_status') in ('physical_values_pass', 'physical_values_fail',
                                         'integrity_error', 'inconclusive'), 'physical status unavailable')
    return dict(path=str(path), sha256=digest, request_sha256=request_sha,
                physical_status=closure['physical_status'], container_state=state,
                finished_utc=closure['finished_utc'], cleanup=closure['cleanup'], errors=closure.get('errors'))


def command():
    return [str(PYTHON), '-B', str(RUNNER), str(PLAN), '--execute',
            '--expected-plan-sha256', PLAN_SHA, '--through', '6']


def child():
    intent = read(LAUNCH/'launch-intent.json')
    write_new(LAUNCH/'supervisor-claim.json', dict(utc=utc(), pid=os.getpid(), plan_sha256=PLAN_SHA))
    report = dict(started_utc=utc(), outcome='supervisor_error', runner_started=False, errors=[],
                  plan_sha256=PLAN_SHA, command=command())
    try:
        need(sha(Path(__file__)) == intent['supervisor_sha256'], 'supervisor changed')
        interpreter()
        inputs()
        closure = intent['physical03_closure']
        physical_closure(Path(closure['path']), closure['sha256'], closure['request_sha256'])
        absent(STUDY)
        with (LAUNCH/'runner.stdout').open('xb') as out, (LAUNCH/'runner.stderr').open('xb') as err:
            process = subprocess.Popen(command(), stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                       start_new_session=True, close_fds=True)
            report.update(runner_started=True, runner_pid=process.pid)
            write_new(LAUNCH/'runner-start.json', dict(utc=utc(), pid=process.pid,
                      supervisor_pid=os.getpid(), command=command(), plan_sha256=PLAN_SHA))
            code = process.wait()  # Existing runner owns every timeout/cleanup policy.
        write_new(LAUNCH/'runner-exit.json', dict(utc=utc(), pid=process.pid, returncode=code,
                  reaped=True, plan_sha256=PLAN_SHA,
                  scope='Runner exit only; per-cell outcomes remain in the original ledger.'))
        report.update(outcome='runner_exited', runner_returncode=code)
        inputs()
        report['pinned_inputs_unchanged'] = True
    except BaseException as error:
        report['errors'].append(type(error).__name__+': '+str(error))
        report['scope'] = 'No retry or signals. Missing runner exit is incomplete; child may remain live.'
    finally:
        report['finished_utc'] = utc()
        write_new(LAUNCH/'supervisor-exit.json', report)


def launch(args):
    identity = interpreter()
    _, files = inputs()
    closed = physical_closure(args.closure, args.closure_sha256, args.request_sha256)
    absent(STUDY)
    absent(LAUNCH)
    LAUNCH.mkdir(mode=0o700)
    write_new(LAUNCH/'launch-intent.json', dict(utc=utc(), supervisor_sha256=args.script_sha256,
              interpreter=identity, pinned_files=files, physical03_closure=closed,
              command=command(), scope='Unchanged six-cell runner; no physical scans during the sequence.'))
    with (LAUNCH/'supervisor.stdout').open('xb') as out, (LAUNCH/'supervisor.stderr').open('xb') as err:
        process = subprocess.Popen([str(PYTHON), '-B', str(Path(__file__).resolve()), 'child',
                                    '--script-sha256', args.script_sha256], stdin=subprocess.DEVNULL,
                                   stdout=out, stderr=err, start_new_session=True, close_fds=True)
    result = dict(utc=utc(), launched=True, pid=process.pid, launch=str(LAUNCH), study=str(STUDY),
                  plan_sha256=PLAN_SHA, scope='PID receipt is not an execution or correctness verdict.')
    write_new(LAUNCH/'launch.json', result)
    print(json.dumps(result))


def selected():
    result = dict(utc=utc(), study=str(STUDY), launch=str(LAUNCH), plan_sha256=PLAN_SHA,
                  records={}, errors=[], active_lock=(STUDY/'active.lock').exists())
    for name in ('launch.json', 'runner-start.json', 'runner-exit.json', 'supervisor-exit.json'):
        path = LAUNCH/name
        if path.exists():
            try: result['records'][name] = read(path)
            except Exception as error: result['errors'].append(name+': '+str(error))
    ledger = STUDY/'sequence.json'
    if ledger.exists():
        try:
            value = read(ledger)
            need(value['plan_sha256'] == PLAN_SHA, 'ledger plan differs')
            result['rows'] = [{k: row.get(k) for k in ('order','phase','host','outcome',
                              'comparison_eligible','seconds','started_utc','finished_utc')}
                              for row in value['rows']]
        except Exception as error: result['errors'].append('sequence: '+str(error))
    for name in ('runner.stdout', 'runner.stderr'):
        path = LAUNCH/name
        if path.is_file() and not path.is_symlink():
            with path.open('rb') as stream:
                stream.seek(max(0, path.stat().st_size-4096))
                result[name+'_tail'] = stream.read(4096).decode(errors='replace')
    result['full_six_records_after_runner_exit'] = bool(
        result['records'].get('runner-exit.json', {}).get('reaped') is True
        and result['records'].get('runner-exit.json', {}).get('returncode') == 0
        and [row['order'] for row in result.get('rows', [])] == list(range(1,7))
        and result['records'].get('supervisor-exit.json', {}).get('outcome') == 'runner_exited'
        and result['records'].get('supervisor-exit.json', {}).get('pinned_inputs_unchanged') is True
        and not result['records'].get('supervisor-exit.json', {}).get('errors', ['missing'])
        and not result['active_lock'] and not result['errors'])
    return result


def collect():
    status = selected()
    end = status['records'].get('supervisor-exit.json')
    exit_record = status['records'].get('runner-exit.json', {})
    need(end and (end.get('runner_started') is False or
                  (end.get('runner_started') is True and exit_record.get('reaped') is True
                   and type(exit_record.get('returncode')) is int))
         and not status['active_lock'], 'runner closure incomplete; no collection of active artifacts')
    files, total = {}, 0
    for label, root in [('launch', LAUNCH), ('study', STUDY)]:
        if not root.exists(): continue
        need(root.is_dir() and not root.is_symlink(), 'linked collection root')
        for path in sorted(root.rglob('*')):
            need(not path.is_symlink(), 'linked artifact refused')
            if path.is_dir(): continue
            need(path.is_file(), 'non-regular artifact refused')
            total += path.stat().st_size
            need(total <= MAX_COLLECTION, 'collection exceeds2GiB; inspect before changing bound')
            files[label+'/'+str(path.relative_to(root))] = dict(bytes=path.stat().st_size, sha256=sha(path))
    manifest = dict(utc=utc(), plan_sha256=PLAN_SHA, files=files, selected_status=status,
                    scope='Host metadata only. VM output Parquet and six physical scans are separate; no scan launched.')
    raw = (json.dumps(manifest, indent=2)+'\n').encode()
    with tarfile.open(fileobj=sys.stdout.buffer, mode='w|') as archive:
        info = tarfile.TarInfo('collection-manifest.json'); info.size=len(raw)
        archive.addfile(info, io.BytesIO(raw))
        for name, expected in files.items():
            label, relative = name.split('/',1)
            path = (LAUNCH if label=='launch' else STUDY)/relative
            need(path.stat().st_size == expected['bytes'] and sha(path)==expected['sha256'], 'artifact changed during collection')
            info = tarfile.TarInfo(name); info.size=expected['bytes']
            with path.open('rb') as stream: archive.addfile(info, stream)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('launch','child','poll','collect'))
    parser.add_argument('--script-sha256', required=True)
    parser.add_argument('--closure', type=Path)
    parser.add_argument('--closure-sha256')
    parser.add_argument('--request-sha256')
    args = parser.parse_args()
    need(sha(Path(__file__)) == args.script_sha256, 'supervisor hash differs')
    interpreter()
    if args.action=='launch':
        need(args.closure and args.closure_sha256 and args.request_sha256, 'physical03 closure pins required')
        launch(args)
    elif args.action=='child': child()
    elif args.action=='poll': print(json.dumps(selected(), indent=2))
    else: collect()


if __name__=='__main__': main()
