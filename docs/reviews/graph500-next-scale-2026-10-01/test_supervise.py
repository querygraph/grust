"""Offline controls only: every subprocess/Docker operation is mocked."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('supervise', HERE / 'supervise.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def base_config():
    return json.loads((HERE / 'next-capacity-pecan-s25.json').read_text())


def item(c, kind='cell', ident='a' * 64):
    cmd = [s.SOURCE + '/examples/extensions/benchmarks/graph_cell.py']
    for key, value in {'--output': s.cell_path(c), '--sail-binary': s.BINARY, '--runtime-source-sha': s.RUNTIME,
                       '--native-source-sha': s.NATIVE, '--engine': c['suites'][0]['engines'][0], '--algorithm': 'sssp', '--variant': 'delta_star'}.items():
        cmd.extend([key, value])
    name, rw = 'sail-' + c['run_id'] + '-1', True
    if kind == 'preflight':
        name = 'sail-' + c['run_id'] + '-preflight'
        cmd = ['-I', '-c', s.PREFLIGHT, s.SOURCE, s.HEAD, s.BINARY]
    if kind == 'collection':
        name, rw = 'random-docker-name', False
        cmd = ['-I', '-c', s.COLLECT, s.cell_path(c)]
    return dict(Id=ident, Name='/' + name, Image=s.IMAGE, Config=dict(Entrypoint=[s.PYTHON], Cmd=cmd),
                Mounts=[dict(Destination='/targets', Name='sail-extension-targets', RW=rw)], State=dict(Running=True))


def closure(root, c):
    c['host_output'] = str(root / 'result')
    n = next(iter(c['datasets'].values()))['vertices']
    data = next(iter(c['datasets'].values()))
    producer = dict(outcome='passed', runtime_source_sha=s.RUNTIME, native_source_sha=s.NATIVE, harness_source_sha=s.HEAD,
                    binary_sha256=s.BINARY_SHA, cgroup_after={'memory.events': 'oom 0\noom_kill 0\n'}, cleanup_errors=[],
                    algorithm_converged=True, algorithm_iterations=60,
                    arguments=dict(output=s.cell_path(c), engine=c['suites'][0]['engines'][0], algorithm='sssp', variant='delta_star',
                        source=data['source'], directed=False, delta=0.1, expected_vertices=n, expected_graph500_sha256=data['expected_edge_sha256'],
                        mode='process-cluster', repeat=1, traversal_validation='certificate', certificate_max_rounds=10000, expected_dataset_family='graph500',
                        dataset='/targets/gn-capacity-b87fb27a-hub/datasets/' + c['suites'][0]['datasets'][0],
                        timeout=28800, max_iterations=1000, partitions=32, threads=32, worker_task_slots=64, sail_pool_bytes=96*s.GIB, native_quota=80*s.GIB),
                    correctness=dict(rows=n, unique=n, reached=10, witness_rounds=22, parent_tree_checked=True,
                        certificate='all-edge inequalities and rooted tight-edge reachability', relative_edge_tolerance=1e-12,
                        max_edge_slack=1e-13, conservative_absolute_distance_error_bound=0.001))
    orchestration = dict(attach_returncode=0, outer_timeout=False, transport_errors=[], remove=dict(returncode=0),
        inspect=dict(image=s.IMAGE, limits=dict(Memory=100*s.GIB, MemorySwap=100*s.GIB, NanoCpus=32_000_000_000, CpusetCpus='0-31'),
        state=dict(Status='exited', ExitCode=0, OOMKilled=False, Running=False, Error='')))
    output = Path(c['host_output'])
    dump(output / 'result.json', dict(outcome='passed'))
    dump(output / 'diagnostics/receipt.json', producer)
    dump(output / 'cell/orchestration.json', orchestration)
    return producer, orchestration


class Controls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        s.STOP.clear()
        s.OBSERVERS.clear()

    def test_real_config_with_only_private_path_relocation(self):
        plan = json.loads((HERE / 'plan.json').read_text())
        with patch.object(s, 'ROOT', self.root):
            for cell in plan['cells']:
                c = json.loads((HERE / Path(cell['config']).name).read_text())
                c['host_output'] = str(self.root / c['run_id'])
                p = self.root / Path(cell['config']).name
                dump(p, c)
                cell = dict(cell, config=str(p), config_sha256=s.sha(p))
                self.assertEqual(s.config(cell), c)
                c['limits']['memory_gib'] = 101
                dump(p, c)
                cell['config_sha256'] = s.sha(p)
                with self.assertRaisesRegex(RuntimeError, 'resource envelope'):
                    s.config(cell)

    def test_helper_ownership_is_exact(self):
        c = base_config()
        for kind in ('cell', 'preflight', 'collection'):
            i = item(c, kind)
            self.assertEqual(s.own_kind(i, c), kind)
            i['Config']['Cmd'].append('foreign')
            if kind != 'cell':
                self.assertIsNone(s.own_kind(i, c))
        i = item(c)
        i['Config']['Cmd'][i['Config']['Cmd'].index('--output') + 1] += '-foreign'
        self.assertIsNone(s.own_kind(i, c))
        i = item(c, 'collection')
        i['Mounts'][0]['RW'] = True
        self.assertIsNone(s.own_kind(i, c))

    def test_same_image_foreign_job_is_interference(self):
        c = base_config()
        i = item(c)
        i['Name'] = '/foreign'
        rows = [json.dumps(dict(ID=i['Id'][:12], Names='foreign', State='running'))]
        with patch.object(s, 'containers', return_value=rows), patch.object(s, 'inspect', return_value=i):
            with self.assertRaisesRegex(RuntimeError, 'interference'):
                s.live(c)

    def test_ps_inspect_disappearance_is_not_observer_failure(self):
        with patch.object(s, 'capture', return_value=dict(returncode=1, stderr='no such container')), patch.object(s, 'containers', return_value=[]):
            self.assertIsNone(s.inspect('a' * 12))
        with patch.object(s, 'capture', return_value=dict(returncode=1, stderr='daemon error')), patch.object(s, 'containers', return_value=[json.dumps(dict(ID='a'*12))]):
            with self.assertRaisesRegex(RuntimeError, 'inspection failed'):
                s.inspect('a' * 12)

    def test_timeout_keeps_partial_output_with_bounded_decode(self):
        error = s.subprocess.TimeoutExpired(['mock'], 1, output=b'partial out', stderr=b'partial err')
        with patch.object(s.subprocess, 'run', side_effect=error):
            r = s.capture(['mock'], 1)
        self.assertEqual((r['stdout'], r['stderr']), ('partial out', 'partial err'))
        self.assertIsNone(r['returncode'])
        self.assertFalse(r['stdout_truncated'])
        error = s.subprocess.TimeoutExpired(['mock'], 1, output=b'x'*65537 + b'\xff')
        with patch.object(s.subprocess, 'run', side_effect=error):
            r = s.capture(['mock'], 1)
        self.assertEqual(len(r['stdout']), 65536)
        self.assertEqual(r['stdout_bytes'], 65538)
        self.assertTrue(r['stdout_truncated'])

    def test_missing_collection_never_qualifies(self):
        c = base_config()
        closure(self.root, c)
        (Path(c['host_output']) / 'result.json').unlink()
        with self.assertRaises(FileNotFoundError):
            s.closed(c, 0)

    def test_admission_boundaries(self):
        spec = dict(min_free_bytes=32*s.GIB, min_available_memory_bytes=102*s.GIB, manifest_sha256={'scale25': 'pin'})
        v = dict(binary_sha256=s.BINARY_SHA, native_sha256=s.NATIVE_SHA, head=s.HEAD, dirty='', manifests={'scale25': 'pin'}, cell_absent=True,
                 free_bytes=33*s.GIB, available_bytes=103*s.GIB)
        s.admission(v, spec)
        for key, value in [('binary_sha256', 'wrong'), ('native_sha256', 'wrong'), ('dirty', 'M file'),
                           ('manifests', {}), ('cell_absent', False), ('free_bytes', 31*s.GIB), ('available_bytes', 101*s.GIB)]:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                s.admission(dict(v, **{key: value}), spec)

    def test_failed_observer_retains_failure_and_disk_stop(self):
        c = base_config()
        for key, probe in [('failure', dict(returncode=None, error='timeout')),
                           ('disk', dict(returncode=0, stdout=json.dumps(dict(boot_id='boot', free_bytes=7*s.GIB)))),
                           ('boot', dict(returncode=0, stdout=json.dumps(dict(boot_id='changed', free_bytes=33*s.GIB))))]:
            d = self.root / key
            d.mkdir()
            results = [dict(returncode=0, stdout='host'), dict(returncode=0, stdout='vm'), probe]
            with patch.object(s, 'live', return_value=[]), patch.object(s, 'containers', return_value=[]), patch.object(s, 'capture', side_effect=results):
                with self.assertRaises(RuntimeError):
                    s.observe(c, d, 1, 'boot')
            record = json.loads((d / 'observations.jsonl').read_text())
            self.assertIn('error', record)
            self.assertIn('recorded_utc', record)

    def test_claimed_pass_requires_complete_correctness_closure(self):
        c = base_config()
        producer, orchestration = closure(self.root, c)
        self.assertEqual(s.closed(c, 0)['outcome'], 'passed')
        self.assertFalse(s.closed(c, 0)['physical_output_checked'])
        for change in ('parent', 'rows', 'nan', 'oom', 'runtime', 'output', 'mode', 'dataset', 'validation', 'exit', 'cleanup'):
            p, o = copy.deepcopy(producer), copy.deepcopy(orchestration)
            if change == 'parent': p['correctness']['parent_tree_checked'] = False
            if change == 'rows': p['correctness']['rows'] = True
            if change == 'nan': p['correctness']['max_edge_slack'] = float('nan')
            if change == 'oom': p['cgroup_after']['memory.events'] = 'oom 1\noom_kill 1\n'
            if change == 'runtime': p['runtime_source_sha'] = 'wrong'
            if change == 'output': p['arguments']['output'] = '/another/cell'
            if change == 'mode': p['arguments']['mode'] = 'local'
            if change == 'dataset': p['arguments']['dataset'] += '-other'
            if change == 'validation': p['arguments']['traversal_validation'] = 'reference'
            if change == 'exit': o['inspect']['state']['ExitCode'] = 1
            if change == 'cleanup': o['remove']['returncode'] = 1
            dump(Path(c['host_output']) / 'diagnostics/receipt.json', p)
            dump(Path(c['host_output']) / 'cell/orchestration.json', o)
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                s.closed(c, 0)

    def test_zero_wrapper_exit_does_not_promote_producer_failure(self):
        c = base_config()
        p, _ = closure(self.root, c)
        p.update(outcome='nonconverged', correctness=None)
        dump(Path(c['host_output']) / 'diagnostics/receipt.json', p)
        dump(Path(c['host_output']) / 'result.json', dict(outcome='nonconverged'))
        self.assertEqual(s.closed(c, 0)['outcome'], 'not_passed')

    def test_abort_stops_only_fingerprinted_own_container(self):
        c = base_config()
        ours, foreign = item(c), item(c, ident='b'*64)
        foreign['Name'] = '/foreign'
        rows = [json.dumps(dict(ID=x['Id'][:12], Names=x['Name'], State='running')) for x in (ours, foreign)]
        class Ended:
            def poll(self): return 0
        with patch.object(s, 'containers', side_effect=[rows, []]), patch.object(s, 'inspect', side_effect=[ours, foreign]), patch.object(s, 'capture', return_value=dict(returncode=0, stdout='stopped')) as commands:
            self.assertTrue(s.abort(Ended(), c, self.root))
        self.assertEqual(commands.call_count, 1)
        self.assertEqual(commands.call_args.args[0][-1], ours['Id'])
        self.assertEqual(commands.call_args.args[0][-4:-1], ['stop', '--time', '30'])

    def test_launcher_exit_race_still_stops_own_container(self):
        c, i = base_config(), item(base_config())
        rows = [json.dumps(dict(ID=i['Id'][:12], Names=i['Name'], State='running'))]
        class Race:
            pid = 123
            def poll(self): return None
            def wait(self, timeout): return 0
        with patch.object(s.os, 'killpg', side_effect=ProcessLookupError), patch.object(s, 'containers', side_effect=[rows, []]), \
             patch.object(s, 'inspect', return_value=i), patch.object(s, 'capture', return_value=dict(returncode=0, stdout='stopped')) as commands:
            self.assertTrue(s.abort(Race(), c, self.root))
        self.assertEqual(commands.call_count, 1)

    def queue(self, outcomes, *, observe_error=False):
        cells = [dict(config=str(self.root / str(i)), config_sha256='pin') for i in range(3)]
        cells[2]['depends_on_success'] = 'run-1'
        configs = [dict(run_id='run-' + str(i), host_output=str(self.root / ('output-' + str(i))), limits=dict(outer_timeout_seconds=32400)) for i in range(3)]
        plan = self.root / 'plan.json'
        dump(plan, dict(run_id='queue', cells=cells, expected_boot_id='boot'))
        class Ended:
            pid, returncode = 123, 0
            def poll(self): return 0
        def cfg(cell): return configs[int(Path(cell['config']).name)]
        obs = {'side_effect': RuntimeError('observer_failure')} if observe_error else {'return_value': {}}
        with patch.object(s, 'ROOT', self.root), patch.object(s.sys, 'argv', ['supervise', '--plan', str(plan)]), patch.object(s, 'config', side_effect=cfg), \
             patch.object(s, 'verify_inputs'), patch.object(s, 'containers', return_value=[]), patch.object(s, 'observe', **obs), patch.object(s, 'admission'), \
             patch.object(s.subprocess, 'Popen', return_value=Ended()) as launches, patch.object(s, 'live', return_value=[]), patch.object(s, 'closed', side_effect=outcomes):
            code = s.main()
        return code, launches.call_count, json.loads((self.root / 'queue-supervisor/receipt.json').read_text())

    def test_independent_failure_does_not_skip_next_but_dependency_does(self):
        code, count, r = self.queue([dict(outcome='not_passed'), dict(outcome='not_passed')])
        self.assertEqual(code, 1)
        self.assertEqual(count, 2)
        self.assertEqual([c['outcome'] for c in r['cells']], ['not_passed', 'not_passed', 'skipped_dependency'])

    def test_three_successes_are_serial_and_closed(self):
        code, count, r = self.queue([dict(outcome='passed')] * 3)
        self.assertEqual((code, count, r['outcome']), (0, 3, 'passed'))
        self.assertFalse(r['lock_retained'])

    def test_observer_failure_stops_before_launch_and_keeps_receipt(self):
        code, count, r = self.queue([], observe_error=True)
        self.assertEqual((code, count), (1, 0))
        self.assertIn('observer_failure', r['error'])


if __name__ == '__main__':
    unittest.main()
