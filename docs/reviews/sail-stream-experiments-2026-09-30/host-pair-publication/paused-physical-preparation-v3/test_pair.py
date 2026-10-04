"""Synthetic six-cell metadata and mocked serial lifecycle; no campaign/result reads."""
import copy
import importlib.util
import json
import stat
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


policy = load(ROOT / 'pair_policy.py', 'pair_policy_test')
runner = load(ROOT / 'run_pair.py', 'pair_runner_test')
preparer = load(ROOT / 'prepare_pair.py', 'pair_prepare_test')
supervisor = load(ROOT/'supervise.py', 'pair_supervisor_modes')
plan = json.loads((ROOT.parent / 'host-pair-16k/pair16k-20260930201356-plan.json').read_text())


def evidence():
    rows, exports = [], []
    for entry in plan['runs']:
        outcomes = dict(docker_state=dict(Running=False, Status='exited', ExitCode=0, OOMKilled=False), receipt_outcome='passed')
        closed = dict(integrity_status='integrity_verified', errors=[], inconclusive_reasons=[], helper_sha256=policy.CLOSED_SHA,
            recorded_outcomes=outcomes, files={'/diagnostics/receipt.json': {'sha256': str(entry['order']) * 64},
                                            'configuration.json': {'sha256': entry['configuration_sha256']}})
        rows.append(dict(order=entry['order'], host=entry['host'], phase=entry['phase'], integrity_status='integrity_verified',
            errors=[], inconclusive_reasons=[], recorded_outcomes=outcomes, sequence_row={'boot_id':'test-boot'}))
        exports.append(dict(order=entry['order'], cell_output=entry['cell_output'], configuration_sha256=entry['configuration_sha256'],
            binary_sha256=entry['binary_sha256'], expected_vertices=16384, expected_source=0, receipt_sha256=str(entry['order']) * 64,
            closed_audit=closed, boot_id='test-boot'))
    return dict(pair_audit=dict(integrity_status='integrity_verified', errors=[], inconclusive_reasons=[], plan_sha256=policy.PLAN_SHA,
        verifier_sha256=policy.PAIR_SHA, helper_sha256=policy.CLOSED_SHA, cells=rows, ratio_eligible=True, shared_host_ratios={'retained':1.25}), cells=exports)


class Policy(unittest.TestCase):
    def test_all_six_closed_and_failed_original_not_promoted(self):
        e = evidence(); self.assertEqual(len(policy.all_six(e, plan)), 6)
        e['pair_audit']['ratio_eligible'] = False
        e['pair_audit']['cells'][0]['recorded_outcomes']['receipt_outcome'] = 'mismatch'
        self.assertEqual(len(policy.all_six(e, plan)), 6)
        self.assertFalse(e['pair_audit']['ratio_eligible'])

    def test_missing_live_wrong_namespace_and_runtime_rejected(self):
        for scenario in ('missing','live','namespace','config','runtime','domain','order'):
            with self.subTest(scenario=scenario):
                e = evidence()
                if scenario == 'missing': e['cells'].pop()
                if scenario == 'live': e['cells'][2]['closed_audit']['recorded_outcomes']['docker_state']['Running'] = True
                if scenario == 'namespace': e['cells'][1]['cell_output'] = e['cells'][0]['cell_output']
                if scenario == 'config': e['cells'][1]['configuration_sha256'] = e['cells'][0]['configuration_sha256']
                if scenario == 'runtime': e['cells'][1]['binary_sha256'] = e['cells'][0]['binary_sha256']
                if scenario == 'domain': e['cells'][1]['expected_source'] = 1
                if scenario == 'order': e['cells'].reverse()
                with self.assertRaises(ValueError): policy.all_six(e, plan)

    def test_ratio_and_all_six_physical_outcomes_required(self):
        manifest = {'original_ratio_eligible': True}
        rows = [dict(cell_output=e['cell_output'], supervisor_returncode=0, physical_status='physical_values_pass',
            cleanup='removed_after_state_capture', physical_report={'sha256':'a'*64}, container_state=dict(OOMKilled=False, Running=False, Status='exited', ExitCode=0)) for e in plan['runs']]
        self.assertTrue(runner.qualifies(manifest, rows, True))
        for scenario in ('mismatch','missing','missing_report','oom','unclosed','changed','original_false'):
            with self.subTest(scenario=scenario):
                copy_rows, copy_manifest = copy.deepcopy(rows), dict(manifest)
                if scenario == 'mismatch': copy_rows[2]['physical_status'] = 'physical_values_fail'
                if scenario == 'missing': copy_rows.pop()
                if scenario == 'missing_report': copy_rows[2]['physical_report'] = None
                if scenario == 'oom': copy_rows[4]['container_state']['OOMKilled'] = True
                if scenario == 'unclosed': copy_rows[4]['container_state']['Running'] = True
                if scenario == 'original_false': copy_manifest['original_ratio_eligible'] = False
                self.assertFalse(runner.qualifies(copy_manifest, copy_rows, scenario != 'changed'))


