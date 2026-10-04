"""Offline only: all Popen/SSH operations are mocked; no Docker or remote calls."""
import ast
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import types
import unittest
from unittest.mock import patch


def load(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


s=load('supervisor','/private/tmp/host_pair_supervisor.py')
c=load('control','/private/tmp/host_pair_control.py')


class Controls(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.patcher=patch.multiple(s,ROOT=self.root,PLAN=self.root/'plan.json',
            RUNNER=self.root/'runner.py',STUDY=self.root/'study',LAUNCH=self.root/'launch')
        self.patcher.start(); self.addCleanup(self.patcher.stop)

    def write(self,path,value):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value))

    def closure(self):
        path=self.root/'physical03'/'outer-receipt.json'
        value=dict(request_sha256='a'*64,finished_utc='fixture-clock',bundle_unchanged=True,
            cleanup='removed_after_state_capture',physical_status='physical_values_pass',errors=[],
            container_state=dict(Running=False,Status='exited',ExitCode=0,OOMKilled=False))
        self.write(path,value)
        return path,value

    def test_frozen_command_only_interpreter_changed(self):
        handoff=json.loads((c.FROZEN/'HANDOFF.json').read_text())
        with patch.multiple(s,PLAN=Path(handoff['remote_plan']),RUNNER=Path(handoff['remote_runner'])):
            actual=s.command()
        self.assertEqual(actual,[str(s.PYTHON),*handoff['future_execution_command'][1:]])
        self.assertEqual(c.PLAN_SHA,handoff['plan_sha256'])
        self.assertEqual(c.RUNNER_SHA,handoff['runner_sha256'])

    def test_closure_preserves_failure_but_rejects_live_or_wrong_pins(self):
        path,value=self.closure()
        for status in ('physical_values_pass','physical_values_fail','integrity_error','inconclusive'):
            value['physical_status']=status; self.write(path,value)
            self.assertEqual(s.physical_closure(path,s.sha(path),'a'*64)['physical_status'],status)
        for key,new in [('cleanup','incomplete'),('bundle_unchanged',False),('request_sha256','b'*64)]:
            changed=dict(value);changed[key]=new;self.write(path,changed)
            with self.assertRaises(RuntimeError):s.physical_closure(path,s.sha(path),'a'*64)
        value['container_state']['Running']=True; self.write(path,value)
        with self.assertRaises(RuntimeError):s.physical_closure(path,s.sha(path),'a'*64)
        with self.assertRaises(RuntimeError):s.physical_closure(path,'0'*64,'a'*64)

    def test_support_hash_mutation_rejected(self):
        plan=dict(namespace=s.NS,remote_root=str(self.root),scripts={'support.py':'pending'},
                  harness_files_sha256={'unit.py':'pending'},runs=[])
        (self.root/'support.py').write_text('support')
        (self.root/'harness').mkdir();(self.root/'harness'/'unit.py').write_text('unit')
        plan['scripts']['support.py']=s.sha(self.root/'support.py')
        plan['harness_files_sha256']['unit.py']=s.sha(self.root/'harness'/'unit.py')
        for order,phase,host in [(1,'warmup','A'),(2,'warmup','B'),(3,'measurement','A'),
                                  (4,'measurement','B'),(5,'measurement','B'),(6,'measurement','A')]:
            path=self.root/f'{order}.json';self.write(path,dict(order=order))
            plan['runs'].append(dict(order=order,phase=phase,host=host,configuration=path.name,
                                    configuration_sha256=s.sha(path)))
        self.write(s.PLAN,plan);s.RUNNER.write_text('not executable')
        with patch.multiple(s,PLAN_SHA=s.sha(s.PLAN),RUNNER_SHA=s.sha(s.RUNNER)):
            self.assertEqual(len(s.inputs()[1]),10)
            (self.root/'harness'/'unit.py').write_text('changed')
            with self.assertRaises(RuntimeError):s.inputs()

    def test_launch_detached_redirected_once(self):
        path,value=self.closure()
        args=types.SimpleNamespace(closure=path,closure_sha256=s.sha(path),request_sha256='a'*64,
                                   script_sha256=s.sha(Path(s.__file__)))
        with patch.object(s,'interpreter',return_value={'fixture':True}), \
             patch.object(s,'inputs',return_value=({},{})), \
             patch.object(s.subprocess,'Popen',return_value=types.SimpleNamespace(pid=12345)) as popen, \
             patch('sys.stdout',new_callable=io.StringIO):
            s.launch(args)
            self.assertTrue(popen.call_args.kwargs['start_new_session'])
            self.assertTrue(popen.call_args.kwargs['close_fds'])
            self.assertEqual(popen.call_args.kwargs['stdin'],s.subprocess.DEVNULL)
            self.assertEqual(popen.call_args.args[0][0],str(s.PYTHON))
            self.assertTrue((s.LAUNCH/'launch.json').is_file())
            with self.assertRaises(RuntimeError):s.launch(args)
            self.assertEqual(popen.call_count,1)

    def test_six_requires_exit_and_no_lock_preserves_failed_outcome(self):
        self.write(s.STUDY/'sequence.json',dict(plan_sha256=s.PLAN_SHA,
            rows=[dict(order=i,outcome='mismatch' if i==4 else 'passed') for i in range(1,7)]))
        self.assertFalse(s.selected()['full_six_records_after_runner_exit'])
        self.write(s.LAUNCH/'runner-exit.json',dict(reaped=True,returncode=0))
        self.write(s.LAUNCH/'supervisor-exit.json',dict(outcome='runner_exited',pinned_inputs_unchanged=True,errors=[]))
        result=s.selected();self.assertTrue(result['full_six_records_after_runner_exit'])
        self.assertEqual(result['rows'][3]['outcome'],'mismatch')
        (s.STUDY/'active.lock').write_text('fixture')
        self.assertFalse(s.selected()['full_six_records_after_runner_exit'])

    def archive(self,path,bad=None):
        data=b'raw failed result retained\n'
        name='study/failure.log'
        manifest=dict(plan_sha256=c.PLAN_SHA,files={name:dict(bytes=len(data),
             sha256=hashlib.sha256(data).hexdigest())})
        if bad=='hash': manifest['files'][name]['sha256']='0'*64
        with tarfile.open(path,'w') as tar:
            for n,body in [('collection-manifest.json',json.dumps(manifest).encode()),(name,data)]:
                info=tarfile.TarInfo(n);info.size=len(body);tar.addfile(info,io.BytesIO(body))
            if bad in ('traversal','duplicate'):
                info=tarfile.TarInfo('../escape' if bad=='traversal' else name)
                info.size=len(data);tar.addfile(info,io.BytesIO(data))

    def test_collection_exact_and_rejects_corruption_without_output(self):
        for mode in (None,'hash','traversal','duplicate'):
            path=self.root/(str(mode)+'.tar'); self.archive(path,mode)
            output=self.root/(str(mode)+'-output')
            if mode:
                with self.assertRaises(RuntimeError):c.unpack(path,output)
                self.assertFalse(output.exists())
            else:
                c.unpack(path,output)
                self.assertEqual((output/'study/failure.log').read_bytes(),b'raw failed result retained\n')
                with self.assertRaises(RuntimeError):c.unpack(path,output)

    def test_local_default_dry_and_timeout_receipt_no_retry(self):
        path=Path(s.__file__)
        args=['control','poll','--supervisor',str(path),'--supervisor-sha256',s.sha(path),
              '--script-sha256',s.sha(Path(c.__file__))]
        with patch.object(c.sys,'argv',args),patch.object(c.subprocess,'run') as run, \
             patch('sys.stdout',new_callable=io.StringIO):
            self.assertEqual(c.main(),0);run.assert_not_called()
        with patch.object(c,'OUTPUT',self.root/'outer'),patch.object(c.sys,'argv',args+['--execute']), \
             patch.object(c.subprocess,'run',side_effect=c.subprocess.TimeoutExpired(['fixture'],90)) as run, \
             patch('sys.stdout',new_callable=io.StringIO):
            self.assertEqual(c.main(),2);self.assertEqual(run.call_count,1)
        receipts=list((self.root/'outer').glob('*.receipt.json'))
        self.assertEqual(len(receipts),1)
        value=json.loads(receipts[0].read_text())
        self.assertIn('TimeoutExpired',value['error']);self.assertIn('Unknown',value['remote_state'])


if __name__=='__main__':unittest.main(verbosity=2)
