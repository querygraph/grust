"""Test-only local receipt substitute; NOT GraphUtils lifecycle evidence."""
from pathlib import Path
from urllib.parse import urlparse
import os,shutil,uuid
import pytest

@pytest.fixture(scope='session',autouse=True)
def local_storage_receipts():
    import pyspark_pecan.algorithms as algorithms
    original=algorithms.GraphUtils
    root=Path(os.environ['PECAN_PROBE_STAGING']).resolve()
    root.mkdir(parents=True,exist_ok=True)
    class LocalReceipts:
        def __init__(self,spark):
            self.root=root.as_uri();self.capabilities={'fs','owned_runs_v1'};self.runs={}
        def allocate(self,**_):
            path=root/str(uuid.uuid4());path.mkdir();(path/'_sail_graph_run').write_text('probe')
            token=str(uuid.uuid4());self.runs[token]=path
            return path.as_uri(),token
        def owned(self,uri,token):
            path=Path(urlparse(uri).path).resolve();assert path.is_relative_to(self.runs[token]);return path
        def exists(self,uri,token):
            return self.owned(uri,token).exists()
        def remove(self,uri,token):
            path=self.owned(uri,token)
            count=sum(p.is_file() for p in path.rglob('*')) if path.exists() else 0
            shutil.rmtree(path,ignore_errors=True);return count
    algorithms.GraphUtils=LocalReceipts
    try:
        yield
    finally:
        algorithms.GraphUtils=original
