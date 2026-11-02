"""Verify exact source/gates and differential scope, not full Spark SDP acceptance."""
from pathlib import Path
import hashlib,json,re,subprocess,sys
HERE=Path(__file__).resolve().parent
SAIL='/Users/alexy/src/sail-pipelines-proposal'
FINAL='7b5667c1fef901c5f6768fd5af222beeed453f15'
TRANSPORT='abadcd8b068d10429ca550dcb51c9a36bf3f42c6'
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',SAIL,*args],text=True).strip()
manifest=json.loads((HERE/'SHA256.json').read_text())
assert set(manifest)=={str(p.relative_to(HERE)) for p in HERE.rglob('*') if p.is_file() and p.name!='SHA256.json'}
for path,sha in manifest.items():assert digest(HERE/path)==sha,path
for folder,sha,counts in [('structured-plan-errors',TRANSPORT,[88,176]),('unresolved-column-ready',FINAL,[91,176])]:
    root=HERE/folder;gate=json.loads((root/'gate.json').read_text());candidate=json.loads((root/'candidate.json').read_text())
    assert gate['sail_commit']==candidate['commit']==sha and gate['outcome']=='passed'
    assert git('rev-parse',sha+'^')==candidate['base']
    assert [c['name'] for c in gate['checks']]==['fmt','clippy','rust']
    for check in gate['checks']:
        assert check['exit_code']==0 and digest(root/(check['name']+'.log'))==check['sha256']
    assert list(map(int,re.findall(r'test result: ok\. (\d+) passed; 0 failed;', (root/'rust.log').read_text())))==counts
assert git('rev-parse',FINAL+'^')==TRANSPORT
for folder in ['attempt-01','attempt-02']:
    gate=json.loads((HERE/folder/'gate.json').read_text())
    assert [c['exit_code'] for c in gate['checks']]==[0,0,101]
    text=(HERE/folder/'rust.log').read_text()
    assert '91 passed; 0 failed;' in text and '175 passed; 1 failed;' in text
    for check in gate['checks']:assert digest(HERE/folder/(check['name']+'.log'))==check['sha256']
control=json.loads((HERE/'native-control/control.json').read_text())
assert control['base']==FINAL and control['exit_code']==101
assert digest(HERE/'native-control/control.log')==control['log_sha256']
assert '2 passed; 1 failed;' in (HERE/'native-control/control.log').read_text()
assert 'unstructured error: analysis error: attribute' in (HERE/'native-control/control.log').read_text()
assert git('diff','--name-only',FINAL,control['control'])==control['changed_path']
test='crates/sail-plan/src/resolver/expression/unresolved_tests.rs'
assert git('rev-parse',FINAL+':'+test)==git('rev-parse',control['control']+':'+test)==control['test_blob']
public=json.loads((HERE/'public/receipt.json').read_text())
assert public['sail_commit']==FINAL and public['before']==public['after'] and public['outcome']=='passed'
assert public['before']['head']==FINAL
assert all(c['exit_code']==0 for c in public['checks'])
assert public['pytest']=={'tests':300,'failures':0,'errors':0,'skipped':0}
assert public['upstream']=={'tests_run':67,'failures':0,'errors':0,'skipped':0,'server_spark_version':'4.2.1'}
assert public['server_exit_code']==0 and public['remaining_listener_pids']==[]
for path,sha in public['artifact_sha256'].items():assert digest(HERE/'public'/path)==sha
source=json.loads((HERE/'reference-source.json').read_text())
for entry in source['files']:
    data=subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','show',source['spark_commit']+':'+entry['path']])
    assert hashlib.sha256(data).hexdigest()==entry['sha256']
assert json.loads((HERE/'spark-ordinary/teardown.json').read_text())['listener_probe_exit_code']==1
changes=[]
def walk(a,b,path):
    assert type(a) is type(b)
    if isinstance(a,dict):
        assert set(a)==set(b)
        for key in a:walk(a[key],b[key],path+[key])
    elif isinstance(a,list):
        assert len(a)==len(b)
        for i,(left,right) in enumerate(zip(a,b)):walk(left,right,path+[i])
    elif a!=b:changes.append((path,a,b))
for filename in ['agg.json','predicate.json']:
    path='crates/sail-spark-connect/tests/gold_data/function/'+filename
    walk(json.loads(git('show',TRANSPORT+':'+path)),json.loads(git('show',FINAL+':'+path)),[filename])
assert len(changes)==3
assert all(path[-1]=='failure' and 'cannot resolve attribute' in a and b.startswith('[UNRESOLVED_COLUMN.WITHOUT_SUGGESTION]') for path,a,b in changes)
comparison=json.loads(subprocess.check_output([sys.executable,str(HERE/'compare.py')],text=True))
assert comparison==json.loads((HERE/'comparison.json').read_text())
print('PASS exact unresolved-column gates/control, unchanged golden inputs, ordinary12/12 and SDP13/13 comparison scope; full Scala acceptance open')
