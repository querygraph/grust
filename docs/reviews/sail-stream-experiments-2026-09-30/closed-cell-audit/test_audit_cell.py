"""Pure local corruption controls; existing evidence is never modified."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('audit_cell', HERE/'audit_cell.py')
audit_cell = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_cell)
ROOT = HERE.parent
PROFILES = audit_cell.read_json(HERE/'profiles.json')['cases']
SMOKE = ROOT/'worker-smoke-compact561-cpu16-23'


class ClosedCell(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='closed-cell-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.cell = Path(self.temp.name)/'cell'
        shutil.copytree(SMOKE, self.cell)

    def mutate(self, name, operation):
        path = self.cell/name
        value = audit_cell.read_json(path)
        operation(value)
        path.write_text(json.dumps(value, indent=2)+'\n')
        if name.startswith('diagnostics/'):
            self.repack()

    def repack(self, extra=None):
        archive = self.cell/'diagnostics.tar'
        with tarfile.open(archive, 'w') as stream:
            for path in sorted((self.cell/'diagnostics').iterdir()):
                stream.add(path, arcname=path.name, recursive=False)
            if extra is not None:
                member = tarfile.TarInfo(extra); member.size = 1
                stream.addfile(member, io.BytesIO(b'x'))
        value = audit_cell.read_json(self.cell/'collection.json')
        value.update(audit_cell.file_info(archive))
        (self.cell/'collection.json').write_text(json.dumps(value)+'\n')

    def run_audit(self):
        return audit_cell.audit(self.cell, PROFILES['compact561-smoke'])

    def test_passing_smoke_integrity_without_independent_oracle(self):
        result = self.run_audit()
        self.assertEqual(result['integrity_status'], 'integrity_verified', result['errors'])
        self.assertEqual(result['recorded_outcomes']['receipt_outcome'], 'passed')
        self.assertEqual(result['correctness_verification'], 'not_performed')

    def test_oom_receipt_and_redaction_are_preserved(self):
        result = audit_cell.audit(ROOT/'logging01', PROFILES['logging01'])
        self.assertEqual(result['integrity_status'], 'integrity_verified', result['errors'])
        self.assertEqual(result['recorded_outcomes']['runner_outcome'], 'oom')
        self.assertEqual(result['recorded_outcomes']['receipt_outcome'], 'error')
        self.assertIs(result['recorded_outcomes']['docker_state']['OOMKilled'], True)
        known = result['known_transformations']
        self.assertNotEqual(known['published_host_before_sha256'], known['host_before_redaction']['original_sha256'])

    def test_missing_receipt_is_inconclusive(self):
        (self.cell/'diagnostics/receipt.json').unlink()
        result = self.run_audit()
        self.assertEqual(result['integrity_status'], 'inconclusive', result)
        self.assertTrue(any('receipt.json' in item for item in result['inconclusive_reasons']))

    def test_missing_collection_is_inconclusive(self):
        (self.cell/'collection.json').unlink()
        self.assertEqual(self.run_audit()['integrity_status'], 'inconclusive')

    def test_missing_result_is_inconclusive(self):
        (self.cell/'result.json').unlink()
        self.assertEqual(self.run_audit()['integrity_status'], 'inconclusive')

    def test_malformed_receipt_is_integrity_error(self):
        (self.cell/'diagnostics/receipt.json').write_text('[]\n')
        self.repack()
        self.assertEqual(self.run_audit()['integrity_status'], 'integrity_error')

    def test_archive_corruption_is_retained(self):
        with (self.cell/'diagnostics.tar').open('ab') as stream:
            stream.write(b'corruption')
        self.assertIn('archive hash differs from collection', self.run_audit()['errors'])

    def test_unsafe_archive_member_is_rejected_without_extraction(self):
        self.repack('../outside')
        result = self.run_audit()
        self.assertTrue(any('unsafe/nonflat' in item for item in result['errors']))
        self.assertFalse((self.cell.parent/'outside').exists())

    def test_resources_remain_checked_on_failure(self):
        self.mutate('diagnostics/receipt.json', lambda x: x['cgroup_after'].update({'memory.max':'1'}))
        result = self.run_audit()
        self.assertIn('cgroup_after: memory limits differ', result['errors'])

    def test_wrong_dataset_manifest_is_rejected(self):
        self.mutate('diagnostics/receipt.json', lambda x: x['dataset']['counts'].update({'edges':1}))
        self.assertIn('embedded dataset manifest differs from pinned baseline', self.run_audit()['errors'])

    def test_boolean_numeric_argument_is_rejected(self):
        self.mutate('diagnostics/receipt.json', lambda x: x['arguments'].update({'threads':True}))
        self.assertIn('default argument differs: threads', self.run_audit()['errors'])

    def test_short_command_is_error_not_crash(self):
        self.mutate('plan.json', lambda x: x['command'].append('--threads'))
        result = self.run_audit()
        self.assertEqual(result['integrity_status'], 'integrity_error')
        self.assertTrue(any('StopIteration' in item for item in result['errors']))

    def test_malformed_orchestration_is_error_not_crash(self):
        self.mutate('cell/orchestration.json', lambda x: x.update({'inspect':[]}))
        self.assertEqual(self.run_audit()['integrity_status'], 'integrity_error')

    def test_running_container_is_inconclusive(self):
        self.mutate('cell/orchestration.json', lambda x: x['inspect']['state'].update({'Running':True}))
        self.assertEqual(self.run_audit()['integrity_status'], 'inconclusive')

    def test_correctness_is_not_silently_recomputed_or_required_for_integrity(self):
        self.mutate('diagnostics/receipt.json', lambda x: x.pop('correctness'))
        result = self.run_audit()
        self.assertEqual(result['integrity_status'], 'integrity_verified', result['errors'])
        self.assertEqual(result['correctness_verification'], 'not_performed')
        self.assertIsNone(result['recorded_outcomes']['correctness'])

    def test_pinned_config_change_is_rejected(self):
        profile = copy.deepcopy(PROFILES['compact561-smoke'])
        profile['evidence_pins'][0]['sha256'] = '0'*64
        result = audit_cell.audit(self.cell, profile)
        self.assertEqual(result['integrity_status'], 'integrity_error')


if __name__ == '__main__':
    unittest.main()