class BundleIntegration(unittest.TestCase):
    def test_synthetic_closed_metadata_exports_all_six_runtime_bindings(self):
        original_load=preparer.load_module
        pair=original_load(ROOT.parent/'host-pair-collection-audit/audit_pair.py','actual_pinned_pair',preparer.PAIR_SHA)
        actual_h=pair.support(); actual_plan,configs=pair.prepared(actual_h)
        with tempfile.TemporaryDirectory(prefix='physical-pair-export-control-') as directory:
            root=Path(directory);collection=root/'collection';collection.mkdir();prepared=root/'prepared';e=evidence();closed_by_run={}
            for entry,config,row,item in zip(actual_plan['runs'],configs,e['pair_audit']['cells'],e['cells']):
                cell=collection/'cells'/config['run_id'];(cell/'diagnostics').mkdir(parents=True)
                receipt={key:config[key] for key in ('harness_source_sha','runtime_source_sha','native_source_sha')}
                receipt.update(outcome='passed',arguments=dict(actual_plan['expected_arguments'],output=entry['cell_output'],
                    sail_binary=config['container_sail_binary'],runtime_source_sha=config['runtime_source_sha']))
                path=cell/'diagnostics/receipt.json';path.write_text(json.dumps(receipt));digest=preparer.sha(path)
                closed=item['closed_audit'];closed['files']={str(path):actual_h.file_info(path),
                    str(ROOT.parent/'host-pair-16k'/entry['configuration']):actual_h.file_info(ROOT.parent/'host-pair-16k'/entry['configuration'])}
                item['receipt_sha256']=digest;closed_by_run[config['run_id']]=closed
            e['pair_audit']['evidence_files']={name:pin for closed in closed_by_run.values() for name,pin in closed['files'].items()}
            fake_h=types.SimpleNamespace(canonical=actual_h.canonical,read_json=actual_h.read_json,file_info=actual_h.file_info,
                audit=lambda cell,profile,exp:copy.deepcopy(closed_by_run[cell.name]))
            fake_pair=types.SimpleNamespace(EXP=pair.EXP,PLAN_NAME=pair.PLAN_NAME,PLAN_SHA=pair.PLAN_SHA,HELPER_SHA=pair.HELPER_SHA,
                support=lambda:fake_h,prepared=pair.prepared,audit_collection=lambda path:copy.deepcopy(e['pair_audit']))
            def load_override(path,name,digest=None):
                if path.name=='audit_pair.py':return fake_pair
                return original_load(path,name,digest)
            with patch.object(preparer,'load_module',side_effect=load_override):result=preparer.prepare(collection,prepared)
            self.assertEqual(result['outcome'],'PREPARED_ONLY',result)
            manifest_path=prepared/'pair-requests.json'
            manifest=runner.validate(manifest_path,preparer.sha(manifest_path),root/'future-output')
            self.assertEqual(len(manifest['cells']),6)
            for entry,item in zip(actual_plan['runs'],manifest['cells']):
                request=json.loads((prepared/item['request']).read_text())
                self.assertEqual(request['binary_sha256'],entry['binary_sha256'])
                self.assertEqual(request['cell_output'],entry['cell_output'])
                self.assertEqual(request['expected_vertices'],16384)
                self.assertEqual(request['execution_identity'],supervisor.IDENTITY)
                bundle=(prepared/item['request']).parent
                self.assertEqual(stat.S_IMODE(bundle.stat().st_mode),0o755)
                self.assertTrue(all(stat.S_IMODE(path.stat().st_mode)==0o644 for path in bundle.iterdir()))


