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
    def test_copy_mutation_cannot_replace_supplied_receipt_pin(self):
        for when in ('before_copy', 'after_copy'):
            with self.subTest(when=when), tempfile.TemporaryDirectory(prefix='physical-copy-control-') as directory:
                root = Path(directory); source = root / 'receipt.json'; source.write_text('{"original":true}')
                expected = p.sha(source); bundle = root / 'bundle'; bundle.mkdir()
                original_copy = shutil.copyfile
                def mutate(src, dst):
                    if when == 'before_copy': source.write_text('{"changed":true}')
                    result = original_copy(src, dst)
                    if when == 'after_copy': source.write_text('{"changed":true}')
                    return result
                with patch.object(p.shutil, 'copyfile', side_effect=mutate):
                    with self.assertRaises(ValueError):
                        p.copy_bundle({'producer-receipt.json': source}, {'producer-receipt.json': expected}, bundle)
                self.assertFalse((bundle / 'request.json').exists())

    def test_container_selected_volume_space_is_recorded(self):
        entry = load('container_check')
        from collections import namedtuple
        usage = namedtuple('Usage', 'total used free')(2000000000, 1000000001, 999999999)
        report = {}
        with patch.object(entry.shutil, 'disk_usage', return_value=usage) as mocked:
            with self.assertRaisesRegex(ValueError, 'insufficient free space'):
                entry.admit_target_space(report, 1073741824)
        mocked.assert_called_once_with('/targets')
        self.assertEqual(report['target_volume_disk_before']['path'], '/targets')
        self.assertEqual(report['target_volume_disk_before']['free_bytes'], 999999999)

    def test_stable_copy_preserves_supplied_pin(self):
        with tempfile.TemporaryDirectory(prefix='physical-copy-control-') as directory:
            root = Path(directory); source = root / 'receipt.json'; source.write_text('{"original":true}')
            expected = p.sha(source); bundle = root / 'bundle'; bundle.mkdir()
            pins = p.copy_bundle({'producer-receipt.json': source}, {'producer-receipt.json': expected}, bundle)
            self.assertEqual(pins['producer-receipt.json']['sha256'], expected)
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
                limits=dict(cpus=1, memory_bytes=2147483648, memory_swap_bytes=2147483648, pids=64), timeout_seconds=1800,
                disk_admission=dict(host_evidence_minimum_free_bytes=268435456, target_volume_minimum_free_bytes=1073741824))
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
                                     ExitCode=137 if scenario == 'oom' else 0, OOMKilled=scenario in ('oom', 'oom_exit_zero'))
                        if scenario == 'created_with_pass': state['Status'] = 'created'
                        response = json.dumps(dict(Id=cid, State=state, Labels=current_labels,
                            Memory=2147483648, MemorySwap=2147483648, NanoCpus=1000000000, ReadonlyRootfs=True, NetworkMode='none',
                            Mounts=[dict(Destination=d, RW=d == '/evidence') for d in ('/targets', '/work', '/evidence')]))
                        if scenario == 'bad_inspect': response = '{invalid'
                elif name == 'start': running = True
                elif name == 'wait':
                    if scenario == 'timeout' and running: raise subprocess.TimeoutExpired(args, timeout)
                    running = False; response = '137\n' if scenario == 'oom' else '0\n'
                    if scenario in ('physical_pass', 'oom_exit_zero', 'created_with_pass'): (output / 'physical-output.json').write_text('{"status":"physical_values_pass"}')
                    if scenario == 'bad_physical': (output / 'physical-output.json').write_text('[]')
                elif name == 'kill': running = False
                elif name == 'logs': response = 'retained checker stdout\n'; stderr.write(b'retained checker stderr\n')
                elif name == 'rm': self.assertTrue((output / 'exited-container.json').exists())
                else: self.fail('unexpected mock command: ' + str(command))
                stdout.write(response.encode()); stdout.flush()
                return subprocess.CompletedProcess(args, rc)

            real_free_space = s.free_space
            def selected_space(path, minimum):
                result = real_free_space(path, minimum)
                if scenario == 'low_disk': result['free_bytes'] = minimum - 1
                return result
            with patch.object(s, 'free_space', side_effect=selected_space), patch.object(s, 'validate', return_value=request), patch.object(s.subprocess, 'run', side_effect=fake_run):
                rc = s.run_supervisor(request_path, 'a' * 64, output)
            receipt = json.loads((output / 'outer-receipt.json').read_text())
            # Only metadata is returned; fixture tree is removed, never published.
            return rc, receipt, commands

    def test_child_admission_exception_retains_outer_receipt_without_docker(self):
        with tempfile.TemporaryDirectory(prefix='physical-admission-control-') as directory:
            root = Path(directory); output = root / 'output'; output.mkdir()
            with patch.object(s, 'validate', side_effect=ValueError('controlled changed source')), patch.object(s.subprocess, 'run') as run:
                rc = s.run_supervisor(root / 'request.json', 'a' * 64, output)
            self.assertEqual(rc, 2); run.assert_not_called()
            report = json.loads((output / 'outer-receipt.json').read_text())
            self.assertTrue(any('controlled changed source' in e for e in report['errors']))
            self.assertFalse(report['bundle_unchanged'])

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

    def test_oom_or_unexited_state_with_zero_exit_and_inner_pass_rejected(self):
        for scenario in ('oom_exit_zero', 'created_with_pass'):
            with self.subTest(scenario=scenario):
                rc, r, _ = self.exercise(scenario)
                self.assertEqual(r['container_state']['ExitCode'], 0)
                self.assertEqual(r['physical_status'], 'physical_values_pass')
                self.assertEqual(rc, 2)

    def test_low_selected_host_space_prevents_all_docker_calls(self):
        rc, r, calls = self.exercise('low_disk')
        self.assertEqual(rc, 2); self.assertEqual(calls, [])
        self.assertEqual(r['host_evidence_disk_before']['free_bytes'], 268435455)
        self.assertTrue(any('insufficient free space' in e for e in r['errors']))

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
