"""Offline admission/classification controls; no SSH or subprocess invocation."""
import copy,importlib.util,json,unittest
from datetime import datetime,timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('series',ROOT/'observe_series.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Guards(unittest.TestCase):
    def prior(self):return {'outcome':'LIVE_NO_NEW_FAULT_OBSERVED','returncode':0,'capture':{'returncode':0},'local_finished_utc':m.FIRST.isoformat()}
    def test_not_before(self):
        with self.assertRaises(RuntimeError):m.admit([],m.FIRST-timedelta(microseconds=1))
        self.assertEqual(m.admit([],m.FIRST),1)
    def test_interval_measured_after_prior_return(self):
        with self.assertRaises(RuntimeError):m.admit([self.prior()],m.FIRST+timedelta(seconds=299.99))
        self.assertEqual(m.admit([self.prior()],m.FIRST+timedelta(seconds=300)),2)
    def test_six_maximum(self):
        self.assertEqual(m.admit([self.prior()]*5,m.FIRST+timedelta(seconds=300)),6)
        with self.assertRaises(RuntimeError):m.admit([self.prior()]*6,m.FIRST+timedelta(seconds=999))
    def test_stop_after_error_or_nonzero(self):
        for value in ({'outcome':'STOP_NEW_EVIDENCE'},{'outcome':'STOP_CAPTURE_FAILURE'}, {'returncode':1},{'capture':{'returncode':1}}):
            prior=self.prior();prior.update(value)
            with self.assertRaises(RuntimeError):m.admit([prior],m.FIRST+timedelta(seconds=999))
    def base(self):
        r=json.loads((ROOT/'observation-20260930T220458591359Z.json').read_text());r['observation']['error_scan']['matches']=[];return r
    def test_valid_mapping_no_new_fault(self):self.assertEqual(m.classify(self.base()),('LIVE_NO_NEW_FAULT_OBSERVED',[]))
    def test_new_fault_receipt_disappearance_and_pid_reuse_stop(self):
        for kind in ('fault','receipt','missing','reused','oom','cgroup_error'):
            r=self.base()
            if kind=='fault':r['observation']['error_scan']['matches']=[{'offset':123,'line_utf8':'[timestamp] ERROR'}]
            elif kind=='receipt':r['observation']['files']['receipt.json']['exists']=True
            elif kind=='missing':r['mapping']['processes'].pop()
            elif kind=='reused':r['mapping']['processes'][-1]['start_ticks']+=1
            elif kind=='oom':r['observation']['cgroup']['memory.events']='oom_kill 1\n'
            else:r['observation']['cgroup']['memory.current']={'error':'read failed'}
            with self.subTest(kind=kind):self.assertEqual(m.classify(r)[0],'STOP_NEW_EVIDENCE')
    def test_timeout_and_remote_failure_stop(self):
        for r in ({'error':'timeout'}, {'returncode':1}, {'returncode':0,'capture':{'returncode':1}}):self.assertEqual(m.classify(r)[0],'STOP_CAPTURE_FAILURE')

if __name__=='__main__':unittest.main(verbosity=2)
