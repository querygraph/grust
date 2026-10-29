from pathlib import Path
import datetime, hashlib, json, os, shutil, subprocess, tempfile
sail=Path('/Users/alexy/src/sail-sdp-gate')
sha=subprocess.check_output(['git','-C',str(sail),'rev-parse','HEAD'],text=True).strip()
assert sha=='ac7bff5007545859b6c972e2d9b9a17ffc38fa97'
assert not subprocess.check_output(['git','-C',str(sail),'status','--porcelain'],text=True).strip()
root=Path(tempfile.mkdtemp(prefix='sail-sdp-plan-gold-'))
source=sail/'crates/sail-spark-connect/tests/gold_data/plan'
output=root/'tests/gold_data/plan'
shutil.copytree(source,output)
binary=sail/'target/debug/deps/sail_spark_connect-94a7bcff04b1a816'
with (root/'generation.log').open('w') as log:
    subprocess.run([str(binary),'proto::plan::tests::test_sql_to_plan','--exact','--nocapture'],cwd=root,env={**os.environ,'SAIL_UPDATE_GOLD_DATA':'1'},stdout=log,stderr=subprocess.STDOUT,check=True)
changes=[]
for old in sorted(source.glob('*.json')):
    before=json.loads(old.read_text());after=json.loads((output/old.name).read_text())
    assert len(before['tests'])==len(after['tests'])
    cases=[]
    for i,(a,b) in enumerate(zip(before['tests'],after['tests'])):
        assert a['input']==b['input']
        assert a.get('exception')==b.get('exception')
        if a!=b:cases.append({'index':i,'input':a['input'],'before':a['output'],'after':b['output']})
    if cases: changes.append({'file':old.name,'cases':cases})
report={'recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sail_commit':sha,'scratch':str(root),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'fixture_files':len(list(source.glob('*.json'))),'changed_files':len(changes),'changed_cases':sum(len(x['cases']) for x in changes),'changes':changes}
Path('/tmp/sail-sdp-plan-gold-inspection.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='changes'},indent=2))
for change in changes:print(change['file'],len(change['cases']))
