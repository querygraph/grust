"""Check exact source/gates, input identity, controls and all stated limits."""
from pathlib import Path
import hashlib,json,re,subprocess,sys
HERE=Path(__file__).resolve().parent
SAIL='/Users/alexy/src/sail-pipelines-proposal'
FINAL='005fcb07826321693c937a23f362f2e0212aa441'
SHARED='52d4403c424542d598de70095b83c491c08c0bc4'
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',SAIL,*args],text=True).strip()
m=json.loads((HERE/'SHA256.json').read_text())
assert set(m)=={str(p.relative_to(HERE)) for p in HERE.rglob('*') if p.is_file() and p.name!='SHA256.json'}
for path,sha in m.items():assert digest(HERE/path)==sha,path
for folder,sha,counts in [('schema-duplicate-validation',SHARED,[139,237,91,176]),('listing-shadow-intermediate','0ad51a67a9878207b5ee4ce09ea80f8c13319ec1',[139,240,91,176]),('listing-schema-ready',FINAL,[139,240,91,176])]:
 root=HERE/folder;x=json.loads((root/'gate.json').read_text());candidate=json.loads((root/'candidate.json').read_text())
 assert x['sail_commit']==candidate['commit']==sha and x['outcome']=='passed'
 assert git('rev-parse',sha+'^')==candidate['base']
 assert [c['name'] for c in x['checks']]==['fmt','clippy','rust']
 for check in x['checks']:assert check['exit_code']==0 and digest(root/(check['name']+'.log'))==check['sha256']
 assert list(map(int,re.findall(r'test result: ok\. (\d+) passed; 0 failed;', (root/'rust.log').read_text())))==counts
assert git('rev-parse',FINAL+'^')==SHARED
failed=json.loads((HERE/'listing-attempt-01/gate.json').read_text())
assert [c['exit_code'] for c in failed['checks']]==[0,0,101]
text=(HERE/'listing-attempt-01/rust.log').read_text()
assert '139 passed; 0 failed;' in text and '239 passed; 1 failed;' in text
assert 'separate_data_and_partition_checks_allow_partition_shadowing ... FAILED' in text
control=json.loads((HERE/'listing-control/control.json').read_text())
assert control['base']==FINAL and control['exit_code']==101
assert digest(HERE/'listing-control/control.log')==control['log_sha256']
assert '0 passed; 3 failed;' in (HERE/'listing-control/control.log').read_text()
assert git('diff','--name-only',FINAL,control['control'])==control['changed_path']
test='crates/sail-data-source/src/listing/schema_validation_tests.rs'
assert git('rev-parse',FINAL+':'+test)==git('rev-parse',control['control']+':'+test)==control['test_blob']
x=json.loads((HERE/'public/receipt.json').read_text())
assert x['sail_commit']==FINAL and x['before']==x['after'] and x['outcome']=='passed'
assert x['before']['head']==FINAL and all(c['exit_code']==0 for c in x['checks'])
assert x['pytest']=={'tests':300,'failures':0,'errors':0,'skipped':0}
assert x['upstream']=={'tests_run':67,'failures':0,'errors':0,'skipped':0,'server_spark_version':'4.2.1'}
assert x['server_exit_code']==0 and x['remaining_listener_pids']==[]
for path,sha in x['artifact_sha256'].items():assert digest(HERE/'public'/path)==sha
reference=json.loads((HERE/'spark-schemautils/observations.json').read_text())
assert reference['spark_version']==reference['pyspark_version']=='4.2.1'
assert reference['harness_sha256']==digest(HERE/'reference.py')
assert len(reference['cases'])==12
assert sum(c['outcome']=='success' for c in reference['cases'])==1
assert sum(c.get('condition')=='COLUMN_ALREADY_EXISTS' for c in reference['cases'])==10
assert sum(c.get('condition')=='INVALID_ATTRIBUTE_NAME_SYNTAX' for c in reference['cases'])==1
source=json.loads((HERE/'reference-source.json').read_text())
for entry in source['files']:
 data=subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','show',source['spark_commit']+':'+entry['path']])
 assert hashlib.sha256(data).hexdigest()==entry['sha256']
assert len(json.loads((HERE/'partition-attempt-01/run/observations.json').read_text())['cases'])==2
assert 'FileExistsError' in (HERE/'partition-attempt-01/run.log').read_text()
assert json.loads(subprocess.check_output([sys.executable,str(HERE/'compare.py')],text=True))==json.loads((HERE/'comparison.json').read_text())
print('PASS shared643/final646 Rust, 0/3 control, fresh300+67, partition6/6 and metadata7/9 with two ambiguity differences retained; Scala acceptance open')
