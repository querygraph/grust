"""Offline follow-up scheduling only; actual observer/classifier is unchanged."""
from datetime import timedelta
from pathlib import Path
import importlib.util,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('followup',ROOT/'observe_followup02.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class Guards(unittest.TestCase):
    def prior(self):return {'outcome':'LIVE_NO_NEW_FAULT_OBSERVED','returncode':0,'capture':{'returncode':0},'local_finished_utc':m.FIRST.isoformat()}
    def test_first_boundary(self):
        with self.assertRaises(RuntimeError):m.admit([],m.FIRST-timedelta(microseconds=1))
        self.assertEqual(m.admit([],m.FIRST),1)
    def test_fifteen_minutes_after_return(self):
        with self.assertRaises(RuntimeError):m.admit([self.prior()],m.FIRST+timedelta(seconds=899.999))
        self.assertEqual(m.admit([self.prior()],m.FIRST+timedelta(seconds=900)),2)
    def test_six_limit(self):
        self.assertEqual(m.admit([self.prior()]*5,m.FIRST+timedelta(seconds=900)),6)
        with self.assertRaises(RuntimeError):m.admit([self.prior()]*6,m.FIRST+timedelta(seconds=9999))
    def test_failure_stops(self):
        for delta in ({'outcome':'STOP_NEW_EVIDENCE'},{'outcome':'STOP_CAPTURE_FAILURE'},{'returncode':1},{'capture':{'returncode':1}}):
            r=self.prior();r.update(delta)
            with self.assertRaises(RuntimeError):m.admit([r],m.FIRST+timedelta(seconds=9999))
    def test_root_stop(self):
        with tempfile.TemporaryDirectory(prefix='followup-stop-',dir='/private/tmp') as d:
            root=Path(d);(root/'followup02-root-stop.json').write_text('{}')
            with patch.object(m,'ROOT',root),self.assertRaises(RuntimeError):m.admit([],m.FIRST)

if __name__=='__main__':unittest.main(verbosity=2)