class Serial(unittest.TestCase):
    def exercise(self, failure=None):
        with tempfile.TemporaryDirectory(prefix='physical-pair-serial-control-') as directory:
            root=Path(directory); output=root/'output'; output.mkdir(); calls=[]
            cells=[]
            for e in plan['runs']:
                path=root/f"bundles/{e['order']:02d}/request.json";path.parent.mkdir(parents=True);path.write_text('{}')
                cells.append(dict(order=e['order'],phase=e['phase'],host=e['host'],cell_output=e['cell_output'],request=str(path.relative_to(root)),request_sha256='x'))
            manifest=dict(cells=cells,original_ratio_eligible=True,original_shared_host_ratios={'original':1.25})
            def run_cell(path,digest,destination):
                self.assertEqual(stat.S_IMODE(destination.stat().st_mode),0o700)
                order=int(destination.name);calls.append(order)
                state=dict(Running=False,Status='exited',ExitCode=0,OOMKilled=False)
                status='physical_values_pass';cleanup='removed_after_state_capture';rc=0
                if order==2:
                    if failure=='mismatch':status='physical_values_fail';rc=2
                    if failure=='oom':state.update(OOMKilled=True,ExitCode=137);status='not_available';rc=2
                    if failure=='missing':status='not_available';rc=2
                    if failure=='cleanup':cleanup='incomplete';rc=2
                    if failure=='exception':raise OSError('controlled missing outer receipt')
                physical=None
                if status!='not_available':
                    (destination/'physical-output.json').write_text(json.dumps({'status':status}))
                    physical={'sha256':runner.sha(destination/'physical-output.json')}
                (destination/'outer-receipt.json').write_text(json.dumps(dict(physical_status=status,physical_report=physical,cleanup=cleanup,container_state=state)))
                return rc
            with patch.object(runner,'validate',return_value=manifest), patch.object(runner,'load_supervisor',return_value=types.SimpleNamespace(run_supervisor=run_cell,create_evidence_directory=supervisor.create_evidence_directory)):
                rc=runner.execute(root/'pair-requests.json','x',output)
            report=json.loads((output/'serial-receipt.json').read_text())
            return rc,report,calls

    def test_all_six_serial_success(self):
        rc,r,calls=self.exercise();self.assertEqual(rc,0);self.assertEqual(calls,[1,2,3,4,5,6]);self.assertTrue(r['supplemental_physical_qualification'])

    def test_mismatch_oom_missing_retained_and_do_not_qualify(self):
        for failure in ('mismatch','oom','missing'):
            with self.subTest(failure=failure):
                rc,r,calls=self.exercise(failure);self.assertEqual(rc,2);self.assertEqual(calls,[1,2,3,4,5,6])
                self.assertFalse(r['supplemental_physical_qualification']);self.assertEqual(r['original_shared_host_ratios'],{'original':1.25})

    def test_uncertain_cleanup_or_outer_failure_stops_remaining(self):
        for failure in ('cleanup','exception'):
            with self.subTest(failure=failure):
                rc,r,calls=self.exercise(failure);self.assertEqual(rc,2);self.assertEqual(calls,[1,2]);self.assertEqual(len(r['cells']),6)
                self.assertTrue(all(x['outcome']=='not_attempted_after_stop' for x in r['cells'][2:]));self.assertFalse(r['supplemental_physical_qualification'])


if __name__ == '__main__':
    suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(c) for c in (Policy,BundleIntegration,Serial)])
    # Reuse the reviewed v3 lifecycle and permission controls against the derivative supervisor.
    path=ROOT.parent/'physical-output-execution-preparation-v3/test_preparation.py'
    if preparer.sha(path) != 'dee000bf8dc04d8bad613fafa34c97a7162624141977b3d6d79a79325fc5529b': raise ValueError('frozen lifecycle controls differ')
    inherited=load(path,'inherited_lifecycle_controls');inherited.s=load(ROOT/'supervise.py','pair_supervisor_controls')
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(inherited.Supervisor))
    permissions_path=ROOT.parent/'physical-output-execution-preparation-v3/test_permissions.py'
    if preparer.sha(permissions_path) != '7152811bf9b14089ec02d5e6b63d18929bb80c0efe68dd99ae65d67e17fd434b': raise ValueError('frozen permission controls differ')
    permissions=load(permissions_path,'inherited_permission_controls')
    permissions.p=load(ROOT/'baseline-v3/prepare.py','reviewed_v3_copier')
    permissions.s=supervisor; permissions.entry=load(ROOT/'container_check.py','pair_entry_modes')
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(permissions.Permissions))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
