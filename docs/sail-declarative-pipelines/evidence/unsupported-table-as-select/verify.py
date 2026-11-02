from pathlib import Path
import collections,hashlib,json,re,subprocess,xml.etree.ElementTree as ET
E=Path(__file__).resolve().parent;S='/Users/alexy/src/sail-pipelines-proposal';R='/Users/alexy/src/grust-sdp'
def read(p):return json.loads((E/p).read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for p,h in read('MANIFEST.json').items():assert sha(E/p)==h,p
summary=read('summary.json');assert not summary['full_conformance'] and not summary['original_scala_suite_executed_on_sail']
for label in ['unsupported-pipeline-ctas-01','unsupported-pipeline-ctas-02']:
 g=read(label+'/sail-sdp-'+label+'-gate.json');assert g['outcome']=='passed'
 for c in g['checks']:assert c['exit_code']==0 and sha(E/label/Path(c['log']).name)==c['sha256']
 assert sum(map(int,re.findall(r'test result: ok\. (\d+) passed;',(E/label/('sail-sdp-'+label+'-rust.log')).read_text())))==248
assert g['sail_commit']==summary['sail_commit']
p=read('public/receipt.json');assert p['outcome']=='passed'and p['sail_commit']==summary['sail_commit']and not p['remaining_listener_pids']
assert p['pytest']==dict(tests=300,failures=0,errors=0,skipped=0)
u=read('public/upstream.json');assert u['tests_run']==67 and not u['failures']and not u['errors']and not u['skipped']
records=[]
for mode in ['spark','sail']:
 r=read(mode+'-feature/observations.json');records.append(r);assert r['version']=='4.2.1'and r['pytest_exit_code']==0 and not r['remaining_listeners']
 cases=list(ET.parse(E/(mode+'-feature/pytest.xml')).iter('testcase'));assert len(cases)==6 and all(not list(t)for t in cases)
 source=subprocess.check_output(['git','-C',S,'show',summary['sail_commit']+':python/pysail/tests/spark/pipelines/test_unsupported_pipeline_statements.py']);assert hashlib.sha256(source).hexdigest()==r['test_sha256']
assert len(records[0]['cases'])==len(records[1]['cases'])==4
for a,b in zip(*(r['cases']for r in records)):
 for key in ['sql','error_type','condition','sql_state','parameters']:assert a[key]==b[key],key
 expected='ReplaceTableAsSelect'if a['label']in['replace','create-or-replace']else'CreateTableAsSelect'
 assert a['parameters']['message']==f'Unsupported plan {expected} parsed from SQL query'
 assert a['condition']=='PIPELINE_SQL_GRAPH_ELEMENT_REGISTRATION_ERROR'and a['sql_state']=='42000'
for name in ['producer','message']:
 c=read('control-'+name+'.json');assert c['base']==summary['sail_commit']and c['exit_code']==101
 log=E/('control-'+name+'.log');assert sha(log)==c['log_sha256']and '0 passed; 1 failed;'in log.read_text()
 assert subprocess.check_output(['git','-C',S,'diff','--name-only',c['base'],c['control']],text=True).strip()==c['path']
 for rev in[c['base'],c['control']]:assert subprocess.check_output(['git','-C',S,'rev-parse',rev+':'+c['test_path']],text=True).strip()==c['test_blob']
x=read('inventory-snapshot.json');old=json.loads(subprocess.check_output(['git','-C',R,'show','408ec930ca9fa0483afd20afeeab5bf0ee4d3492:docs/sail-declarative-pipelines/spark-4.2.1-inventory.json']));now={c['id']:c for c in x['cases']}
for c in old['cases']:
 if c['id']!=summary['changed_inventory_id']:assert c==now[c['id']]
assert now[summary['changed_inventory_id']]['coverage_review']['runtime_commit']==summary['sail_commit']
assert len(now)==486 and sum('coverage_review'in c for c in now.values())==116
assert dict(collections.Counter(c['status']for c in now.values()))=={'unmapped':399,'partial-behavioral-port':87}
next_oracle=read('next-insert-oracle/observations.json');assert len(next_oracle['cases'])==12 and not next_oracle['remaining_listeners']
for c in next_oracle['cases']:
 if 'if-not-exists'in c['label']:assert c['error_type']=='ParseException'and c['condition']=='INVALID_STATEMENT_OR_CLAUSE'and c['sql_state']=='42601'and c['parameters']=={'operation':'INSERT INTO ... IF NOT EXISTS'}
assert not summary['next_insert_sail_implemented']
print('PASS table-as-select248-native/300+67/paired6/four modes/two controls;only existing525 improved;next INSERT oracle preserved,no Sail claim')
