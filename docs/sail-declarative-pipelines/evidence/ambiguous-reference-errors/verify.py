"""Qualify exact diagnostics scope; full Spark SDP acceptance remains open."""
from pathlib import Path
import hashlib,json,re,subprocess,sys
HERE=Path(__file__).resolve().parent
SAIL='/Users/alexy/src/sail-pipelines-proposal'
FINAL='95c32c055712995e06a56fc5c0a86d09bc3c954f'
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',SAIL,*args],text=True).strip()
m=json.loads((HERE/'SHA256.json').read_text())
assert set(m)=={str(p.relative_to(HERE)) for p in HERE.rglob('*') if p.is_file() and p.name!='SHA256.json'}
for path,sha in m.items():assert digest(HERE/path)==sha,path
x=json.loads((HERE/'final/gate.json').read_text());candidate=json.loads((HERE/'final/candidate.json').read_text())
assert candidate['commit']==x['sail_commit']==FINAL and x['outcome']=='passed'
assert git('rev-parse',FINAL+'^')==candidate['base']=='005fcb07826321693c937a23f362f2e0212aa441'
assert [c['name'] for c in x['checks']]==['fmt','clippy','rust']
for c in x['checks']:assert c['exit_code']==0 and digest(HERE/'final'/(c['name']+'.log'))==c['sha256']
assert list(map(int,re.findall(r'test result: ok\. (\d+) passed; 0 failed;', (HERE/'final/rust.log').read_text())))==[139,240,92,176]
x=json.loads((HERE/'attempt-01/gate.json').read_text());assert [c['exit_code'] for c in x['checks']]==[0,101]
assert 'needless_borrow' in (HERE/'attempt-01/clippy.log').read_text()
x=json.loads((HERE/'attempt-02/gate.json').read_text());assert [c['exit_code'] for c in x['checks']]==[0,0,101]
text=(HERE/'attempt-02/rust.log').read_text()
assert '139 passed; 0 failed;' in text and '240 passed; 0 failed;' in text and '91 passed; 1 failed;' in text
assert 'session extension not found: catalog manager' in text
control=json.loads((HERE/'native-control/control.json').read_text())
assert control['base']==FINAL and control['exit_code']==101
assert digest(HERE/'native-control/control.log')==control['log_sha256']
assert '0 passed; 1 failed;' in (HERE/'native-control/control.log').read_text()
assert 'unstructured error: analysis error: ambiguous attribute' in (HERE/'native-control/control.log').read_text()
assert git('diff','--name-only',FINAL,control['control'])=='crates/sail-plan/src/resolver/expression/attribute.rs'
test='crates/sail-plan/src/resolver/expression/ambiguous_tests.rs'
assert git('rev-parse',FINAL+':'+test)==git('rev-parse',control['control']+':'+test)==control['test_blob']
x=json.loads((HERE/'public/receipt.json').read_text())
assert x['sail_commit']==FINAL and x['before']==x['after'] and x['outcome']=='passed'
assert x['before']['head']==FINAL and all(c['exit_code']==0 for c in x['checks'])
assert x['pytest']=={'tests':300,'failures':0,'errors':0,'skipped':0}
assert x['upstream']=={'tests_run':67,'failures':0,'errors':0,'skipped':0,'server_spark_version':'4.2.1'}
assert x['server_exit_code']==0 and x['remaining_listener_pids']==[]
for path,sha in x['artifact_sha256'].items():assert digest(HERE/'public'/path)==sha
for folder,probe,count in [('spark','reference.py',10),('spark-initial','reference-initial.py',8)]:
 x=json.loads((HERE/folder/'observations.json').read_text());assert len(x['cases'])==count and x['spark_version']=='4.2.1'
 assert x['harness_sha256']==digest(HERE/probe)
source=json.loads((HERE/'reference-source.json').read_text())
for entry in source['files']:
 data=subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','show',source['spark_commit']+':'+entry['path']]);assert hashlib.sha256(data).hexdigest()==entry['sha256']
assert json.loads(subprocess.check_output([sys.executable,str(HERE/'compare.py')],text=True))==json.loads((HERE/'comparison.json').read_text())
print('PASS exact647 Rust, 0/1 unchanged control, fresh300+67, ordinary10/10 and original-byte metadata9/9; full Scala acceptance open')
