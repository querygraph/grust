"""Offline controls use retained real receipts; never start Docker or a workload."""
import copy
import json
import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch
from pathlib import Path
import unittest

from run_host_pair import digest, normalized, summary, verify_row, load_optional, sha, valid_seconds
import stage_host_pair

ROOT = Path(__file__).resolve().parent
EXP = ROOT.parent


class PairControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = json.loads(next(ROOT.glob('*-plan.json')).read_text())
        cls.receipt = json.loads((EXP / 'worker-smoke-instrumented289-cpu16-23/diagnostics/receipt.json').read_text())
        cls.record = json.loads((EXP / 'worker-smoke-instrumented289-cpu16-23/cell/orchestration.json').read_text())
        cls.config = json.loads((EXP / 'worker-smoke-instrumented289-cpu16-23.json').read_text())
        cls.entry = dict(binary_sha256=cls.receipt['binary_sha256'], cell_output=cls.receipt['arguments']['output'])

    def test_retained_real_receipt_matches_and_mutations_rejected(self):
        self.assertEqual(verify_row(self.plan, self.entry, self.config, self.receipt, self.record), [])
        mutations = [(['binary_sha256'], '0' * 64), (['correctness', 'unique'], 1),
                     (['arguments', 'threads'], 8), (['dataset', 'counts', 'edges'], 1),
                     (['native_package_identity', 'root'], '/different'),
                     (['cgroup_execution_after', 'cpu.max'], 'max 100000')]
        for keys, value in mutations:
            changed = copy.deepcopy(self.receipt)
            node = changed
            for key in keys[:-1]:
                node = node[key]
            node[keys[-1]] = value
            with self.subTest(keys=keys):
                self.assertTrue(verify_row(self.plan, self.entry, self.config, changed, self.record))
        changed = copy.deepcopy(self.record)
        changed['inspect']['image'] = 'changed'
        self.assertIn('Docker image differs', verify_row(self.plan, self.entry, self.config, self.receipt, changed))

    def test_config_parity_only_permits_declared_differences(self):
        configs = [json.loads((ROOT / row['configuration']).read_text()) for row in self.plan['runs']]
        self.assertEqual({digest(normalized(c)) for c in configs}, {self.plan['common_configuration_sha256']})
        changed = copy.deepcopy(configs[-1])
        changed['defaults']['threads'] = 8
        self.assertNotEqual(digest(normalized(changed)), self.plan['common_configuration_sha256'])
        self.assertEqual([r['host'] for r in self.plan['runs']], ['A','B','A','B','B','A'])

    def test_ratios_exclude_invalid_missing_warmup_or_changed_boot(self):
        rows = [dict(order=r['order'], phase=r['phase'], comparison_eligible=True,
                     boot_id='same', seconds=20 if r['host'] == 'A' else 10)
                for r in self.plan['runs']]
        self.assertEqual(summary(self.plan, rows)['shared_host_ratios']['geometric_mean_A_over_B'], 2)
        for index in range(6):
            invalid = copy.deepcopy(rows)
            invalid[index]['comparison_eligible'] = False
            self.assertIsNone(summary(self.plan, invalid)['shared_host_ratios'])
        self.assertIsNone(summary(self.plan, rows[1:])['shared_host_ratios'])
        rows[-1]['boot_id'] = 'new'
        self.assertIsNone(summary(self.plan, rows)['shared_host_ratios'])

    def test_staging_ssh_timeout_retains_local_uncertainty_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory)
            source = next(ROOT.glob('*-plan.json'))
            names = [source.name, 'run_host_pair.py'] + [r['configuration'] for r in self.plan['runs']]
            for name in names:
                shutil.copyfile(ROOT / name, copied / name)
            argv = ['stage_host_pair.py', str(copied / source.name), '--stage',
                    '--expected-plan-sha256', sha(source)]
            with patch.object(sys, 'argv', argv), patch.object(stage_host_pair.subprocess, 'run',
                    side_effect=subprocess.TimeoutExpired(['ssh'], 120)), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(subprocess.TimeoutExpired):
                    stage_host_pair.main()
            receipts = list(copied.glob('staging-*.json'))
            self.assertEqual(len(receipts), 1)
            self.assertIn('TimeoutExpired', json.loads(receipts[0].read_text())['error'])
            self.assertIn('unknown', json.loads(receipts[0].read_text())['remote_state'])

    def test_boolean_or_nonfinite_time_is_not_a_measurement(self):
        for value in (True, False, None, 0, -1, float('inf'), float('nan'), '1'):
            with self.subTest(value=value):
                self.assertFalse(valid_seconds(value))
        self.assertTrue(valid_seconds(1))
        self.assertTrue(valid_seconds(0.5))

    def test_nonobject_receipt_rejected_before_field_access(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'receipt.json'
            path.write_text('[]')
            with self.assertRaisesRegex(ValueError, 'expected JSON object'):
                load_optional(path)


if __name__ == '__main__':
    unittest.main()
