from pathlib import Path
import hashlib,json,subprocess,xml.etree.ElementTree as ET
E=Path(__file__).resolve().parent;R='/Users/alexy/src/sail-pipelines-proposal';S='/Users/alexy/src/spark-sdp-4.2.1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def git(*a):return subprocess.check_output(['git','-C',R,*a],text=True).strip()
for p,h in json.loads((E/'MANIFEST.json').read_text()).items():assert sha(E/p)==h,p
c=json.loads((E/'native/candidate.json').read_text());g=json.loads((E/'native/gate.json').read_text());assert g['outcome']=='passed' and g['sail_commit']==c['commit']
assert [x['name']for x in g['checks']]==['fmt','clippy','rust']
for x in g['checks']:assert x['exit_code']==0 and sha(E/'native'/Path(x['log']).name.split('metadata-partition-errors-02-')[1])==x['sha256']
assert '191 passed; 0 failed; 0 ignored;' in (E/'native/rust.log').read_text()
control=json.loads((E/'control/control.json').read_text());assert control['base']==c['commit'] and control['exit_code']==101
assert sha(E/'control/control.log')==control['log_sha256'];assert '0 passed; 2 failed;' in (E/'control/control.log').read_text()
assert git('diff','--name-only',c['commit'],control['control'])==control['path']
assert git('rev-parse',c['commit']+':'+control['test_path'])==control['test_blob']==git('rev-parse',control['control']+':'+control['test_path'])
assert git('rev-parse',c['base']+':Cargo.lock')==git('rev-parse',c['commit']+':Cargo.lock')
assert git('rev-parse',c['base']+':crates/sail-spark-connect/src/pipelines/execution.rs')==git('rev-parse',c['commit']+':crates/sail-spark-connect/src/pipelines/execution.rs')
spark=json.loads((E/'spark/receipt.json').read_text());assert len(spark['checks'])==3 and all(x['exit_code']==0 for x in spark['checks'])
for x in spark['checks']:assert sha(E/'spark'/Path(x['log']).name)==x['sha256']
log=(E/'spark/check-2.log').read_text();assert log.count('SDP_ORACLE_ERROR')==3 and log.count('SDP_ORACLE_PASS')==1
helper=subprocess.check_output(['git','-C',S,'show',spark['spark_source_commit']+':sql/pipelines/src/test/scala/org/apache/spark/sql/pipelines/utils/TestGraphRegistrationContext.scala']);assert (E/'spark/TestGraphRegistrationContext.scala').read_bytes()==helper
pub=json.loads((E/'public/receipt.json').read_text());assert pub['outcome']=='passed' and pub['sail_commit']==c['commit'] and pub['remaining_listener_pids']==[]
tests=list(ET.parse(E/'public/pytest.xml').iter('testcase'));assert len(tests)==300 and all(not list(t)for t in tests)
u=json.loads((E/'public/upstream.json').read_text());assert u['tests_run']==67 and u['failures']==u['errors']==u['skipped']==0 and u['server_spark_version']=='4.2.1'
delta=json.loads((E/'inventory-delta.json').read_text());assert len(delta['changed_ids'])==3 and delta['after']=={'unmapped':394,'partial-behavioral-port':68} and not delta['scala_suite_executed']
print('PASS structured materialization cause/native191/control0of2/Spark3cases/public300+67/three partial ports')
