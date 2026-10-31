from pathlib import Path
import hashlib,json,subprocess,xml.etree.ElementTree as ET
E=Path(__file__).resolve().parent;S='/Users/alexy/src/sail-pipelines-proposal'
def read(p):return json.loads((E/p).read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',S,*args])
for f,h in read('MANIFEST.json').items():assert sha(E/f)==h,f
commits=[]
for label in ['truncate-cache','full-refresh-aux']:
 c=read(label+'/sail-sdp-'+label+'-candidate.json');g=read(label+'/sail-sdp-'+label+'-gate.json');commits.append(c['commit'])
 assert g['sail_commit']==c['commit'] and g['outcome']=='passed'
 for x in g['checks']:assert x['exit_code']==0 and sha(E/label/Path(x['log']).name)==x['sha256']
 assert 'Co-Authored-By: Claude Fable 5.1'in git('show','-s','--format=%B',c['commit']).decode()
assert git('show',commits[0]+':crates/sail-catalog/src/command.rs')==git('show','a0b3cecb2:crates/sail-catalog/src/command.rs')
c=read('full-refresh-aux/sail-sdp-full-refresh-aux-candidate.json');assert c['base']==commits[0]
for path in ['crates/sail-spark-connect/src/pipelines/autocdc/mod.rs','crates/sail-spark-connect/src/pipelines/autocdc/auxiliary.rs','crates/sail-spark-connect/src/pipelines/materialize.rs','crates/sail-spark-connect/src/pipelines/materialize/tests.rs','crates/sail-spark-connect/src/pipelines/mod.rs']:
 assert git('show',commits[1]+':'+path)==git('show','bd782c422:'+path)
text=(E/'full-refresh-aux/sail-sdp-full-refresh-aux-rust.log').read_text()
assert '20 passed; 0 failed;'in text and '214 passed; 0 failed;'in text
p=read('public/receipt.json');assert p['sail_commit']==commits[1] and p['outcome']=='passed' and p['before']==p['after'] and not p['remaining_listener_pids']
assert p['pytest']==dict(tests=300,failures=0,errors=0,skipped=0)
for f,h in p['artifact_sha256'].items():assert sha(E/'public'/f)==h
u=read('public/upstream.json');assert u['tests_run']==67 and not any(u[k]for k in ['errors','failures','skipped'])
r=read('paired/observations.json');assert r['pytest_exit_code']==0 and r['runtime_commit']==commits[1] and r['cli_sha256']==p['cli_sha256'] and not r['remaining_listeners'] and r['server_exit_code']==0
for path,h in r['source_sha256'].items():assert hashlib.sha256(git('show',commits[1]+':'+path)).hexdigest()==h
cases=list(ET.parse(E/'paired/pytest.xml').iter('testcase'));assert len(cases)==10 and all(not [x for x in case if x.tag in ['failure','error','skipped']]for case in cases)
print('PASS Fable A1 integration:20 catalog+214 Connect/fmt/strict Clippy/public300+67/ten phase regressions; CDC writes remain disabled')
