from pathlib import Path
import hashlib,json,subprocess,re,collections
E=Path(__file__).resolve().parent;D=E.parent.parent
S='/Users/alexy/src/sail-pipelines-proposal';R='/Users/alexy/src/grust-sdp';SP='/Users/alexy/src/spark-sdp-4.2.1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for p,h in json.loads((E/'MANIFEST.json').read_text()).items():assert sha(E/p)==h,p
c=json.loads((E/'sail-sdp-pipeline-parser-positive-01-candidate.json').read_text());g=json.loads((E/'sail-sdp-pipeline-parser-positive-01-gate.json').read_text())
assert g['outcome']=='passed' and c['commit']==g['sail_commit']=='19b7e9c0527a1c48790909d7d0631b194f4fddb7'
for x in g['checks']:assert x['exit_code']==0 and sha(E/Path(x['log']).name)==x['sha256']
assert re.findall(r'test result: ok\. (\d+) passed;',(E/'sail-sdp-pipeline-parser-positive-01-rust.log').read_text())==['40']
paths=subprocess.check_output(['git','-C',S,'diff','--name-only',c['base'],c['commit']],text=True).splitlines();assert set(paths)==set(c['paths']) and all('/pipeline/tests' in p for p in paths)
x=json.loads((E/'inventory-snapshot.json').read_text());by={c['id']:c for c in x['cases']}
legacy=json.loads(subprocess.check_output(['git','-C',R,'show','e14f64dcdc5ddebcac628706237177037b64ecf2:docs/sail-declarative-pipelines/spark-4.2.1-inventory.json']))
delta=json.loads((E/'inventory-delta.json').read_text());ids={c['id']for c in delta};assert len(ids)==9
for before in legacy['cases']:
 if before['id']not in ids:assert before==by[before['id']],before['id']
for row in delta:
 now=by[row['id']];assert now['status']=='partial-behavioral-port' and row['native_test']in now['sail_tests']
 data=subprocess.check_output(['git','-C',SP,'show',x['spark_commit']+':'+now['source']]);assert hashlib.sha256(data).hexdigest()==row['source_sha256']
assert len(by)==486 and sum('coverage_review'in c for c in by.values())==109
assert dict(collections.Counter(c['status']for c in by.values()))=={'unmapped':406,'partial-behavioral-port':80}
print('PASS test-only40,9 exact source-bound partial ports,109reviewed80partial406unmapped; pending diagnostics unpromoted')
