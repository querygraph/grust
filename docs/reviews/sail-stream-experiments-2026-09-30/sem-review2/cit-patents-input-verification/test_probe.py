#!/usr/bin/env python3
"""Tiny offline controls; all generated Parquet stays in private temporary files."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import pyarrow as pa
import pyarrow.parquet as pq

spec = importlib.util.spec_from_file_location('cit_probe', Path(__file__).with_name('probe.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class Response:
    def __init__(self, url=p.PREFIX+p.NAMES[0], status=200, **headers):
        self.url, self.status = url, status
        self.headers = {'Content-Length': '16', 'Content-Type': 'application/octet-stream', **headers}
    def geturl(self):
        return self.url


class ProbeControls(unittest.TestCase):
    def test_http_admission(self):
        self.assertEqual(p.admit_response(Response(), 16), 16)
        for response, cap in [(Response(url='https://example.com/x'),16),
                (Response(status=206),16),
                (Response(**{'Content-Type':'text/html'}),16),
                (Response(**{'Content-Encoding':'gzip'}),16), (Response(),15)]:
            with self.assertRaises(ValueError):
                p.admit_response(response,cap)
        for url in [p.PREFIX+'cit-patents-v.parquet',p.PREFIX+p.NAMES[0]+'?x=1']:
            with self.assertRaises(ValueError):p.check_url(url)
        with self.assertRaises(ValueError):
            p.NoRedirect().redirect_request(None,None,302,None,None,'https://example.com/x')

    def validate(self, vertices, source, target, weight=None):
        with tempfile.TemporaryDirectory(prefix='cit-patents-offline-control-', dir='/private/tmp') as name:
            private=Path(name)
            pq.write_table(pa.table({'id':pa.array(vertices,type=pa.int64())}), private/p.NAMES[0])
            columns={'source':pa.array(source,type=pa.int64()),'target':pa.array(target,type=pa.int64())}
            if weight is not None:columns['weight']=pa.array(weight,type=pa.float64())
            pq.write_table(pa.table(columns),private/p.NAMES[1])
            received={'objects':[{'name':n,'sha256':p.digest(private/n)} for n in p.NAMES]}
            return p.validate(private,received)

    def test_extremes_membership_selfloops_and_no_dedup(self):
        lo,hi=-(2**63),2**63-1
        r=self.validate([lo,0,hi],[lo,lo,hi,0],[hi,hi,hi,lo])
        self.assertEqual(r['outcome'],'VALIDATED_NEW_OFFICIAL_INPUT')
        self.assertEqual(r['vertices']['minimum'],lo)
        self.assertEqual(r['vertices']['maximum'],hi)
        self.assertEqual(r['edges']['rows'],4)
        self.assertEqual(r['edges']['self_loops'],1)
        self.assertEqual(r['duplicate_edges'],{'measured':False,'count':None})
        self.assertTrue(r['original_files_unchanged'])

    def test_duplicate_null_missing_and_weight_invalid_retained(self):
        r=self.validate([0,0,1,None],[0,2,None,1],[0,1,1,None],[1,float('nan'),-2,None])
        self.assertEqual(r['outcome'],'INPUT_VALIDATION_FAILED')
        self.assertEqual(r['vertices']['duplicate_rows_after_first'],1)
        self.assertEqual(r['vertices']['nulls'],1)
        self.assertEqual(r['edges']['source_nulls'],1)
        self.assertEqual(r['edges']['target_nulls'],1)
        self.assertEqual(r['edges']['missing_source_endpoint_rows'],1)
        self.assertEqual(r['weights']['nonfinite'],1)
        self.assertEqual(r['weights']['negative'],1)
        self.assertEqual(r['weights']['nulls'],1)
        self.assertTrue(r['original_files_unchanged'])

    def test_empty_vertices_do_not_crash_membership(self):
        r=self.validate([], [0], [1])
        self.assertEqual(r['outcome'],'INPUT_VALIDATION_FAILED')
        self.assertEqual(r['edges']['missing_source_endpoint_rows'],1)
        self.assertEqual(r['edges']['missing_target_endpoint_rows'],1)


if __name__=='__main__':unittest.main(verbosity=2)
