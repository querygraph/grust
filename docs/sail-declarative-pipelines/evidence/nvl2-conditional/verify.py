from pathlib import Path
import hashlib,json,subprocess,xml.etree.ElementTree as ET
p=Path(__file__).resolve().parent
read=lambda path:json.loads((p/path).read_text())
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
for f in read('manifest.json')['files']:
 q=p/f['path'];assert q.stat().st_size==f['bytes'] and sha(q)==f['sha256'],q
candidate=read('final/native/candidate.json');commit=candidate['commit'];base=candidate['base'];assert base=='226b0c1cfc9ac72dadc3ec8a81667f7acc3aacec'
assert commit=='982877d859bed7b7e82662d6873a6b7f88eb04a3'
gate=read('final/native/gate.json');assert gate['sail_commit']==commit and gate['outcome']=='passed'
for check in gate['checks']:
 assert check['exit_code']==0
 assert sha(p/'final/native'/Path(check['log']).name.replace('sail-sdp-nvl2-conditional-',''))==check['sha256']
log=(p/'final/native/rust.log').read_text();assert '119 passed; 0 failed; 0 ignored;' in log and '51 passed; 0 failed; 1 ignored;' in log
control=read('final/control.json');assert control['base']==commit and control['exit_code']==101
assert sha(p/'final/control.log')==control['log_sha256'] and '0 passed; 2 failed;' in (p/'final/control.log').read_text()
repo='/Users/alexy/src/sail-pipelines-proposal'
def git(*args):return subprocess.check_output(['git','-C',repo,*args],text=True).strip()
assert git('diff','--name-only',commit,control['control'])==control['path']
for rev in [commit,control['control']]:assert git('rev-parse',rev+':'+control['test_path'])==control['test_blob']
public=read('final/public/receipt.json');assert public['sail_commit']==commit and public['outcome']=='passed'
assert public['pytest']==dict(tests=300,failures=0,errors=0,skipped=0)
u=read('final/public/upstream.json');assert u['tests_run']==67 and u['failures']==u['errors']==u['skipped']==0
for name,digest in public['artifact_sha256'].items():assert sha(p/'final/public'/name)==digest
spark=read('spark/observations.json');assert spark['commit']=='617618396087429b5627a86ce933bb0f5d6645cb' and spark['version']=='4.2.1' and len(spark['cases'])==16
reports={name:read(path+'/observations.json') for name,path in [('parent','parent'),('attempt-01','attempt-01/probe'),('final','final/probe')]}
for report in [spark,*reports.values()]:assert not report['remaining_listeners']
final=reports['final'];assert final['commit']==commit and final['cli_sha256']==public['cli_sha256'] and final['feature_exit_code']==0
suite=ET.parse(p/'final/probe/features.xml').getroot().find('testsuite');assert (suite.get('tests'),suite.get('failures'),suite.get('errors'),suite.get('skipped'))==('6','0','0','0')
failed=ET.parse(p/'attempt-01/probe/features.xml').getroot().find('testsuite');assert (failed.get('tests'),failed.get('failures'),failed.get('errors'))==('5','1','0')
summary={}
for name,report in reports.items():
 assert len(report['cases'])==16
 for oracle,actual in zip(spark['cases'],report['cases']):assert (oracle['ansi'],oracle['expression'])==(actual['ansi'],actual['expression'])
 summary[name]={'rows':sum(a.get('rows')==b.get('rows') for a,b in zip(spark['cases'],report['cases'])),'complete':sum(a.get('rows')==b.get('rows') and a.get('schema')==b.get('schema') for a,b in zip(spark['cases'],report['cases']))}
assert summary['parent']=={'rows':2,'complete':1} and summary['attempt-01']=={'rows':16,'complete':9}
assert summary['final']['rows']==16
for index in [0,1,2,3,4,8,9,10,11,12]:assert spark['cases'][index]['schema']==final['cases'][index]['schema']
print('PASS NVL2 retained evidence:',json.dumps(summary),'native119+51 (one existing ignored), public300+67, features6, unchanged control0/2')
print('Remaining schema gaps:',[(a['ansi'],a['expression']) for a,b in zip(spark['cases'],final['cases']) if a['schema']!=b['schema']])

follow_spark=read('follow-up/spark/observations.json');follow_sail=read('follow-up/sail/observations.json')
assert follow_spark['commit']==spark['commit'] and follow_sail['commit']==commit
assert follow_sail['cli_sha256']==public['cli_sha256']
assert not follow_spark['remaining_listeners'] and not follow_sail['remaining_listeners']
assert len(follow_spark['cases'])==len(follow_sail['cases'])==8
assert all(a['expression']==b['expression'] and a['ansi']==b['ansi'] and a['rows']!=b['rows'] for a,b in zip(follow_spark['cases'],follow_sail['cases']))
print('REQUIRED FOLLOW-UP: ordinary IF/CASE early type introspection mismatches Spark8/8; retained, not resolved by NVL2')
