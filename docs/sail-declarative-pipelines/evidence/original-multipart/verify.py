from pathlib import Path
import hashlib,json,subprocess,xml.etree.ElementTree as ET
from collections import Counter
p=Path(__file__).resolve().parent
read=lambda path:json.loads((p/path).read_text())
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
for f in read('manifest.json')['files']:
 q=p/f['path'];assert q.stat().st_size==f['bytes'] and sha(q)==f['sha256'],q
c=read('candidate.json');commit=c['commit'];assert commit=='8e5e06ff48a5458fb6d68e4d82ca147f634e406e' and c['base']=='d99e8b86d4db7aa2c5f79848496e6f3bfad6acb2'
repo='/Users/alexy/src/sail-pipelines-proposal'
def git(*a):return subprocess.check_output(['git','-C',repo,*a],text=True).strip()
paths=['python/pysail/tests/spark/pipelines/conftest.py','python/pysail/tests/spark/pipelines/test_sql_namespace.py']
assert git('diff','--name-only',c['base'],commit).splitlines()==paths
assert git('diff','--name-only','84d2ddbe0a0d615bbc991022b7d5992f1a623015',commit)==paths[0]
ruff=read('ruff.json');assert ruff['test_commit']==commit
for check in ruff['checks']:
 assert check['exit_code']==0 and sha(p/Path(check['log']).name.replace('sail-sdp-original-multipart-',''))==check['sha256']
spark=read('spark/observations.json');sail=read('sail/observations.json')
assert spark['commit']=='617618396087429b5627a86ce933bb0f5d6645cb'
assert spark['sail_test_commit']==sail['sail_test_commit']==commit
for r in [spark,sail]:
 assert r['version']=='4.2.1' and r['feature_exit_code']==0 and not r['remaining_listeners']
 assert r['script_sha256']==sha(p/'probe.py')
for key,path in [('feature_sha256',paths[1]),('fixture_sha256',paths[0])]:
 content=subprocess.check_output(['git','-C',repo,'show',commit+':'+path]);assert hashlib.sha256(content).hexdigest()==spark[key]==sail[key]
for name in ['spark','sail']:
 suite=ET.parse(p/name/'features.xml').getroot().find('testsuite')
 assert (suite.get('tests'),suite.get('failures'),suite.get('errors'),suite.get('skipped'))==('9','0','0','0')
 assert any(t.get('name')=='test_multipart_outputs_across_two_namespaces'for t in suite.findall('testcase'))
bad=ET.parse(p/'attempt-01/spark/features.xml').getroot().find('testsuite')
assert (bad.get('tests'),bad.get('errors'))==('9','9')
assert 'CANNOT_MODIFY_STATIC_CONFIG' in (p/'attempt-01/spark/features.log').read_text()
runtime=json.loads((p.parent/'ansi-nullability/public/receipt.json').read_text())
assert runtime['outcome']=='passed' and sail['server_artifact_source_commit']==runtime['sail_commit']==c['base']
assert sail['cli_sha256']==runtime['cli_sha256']
assert sail['public_receipt_sha256']==sha(p.parent/'ansi-nullability/public/receipt.json')
combined=read('sail/combined.json')
assert sail['combined_exit_code']==0 and combined['outcome']=='passed' and combined['runner_commit']==commit
assert combined['cleanup']=={'outcome':'passed','errors':[]}
assert combined['private_view_hidden'] and combined['session_defaults_preserved']
assert len(combined['outputs'])==7 and sum(o['upstream_assertion'] for o in combined['outputs'])==5
assert all(o['outcome']=='passed' and o['rows']==o['expected'] for o in combined['outputs'])
print('PASS original SqlPipelineSuite:562 assertion port: identical Spark/Sail tests9 each; exact d99 binary with two-path test-only equivalence; current catalog assertions5+2 and cleanup; prior Spark setup failure retained')

update=read('inventory-update.json')
old=json.loads(subprocess.check_output(['git','-C',str(p.parents[3]),'show','ae34f6426df210ca62c3fd6d533d0c0b11f59464:docs/sail-declarative-pipelines/spark-4.2.1-inventory.json'],text=True))
index=next(i for i,c in enumerate(old['cases'])if c['id']==update['before']['id'])
assert old['cases'][index]==update['before'] and update['before']['status']=='unmapped'
old['cases'][index]=update['after']
assert dict(Counter(c['status']for c in old['cases']))==update['counts_after']=={'unmapped':400,'partial-behavioral-port':62}
assert update['after']['status']=='partial-behavioral-port' and update['after']['coverage_review']['scala_suite_executed'] is False
assert update['after']['sail_tests']==['python/pysail/tests/spark/pipelines/test_sql_namespace.py::test_multipart_outputs_across_two_namespaces']
print('PASS single original-registration inventory delta: 62 partial / 400 unmapped, original Scala suite unexecuted')
