from pathlib import Path
import hashlib,json,subprocess,xml.etree.ElementTree as ET
p=Path(__file__).resolve().parent
read=lambda path:json.loads((p/path).read_text())
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
for f in read('manifest.json')['files']:
 q=p/f['path'];assert q.stat().st_size==f['bytes'] and sha(q)==f['sha256'],q
c=read('native/candidate.json');commit=c['commit'];assert commit=='e18c7a81ae0c5a933c518ef8ca47727753ff8aa8' and c['base']=='a51bef4ce1b1b18b025fc697ace4b03c891380e8'
g=read('native/gate.json');assert g['sail_commit']==commit and g['outcome']=='passed'
for check in g['checks']:
 assert check['exit_code']==0
 assert sha(p/'native'/Path(check['log']).name.replace('sail-sdp-case-else-',''))==check['sha256']
assert '123 passed; 0 failed; 0 ignored;' in (p/'native/rust.log').read_text()
control=read('control.json');assert control['base']==commit and control['exit_code']==101
assert sha(p/'control.log')==control['log_sha256'] and '0 passed; 1 failed;' in (p/'control.log').read_text()
repo='/Users/alexy/src/sail-pipelines-proposal'
def git(*a):return subprocess.check_output(['git','-C',repo,*a],text=True).strip()
assert git('diff','--name-only',commit,control['control'])==control['path']
for rev in [commit,control['control']]:assert git('rev-parse',rev+':'+control['test_path'])==control['test_blob']
public=read('public/receipt.json');assert public['sail_commit']==commit and public['outcome']=='passed'
assert public['pytest']==dict(tests=300,failures=0,errors=0,skipped=0)
u=read('public/upstream.json');assert u['tests_run']==67 and u['failures']==u['errors']==u['skipped']==0
for name,digest in public['artifact_sha256'].items():assert sha(p/'public'/name)==digest
spark=read('spark/observations.json');sail=read('sail/observations.json')
assert spark['commit']=='617618396087429b5627a86ce933bb0f5d6645cb'
assert sail['commit']==commit and sail['cli_sha256']==public['cli_sha256']
assert sail['public_receipt_sha256']==sha(p/'public/receipt.json')
assert spark['sail_test_commit']=='8403829d9244c292b5f78bc6a231bc39ee59941f'
assert sail['sail_test_commit']==commit
assert git('diff','--name-only',spark['sail_test_commit'],commit)=='crates/sail-plan/src/function/scalar/conditional/tests.rs'
assert not git('diff',spark['sail_test_commit'],commit,'--','python')
assert spark['script_sha256']==sail['script_sha256']==sha(p/'scripts/probe.py')
feature='python/pysail/tests/spark/function/features/conditional/when.feature'
content=subprocess.check_output(['git','-C',repo,'show',commit+':'+feature])
assert hashlib.sha256(content).hexdigest()==spark['feature_sha256']==sail['feature_sha256']
for name,r in [('spark',spark),('sail',sail)]:
 assert r['version']=='4.2.1' and r['feature_exit_code']==0 and not r['remaining_listeners'] and len(r['cases'])==16
 suite=ET.parse(p/name/'features.xml').getroot().find('testsuite')
 assert (suite.get('tests'),suite.get('failures'),suite.get('errors'),suite.get('skipped'))==('18','0','0','0')
for a,b in zip(spark['cases'],sail['cases']):
 assert all(a[k]==b[k] for k in ['ansi','expression','rows','schema']),(a,b)

parent=read('parent/observations.json');old_spark=read('spark-baseline/observations.json')
assert parent['commit']==c['base'] and len(parent['cases'])==16
assert parent['cli_sha256']==json.loads((p.parent/'conditional-types/public/receipt.json').read_text())['cli_sha256']
assert sum(a['rows']==b['rows'] and a['schema']==b['schema'] for a,b in zip(spark['cases'],parent['cases']))==6
assert all(a['rows']==b['rows'] for a,b in zip(spark['cases'],parent['cases']))
assert all(all(a[k]==b[k] for k in ['ansi','expression','rows','schema']) for a,b in zip(spark['cases'],old_spark['cases']))
assert not parent['remaining_listeners'] and not old_spark['remaining_listeners']
feature_text=content.decode()
assert '    @sail-bug' not in feature_text and 'result: decimal(11,1) (nullable = false)' in feature_text
print('PASS CASE ELSE: native123/fmt/strictClippy; unchanged control0/1; public300+67; Spark/Sail features18 each; complete16/16 vs parent6/16')
print('Scope: explicit ELSE and nullability; separate NVL2 cast/nullability failures are not declared closed')

extra_spark=read('unreached-null/spark/observations.json');extra_sail=read('unreached-null/sail/observations.json')
assert extra_spark['commit']==spark['commit'] and extra_sail['commit']==commit and extra_sail['cli_sha256']==sail['cli_sha256']
assert not extra_spark['remaining_listeners'] and not extra_sail['remaining_listeners']
assert len(extra_spark['cases'])==len(extra_sail['cases'])==4
assert all(a['rows']==b['rows'] and a['schema']!=b['schema'] and a['expression']==b['expression'] and a['ansi']==b['ansi'] for a,b in zip(extra_spark['cases'],extra_sail['cases']))
print('REQUIRED FOLLOW-UP: four CASE literal-condition/nullability mismatches remain, in both directions; CASE ELSE fix is not full conditional-schema parity')
