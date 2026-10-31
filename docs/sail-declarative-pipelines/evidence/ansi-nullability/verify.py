from pathlib import Path
import hashlib,json,subprocess,xml.etree.ElementTree as ET
p=Path(__file__).resolve().parent
read=lambda path:json.loads((p/path).read_text())
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
for f in read('manifest.json')['files']:
 q=p/f['path'];assert q.stat().st_size==f['bytes'] and sha(q)==f['sha256'],q
c=read('native/candidate.json');commit=c['commit'];assert commit=='d99e8b86d4db7aa2c5f79848496e6f3bfad6acb2' and c['base']=='e18c7a81ae0c5a933c518ef8ca47727753ff8aa8'
g=read('native/gate.json');assert g['sail_commit']==commit and g['outcome']=='passed'
for check in g['checks']:
 assert check['exit_code']==0
 assert sha(p/'native'/Path(check['log']).name.replace('sail-sdp-ansi-nullability-',''))==check['sha256']
for count in [243,410,123]:assert f'{count} passed; 0 failed; 0 ignored;' in (p/'native/rust.log').read_text()
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
assert spark['sail_test_commit']==sail['sail_test_commit']==commit
assert spark['script_sha256']==sail['script_sha256']==sha(p/'scripts/probe.py')
feature='python/pysail/tests/spark/function/features/conversion/ansi_string_cast_schema.feature'
content=subprocess.check_output(['git','-C',repo,'show',commit+':'+feature])
assert hashlib.sha256(content).hexdigest()==spark['feature_sha256']==sail['feature_sha256']
for name,r in [('spark',spark),('sail',sail)]:
 assert r['version']=='4.2.1' and r['feature_exit_code']==0 and not r['remaining_listeners'] and len(r['cases'])==90
 suite=ET.parse(p/name/'features.xml').getroot().find('testsuite')
 assert (suite.get('tests'),suite.get('failures'),suite.get('errors'),suite.get('skipped'))==('21','0','0','0')

parent=read('parent/observations.json');old_spark=read('spark-baseline/observations.json')
assert parent['commit']==c['base'] and len(parent['cases'])==90
assert parent['cli_sha256']==json.loads((p.parent/'case-else/public/receipt.json').read_text())['cli_sha256']
assert not parent['remaining_listeners'] and not old_spark['remaining_listeners']
for a,b in zip(spark['cases'],old_spark['cases']):assert all(a[k]==b[k] for k in ['ansi','expression','rows','schema'])
summary={}
for name,report in [('parent',parent),('final',sail)]:
 assert len(report['cases'])==90
 for a,b in zip(spark['cases'],report['cases']):assert all(a[k]==b[k] for k in ['ansi','expression','rows'])
 summary[name]=sum(a['schema']==b['schema'] for a,b in zip(spark['cases'],report['cases']))
assert summary['parent']==64
assert summary['final']==79,summary
for a,b in zip(spark['cases'],sail['cases']):
 if a['ansi'] and 'SELECT CAST(' in a['expression']:
  assert a['schema']==b['schema'],(a,b)
failed=read('attempt-01/gate.json');assert failed['sail_commit']=='c269dabc7811ad8dadcd3706fcd32a8a384a87ea'
assert failed['checks'][-1]['exit_code']==101 and 'error[E0433]' in (p/'attempt-01/clippy.log').read_text()
assert git('diff','--name-only',failed['sail_commit'],commit)=='crates/sail-execution/src/proto/codec/ansi_string_cast_tests.rs'
print('PASS ANSI cast field: native776/fmt/strictClippy; unchanged control0/1; public300+67; Spark/Sail features21 each; complete79/90 vs parent64/90, rows90/90')
print('REQUIRED FOLLOW-UP: 8 legacy primitive CAST schemas and 3 NVL2 schemas remain; no full cast/folding/SDP acceptance claim')
