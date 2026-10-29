from pathlib import Path
from argparse import Namespace
from dataclasses import replace
import importlib.util,json,sys
p=Path('scripts/spark-pipelines-tests/catalog.py')
spec=importlib.util.spec_from_file_location('catalog_acceptance_control',p)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
m.CASES=(replace(m.CASES[0],rows=[99]),)
c=json.loads(Path('/tmp/sail-sdp-lakecat-integration.json').read_text())
args=Namespace(remote='sc://localhost:50082',provider='parquet',storage=(Path(c['root'])/'mismatch-control').as_uri(),warehouse=c['warehouse'],catalog=None,database=None)
report={'cases':[]}
assert not m.execute(args,report)
assert report['cleanup']=='passed' and len(report['cases'])==1
assert report['cases'][0]['outcome']=='failed' and '99' in report['cases'][0]['error']
Path('/tmp/sail-sdp-catalog-runner-failure-control.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS deliberate answer mismatch fails acceptance and cleans its table')
