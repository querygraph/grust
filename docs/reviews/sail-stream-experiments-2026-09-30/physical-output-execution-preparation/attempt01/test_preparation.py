"""Tiny local policy/supervisor controls. Docker and result reads are mocked."""
import copy
import importlib.util
import json
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p, s = load('prepare'), load('supervise')


class Policy(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT.parent / 'logging03-compact.json').read_text())
        self.receipt = {key: self.config[key] for key in ('runtime_source_sha', 'native_source_sha', 'harness_source_sha')}
        self.receipt.update(outcome='passed', arguments=dict(output=p.CELL, engine='pecan', algorithm='sssp', variant='delta_star',
            expected_vertices=16777216, source=13507776, sail_binary=self.config['container_sail_binary']), result_files=[{'name': 'placeholder.parquet'}])
        self.closed = dict(integrity_status='integrity_verified', errors=[], inconclusive_reasons=[], helper_sha256=p.CLOSED,
            files={'/diagnostics/receipt.json': {'sha256': 'a' * 64}, 'config': {'sha256': p.CONFIG}},
            recorded_outcomes=dict(receipt_outcome='passed', docker_state=dict(Running=False, Status='exited')))

    def test_valid_closed_metadata(self):
        p.validate(self.config, self.receipt, self.closed, 'a' * 64)

    def test_live_or_mismatched_closed_inputs_rejected(self):
        for key in ('running', 'missing_inventory', 'wrong_cell', 'wrong_binary', 'wrong_domain', 'wrong_native', 'unverified'):
            with self.subTest(key=key):
                r, c = copy.deepcopy(self.receipt), copy.deepcopy(self.closed)
                if key == 'running': c['recorded_outcomes']['docker_state']['Running'] = True
                if key == 'missing_inventory': r['result_files'] = []
                if key == 'wrong_cell': r['arguments']['output'] = p.CELL + '-other'
                if key == 'wrong_binary': r['arguments']['sail_binary'] = '/targets/other'
                if key == 'wrong_domain': r['arguments']['source'] = 0
                if key == 'wrong_native': r['native_source_sha'] = 'f' * 40
                if key == 'unverified': c['integrity_status'] = 'inconclusive'
                with self.assertRaises(ValueError): p.validate(self.config, r, c, 'a' * 64)

    def test_preserves_failed_producer_with_completed_output(self):
        self.receipt['outcome'] = self.closed['recorded_outcomes']['receipt_outcome'] = 'mismatch'
        p.validate(self.config, self.receipt, self.closed, 'a' * 64)
        self.assertEqual(self.receipt['outcome'], 'mismatch')

    def test_command_has_caps_readonly_inputs_and_no_auto_remove(self):
        cmd = s.create_command({'container_name': 'test'}, Path('/bundle'), Path('/evidence-new'), 'a' * 64, 'nonce')
        for item in ('--read-only', '--network=none', '--memory=2147483648', '--memory-swap=2147483648', '--cpus=1', '--pids-limit=64'):
            self.assertIn(item, cmd)
        self.assertNotIn('--rm', cmd)
        self.assertIn('type=volume,source=sail-extension-targets,target=/targets,readonly,volume-nocopy', cmd)
        self.assertIn('type=bind,source=/bundle,target=/work,readonly', cmd)
        self.assertIn('type=bind,source=/evidence-new,target=/evidence', cmd)


class BundleGuards(unittest.TestCase):
    def test_frozen_files_and_output_overlap(self):
        with tempfile.TemporaryDirectory(prefix='physical-bundle-control-') as directory:
            root = Path(directory) / 'bundle'; root.mkdir()
            sources = {'configuration.json': ROOT.parent / 'logging03-compact.json',
                'audit_output.py': ROOT.parent / 'physical-output-audit/audit_output.py',
                'container_check.py': ROOT / 'container_check.py', 'supervise.py': ROOT / 'supervise.py'}
            for name, path in sources.items(): shutil.copyfile(path, root / name)
            for name in ('producer-receipt.json', 'closed-audit.json'): (root / name).write_text('{}')
            request = dict(files={f.name: dict(sha256=s.sha(f), bytes=f.stat().st_size) for f in root.iterdir()},
                container_name='physical-output-log03-' + '1' * 16,
                limits=dict(cpus=1, memory_bytes=2147483648, memory_swap_bytes=2147483648, pids=64), timeout_seconds=1800)
            path = root / 'request.json'; path.write_text(json.dumps(request)); digest = s.sha(path)
            s.validate(path, digest, root.parent / 'output')
            with self.assertRaises(ValueError): s.validate(path, digest, root / 'output')
            (root / 'producer-receipt.json').write_text('{"changed":true}')
            with self.assertRaises(ValueError): s.validate(path, digest, root.parent / 'output')


