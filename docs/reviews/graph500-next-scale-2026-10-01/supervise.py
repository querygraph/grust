"""Serial, pinned Graph500 qualification; invoke only after separate launch approval.

The lock coordinates this supervisor, not arbitrary host jobs. Admission is a
point-in-time observation; polling has gaps. Only proven own containers may stop.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time

ROOT = Path('/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930')
TARGETS = '/targets/sail-stream-experiments-20260930'
DOCKER = ['/usr/local/bin/docker', '--context', 'colima-sail-gate']
IMAGE = 'sha256:f3518d652fbea8b9b9f9ebf9849277ca3bd39d0c21bb2c6e36fbaeaa2dc2678e'
PYTHON = '/targets/graph-nuts-ffcfbd569/venv/bin/python'
SOURCE = TARGETS + '/source-3a9028057'
HEAD = '3a9028057c6c6c5034492845926fc4bc18f9626f'
RUNTIME = '56194b170155301ba91077f0ba3df31fe2c78b6b'
NATIVE = 'ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73'
BINARY = '/targets/sail-compact-host-56194b170155/sail-linux-x86_64-56194b170155-release'
BINARY_SHA = '5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec'
NATIVE_SHA = 'eb0be839de652e059799dea3bba22cc0908998bd97cfa2f4cf04c67817e2ee50'
LAUNCHER_SHA = '53589784544a1414b29b1a42e061bada15a0a868801cd356addf4e35f29abdd1'
STOP = threading.Event()
OBSERVERS = {}
GIB = 2**30
PREFLIGHT = ('import pathlib,subprocess,sys; p=pathlib.Path(sys.argv[1]); '
             'assert subprocess.check_output(["git","-C",str(p),"rev-parse","HEAD"],text=True).strip()==sys.argv[2]; '
             'assert not subprocess.check_output(["git","-C",str(p),"status","--porcelain"],text=True).strip(); '
             'assert pathlib.Path(sys.argv[3]).is_file(); print("preflight passed")')
COLLECT = '''
from pathlib import Path
import sys,tarfile
p=Path(sys.argv[1])
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as t:
 for f in sorted(p.iterdir()):
  if f.is_file() and not f.is_symlink(): t.add(f,arcname=f.name,recursive=False)
'''
PROBE = r'''
import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
os.environ['GIT_OPTIONAL_LOCKS']='0'
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
c=json.loads(sys.argv[1]);r={'free_bytes':shutil.disk_usage('/targets').free,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
r['memory']=Path('/proc/meminfo').read_text();r['available_bytes']=int(next(x.split()[1] for x in r['memory'].splitlines() if x.startswith('MemAvailable:')))*1024
if sys.argv[2]=='admit':
 r['binary_sha256']=sha(c['container_sail_binary']);r['native_sha256']=sha('/targets/graph-nuts-ffcfbd569/venv/lib/python3.12/site-packages/sail_nutmeg/_native.cpython-312-x86_64-linux-gnu.so')
 r['head']=subprocess.check_output(['git','-C',c['container_repo'],'rev-parse','HEAD'],text=True).strip();r['dirty']=subprocess.check_output(['git','-C',c['container_repo'],'status','--porcelain'],text=True).strip()
 r['manifests']={n:sha(Path(c['container_root'])/'datasets'/n/'manifest.json') for n in c['datasets']}
 r['cell_absent']=not (Path(c['container_root'])/'cells').exists()
print(json.dumps(r))
'''


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def write(path, data, append=False):
    with path.open('a' if append else 'x') as stream:
        stream.write(json.dumps(dict(recorded_utc=datetime.now(timezone.utc).isoformat(), **data)) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def capture(command, timeout=45):
    started = time.monotonic()
    try:
        p = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        return dict(returncode=p.returncode, stdout=p.stdout, stderr=p.stderr,
                    seconds=time.monotonic() - started)
    except subprocess.TimeoutExpired as error:
        retained = {}
        for name, data in [('stdout', error.stdout), ('stderr', error.stderr)]:
            data = data.encode('utf-8', errors='replace') if isinstance(data, str) else (data or b'')
            retained[name] = data[:65536].decode('utf-8', errors='replace')
            retained[name + '_bytes'] = len(data)
            retained[name + '_sha256'] = hashlib.sha256(data).hexdigest()
            retained[name + '_truncated'] = len(data) > 65536
        return dict(returncode=None, error=repr(error), seconds=time.monotonic() - started, **retained)
    except OSError as error:
        return dict(returncode=None, error=repr(error), seconds=time.monotonic() - started)


def successful(result):
    require(result['returncode'] == 0, 'observer command failed: ' + repr(result))
    return result['stdout']


def containers():
    return successful(capture(DOCKER + ['ps', '-a', '--format', '{{json .}}'])).splitlines()


def inspect(ident):
    result = capture(DOCKER + ['inspect', ident])
    if result['returncode'] != 0:
        # An own --rm helper can vanish after ps. A fresh successful inventory
        # proves absence; a still-listed item or failed inventory stays fatal.
        require(not any(ident.startswith(json.loads(x)['ID']) or json.loads(x)['ID'].startswith(ident)
                        for x in containers()), 'listed container inspection failed')
        return None
    return json.loads(result['stdout'])[0]


def cell_path(c):
    s = c['suites'][0]
    return c['container_root'] + '/cells/' + '-'.join([s['name'], 'r1', s['datasets'][0], s['engines'][0], 'sssp', 'delta_star'])


def own_kind(item, c):
    """Exact pinned helper fingerprints; an image/name alone grants no ownership."""
    if item is None:
        return None
    cfg, mounts = item['Config'], item['Mounts']
    if item['Image'] != IMAGE or cfg.get('Entrypoint') != [PYTHON]:
        return None
    volume = [m for m in mounts if m.get('Destination') == '/targets']
    if len(mounts) != 1 or len(volume) != 1 or volume[0].get('Name') != 'sail-extension-targets':
        return None
    cmd, name = cfg.get('Cmd'), item['Name'].lstrip('/')
    prefix = 'sail-' + c['run_id']
    if name in OBSERVERS and cmd == OBSERVERS[name] and not volume[0]['RW']:
        return 'observer'
    if name == prefix + '-preflight' and cmd == ['-I', '-c', PREFLIGHT, SOURCE, HEAD, BINARY]:
        return 'preflight'
    if cmd == ['-I', '-c', COLLECT, cell_path(c)] and not volume[0]['RW']:
        return 'collection'
    if name == prefix + '-1' and isinstance(cmd, list) and cmd[:1] == [SOURCE + '/examples/extensions/benchmarks/graph_cell.py']:
        required = {'--output': cell_path(c), '--sail-binary': BINARY, '--runtime-source-sha': RUNTIME,
                    '--native-source-sha': NATIVE, '--engine': c['suites'][0]['engines'][0], '--algorithm': 'sssp', '--variant': 'delta_star'}
        if all(cmd.count(k) == 1 and cmd.index(k) + 1 < len(cmd) and cmd[cmd.index(k) + 1] == v for k, v in required.items()):
            return 'cell'
    return None


def live(c=None):
    rows = [json.loads(x) for x in containers()]
    running = [r for r in rows if r['State'] == 'running']
    items = [(r, inspect(r['ID'])) for r in running]
    items = [(r, i) for r, i in items if i is not None]
    require(all(c is not None and own_kind(i, c) for _, i in items), 'interference: unexpected running container')
    return [dict(id=i['Id'], name=i['Name'], kind=own_kind(i, c)) for _, i in items]


def verify_inputs(plan_path, plan_hash, plan):
    require(sha(plan_path) == plan_hash, 'plan changed')
    support = plan['support_sha256']
    require(support.get('run_focused_safe.py') == LAUNCHER_SHA and 'harness/run_matrix.py' in support, 'missing launcher/harness pins')
    actual = {str(p.relative_to(ROOT)) for p in (ROOT / 'harness').glob('*.py')}
    require(actual == {p for p in support if p.startswith('harness/')}, 'harness inventory mismatch')
    for name, expected in support.items():
        p = ROOT / name
        require(not p.is_symlink() and p.resolve().is_relative_to(ROOT) and sha(p) == expected, 'support mismatch: ' + name)


def config(spec):
    p = Path(spec['config'])
    require(p.parent == ROOT and not p.is_symlink() and sha(p) == spec['config_sha256'], 'config identity mismatch')
    c = load(p)
    expected = dict(docker_context='colima-sail-gate', image=IMAGE, target_volume='sail-extension-targets', container_python=PYTHON,
                    container_repo=SOURCE, container_sail_binary=BINARY, runtime_source_sha=RUNTIME, native_source_sha=NATIVE, harness_source_sha=HEAD)
    require(all(c.get(k) == v for k, v in expected.items()), 'configuration source mismatch')
    require(re.fullmatch(r'[a-z0-9-]+', c['run_id']) is not None, 'invalid run identifier')
    require(c['host_output'] == str(ROOT / c['run_id']) and c['container_root'] == TARGETS + '/' + c['run_id'], 'non-fresh namespace shape')
    require(len(c['suites']) == 1, 'not one cell')
    s = c['suites'][0]
    require(s['name'] == c['run_id'] and s['mode'] == 'process-cluster' and s['repetitions'] == 1 and
            len(s['datasets']) == 1 and s['engines'] in [['pecan'], ['nutmeg-datafusion']] and
            s['algorithms'] == ['sssp'] and s['variants'] == ['delta_star'], 'unexpected cell shape')
    require(set(spec['manifest_sha256']) == set(c['datasets']) == set(s['datasets']), 'manifest inventory mismatch')
    require(c['defaults']['timeout'] == 28800 and c['limits']['outer_timeout_seconds'] == 32400, 'deadline mismatch')
    require(c['limits'] == dict(cpus=32, cpuset_cpus='0-31', memory_gib=100, outer_timeout_seconds=32400), 'resource envelope mismatch')
    require(all(c['defaults'][k] == v for k, v in dict(partitions=32, threads=32, worker_task_slots=64, sail_pool_bytes=96*GIB, native_quota=80*GIB, delta=0.1, max_iterations=1000).items()) and s['max_iterations'] == 1000, 'execution settings mismatch')
    require(c['extra_cell_args'] == ['--record-plans', '--http2-keepalive-timeout', '120'] and
            c['environment'] == {'SAIL_CLUSTER__TASK_STREAM_CREATION_TIMEOUT_SECS': '900', 'SAIL_CLUSTER__WORKER_MAX_IDLE_TIME_SECS': '86400', 'SAIL_BENCHMARK_RUST_LOG': 'info,h2::proto::connection=debug,h2::proto::streams=warn,h2::frame::go_away=trace,h2::frame::reset=trace,h2::frame::ping=trace,h2::proto::ping_pong=trace,sail_execution::task_runner=debug,tonic::transport::server=debug'}, 'logging/transport settings mismatch')
    require(type(spec['min_free_bytes']) is int and spec['min_free_bytes'] >= 30 * GIB and
            type(spec['min_available_memory_bytes']) is int and spec['min_available_memory_bytes'] >= 102 * GIB, 'admission too small')
    return c


def observe(c, evidence, serial, boot, admit=False):
    record = dict(serial=serial, kind='admission' if admit else 'poll', started_monotonic=time.monotonic())
    try:
        record['containers'] = live(None if admit else c)
        for key, cmd in [('host_memory', ['/usr/sbin/sysctl', 'vm.swapusage', 'vm.loadavg']), ('vm_stat', ['/usr/bin/vm_stat'])]:
            record[key] = capture(cmd)
            successful(record[key])
        name = 'sail-' + c['run_id'] + '-observer-' + str(serial)
        require(not any(json.loads(x)['Names'] == name for x in containers()), 'observer name exists')
        OBSERVERS[name] = ['-I', '-B', '-c', PROBE, json.dumps(c), 'admit' if admit else 'poll']
        command = DOCKER + ['run', '--rm', '--name', name, '--read-only', '--network', 'none', '--memory', '256m', '--memory-swap', '256m', '--cpus', '1', '--pids-limit', '32', '--mount', 'type=volume,source=sail-extension-targets,target=/targets,readonly', '--entrypoint', PYTHON, IMAGE] + OBSERVERS[name]
        record['probe'] = capture(command, 120 if admit else 45)
        value = json.loads(successful(record['probe']))
        record['values'] = value
        require(value['boot_id'] == boot, 'VM boot changed')
        require(value['free_bytes'] >= 8 * GIB, 'resource_stop: disk below 8 GiB')
        record['containers_after'] = live(None if admit else c)
        return value
    except BaseException as error:
        record['error'] = repr(error)
        raise
    finally:
        record['seconds'] = time.monotonic() - record['started_monotonic']
        record['over_30s'] = record['seconds'] > 30
        write(evidence / 'observations.jsonl', record, append=True)


def admission(v, spec):
    require(v['binary_sha256'] == BINARY_SHA and v['native_sha256'] == NATIVE_SHA and v['head'] == HEAD and not v['dirty'], 'runtime/native/source identity mismatch')
    require(v['manifests'] == spec['manifest_sha256'] and v['cell_absent'], 'dataset mismatch or existing cell directory')
    require(v['free_bytes'] >= spec['min_free_bytes'] and v['available_bytes'] >= spec['min_available_memory_bytes'], 'insufficient admission headroom')


def closed(c, returncode):
    output = Path(c['host_output'])
    r, p, o = [load(output / name) for name in ('result.json', 'diagnostics/receipt.json', 'cell/orchestration.json')]
    state = o['inspect']['state']
    counters = dict(line.split() for line in p['cgroup_after']['memory.events'].splitlines())
    data = c['datasets'][c['suites'][0]['datasets'][0]]
    require(o['inspect']['image'] == IMAGE and all(o['inspect']['limits'][k] == v for k, v in
            dict(Memory=100*GIB, MemorySwap=100*GIB, NanoCpus=32_000_000_000, CpusetCpus='0-31').items()), 'closure resource identity mismatch')
    require(all(p['arguments'][k] == v for k, v in dict(output=cell_path(c), engine=c['suites'][0]['engines'][0], algorithm='sssp', variant='delta_star',
            source=data['source'], directed=False, delta=0.1, expected_vertices=data['vertices'], expected_graph500_sha256=data['expected_edge_sha256'],
            mode='process-cluster', repeat=1, traversal_validation='certificate', certificate_max_rounds=10000, expected_dataset_family='graph500',
            dataset='/targets/gn-capacity-b87fb27a-hub/datasets/' + c['suites'][0]['datasets'][0],
            timeout=28800, max_iterations=1000, partitions=32, threads=32, worker_task_slots=64, sail_pool_bytes=96*GIB, native_quota=80*GIB).items()), 'producer argument identity mismatch')
    require(o['remove']['returncode'] == 0 and not state['Running'] and state['Status'] == 'exited' and
            not o['transport_errors'] and not p['cleanup_errors'], 'incomplete cleanup/collection')
    require(p['runtime_source_sha'] == RUNTIME and p['binary_sha256'] == BINARY_SHA and p['native_source_sha'] == NATIVE and p['harness_source_sha'] == HEAD, 'producer source mismatch')
    files = {name: sha(output / name) for name in ('result.json', 'diagnostics/receipt.json', 'cell/orchestration.json')}
    if r['outcome'] != 'passed' or p['outcome'] != 'passed':
        return dict(outcome='not_passed', producer_outcome=p['outcome'], result_outcome=r['outcome'], files=files)
    correct = p['correctness']
    n = data['vertices']
    ok = (returncode == 0 and r['outcome'] == p['outcome'] == 'passed' and o['attach_returncode'] == 0 and
          state['Status'] == 'exited' and state['ExitCode'] == 0 and state['OOMKilled'] is False and not state['Running'] and not state['Error'] and
          not o['outer_timeout'] and not o['transport_errors'] and o['remove']['returncode'] == 0 and not p['cleanup_errors'] and
          all(int(counters[k]) == 0 for k in ('oom', 'oom_kill')) and p['algorithm_converged'] is True and
          type(correct['rows']) is int and type(correct['unique']) is int and correct['rows'] == correct['unique'] == n and correct['parent_tree_checked'] is True and
          correct['certificate'] == 'all-edge inequalities and rooted tight-edge reachability' and
          type(correct['reached']) is int and 1 <= correct['reached'] <= n and type(correct['witness_rounds']) is int and correct['witness_rounds'] > 0 and
          all(type(correct[k]) in (int, float) and math.isfinite(correct[k]) and correct[k] >= 0 for k in ('relative_edge_tolerance', 'max_edge_slack', 'conservative_absolute_distance_error_bound')) and
          correct['relative_edge_tolerance'] == 1e-12 and type(p['algorithm_iterations']) is int and 0 < p['algorithm_iterations'] <= 1000)
    require(ok, 'closed cell did not pass all producer/closure requirements')
    return dict(outcome='passed', producer_outcome=p['outcome'], result_outcome=r['outcome'], correctness=correct,
                files=files, physical_output_checked=False)


def abort(p, c, evidence):
    record = {'scope': 'own launcher process group and fingerprinted own containers only', 'stops': []}
    try:
        if p is not None and p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGTERM)  # Prevent a preflight launcher from starting another container.
            except ProcessLookupError:
                pass  # A normal launcher exit can race poll; still inspect own containers.
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                p.wait(timeout=10)
        record['launcher_returncode'] = p.poll() if p is not None else None
        for raw in containers():
            row = json.loads(raw)
            if row['State'] == 'running':
                item = inspect(row['ID'])
                kind = own_kind(item, c)
                if kind and (p is not None or kind == 'observer'):
                    stop = capture(DOCKER + ['stop', '--time', '30', item['Id']], 45)
                    record['stops'].append(dict(id=item['Id'], kind=own_kind(item, c), stop=stop))
                    successful(stop)
                    # --rm observers can disappear after stop; absence is a valid closure.
                    require(not any(item['Id'].startswith(json.loads(x)['ID']) and json.loads(x)['State'] == 'running' for x in containers()), 'own container still running')
    except BaseException as error:
        record['error'] = repr(error)
    finally:
        write(evidence / 'stop.json', record)
    return 'error' not in record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True, type=Path)
    args = parser.parse_args()
    require(args.plan.parent == ROOT and not args.plan.is_symlink(), 'plan outside fixed root')
    plan_hash, plan = sha(args.plan), load(args.plan)
    require(re.fullmatch(r'[a-z0-9-]+', plan['run_id']) is not None, 'bad supervisor name')
    evidence = ROOT / (plan['run_id'] + '-supervisor')
    evidence.mkdir()
    lock = ROOT / 'next-graph500.lock'
    p = c = None
    acquired, safe = False, True
    final = dict(outcome='error', plan_sha256=plan_hash, supervisor_sha256=sha(__file__), cells=[])
    try:
        lock.mkdir()
        acquired = True
        verify_inputs(args.plan, plan_hash, plan)
        configs = [config(s) for s in plan['cells']]
        require(configs and len({c['run_id'] for c in configs}) == len(configs), 'empty/duplicate cell namespace')
        passed = set()
        for index, (spec, c) in enumerate(zip(plan['cells'], configs)):
            require(not STOP.is_set(), 'operator_interrupted')
            p = None
            if spec.get('depends_on_success') and spec['depends_on_success'] not in passed:
                final['cells'].append(dict(run_id=c['run_id'], outcome='skipped_dependency', depends_on_success=spec['depends_on_success']))
                continue
            verify_inputs(args.plan, plan_hash, plan)
            require(sha(__file__) == final['supervisor_sha256'], 'supervisor source changed')
            config(spec)
            require(not Path(c['host_output']).exists(), 'existing host output')
            prefix = 'sail-' + c['run_id']
            require(not any(json.loads(x)['Names'] in (prefix + '-1', prefix + '-preflight') for x in containers()), 'existing named container')
            cell = evidence / c['run_id']
            cell.mkdir()
            admission(observe(c, cell, 0, plan['expected_boot_id'], True), spec)
            with (cell / 'runner.stdout').open('x') as out, (cell / 'runner.stderr').open('x') as err:
                p = subprocess.Popen([sys.executable, '-I', '-B', str(ROOT / 'run_focused_safe.py'), spec['config']], stdout=out, stderr=err, start_new_session=True)
                write(cell / 'launch.json', dict(pid=p.pid, config_sha256=spec['config_sha256'], config=spec['config']))
                start, serial = time.monotonic(), 0
                while p.poll() is None:
                    require(not STOP.wait(30), 'operator_interrupted')
                    serial += 1
                    observe(c, cell, serial, plan['expected_boot_id'])
                    require(time.monotonic() - start <= c['limits']['outer_timeout_seconds'] + 900, 'launcher overrun')
                write(cell / 'exit.json', dict(returncode=p.returncode, seconds=time.monotonic() - start))
            live()  # A failed cleanup or any foreign workload blocks the next launch.
            verify_inputs(args.plan, plan_hash, plan)
            config(spec)
            result = closed(c, p.returncode)
            write(cell / 'qualification.json', result)
            final['cells'].append(dict(run_id=c['run_id'], **result))
            if result['outcome'] == 'passed':
                passed.add(c['run_id'])
        require(sha(__file__) == final['supervisor_sha256'], 'supervisor source changed')
        final['outcome'] = 'passed' if len(passed) == len(configs) else 'completed_with_nonpass'
    except BaseException as error:
        final['error'] = repr(error)
        if c is not None:
            safe = abort(p, c, evidence)
    finally:
        if acquired and safe:
            try:
                lock.rmdir()  # Never remove evidence, outputs, foreign containers, or a nonempty lock.
            except OSError as error:
                final['lock_error'] = repr(error)
                final['outcome'] = 'error'
        final['lock_retained'] = acquired and lock.exists()
        write(evidence / 'receipt.json', final)
    return 0 if final['outcome'] == 'passed' else 1


if __name__ == '__main__':
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: STOP.set())
    raise SystemExit(main())
