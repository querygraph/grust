"""Bounded serial host comparison, dry by default; uses the frozen safe runner.

Execute only after operator scheduling authorization. The shared-host result is
a descriptive ratio with raw cells retained, never an absolute benchmark claim.
No dataset generation, controller change, cache deletion, or automatic retry.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import signal
from pathlib import Path
import subprocess
import sys
import time


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def save(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def normalized(config):
    value = json.loads(json.dumps(config))
    for key in ('run_id', 'host_output', 'runtime_source_sha', 'container_sail_binary'):
        value.pop(key)
    value['suites'][0].pop('name')
    return value


def load_optional(path):
    if not path.exists():
        return None
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('expected JSON object: ' + str(path))
    return value


def inventory(docker):
    try:
        result = subprocess.run(docker + ['ps', '--format', '{{.Names}}'],
                                text=True, capture_output=True, timeout=30)
        return dict(utc=utc(), returncode=result.returncode, names=result.stdout.splitlines(),
                    stderr=result.stderr)
    except (OSError, subprocess.TimeoutExpired) as error:
        return dict(utc=utc(), returncode=None, names=[], stderr=repr(error))


def stop_owned(process, docker, active_name):
    """Bound cleanup to this invocation's process group and exact measured name."""
    record = dict(utc=utc())
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGINT)
            process.wait(timeout=240)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=30)
        except ProcessLookupError:
            process.wait(timeout=30)
    try:
        result = subprocess.run(docker + ['rm', '--force', active_name],
                                text=True, capture_output=True, timeout=60)
        record.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
    except (OSError, subprocess.TimeoutExpired) as error:
        record['error'] = repr(error)
    record['remaining_containers'] = inventory(docker)
    return record


def verify_row(plan, entry, config, receipt, orchestration):
    errors = []
    if not receipt:
        return ['receipt unavailable']
    for key in ('harness_source_sha', 'native_source_sha', 'runtime_source_sha'):
        if receipt.get(key) != config[key]:
            errors.append('source differs: ' + key)
    if receipt.get('source_dirty') != '':
        errors.append('source cleanliness is missing or dirty')
    if receipt.get('binary_sha256') != entry['binary_sha256']:
        errors.append('host binary differs')
    if receipt.get('native_package_identity') != plan['expected_native_package_identity']:
        errors.append('native installed files differ')
    if receipt.get('dataset') != plan['expected_dataset']:
        errors.append('dataset manifest differs')
    actual = receipt.get('arguments') or {}
    expected = dict(plan['expected_arguments'], sail_binary=config['container_sail_binary'],
                    runtime_source_sha=config['runtime_source_sha'], output=entry['cell_output'])
    if actual != expected:
        errors.append('cell arguments differ')
    correctness = receipt.get('correctness') or {}
    if not isinstance(correctness, dict):
        correctness = {}
        errors.append('invalid correctness shape')
    for key, value in (('rows', 16384), ('unique', 16384), ('parent_tree_checked', True),
                       ('reference', 'independent BFS/heap-Dijkstra')):
        if correctness.get(key) != value:
            errors.append('independent correctness check differs: ' + key)
    inspection = orchestration.get('inspect') or {}
    inspection = inspection if isinstance(inspection, dict) else {}
    limits = inspection.get('limits') or {}
    limits = limits if isinstance(limits, dict) else {}
    expected_limits = dict(NanoCpus=8_000_000_000, CpusetCpus='16-23', Memory=12 << 30,
                           MemorySwap=12 << 30, PidsLimit=1024)
    if any(limits.get(key) != value for key, value in expected_limits.items()):
        errors.append('Docker resource envelope differs')
    if inspection.get('image') != config['image']:
        errors.append('Docker image differs')
    cgroup = receipt.get('cgroup_execution_after') or receipt.get('cgroup_after') or {}
    cgroup = cgroup if isinstance(cgroup, dict) else {}
    for key, value in (('memory.max', str(12 << 30)), ('memory.swap.max', '0'),
                       ('cpu.max', '800000 100000'), ('cpuset.cpus.effective', '16-23')):
        if cgroup.get(key) != value:
            errors.append('cgroup envelope differs: ' + key)
    return errors


