from pathlib import Path
import hashlib,json,re,xml.etree.ElementTree as ET
E=Path(__file__).resolve().parent
for p,h in json.loads((E/'MANIFEST.json').read_text()).items():assert hashlib.sha256((E/p).read_bytes()).hexdigest()==h,p
g=json.loads((E/'native/sail-sdp-pipeline-dataset-clauses-01-gate.json').read_text());assert g['sail_commit']=='7d7c3640fd780499cfa9658a4501c97d82c11f29' and g['outcome']=='passed'
for c in g['checks']:assert c['exit_code']==0 and hashlib.sha256((E/'native'/Path(c['log']).name).read_bytes()).hexdigest()==c['sha256']
assert sum(map(int,re.findall(r'test result: ok\. (\d+) passed;',(E/'native/sail-sdp-pipeline-dataset-clauses-01-rust.log').read_text())))==262
spark=json.loads((E/'spark/observations.json').read_text());assert spark['pytest_exit_code']==0 and not spark['remaining_listeners']
tests=list(ET.parse(E/'spark/pytest.xml').iter('testcase'));assert len(tests)==11 and all(not list(t)for t in tests)
assert len(spark['cases'])==11 and all(c['error_type']=='ParseException' and c['condition']=='_LEGACY_ERROR_TEMP_0035' and c['sql_state']is None for c in spark['cases'])
f=json.loads((E/'failed-public-registration-wrapper/receipt.json').read_text());assert f['outcome']=='failed' and f['sail_commit']==g['sail_commit'] and not f['remaining_listener_pids']
assert f['pytest']==dict(tests=300,failures=1,errors=0,skipped=0)
tests=list(ET.parse(E/'failed-public-registration-wrapper/pytest.xml').iter('testcase'));bad=[t for t in tests if list(t)];assert len(tests)==300 and len(bad)==1 and bad[0].attrib['name']=='test_dataset_location_is_rejected_during_registration'
assert 'location.sql'in ''.join(bad[0].itertext())
print('PASS historical candidate262/Spark11 and preserved Sail299/1 failure of old filename expectation')
# Final qualification follows the separately preserved reference correction.
G=E/'native-final';g=json.loads((G/'sail-sdp-pipeline-dataset-clauses-02-gate.json').read_text());assert g['sail_commit']=='14eb7766f7efc3c39b1df0df396d13cd9551dc7d' and g['outcome']=='passed'
for c in g['checks']:assert c['exit_code']==0 and hashlib.sha256((G/Path(c['log']).name).read_bytes()).hexdigest()==c['sha256']
assert sum(map(int,re.findall(r'test result: ok\. (\d+) passed;',(G/'sail-sdp-pipeline-dataset-clauses-02-rust.log').read_text())))==271
f=json.loads((E/'public-final/receipt.json').read_text());assert f['outcome']=='passed' and f['sail_commit']==g['sail_commit'] and not f['remaining_listener_pids']
assert f['pytest']==dict(tests=300,failures=0,errors=0,skipped=0)
for mode in ['spark','sail']:
 root=E/(mode+'-final');r=json.loads((root/'observations.json').read_text());assert r['pytest_exit_code']==0 and not r['remaining_listeners']
 tests=list(ET.parse(root/'pytest.xml').iter('testcase'));assert len(tests)==22 and all(not list(t)for t in tests)
a=json.loads((E/'registration-oracle-spark/observations.json').read_text());b=json.loads((E/'registration-oracle-sail/observations.json').read_text());assert len(a['cases'])==len(b['cases'])==11
for x,y in zip(a['cases'],b['cases']):
 for k in ['sql','error_type','condition','sql_state','parameters','contains_filename','table_exists']:assert x[k]==y[k],k
 assert x['error_type']=='ParseException' and not x['contains_filename'] and not x['table_exists']
print('PASS final271-native,300 public and22 paired tests;raw parser registration error is the reference contract')

u=json.loads((E/'public-final/upstream.json').read_text());assert u['tests_run']==67 and not u['failures'] and not u['errors'] and not u['skipped']
print('PASS all67 original upstream Python executions')
import subprocess,collections
S='/Users/alexy/src/sail-pipelines-proposal'
for name in ['validation','state']:
 c=json.loads((E/('control-'+name+'.json')).read_text());log=E/('control-'+name+'.log')
 assert c['base']==g['sail_commit'] and c['exit_code']==101 and hashlib.sha256(log.read_bytes()).hexdigest()==c['log_sha256'] and '0 passed; 1 failed;'in log.read_text()
 assert subprocess.check_output(['git','-C',S,'diff','--name-only',c['base'],c['control']],text=True).strip()==c['path']
 for rev in [c['base'],c['control']]:assert subprocess.check_output(['git','-C',S,'rev-parse',rev+':'+c['test_path']],text=True).strip()==c['test_blob']
x=json.loads((E/'inventory-snapshot.json').read_text());old=json.loads((E.parent/'pipeline-parser-positive/inventory-snapshot.json').read_text());new={c['id']:c for c in x['cases']};ids={c['id']for c in json.loads((E/'assertion-ledger.json').read_text())['cases']};assert len(ids)==7
for c in old['cases']:
 if c['id']not in ids:assert c==new[c['id']]
for key in ids:assert new[key]['status']=='partial-behavioral-port' and new[key]['coverage_review']['runtime_commit']==g['sail_commit']
assert len(new)==486 and sum('coverage_review'in c for c in new.values())==116
assert dict(collections.Counter(c['status']for c in new.values()))=={'unmapped':399,'partial-behavioral-port':87}
print('PASS unchanged-test0/1 controls and exact7 accepted coverage changes;116reviewed87partial399unmapped')
