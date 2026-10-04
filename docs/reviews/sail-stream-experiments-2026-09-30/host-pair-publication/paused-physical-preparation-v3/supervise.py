#!/usr/bin/env python3
"""Explicit post-closure launcher. No Docker contact without --execute-after-closure."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import uuid

DOCKER = ['/usr/local/bin/docker', '--context', 'colima-sail-gate']
IMAGE = 'sha256:f3518d652fbea8b9b9f9ebf9849277ca3bd39d0c21bb2c6e36fbaeaa2dc2678e'
PLAN_SHA = 'd51e9f4d5a1d16fb18c36e93fcb3d641c017610a7319ee56a203676800dbe1ab'
HELPER_SHA = '4c5fe87d0eb0b3f4aec3e70841bc7db968017f952dda6978840d101d2f2f7872'
VOLUME = 'sail-extension-targets'
INSPECT = '{"Id":{{json .Id}},"State":{{json .State}},"Labels":{{json .Config.Labels}},"User":{{json .Config.User}},"Mounts":{{json .Mounts}},"Memory":{{.HostConfig.Memory}},"MemorySwap":{{.HostConfig.MemorySwap}},"NanoCpus":{{.HostConfig.NanoCpus}},"ReadonlyRootfs":{{.HostConfig.ReadonlyRootfs}},"NetworkMode":{{json .HostConfig.NetworkMode}}}'


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def need(ok, message):
    if not ok:
        raise ValueError(message)


def save(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def free_space(path, minimum):
    usage = shutil.disk_usage(path)
    result = dict(path=str(path), total_bytes=usage.total, used_bytes=usage.used,
                  free_bytes=usage.free, minimum_free_bytes=minimum)
    return result


IDENTITY = dict(host_uid=501, host_gid=20, container_user='501:20',
                bundle_mode='0755', bundle_file_mode='0644', evidence_mode='0700')


def path_permissions(path):
    info = path.lstat()
    return dict(uid=info.st_uid, gid=info.st_gid, mode=format(stat.S_IMODE(info.st_mode), '04o'))


def validate_bundle_permissions(root, request):
    need(request.get('execution_identity') == IDENTITY, 'execution identity differs')
    need(os.getuid() == IDENTITY['host_uid'] and os.getgid() == IDENTITY['host_gid'], 'host UID/GID differs')
    need(root.is_dir() and not root.is_symlink() and path_permissions(root)['mode'] == '0755', 'bundle mode must be0755')
    for name in ['request.json', *request['files']]:
        path = root / name
        need(path.is_file() and not path.is_symlink() and path_permissions(path)['mode'] == '0644', 'bundle file mode must be0644: ' + name)


def create_evidence_directory(output):
    # The parent creates only a new directory; never chmod earlier evidence.
    output.mkdir(parents=False, exist_ok=False)
    output.chmod(0o700)


def validate_evidence_directory(output):
    need(output.is_dir() and not output.is_symlink(), 'evidence directory invalid')
    value = path_permissions(output)
    need(value['uid'] == IDENTITY['host_uid'] and value['mode'] == '0700', 'evidence owner/mode differs')
    return value


def validate(request_path, digest, output):
    need(request_path.name == 'request.json' and request_path.is_file() and not request_path.is_symlink(), 'request path invalid')
    need(sha(request_path) == digest, 'request hash differs')
    request = json.loads(request_path.read_text())
    root = request_path.parent
    need(not output.is_relative_to(root) and not root.is_relative_to(output), 'output overlaps immutable bundle')
    need(not output.is_relative_to(Path('/targets')), 'host output must not be retained volume')
    need(all(',' not in str(p) and '\n' not in str(p) for p in (root, output)), 'unsafe Docker mount path')
    names = {'configuration.json', 'producer-receipt.json', 'closed-audit.json', 'audit_output.py', 'container_check.py', 'supervise.py', 'pair-plan.json', 'all-six-closures.json', 'pair_policy.py'}
    need(set(request['files']) == names, 'bundle inventory differs')
    validate_bundle_permissions(root, request)
    for name, pin in request['files'].items():
        path = root / name
        need(path.is_file() and not path.is_symlink() and path.stat().st_size == pin['bytes'] and sha(path) == pin['sha256'], 'bundle changed: ' + name)
    need(request['files']['pair-plan.json']['sha256'] == PLAN_SHA and request['files']['audit_output.py']['sha256'] == HELPER_SHA, 'frozen plan/helper differs')
    import importlib.util
    spec = importlib.util.spec_from_file_location('sealed_pair_policy', root / 'pair_policy.py')
    policy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(policy)
    policy.validate_context(request, root)
    need(sha(Path(__file__).resolve()) == request['files']['supervise.py']['sha256'], 'supervisor differs')
    need(re.fullmatch(r'physical-output-pair-[0-9a-f]{16}', request['container_name']), 'unsafe container name')
    need(request['limits'] == dict(cpus=1, memory_bytes=2147483648, memory_swap_bytes=2147483648, pids=64), 'limits differ')
    need(request['disk_admission'] == dict(host_evidence_minimum_free_bytes=268435456, target_volume_minimum_free_bytes=1073741824), 'disk admission differs')
    need(type(request['timeout_seconds']) is int and 1 <= request['timeout_seconds'] <= 1800, 'timeout exceeds prepared bound')
    return request


def create_command(request, root, output, digest, execution_id):
    return DOCKER + ['create', '--name', request['container_name'], '--label', 'physical-check.request=' + digest, '--label', 'physical-check.execution=' + execution_id,
        '--pull=never', '--user=501:20', '--read-only', '--network=none', '--cpus=1', '--memory=2147483648',
        '--memory-swap=2147483648', '--pids-limit=64', '--cap-drop=ALL', '--security-opt=no-new-privileges',
        '--mount', 'type=volume,source=' + VOLUME + ',target=/targets,readonly,volume-nocopy',
        '--mount', 'type=bind,source=' + str(root) + ',target=/work,readonly',
        '--mount', 'type=bind,source=' + str(output) + ',target=/evidence', '--workdir=/targets',
        '--env', 'PYTHONDONTWRITEBYTECODE=1', '--env', 'OMP_NUM_THREADS=1', '--env', 'OPENBLAS_NUM_THREADS=1',
        '--env', 'MKL_NUM_THREADS=1', '--env', 'NUMEXPR_NUM_THREADS=1',
        '--entrypoint=/targets/graph-nuts-ffcfbd569/venv/bin/python', IMAGE,
        '-I', '-B', '/work/container_check.py', digest]


def run_supervisor(request_path, digest, output):
    validate_evidence_directory(output)
    with (output / 'supervisor-claim.json').open('x') as stream:
        json.dump(dict(utc=utc(), pid=os.getpid(), request_sha256=digest), stream)
        stream.write('\n')
    report = dict(started_utc=utc(), outcome='supervisor_error', request_sha256=digest,
                  commands=[], errors=[], container_state=None, cleanup='not_attempted',
                  scope='Physical-value audit only; original benchmark outcome is unchanged. No timing comparison.')
    container_id = None
    request = None
    command_count = 0
    create_attempted = False
    execution_id = uuid.uuid4().hex
    report['execution_id'] = execution_id

    def command(label, args, timeout=60, check=True):
        nonlocal command_count
        command_count += 1
        prefix = f'{command_count:02d}-{label}'
        stdout, stderr = output / (prefix + '.stdout'), output / (prefix + '.stderr')
        record = dict(started_utc=utc(), command=args, stdout=stdout.name, stderr=stderr.name, timeout_seconds=timeout)
        report['commands'].append(record)
        save(output / 'outer-receipt.json', report)
        try:
            with stdout.open('xb') as out, stderr.open('xb') as err:
                process = subprocess.run(args, stdout=out, stderr=err, timeout=timeout, check=False)
            record['returncode'] = process.returncode
        except Exception as error:
            record['error'] = type(error).__name__ + ': ' + str(error)
            raise
        finally:
            record['finished_utc'] = utc()
            for key, path in (('stdout', stdout), ('stderr', stderr)):
                if path.exists():
                    record[key + '_file'] = dict(bytes=path.stat().st_size, sha256=sha(path))
            save(output / 'outer-receipt.json', report)
        if check:
            need(process.returncode == 0, label + ' command failed')
        return stdout.read_text(errors='replace')

    def inspect(target, label):
        state = json.loads(command(label, DOCKER + ['inspect', '--format', INSPECT, target]))
        need(re.fullmatch('[0-9a-f]{64}', state['Id']) and
             state.get('Labels', {}).get('physical-check.request') == digest and
             state.get('Labels', {}).get('physical-check.execution') == execution_id, 'container ownership differs')
        return state

    try:
        request = validate(request_path, digest, output)
        report['host_identity'] = dict(uid=os.getuid(), gid=os.getgid())
        report['evidence_permissions'] = validate_evidence_directory(output)
        report['bundle_permissions'] = path_permissions(request_path.parent)
        report['supervisor_pid'] = os.getpid()
        report['supervisor_sha256'] = sha(Path(__file__).resolve())
        save(output / 'outer-receipt.json', report)
        report['host_evidence_disk_before'] = free_space(output, 268435456)
        save(output / 'outer-receipt.json', report)
        need(report['host_evidence_disk_before']['free_bytes'] >= 268435456, 'host evidence filesystem has insufficient free space')
        need(not command('running-before', DOCKER + ['ps', '-q']).strip(), 'other Docker workload is running')
        actual_image = command('image', DOCKER + ['image', 'inspect', '--format', '{{.Id}}', IMAGE]).strip()
        need(actual_image == IMAGE, 'image identity differs')
        need(command('volume', DOCKER + ['volume', 'inspect', '--format', '{{.Name}}', VOLUME]).strip() == VOLUME, 'volume unavailable')
        need(not command('running-before-create', DOCKER + ['ps', '-q']).strip(), 'other Docker workload appeared')
        create_attempted = True
        text = command('create', create_command(request, request_path.parent, output, digest, execution_id))
        need(re.fullmatch('[0-9a-f]{64}', text.strip()), 'create did not return one container ID')
        container_id = text.strip()
        report['container_id'] = container_id
        initial = inspect(container_id, 'inspect-created')
        report['created_container'] = initial
        need(initial['User'] == request['execution_identity']['container_user'], 'created container user differs')
        need(initial['Memory'] == 2147483648 and initial['MemorySwap'] == 2147483648 and
             initial['NanoCpus'] == 1000000000 and initial['ReadonlyRootfs'] is True and
             initial['NetworkMode'] == 'none', 'created resource policy differs')
        mounts = {item['Destination']: item for item in initial['Mounts']}
        need(set(mounts) == {'/targets', '/work', '/evidence'} and
             all(mounts[x]['RW'] is False for x in ('/targets', '/work')) and
             mounts['/evidence']['RW'] is True, 'created mounts differ')
        need(not command('running-before-start', DOCKER + ['ps', '-q']).strip(), 'other Docker workload appeared before start')
        command('start', DOCKER + ['start', container_id])
        command('wait', DOCKER + ['wait', container_id], timeout=request['timeout_seconds'])
        report['outcome'] = 'container_completed'
    except Exception as error:
        report['errors'].append(type(error).__name__ + ': ' + str(error))
    finally:
        # Recover even if `docker create` succeeded but its response was lost.
        if request is not None and create_attempted:
            try:
                current = inspect(container_id or request['container_name'], 'inspect-final')
                container_id = current['Id']
                report['container_id'] = container_id
                if current['State'].get('Running'):
                    report['cleanup'] = 'stopping_owned_checker'
                    command('kill-owned-checker', DOCKER + ['kill', container_id])
                    command('wait-after-kill', DOCKER + ['wait', container_id], timeout=30)
                    current = inspect(container_id, 'inspect-after-kill')
                report['container_state'] = current['State']
                save(output / 'exited-container.json', current)
                need(current['State'].get('Running') is False, 'owned checker still running')
                command('logs', DOCKER + ['logs', container_id], timeout=60)
                # Never --rm: exited state and OOM flag are durable before removal.
                command('remove-owned-checker', DOCKER + ['rm', container_id])
                report['cleanup'] = 'removed_after_state_capture'
            except Exception as error:
                report['errors'].append('cleanup: ' + type(error).__name__ + ': ' + str(error))
                report['cleanup'] = 'incomplete; no unverified container removal'
        inner = output / 'physical-output.json'
        if inner.is_file():
            report['physical_report'] = dict(bytes=inner.stat().st_size, sha256=sha(inner))
            try:
                report['physical_status'] = json.loads(inner.read_text()).get('status')
                need(report['physical_status'] in ('physical_values_pass', 'physical_values_fail', 'integrity_error', 'inconclusive'), 'invalid physical status')
            except Exception as error:
                report['errors'].append('physical report parse: ' + str(error))
        else:
            report['physical_status'] = 'not_available'
        try:
            validate(request_path, digest, output)
            report['bundle_unchanged'] = True
        except Exception as error:
            report['errors'].append('final bundle guard: ' + type(error).__name__ + ': ' + str(error))
            report['bundle_unchanged'] = False
        report['finished_utc'] = utc()
        save(output / 'outer-receipt.json', report)
    return 0 if (not report['errors'] and report['container_state']['ExitCode'] == 0
                 and report['container_state'].get('OOMKilled') is False
                 and report['container_state'].get('Running') is False
                 and report['container_state'].get('Status') == 'exited'
                 and report.get('physical_status') == 'physical_values_pass') else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--request-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute-after-closure', action='store_true')
    parser.add_argument('--detached-child', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    request_path, output = args.request.resolve(), args.output.resolve()
    if args.detached_child:
        need(args.execute_after_closure, 'child requires explicit execution')
        return run_supervisor(request_path, args.request_sha256, output)
    request = validate(request_path, args.request_sha256, output)
    if not args.execute_after_closure:
        print(json.dumps(dict(prepared_only=True, docker_command=create_command(request, request_path.parent, output, args.request_sha256, '<new-per-execution-UUID>')), indent=2))
        return 0
    create_evidence_directory(output)
    child = [sys.executable, '-I', '-B', str(Path(__file__).resolve()), '--request', str(request_path),
             '--request-sha256', args.request_sha256, '--output', str(output), '--execute-after-closure', '--detached-child']
    with (output / 'supervisor.stdout').open('xb') as out, (output / 'supervisor.stderr').open('xb') as err:
        process = subprocess.Popen(child, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                   start_new_session=True, close_fds=True)
    save(output / 'launch.json', dict(utc=utc(), pid=process.pid, command=child, request_sha256=args.request_sha256,
         detached=True, scope='Launch identity only. A missing final outer receipt is incomplete, never success.'))
    print(json.dumps(dict(pid=process.pid, output=str(output), launched=True)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
