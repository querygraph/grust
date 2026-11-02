from pathlib import Path
import hashlib,json,subprocess,xml.etree.ElementTree as ET
E=Path(__file__).resolve().parent;D=E.parent.parent;R='/Users/alexy/src/grust-sdp';S='/Users/alexy/src/spark-sdp-4.2.1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
for p,h in json.loads((E/'MANIFEST.json').read_text()).items():assert sha(E/p)==h,p
summary=json.loads((E/'summary.json').read_text());assert not summary['sail_executed'] and summary['registered_names']==554 and summary['nonempty_suites']==35
g=json.loads((E/'qualified/gate.json').read_text());assert g['commit']==summary['tool_commit'] and g['outcome']=='passed'
for check in g['checks']:assert check['exit_code']==0 and sha(E/'qualified'/Path(check['log']).name)==check['sha256']
collect=json.loads((E/'qualified/collect/receipt.json').read_text());assert collect['outcome']=='passed' and len(collect['bindings'])==47
for name,h in collect['tool_sha256'].items():
 data=subprocess.check_output(['git','-C',R,'show',g['commit']+':scripts/sdp-scala-reference/'+name]);assert hashlib.sha256(data).hexdigest()==h
for binding in collect['bindings']:
 data=subprocess.check_output(['git','-C',S,'show',collect['source_pin']+':'+binding['source']]);assert hashlib.sha256(data).hexdigest()==binding['sha256']
rows=json.loads((E/'qualified/collect/suites.json').read_text());assert sum(bool(r['testNames'])for r in rows)==35 and sum(len(r['testNames'])for r in rows)==554
assert sum(r['status']=='registered'for r in rows)==36 and not any(r['status']=='unresolved'or r['tags']or r['nestedSuiteIds']for r in rows)
assert sha(E/'qualified/collect/suites.json')==collect['output_sha256']['suites.json']
for label in ['default','hive']:
 root=E/'qualified'/label;r=json.loads((root/'receipt.json').read_text());assert r['outcome']=='passed' and r['tool_sha256']==collect['tool_sha256'] and r['runtime_sha256']==collect['runtime_sha256']
 for check in r['checks']:assert check['exit_code']==0 and sha(root/check['log'])==check['sha256']
 tests=[t for p in (root/'xml').glob('*.xml')for t in ET.parse(p).iter('testcase')];assert len(tests)==29 and all(not list(t)for t in tests)
 for name,h in r['output_sha256'].items():assert sha(root/name)==h
failed=json.loads((E/'bootstrap/materialize-hive-attempt-01/receipt.json').read_text());assert failed['exit_code']!=0 and 'SparkEnv' in (E/'bootstrap/materialize-hive-attempt-01/run.log').read_text()
# Historical counters are bound to their original immutable documentation snapshot.
SNAPSHOT='3806b1bc58cf466c5146ca0f6829a3632701aaec'
def historical(name):return json.loads(subprocess.check_output(['git','-C',R,'show',SNAPSHOT+':docs/sail-declarative-pipelines/'+name]))
exp=historical('spark-4.2.1-scope-expansion.json');assert exp['completion_blocker'] and len(exp['cases'])==exp['additional_identified_declarations']==20 and not exp['owned_runtime_is_complete_goal_denominator']
for name,h in exp['source_sha256'].items():
 data=subprocess.check_output(['git','-C',S,'show',exp['spark_commit']+':'+name]);assert hashlib.sha256(data).hexdigest()==h
assert any(c['source'].endswith('/CreateStreamingTableParserSuite.scala')and c['line']==31 for c in exp['cases'])
legacy=historical('spark-4.2.1-inventory.json');assert len(legacy['cases'])==462 and all(c['id']not in {x['id']for x in legacy['cases']}for c in exp['cases'])
print('PASS exact reference tool,47 source bindings,554 owned names,58 original Spark passes;20 outside declarations open; no Sail promotion')
