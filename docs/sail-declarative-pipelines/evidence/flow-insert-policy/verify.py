from pathlib import Path
import hashlib,json,re,subprocess,xml.etree.ElementTree as ET

E=Path(__file__).resolve().parent;S='/Users/alexy/src/sail-pipelines-proposal'
def read(p):return json.loads((E/p).read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*a):return subprocess.check_output(['git','-C',S,*a])
for f,h in read('MANIFEST.json').items():assert sha(E/f)==h,f
s=read('summary.json');commit=s['sail_commit']
assert not any(s[k] for k in ['inventory_changed','full_conformance','original_scala_suite_executed_on_sail','streaming_cdc_activated'])
g=read('native/sail-sdp-flow-insert-policy-01-gate.json')
assert g['sail_commit']==commit and g['outcome']=='passed'
for c in g['checks']:assert c['exit_code']==0 and sha(E/'native'/Path(c['log']).name)==c['sha256']
log=(E/'native/sail-sdp-flow-insert-policy-01-rust.log').read_text()
assert sorted(map(int,re.findall(r'test result: ok\. (\d+) passed;',log)))==[52,202]
p=read('public/receipt.json')
assert p['outcome']=='passed' and p['sail_commit']==commit and p['before']==p['after'] and p['before']['head']==commit
assert p['pytest']==dict(tests=300,failures=0,errors=0,skipped=0) and not p['remaining_listener_pids'] and p['server_exit_code']==0
for f,h in p['artifact_sha256'].items():assert sha(E/'public'/f)==h,f
u=read('public/upstream.json');assert u['tests_run']==67 and not any(u[k]for k in ['failures','errors','skipped'])
before=read('public-harness/preparation-before-flow-policy.json');after=read('public-harness/preparation.json')
a=after['flow_policy_alignment'];feature=a['feature'];mapping=a['id_mapping'];assert len(mapping)==3
assert {k:v for k,v in before['source_sha256'].items()if k!=feature}=={k:v for k,v in after['source_sha256'].items()if k!=feature}
assert before['source_sha256'][feature]==a['old_feature_sha256'] and after['source_sha256'][feature]==a['new_feature_sha256']
assert hashlib.sha256(git('show',commit+':'+feature)).hexdigest()==a['new_feature_sha256']
old=json.loads((E.parent/'insert-mode-validation/public/selected-nodes.json').read_text());new=read('public-harness/selected-nodes.json')
assert len(new)==len(set(new))==300 and len(set(old)&set(new))==297 and [mapping.get(n,n)for n in old]==new
assert read('public/selected-nodes.json')==new
for old_id,new_id in mapping.items():assert new_id.startswith(old_id[:-1]+'-')
records=[]
for mode in ['spark','sail']:
 r=read(mode+'/observations.json');records.append(r)
 assert r['version']=='4.2.1' and r['pytest_exit_code']==0 and not r['remaining_listeners'] and not r['cleanup_errors']
 assert len(r['cases'])==12
 assert r['test_sha256']==hashlib.sha256(git('show',commit+':python/pysail/tests/spark/pipelines/test_flow_insert_policy.py')).hexdigest()
 assert r['script_sha256']==sha(E/'sail-sdp-flow-policy-feature-probe.py')
 cases=list(ET.parse(E/mode/'pytest.xml').iter('testcase'));assert len(cases)==15 and all(not list(t) for t in cases)
assert records[1]['runtime_commit']==commit and records[1]['cli_sha256']==p['cli_sha256']
for a,b in zip(*(r['cases']for r in records)):
 for k in ['label','sql','outcome','error_type','condition','sql_state','parameters']:assert a.get(k)==b.get(k),k
for label in ['message','precedence']:
 c=read('control-'+label+'.json');log=E/('control-'+label+'.log')
 assert c['base']==commit and c['exit_code']==101 and sha(log)==c['log_sha256'] and '0 passed; 1 failed;'in log.read_text()
 assert git('diff','--name-only',commit,c['control']).decode().strip()==c['path']
 for rev in [commit,c['control']]:assert git('rev-parse',rev+':'+c['test_path']).decode().strip()==c['test_blob']
print('PASS Flow INSERT policy:254native,300+67,paired15,12 vectors,two controls;297 IDs retained/three same-input migrations;no full-conformance claim')
