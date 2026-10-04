"""Synthetic offline collection controls; no fixture represents an executed pair."""
import copy
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

import audit_pair as audit


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + '\n')


def replace(value, replacements):
    if isinstance(value, str):
        for before, after in replacements:
            value = value.replace(before, after)
        return value
    if isinstance(value, dict):
        return {k: replace(v, replacements) for k, v in value.items()}
    if isinstance(value, list):
        return [replace(v, replacements) for v in value]
    return value


def archive(cell):
    path = cell / 'diagnostics.tar'
    with tarfile.open(path, 'w') as bundle:
        for file in sorted((cell / 'diagnostics').iterdir()):
            bundle.add(file, arcname=file.name, recursive=False)
    receipt = json.loads((cell / 'diagnostics/receipt.json').read_text())
    save(cell / 'collection.json', dict(returncode=0, stderr='',
         full_artifact_path=receipt['arguments']['output'], **audit.support().file_info(path)))


def fixture(root):
    h = audit.support(); plan, configs = audit.prepared(h)
    seed = audit.EXP / 'worker-smoke-instrumented289-cpu16-23'
    old = json.loads((seed / 'configuration.json').read_text())
    rows = []
    for entry, config in zip(plan['runs'], configs):
        cell = root / 'cells' / config['run_id']
        replacements = [(old['run_id'], config['run_id']),
                        (old['container_sail_binary'], config['container_sail_binary']),
                        (old['runtime_source_sha'], config['runtime_source_sha'])]
        for name in ['plan.json', 'cell/orchestration.json', 'diagnostics/receipt.json',
                     'diagnostics/server-settings.json', 'result.json']:
            save(cell / name, replace(json.loads((seed / name).read_text()), replacements))
        save(cell / 'configuration.json', config)
        save(cell / 'host-before.json', dict(synthetic_fixture=True))
        for name in ['server.log', 'memory-samples.jsonl']:
            (cell / 'diagnostics' / name).write_text('synthetic offline control\n')
        receipt = json.loads((cell / 'diagnostics/receipt.json').read_text())
        receipt.update(runtime_source_sha=config['runtime_source_sha'], binary_sha256=entry['binary_sha256'])
        receipt['arguments'] = dict(plan['expected_arguments'], sail_binary=config['container_sail_binary'],
            runtime_source_sha=config['runtime_source_sha'], output=entry['cell_output'])
        receipt['end_to_end_seconds'] = 20 if entry['host'] == 'A' else 10
        save(cell / 'diagnostics/receipt.json', receipt)
        archive(cell)
        record = json.loads((cell / 'cell/orchestration.json').read_text())
        prefix = root / f"{entry['order']:02d}"
        observed = dict(binary_sha256=entry['binary_sha256'], harness_head=config['harness_source_sha'],
            harness_status='', native_sha256=plan['expected_native_package_identity']['files_sha256']['_native.cpython-312-x86_64-linux-gnu.so'],
            datasets={'weighted16k': {'sha256': plan['dataset_manifest_sha256']}},
            boot_id='synthetic-shared-boot', free_bytes=20 << 30)
        save(prefix.with_suffix('.preflight.json'), dict(outcome='passed', config_sha256=entry['configuration_sha256'], observed=observed))
        save(prefix.with_suffix('.inventory-before.json'), dict(returncode=0, names=[]))
        save(prefix.with_suffix('.inventory.json'), [dict(returncode=0, names=['sail-' + config['run_id'] + '-1'])])
        peaks = receipt['memory']['phase_peaks']['execute']
        row = dict(order=entry['order'], phase=entry['phase'], host=entry['host'], configuration=entry['configuration'],
            started_utc='2026-09-30T20:00:00+00:00', finished_utc='2026-09-30T20:01:00+00:00',
            outcome='passed', receipt_outcome='passed', orchestration=record, runner_wall_timeout=False,
            runner_returncode=0, boot_id='synthetic-shared-boot', seconds=receipt['end_to_end_seconds'],
            execution_pss_bytes=peaks['pss_bytes'], execution_rss_bytes=peaks['rss_bytes'],
            guest_steal_fraction=receipt['guest_steal_fraction'], correctness=receipt['correctness'],
            algorithm_iterations=receipt['algorithm_iterations'], comparison_eligible=True,
            concurrency_sampling=dict(interval_seconds=2, samples_during_cell=1, observed_sibling_containers=[],
                inventory_errors=0, scope='sampled observation, not a host-wide lock'))
        save(prefix.with_suffix('.result.json'), row); rows.append(row)
    save(root / 'sequence.json', dict(plan_sha256=audit.PLAN_SHA, rows=rows))
    return plan, configs


class CollectionControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='pair-collection-offline-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.plan, self.configs = fixture(self.root)
        self.cell = self.root / 'cells' / self.configs[0]['run_id']

    def mutate(self, relative, callback):
        path = self.root / relative
        value = json.loads(path.read_text()); callback(value); save(path, value)

    def sync_row(self, index=0):
        row = json.loads((self.root / f'{index+1:02d}.result.json').read_text())
        self.mutate('sequence.json', lambda s: s['rows'].__setitem__(index, row))

    def test_complete_synthetic_real_namespace_sequence_has_descriptive_ratio(self):
        report = audit.audit_collection(self.root)
        self.assertEqual(report['integrity_status'], 'integrity_verified', report)
        self.assertTrue(report['ratio_eligible'], report)
        self.assertEqual(report['shared_host_ratios']['geometric_mean_A_over_B'], 2)
        self.assertEqual([r['run_id'] for r in report['cells']], [c['run_id'] for c in self.configs])

    def test_wrong_namespace_or_runtime_cannot_be_eligible(self):
        for key, value in [('runtime_source_sha', '0' * 40), ('output', '/wrong/namespace')]:
            with self.subTest(key=key):
                path = self.cell / 'diagnostics/receipt.json'
                original = path.read_text(); receipt = json.loads(original)
                receipt['arguments'][key] = value; save(path, receipt); archive(self.cell)
                report = audit.audit_collection(self.root)
                self.assertEqual(report['integrity_status'], 'integrity_error')
                self.assertFalse(report['ratio_eligible'])
                path.write_text(original); archive(self.cell)

    def test_missing_archive_member_or_closure_is_inconclusive(self):
        missing = self.cell / 'diagnostics/server.log'; original = missing.read_text()
        missing.unlink()
        report = audit.audit_collection(self.root)
        self.assertEqual(report['integrity_status'], 'inconclusive', report)
        self.assertFalse(report['ratio_eligible'])
        missing.write_text(original)
        path = self.cell / 'cell/orchestration.json'
        record = json.loads(path.read_text()); record.pop('finished_utc'); save(path, record)
        self.mutate('01.result.json', lambda r: r.__setitem__('orchestration', record)); self.sync_row()
        report = audit.audit_collection(self.root)
        self.assertEqual(report['integrity_status'], 'inconclusive', report)
        self.assertFalse(report['ratio_eligible'])

    def test_completed_correctness_failure_retains_outcome_not_integrity_error(self):
        path = self.cell / 'diagnostics/receipt.json'; receipt = json.loads(path.read_text())
        receipt.update(outcome='mismatch', correctness=None); receipt.pop('cgroup_execution_after')
        save(path, receipt); archive(self.cell)
        self.mutate(str((self.cell / 'result.json').relative_to(self.root)),
                    lambda r: r.update(outcome='mismatch', receipt_outcome='mismatch'))
        self.mutate('01.result.json', lambda r: r.update(outcome='mismatch', receipt_outcome='mismatch', correctness=None, comparison_eligible=False))
        self.sync_row()
        report = audit.audit_collection(self.root)
        self.assertEqual(report['integrity_status'], 'integrity_verified', report)
        self.assertEqual(report['cells'][0]['recorded_outcomes']['runner_outcome'], 'mismatch')
        self.assertFalse(report['ratio_eligible'])

    def test_false_pass_without_parent_check_is_integrity_error(self):
        path = self.cell / 'diagnostics/receipt.json'; receipt = json.loads(path.read_text())
        receipt['correctness']['parent_tree_checked'] = False; save(path, receipt); archive(self.cell)
        self.mutate('01.result.json', lambda r: r.__setitem__('correctness', receipt['correctness'])); self.sync_row()
        report = audit.audit_collection(self.root)
        self.assertEqual(report['integrity_status'], 'integrity_error')
        self.assertFalse(report['ratio_eligible'])

    def test_claimed_pass_missing_execution_end_snapshot_is_inconclusive(self):
        path = self.cell / 'diagnostics/receipt.json'; receipt = json.loads(path.read_text())
        receipt.pop('cgroup_execution_after'); save(path, receipt); archive(self.cell)
        report = audit.audit_collection(self.root)
        self.assertEqual(report['integrity_status'], 'inconclusive', report)
        self.assertFalse(report['ratio_eligible'])

    def test_wrong_plan_and_reordered_rows_cannot_pass(self):
        self.mutate('sequence.json', lambda s: s.update(plan_sha256='0' * 64, rows=list(reversed(s['rows']))))
        report = audit.audit_collection(self.root)
        self.assertEqual(report['integrity_status'], 'integrity_error')
        self.assertFalse(report['ratio_eligible'])

    def test_archive_corruption_and_missing_final_cell_remain_distinct(self):
        path = self.cell / 'diagnostics/server.log'; path.write_text('changed after archive\n')
        report = audit.audit_collection(self.root)
        self.assertEqual(report['integrity_status'], 'integrity_error')
        self.assertFalse(report['ratio_eligible'])
        archive(self.cell)
        (self.root / '06.result.json').unlink()
        self.mutate('sequence.json', lambda s: s['rows'].pop())
        report = audit.audit_collection(self.root)
        self.assertEqual(report['integrity_status'], 'inconclusive')
        self.assertFalse(report['ratio_eligible'])


if __name__ == '__main__':
    unittest.main()
