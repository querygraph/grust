"""Local mocks only: no SSH, Colima, Docker or kernel command is executed."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SOURCE=Path('/Users/alexy/src/grust/docs/reviews/sail-stream-experiments-2026-09-30/collect_host_closure.py')
spec=importlib.util.spec_from_file_location('closure',SOURCE)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
BOOT='12345678-1234-1234-1234-123456789abc'
SECRET='PRIVATE_NON_OOM_AND_STDERR_SENTINEL'


def host(kernel_returncode=0,boot_after=BOOT):
    guest={'started_utc':'2026-09-30T21:00:00+00:00','finished_utc':'2026-09-30T21:00:01+00:00',
           'boot_id':BOOT,'boot_id_after':boot_after,'uptime':'12.34 56.78','returncode':kernel_returncode,
           'stdout':'[0.1] '+SECRET+'\n[1.2] oom-kill:constraint=CONSTRAINT_MEMCG,task=worker,pid=9\n[1.3] Killed process 9 (worker) total-vm:42kB\n',
           'stderr':SECRET}
    snaps={name:{'returncode':0,'stdout':name+'\n','stderr':SECRET} for name in m.HOST_SNAPSHOTS}
    snaps['guest']={'returncode':0,'stdout':json.dumps(guest),'stderr':SECRET}
    return {'started_utc':'2026-09-30T21:00:00+00:00','finished_utc':'2026-09-30T21:00:02+00:00','snapshots':snaps}


class Collector(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='closure-mock-',dir='/private/tmp')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'logging02.json').write_text('{"mock":true}\n')
        self.out=self.root/'receipt.json'

    def run_mock(self,result):
        with patch.object(m,'ROOT',self.root),patch.object(m,'PRIVATE',self.root/'private'),patch.object(m.subprocess,'run') as run:
            if isinstance(result,Exception):run.side_effect=result
            else:run.return_value=subprocess.CompletedProcess([],0,result,SECRET.encode())
            r=m.collect('logging02',self.out)
            if run.called:
                args,kwargs=run.call_args
                self.assertEqual(args[0],['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','morrobay','python3 -B -'])
                self.assertNotIn('shell',kwargs)
                self.assertIsInstance(kwargs['input'],bytes)
                self.assertEqual(kwargs['timeout'],55)
            self.assertEqual(json.loads(self.out.read_text()),r)
            self.assertNotIn(SECRET,self.out.read_text())
            self.assertEqual(r['private_retention_errors'],[])
            return r,Path(r['private_directory'])

    def test_success_preserves_exact_selected_lines_and_private_full_payload(self):
        raw=json.dumps(host()).encode();r,private=self.run_mock(raw)
        self.assertEqual(r['outcome'],'CAPTURED')
        self.assertEqual((private/'ssh.stdout').read_bytes(),raw)
        self.assertEqual((private/'ssh.stderr').read_bytes(),SECRET.encode())
        self.assertEqual([x['line_number'] for x in r['guest']['oom_lines']],[2,3])
        self.assertEqual(r['guest']['oom_lines'][0]['text'],'[1.2] oom-kill:constraint=CONSTRAINT_MEMCG,task=worker,pid=9')
        self.assertTrue(r['guest']['boot_identity_stable'])

    def test_local_oserror_still_has_failure_receipt(self):
        r,private=self.run_mock(OSError(SECRET))
        self.assertEqual(r['outcome'],'FAILED');self.assertEqual(r['error_type'],'OSError')
        self.assertEqual((private/'ssh.stdout').read_bytes(),b'')
        self.assertIn(SECRET,(private/'exception.txt').read_text())

    def test_local_timeout_preserves_non_utf8_partial_bytes(self):
        raw=b'partial\xff';r,private=self.run_mock(subprocess.TimeoutExpired('ssh',55,output=raw,stderr=SECRET.encode()))
        self.assertEqual(r['outcome'],'FAILED');self.assertEqual(r['error_type'],'TimeoutExpired')
        self.assertEqual((private/'ssh.stdout').read_bytes(),raw)
        self.assertIn('termination unproven',r['error'])

    def test_malformed_host_json_receipted(self):
        raw=b'{broken';r,private=self.run_mock(raw)
        self.assertEqual(r['outcome'],'FAILED');self.assertEqual(r['error_type'],'JSONDecodeError')
        self.assertEqual((private/'ssh.stdout').read_bytes(),raw)

    def test_malformed_guest_json_receipted(self):
        value=host();value['snapshots']['guest']['stdout']='[bad'
        raw=json.dumps(value).encode();r,private=self.run_mock(raw)
        self.assertEqual(r['outcome'],'FAILED');self.assertEqual((private/'ssh.stdout').read_bytes(),raw)

    def test_dmesg_failure_and_boot_change_each_partial(self):
        for value in [host(kernel_returncode=1),host(boot_after='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')]:
            with self.subTest(value=value):
                if self.out.exists():self.out.unlink()
                r,_=self.run_mock(json.dumps(value).encode())
                self.assertEqual(r['outcome'],'PARTIAL_CAPTURE')
                self.assertIn('No absence-of-OOM inference',r['guest']['selection'])

    def test_malformed_shape_and_duplicate_key_each_receipted(self):
        for raw in (b'[]',b'{"snapshots":1}',b'{"snapshots":{},"snapshots":{}}'):
            with self.subTest(raw=raw):
                if self.out.exists():self.out.unlink()
                r,private=self.run_mock(raw)
                self.assertEqual(r['outcome'],'FAILED')
                self.assertEqual((private/'ssh.stdout').read_bytes(),raw)

    def test_existing_receipt_refused_before_subprocess(self):
        self.out.write_text('original')
        with patch.object(m.subprocess,'run') as run,self.assertRaises(FileExistsError):
            m.collect('logging02',self.out)
        run.assert_not_called();self.assertEqual(self.out.read_text(),'original')

    def test_config_oserror_receipted_without_launch(self):
        (self.root/'logging02.json').unlink()
        r,_=self.run_mock(b'never read')
        self.assertEqual(r['outcome'],'FAILED');self.assertEqual(r['error_type'],'FileNotFoundError')

    def test_remote_oserror_retained_and_other_reads_continue(self):
        code=m.build_remote('logging02.json',m.sha(b'config'))
        calls=[]
        def fake(command,**kwargs):
            calls.append((command,kwargs['timeout']))
            if len(calls)==1:raise OSError(SECRET)
            return subprocess.CompletedProcess(command,0,'ok','')
        capture=io.StringIO()
        with patch('pathlib.Path.read_bytes',return_value=b'config'),patch('subprocess.run',side_effect=fake),patch.dict(os.environ),contextlib.redirect_stdout(capture):
            exec(compile(code,'<mock-remote>','exec'),{})
        r=json.loads(capture.getvalue())
        self.assertEqual(len(calls),6);self.assertEqual(sum(t for _,t in calls),39)
        self.assertEqual(r['snapshots']['physical_memory']['error_type'],'OSError')
        self.assertEqual(calls[3][0],['/bin/ps','-axo','pid=,ppid=,rss=,comm='])
        self.assertIn('-B',calls[-1][0]);self.assertIn('-n',calls[-1][0])

    def test_vm_oserror_and_timeout_are_json_failures(self):
        for failure in (OSError(SECRET),subprocess.TimeoutExpired('dmesg',15,output=b'partial',stderr=b'failed')):
            capture=io.StringIO()
            with patch('pathlib.Path.read_text',side_effect=[BOOT,'12.34 56.78']),patch('subprocess.run',side_effect=failure),contextlib.redirect_stdout(capture):
                exec(compile(m.VM_CODE,'<mock-vm>','exec'),{})
            r=json.loads(capture.getvalue());self.assertIn('finished_utc',r)
            self.assertEqual(r['error_type'],type(failure).__name__)


if __name__=='__main__':unittest.main(verbosity=2)
