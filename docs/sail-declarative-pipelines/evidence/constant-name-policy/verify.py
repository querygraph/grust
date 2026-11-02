from pathlib import Path
import hashlib,json,re,subprocess,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent
SAIL='/Users/alexy/src/sail-pipelines-proposal'
PRIOR=HERE.parent/'constant-context-lowering'
def load(path):return json.loads((HERE/path).read_text())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',SAIL,*args],text=True).strip()
m=load('SHA256.json')
assert set(m)=={str(p.relative_to(HERE)) for p in HERE.rglob('*') if p.is_file() and p.name!='SHA256.json'}
for path,sha in m.items():assert digest(HERE/path)==sha,path
c=load('native/candidate.json');final=c['commit']
assert c['base']==git('rev-parse',final+'^')=='3ffb497d3e5dcbb48c56a5dd06687044ef994508'
assert subprocess.check_output(['git','-C',SAIL,'diff',c['base'],final])==(HERE/'native/source.patch').read_bytes()
r=load('native/gate.json');assert r['sail_commit']==final and r['outcome']=='passed'
for check in r['checks']:assert check['exit_code']==0 and digest(HERE/'native'/(check['name']+'.log'))==check['sha256']
assert re.findall(r'test result: ok\. (\d+) passed; 0 failed;', (HERE/'native/rust.log').read_text())==['101','177']
r=load('public/receipt.json');assert r['sail_commit']==final and r['outcome']=='passed' and r['before']==r['after']
assert r['pytest']=={'tests':300,'failures':0,'errors':0,'skipped':0}
assert r['upstream']=={'tests_run':67,'failures':0,'errors':0,'skipped':0,'server_spark_version':'4.2.1'}
assert all(check['exit_code']==0 for check in r['checks']) and r['server_exit_code']==0 and r['remaining_listener_pids']==[]
for path,sha in r['artifact_sha256'].items():assert digest(HERE/'public'/path)==sha
for folder,old,count,probe in [('arithmetic','candidate',14,PRIOR/'reference.py'),('provenance','provenance',20,HERE.parent/'identifier-function-provenance/reference.py')]:
 receipt=load(folder+'/receipt.json');observed=load(folder+'/probe/observations.json')
 assert receipt['before']==receipt['after'] and receipt['before']['sail_commit']==final
 assert receipt['before']['cli_sha256']==r['cli_sha256']
 assert receipt['before']['probe_sha256']==observed['harness_sha256']==digest(probe)
 assert len(observed['cases'])==count and observed['spark_version']=='4.2.1'
 assert receipt['server_exit_code']==receipt['probe_exit_code']==0 and receipt['remaining_listener_pids']==[]
 for f in receipt['files']:assert digest(HERE/folder/f['path'])==f['sha256']
 previous=json.loads((PRIOR/old/'probe/observations.json').read_text())
 assert observed['cases']==previous['cases'],folder+' outcome or metadata changed'
assert load('provenance/receipt.json')['parameter_tests']['exit_code']==0
suite=ET.parse(HERE/'provenance/parameters.xml').getroot().find('testsuite')
assert tuple(suite.get(k) for k in ['tests','failures','errors','skipped'])==('4','0','0','0')
print('PASS exact101+177, strict Clippy/fmt, fresh300+67, parameter4; 14+20 outcomes/metadata unchanged; full original Scala acceptance remains open')