class Supervisor(unittest.TestCase):
    def exercise(self, scenario):
        with tempfile.TemporaryDirectory(prefix='physical-supervisor-control-') as directory:
            root = Path(directory); output = root / 'output'; output.mkdir()
            request_path = root / 'request.json'; request_path.write_text('{}')
            request = dict(container_name='physical-output-log03-' + '1' * 16, timeout_seconds=1)
            commands, labels = [], {}
            running = False
            created = False
            cid = '1' * 64

            def fake_run(args, stdout, stderr, timeout, check):
                nonlocal running, created
                command = args[3:]; commands.append(command)
                name = command[0]; response = ''; rc = 0
                if name == 'ps': response = 'busy\n' if scenario == 'busy' else ''
                elif name == 'image': response = s.IMAGE + '\n'
                elif name == 'volume': response = s.VOLUME + '\n'
                elif name == 'create':
                    created = True
                    for i, value in enumerate(command):
                        if value == '--label':
                            key, value = command[i + 1].split('=', 1); labels[key] = value
                    response = cid + '\n'
                    if scenario == 'lost_create': raise subprocess.TimeoutExpired(args, timeout)
                    if scenario == 'create_oserror': raise OSError('controlled launch failure')
                elif name == 'inspect':
                    if not created: rc = 1
                    else:
                        current_labels = dict(labels)
                        if scenario == 'foreign': current_labels['physical-check.execution'] = 'different'
                        state = dict(Running=running, Status='running' if running else 'exited',
                                     ExitCode=137 if scenario == 'oom' else 0, OOMKilled=scenario == 'oom')
                        response = json.dumps(dict(Id=cid, State=state, Labels=current_labels,
                            Memory=2147483648, MemorySwap=2147483648, NanoCpus=1000000000, ReadonlyRootfs=True, NetworkMode='none',
                            Mounts=[dict(Destination=d, RW=d == '/evidence') for d in ('/targets', '/work', '/evidence')]))
                        if scenario == 'bad_inspect': response = '{invalid'
                elif name == 'start': running = True
                elif name == 'wait':
                    if scenario == 'timeout' and running: raise subprocess.TimeoutExpired(args, timeout)
                    running = False; response = '137\n' if scenario == 'oom' else '0\n'
                    if scenario == 'physical_pass': (output / 'physical-output.json').write_text('{"status":"physical_values_pass"}')
                    if scenario == 'bad_physical': (output / 'physical-output.json').write_text('[]')
                elif name == 'kill': running = False
                elif name == 'logs': response = 'retained checker stdout\n'; stderr.write(b'retained checker stderr\n')
                elif name == 'rm': self.assertTrue((output / 'exited-container.json').exists())
                else: self.fail('unexpected mock command: ' + str(command))
                stdout.write(response.encode()); stdout.flush()
                return subprocess.CompletedProcess(args, rc)

            with patch.object(s, 'validate', return_value=request), patch.object(s.subprocess, 'run', side_effect=fake_run):
                rc = s.run_supervisor(request_path, 'a' * 64, output)
            receipt = json.loads((output / 'outer-receipt.json').read_text())
            # Only metadata is returned; fixture tree is removed, never published.
            return rc, receipt, commands

    def test_success_state_before_cleanup(self):
        rc, r, calls = self.exercise('success')
        self.assertEqual(rc, 2); self.assertEqual(r['container_state']['ExitCode'], 0)
        self.assertEqual(r['cleanup'], 'removed_after_state_capture')
        self.assertEqual(r['physical_status'], 'not_available')  # No fake physical pass is manufactured.

    def test_physical_pass_and_bad_report_separate(self):
        rc, r, _ = self.exercise('physical_pass')
        self.assertEqual(rc, 0); self.assertEqual(r['physical_status'], 'physical_values_pass')
        rc, r, _ = self.exercise('bad_physical')
        self.assertEqual(rc, 2); self.assertTrue(r['errors'])

    def test_busy_never_creates_or_kills(self):
        rc, r, calls = self.exercise('busy')
        self.assertEqual(rc, 2); self.assertTrue(r['errors'])
        self.assertEqual([x[0] for x in calls], ['ps'])

    def test_oom_retained_without_inner_report(self):
        rc, r, calls = self.exercise('oom')
        self.assertEqual(rc, 2); self.assertTrue(r['container_state']['OOMKilled'])
        self.assertEqual(r['container_state']['ExitCode'], 137)
        self.assertEqual(r['physical_status'], 'not_available')

    def test_timeout_kills_only_owned_checker_and_retains_failure(self):
        rc, r, calls = self.exercise('timeout')
        self.assertEqual(rc, 2); self.assertTrue(any('TimeoutExpired' in e for e in r['errors']))
        self.assertEqual([x for x in calls if x[0] == 'kill'], [['kill', '1' * 64]])
        self.assertEqual(r['cleanup'], 'removed_after_state_capture')

    def test_lost_create_response_recovers_owned_container(self):
        rc, r, calls = self.exercise('lost_create')
        self.assertEqual(rc, 2); self.assertEqual(r['container_id'], '1' * 64)
        self.assertEqual(r['cleanup'], 'removed_after_state_capture')

    def test_oserror_and_malformed_json_retained(self):
        for scenario in ('create_oserror', 'bad_inspect'):
            with self.subTest(scenario=scenario):
                rc, r, calls = self.exercise(scenario)
                self.assertEqual(rc, 2); self.assertTrue(r['errors'])
                if scenario == 'bad_inspect': self.assertFalse(any(x[0] in ('kill', 'rm') for x in calls))

    def test_same_request_different_execution_never_killed(self):
        rc, r, calls = self.exercise('foreign')
        self.assertEqual(rc, 2); self.assertIn('ownership differs', ' '.join(r['errors']))
        self.assertFalse(any(x[0] in ('kill', 'rm') for x in calls))


if __name__ == '__main__':
    unittest.main()
