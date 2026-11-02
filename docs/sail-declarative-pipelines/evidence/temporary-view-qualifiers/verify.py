from pathlib import Path
import hashlib,json,subprocess,xml.etree.ElementTree as ET
from collections import Counter
p=Path(__file__).resolve().parent
read=lambda name:json.loads((p/name).read_text())
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
for f in read('manifest.json')['files']:
 q=p/f['path'];assert q.stat().st_size==f['bytes']and sha(q)==f['sha256'],q
repo='/Users/alexy/src/sail-pipelines-proposal'
def git(*a):return subprocess.check_output(['git','-C',repo,*a],text=True).strip()
shared=read('shared/candidate.json');candidate=read('native/candidate.json');commit=candidate['commit']
assert shared['commit']=='60a5f290c1e019e4d01d24f140d224b583f0698f' and shared['base']=='8e5e06ff48a5458fb6d68e4d82ca147f634e406e'
assert commit=='db650c40e7605658b047fafac2fc721a395c4a0c' and candidate['base']==shared['commit']
assert git('rev-parse',shared['base']+':crates/sail-common-datafusion/src/error/structured.rs')==git('rev-parse',shared['commit']+':crates/sail-common/src/error/structured.rs')
assert git('rev-parse',shared['base']+':Cargo.lock')==git('rev-parse',commit+':Cargo.lock')
for section,source in [('shared',shared),('native',candidate)]:
 gate=read(section+'/gate.json');assert gate['sail_commit']==source['commit'] and gate['outcome']=='passed'
 for check in gate['checks']:
  assert check['exit_code']==0
  suffix=Path(check['log']).name.split('-')[-1]
  assert sha(p/section/suffix)==check['sha256']
for section,counts in [('shared',[33,140]),('native',[123,185,29])]:
 log=(p/section/'rust.log').read_text()
 for count in counts:assert f'{count} passed; 0 failed; 0 ignored;'in log
for name in ['normalization','pipeline']:
 c=read('controls/'+name+'.json');assert c['base']==commit and c['exit_code']==101
 assert sha(p/'controls'/f'{name}.log')==c['log_sha256'] and '0 passed; 1 failed;'in(p/'controls'/f'{name}.log').read_text()
 assert git('diff','--name-only',commit,c['control'])==c['path']
 for rev in [commit,c['control']]:assert git('rev-parse',rev+':'+c['test_path'])==c['test_blob']
public=read('public/receipt.json');assert public['sail_commit']==commit and public['outcome']=='passed'
assert public['pytest']==dict(tests=300,failures=0,errors=0,skipped=0)
u=read('public/upstream.json');assert u['tests_run']==67 and u['failures']==u['errors']==u['skipped']==0
for name,digest in public['artifact_sha256'].items():assert sha(p/'public'/name)==digest
spark=read('spark/observations.json');sail=read('sail/observations.json');parent=read('sail-baseline/observations.json');oracle=read('spark-baseline/observations.json')
assert spark['spark_source_commit']==oracle['spark_source_commit']=='617618396087429b5627a86ce933bb0f5d6645cb'
assert sail['server_artifact_source_commit']==commit and sail['cli_sha256']==public['cli_sha256']
assert sail['public_receipt_sha256']==sha(p/'public/receipt.json')
assert spark['test_commit']==sail['test_commit']==commit
assert spark['script_sha256']==sail['script_sha256']==sha(p/'scripts/probe.py')
test_path='python/pysail/tests/spark/pipelines/test_temporary_view_qualifiers.py'
content=subprocess.check_output(['git','-C',repo,'show',commit+':'+test_path])
assert hashlib.sha256(content).hexdigest()==spark['test_sha256']==sail['test_sha256']
for name,r in [('spark',spark),('sail',sail)]:
 assert r['version']=='4.2.1'and not r['cleanup_errors']and not r['remaining_listeners']and r['pytest_exit_code']==0
 suite=ET.parse(p/name/'pytest.xml').getroot().find('testsuite')
 assert (suite.get('tests'),suite.get('failures'),suite.get('errors'),suite.get('skipped'))==('19','0','0','0')
def matches(a,b):
 if any(a[k]!=b[k]for k in ['api','name','sql','outcome']):return False
 if a['outcome']=='accepted':return a.get('rows')==b.get('rows')
 return all(a[k]==b[k]for k in ['error_type','condition','sql_state','parameters'])
for report in [spark,sail,parent,oracle]:
 assert len(report['cases'])==30 and not report['cleanup_errors']and not report['remaining_listeners']
assert all(matches(a,b)for a,b in zip(spark['cases'],oracle['cases']))
assert sum(matches(a,b)for a,b in zip(spark['cases'],parent['cases']))==4
assert all(matches(a,b)for a,b in zip(spark['cases'],sail['cases']))
print('PASS shared diagnostics173 native; temp-view qualifiers337 native/fmt/strictClippy/two unchanged controls0/1; public300+67; Spark/Sail focused19 each; class/condition/state/params30/30 vs parent4/30')
print('Scope: query-defined temporary views; USING and DROP semantics unchanged; original Scala suite remains unexecuted')

failed=read('preflight-failure/receipt.json')
assert failed['outcome']=='failed' and failed['checks']==[] and 'frozen test/helper source changed'in failed['error']
before=read('harness-refresh/preparation-before.json');after=read('harness-refresh/preparation-after.json')
assert before['selected_nodes_sha256']==after['selected_nodes_sha256']==sha(p/'public/selected-nodes.json')
changed={path for path in before['source_sha256']if before['source_sha256'][path]!=after['source_sha256'][path]}
assert changed=={'python/pysail/tests/spark/pipelines/conftest.py','python/pysail/tests/spark/pipelines/test_sql_namespace.py'}
assert after['sail_commit']=='8e5e06ff48a5458fb6d68e4d82ca147f634e406e'
for path in changed:
 content=subprocess.check_output(['git','-C',repo,'show',after['sail_commit']+':'+path])
 assert hashlib.sha256(content).hexdigest()==after['source_sha256'][path]
assert after['inputs']==before['inputs']
assert public['preparation_sha256']==sha(p/'harness-refresh/preparation-after.json')
assert public['harness_sha256']==failed['harness_sha256']
print('PASS reviewed two-file harness-source refresh; frozen300 identifiers/assertions/harness unchanged; failed preflight retained')

update=read('inventory-update.json')
old=json.loads(subprocess.check_output(['git','-C',str(p.parents[3]),'show','c7c691ab491371af65a1e9b06fd7e1743f9512ff:docs/sail-declarative-pipelines/spark-4.2.1-inventory.json'],text=True))
index=next(i for i,c in enumerate(old['cases'])if c['id']==update['before']['id'])
assert old['cases'][index]==update['before'] and update['before']['status']=='unmapped'
old['cases'][index]=update['after']
assert dict(Counter(c['status']for c in old['cases']))==update['counts_after']=={'unmapped':399,'partial-behavioral-port':63}
assert update['after']['status']=='partial-behavioral-port' and update['after']['coverage_review']['scala_suite_executed'] is False
assert update['after']['sail_tests']==['python/pysail/tests/spark/pipelines/test_temporary_view_qualifiers.py::test_temporary_view_rejects_database_qualifier[pipeline]']
print('PASS single original :599 mapping:63 partial/399 unmapped; original Scala suite unexecuted')