def valid_seconds(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def summary(plan, rows):
    measurements = [row for row in rows if row['phase'] == 'measurement']
    valid = (len(rows) == 6 and len(measurements) == 4 and
             all(row.get('comparison_eligible') for row in rows) and
             len({row.get('boot_id') for row in rows}) == 1)
    ratios = None
    if valid:
        a1, b1, b2, a2 = (row['seconds'] for row in measurements)
        ratios = dict(adjacent_A_over_B=[a1 / b1, a2 / b2],
                      geometric_mean_A_over_B=math.sqrt((a1 / b1) * (a2 / b2)))
    return dict(recorded_utc=utc(), namespace=plan['namespace'], planned=6,
                completed_records=len(rows), measurement_order='ABBA',
                A='host289', B='host561', rows=rows, shared_host_ratios=ratios,
                measurement_scopes=plan['measurement_scopes'],
                ratio_scope='descriptive ratios on a shared host; two measured samples per host',
                ratio_requires='both warmups and all four measurements passed all identity/metrics checks, same VM boot',
                missing_or_invalid_trials_retained=True,
                unrecorded=[entry for entry in plan['runs'] if entry['order'] not in
                            {row['order'] for row in rows}])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--through', type=int, choices=range(1, 7), default=6,
                        help='execute only this authorized prefix; a later call can continue the remaining prefix')
    parser.add_argument('--expected-plan-sha256')
    args = parser.parse_args()
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    root = args.plan.resolve().parent
    plan = json.loads(args.plan.read_text())
    if args.execute and (not args.expected_plan_sha256 or sha(args.plan) != args.expected_plan_sha256):
        parser.error('execute requires the pinned plan SHA256')
    if sha(__file__) != plan['scripts']['run_host_pair.py']:
        raise RuntimeError('paired runner differs from prepared plan')
    configs = []
    for entry in plan['runs']:
        path = root / entry['configuration']
        if sha(path) != entry['configuration_sha256']:
            raise RuntimeError('configuration changed: ' + str(path))
        config = json.loads(path.read_text())
        if digest(normalized(config)) != plan['common_configuration_sha256']:
            raise RuntimeError('configs differ beyond runtime and namespaces')
        configs.append(config)
    if not args.execute:
        print(json.dumps(dict(scope='dry plan; no Docker or workload', runs=plan['runs'],
                              resource_fingerprint=plan['resource_fingerprint']), indent=2))
        return 0
    for name in ('run_focused_safe.py', 'preflight_cell.py'):
        if sha(root / name) != plan['scripts'][name]:
            raise RuntimeError('support script changed: ' + name)
    for name, expected in plan['harness_files_sha256'].items():
        if sha(root / 'harness' / name) != expected:
            raise RuntimeError('host harness changed: ' + name)
    sys.path.insert(0, str(root / 'harness'))
    import run_matrix as matrix
    os.environ['PATH'] = '/usr/local/bin:/usr/bin:/bin:' + os.environ.get('PATH', '')
    output = root / plan['namespace']
    output.mkdir(exist_ok=True)
    ledger_path = output / 'sequence.json'
    ledger = load_optional(ledger_path) or dict(plan_sha256=sha(args.plan), created_utc=utc(), rows=[])
    if ledger['plan_sha256'] != sha(args.plan):
        raise RuntimeError('existing sequence belongs to another plan')
    # This lock serializes invocations of this study, not other host workflows.
    lock = output / 'active.lock'
    with lock.open('x') as stream:
        stream.write(json.dumps(dict(pid=os.getpid(), utc=utc())))
    row = None
    process = None
    try:
        for entry, config in zip(plan['runs'][len(ledger['rows']):args.through],
                                 configs[len(ledger['rows']):args.through]):
            process = None
            docker = ['/usr/local/bin/docker', '--context', config['docker_context']]
            row = {key: entry[key] for key in ('order', 'phase', 'host', 'configuration')}
            row.update(started_utc=utc(), outcome='not_run', comparison_eligible=False)
            prefix = output / f"{entry['order']:02d}"
            before = inventory(docker)
            save(prefix.with_suffix('.inventory-before.json'), before)
            if before['returncode'] or before['names']:
                raise RuntimeError('another container is active; no cell admitted')
            if Path(config['host_output']).exists():
                raise RuntimeError('cell output exists; no retries or overwrites')
            preflight = prefix.with_suffix('.preflight.json')
            command = [sys.executable, str(root / 'preflight_cell.py'),
                       str(root / entry['configuration']), str(preflight),
                       '--expected-config-sha256', entry['configuration_sha256'],
                       '--expected-binary-sha256', entry['binary_sha256'],
                       '--minimum-free-bytes', str(plan['minimum_free_bytes'])]
            with prefix.with_suffix('.preflight.log').open('x') as log:
                checked = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=300)
            pre = load_optional(preflight)
            if checked.returncode or not pre or pre['outcome'] != 'passed':
                raise RuntimeError('identity/disk admission failed; preserved preflight, no cell launched')
            observed = pre['observed']
            if observed['datasets']['weighted16k']['sha256'] != plan['dataset_manifest_sha256']:
                raise RuntimeError('dataset manifest differs; no cell launched')
            row['boot_id'] = observed['boot_id']
            row['free_bytes_before'] = observed['free_bytes']
            row['runner_command'] = [sys.executable, str(root / 'run_focused_safe.py'),
                                     str(root / entry['configuration'])]
            save(prefix.with_suffix('.started.json'), row)
            active_name = 'sail-' + config['run_id'] + '-1'
            concurrency = []
            with prefix.with_suffix('.runner.log').open('x') as log:
                process = subprocess.Popen(row['runner_command'], stdout=log, stderr=subprocess.STDOUT,
                                           start_new_session=True)
                deadline = time.monotonic() + plan['runner_wall_timeout_seconds']
                row['runner_wall_timeout'] = False
                while process.poll() is None:
                    if time.monotonic() >= deadline:
                        row['runner_wall_timeout'] = True
                        row['deadline_cleanup'] = stop_owned(process, docker, active_name)
                        break
                    sample = inventory(docker)
                    concurrency.append(sample)
                    # Preserve progress durably; no tool call must wait for the sequence.
                    save(prefix.with_suffix('.inventory.json'), concurrency)
                    time.sleep(2)
            row['runner_returncode'] = process.returncode
            cell_root = Path(config['host_output'])
            orchestration = None
            try:
                orchestration = load_optional(cell_root / 'cell/orchestration.json')
            except (ValueError, OSError) as error:
                row['orchestration_read_error'] = repr(error)
            receipt = None
            receipt_error = None
            try:
                receipt = load_optional(cell_root / 'diagnostics/receipt.json')
            except (ValueError, OSError) as error:
                receipt_error = repr(error)
            if orchestration:
                classification_record = dict(orchestration)
                if receipt_error:
                    classification_record['receipt_read_error'] = receipt_error
                try:
                    row['outcome'] = matrix.classify(classification_record, receipt, config['harness_source_sha'])
                except (ValueError, TypeError, KeyError, AttributeError) as error:
                    row['classification_error'] = repr(error)
                    row['outcome'] = 'invalid_receipt'
            else:
                row['outcome'] = 'orchestration_error'
            if row['runner_wall_timeout']:
                row['underlying_outcome'] = row['outcome']
                row['outcome'] = 'orchestrator_timeout'
            row['receipt_outcome'] = receipt.get('outcome') if receipt else None
            row['receipt_read_error'] = receipt_error
            row['orchestration'] = orchestration
            row['identity_errors'] = verify_row(plan, entry, config, receipt, orchestration or {})
            memory = (receipt or {}).get('memory') or {}
            if not isinstance(memory, dict):
                memory = {}
                row['identity_errors'].append('invalid memory shape')
            peaks = memory.get('phase_peaks') or {}
            execute = (peaks.get('execute') or {}) if isinstance(peaks, dict) else {}
            if not isinstance(execute, dict):
                execute = {}
            row.update(seconds=(receipt or {}).get('end_to_end_seconds'),
                       elapsed_until_error_seconds=(receipt or {}).get('elapsed_until_error_seconds'),
                       execution_pss_bytes=execute.get('pss_bytes'),
                       execution_rss_bytes=execute.get('rss_bytes'),
                       memory_sampler_error=memory.get('error'),
                       guest_steal_fraction=(receipt or {}).get('guest_steal_fraction'),
                       steal_scope=(receipt or {}).get('steal_scope'),
                       cgroup_execution_after=(receipt or {}).get('cgroup_execution_after'),
                       cgroup_after=(receipt or {}).get('cgroup_after'),
                       correctness=(receipt or {}).get('correctness'),
                       algorithm_iterations=(receipt or {}).get('algorithm_iterations'))
            samples = [sample for sample in concurrency if active_name in sample['names']]
            row['concurrency_sampling'] = dict(interval_seconds=2, samples_during_cell=len(samples),
                observed_sibling_containers=sorted({name for sample in samples for name in sample['names']
                                                   if name != active_name}),
                inventory_errors=sum(sample['returncode'] != 0 for sample in concurrency),
                scope='sampled observation, not a host-wide lock')
            sampling = row['concurrency_sampling']
            seconds = row['seconds']
            pss, steal = row['execution_pss_bytes'], row['guest_steal_fraction']
            valid_pss = type(pss) in (int, float) and math.isfinite(pss) and pss > 0
            valid_steal = type(steal) in (int, float) and math.isfinite(steal) and 0 <= steal <= 1
            row['comparison_eligible'] = (row['outcome'] == 'passed' and not row['identity_errors']
                and row['runner_returncode'] == 0 and memory.get('error') is None
                and memory.get('execution_sampled') is True and valid_pss
                and valid_steal and valid_seconds(seconds) and samples
                and not sampling['observed_sibling_containers'] and not sampling['inventory_errors'])
            row['comparison_eligible'] = bool(row['comparison_eligible'])
            row['finished_utc'] = utc()
            save(prefix.with_suffix('.result.json'), row)
            ledger['rows'].append(row)
            ledger['updated_utc'] = utc()
            save(ledger_path, ledger)
            save(output / 'summary.json', summary(plan, ledger['rows']))
            if row['runner_wall_timeout']:
                raise RuntimeError('wall deadline reached; no later cell launched')
        print(json.dumps(dict(output=str(output), completed_records=len(ledger['rows']),
                              authorized_prefix=args.through)), flush=True)
        return 0
    except BaseException as error:
        if process is not None and process.poll() is None:
            row['interruption_cleanup'] = stop_owned(process, docker, active_name)
        failure = output / ('orchestrator-error-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
        save(failure, dict(utc=utc(), error=repr(error), completed_records=len(ledger['rows']),
                           active_row=row, scope='preserved; no automatic retry or outcome substitution'))
        save(output / 'summary.json', summary(plan, ledger['rows']))
        raise
    finally:
        lock.unlink()


if __name__ == '__main__':
    raise SystemExit(main())
