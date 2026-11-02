from pathlib import Path
import hashlib,json,re,subprocess,xml.etree.ElementTree as ET
E=Path(__file__).resolve().parent
R='/Users/alexy/src/sail-pipelines-proposal';S='/Users/alexy/src/spark-sdp-4.2.1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def git(*a):return subprocess.check_output(['git','-C',R,*a],text=True).strip()
manifest=json.loads((E/'MANIFEST.json').read_text())
for p,h in manifest.items():assert sha(E/p)==h,p
c=json.loads((E/'native/candidate.json').read_text());g=json.loads((E/'native/gate.json').read_text())
assert g['outcome']=='passed' and g['sail_commit']==c['commit']
assert [x['name']for x in g['checks']]==['fmt','clippy','rust']
for x in g['checks']:
 assert x['exit_code']==0 and sha(E/'native'/Path(x['log']).name.split('metadata-streaming-06-')[1])==x['sha256']
log=(E/'native/rust.log').read_text();assert '189 passed; 0 failed; 0 ignored;' in log
for name in ['multiple_streaming_targets_materialize_nullable_columns_without_rows','streaming_target_preserves_declared_schema_and_identity_partition','ordinary_streaming_refresh_merges_schema_without_truncating_rows','unsupported_full_reset_and_public_execution_reject_before_catalog_effects']:
 assert f'pipelines::materialize::tests::{name} ... ok' in log
control=json.loads((E/'control/control.json').read_text());assert control['base']==c['commit'] and control['exit_code']==101
assert sha(E/'control/control.log')==control['log_sha256'];assert '1 passed; 3 failed;' in (E/'control/control.log').read_text()
assert git('diff','--name-only',c['commit'],control['control'])==control['path']
assert git('rev-parse',c['commit']+':'+control['test_path'])==control['test_blob']==git('rev-parse',control['control']+':'+control['test_path'])
assert git('rev-parse',c['base']+':Cargo.lock')==git('rev-parse',c['commit']+':Cargo.lock')
for directory,passes in [('internal-materialization',2),('internal-refresh',1)]:
 root=E/'spark'/directory;r=json.loads((root/'receipt.json').read_text());assert len(r['checks'])==3 and all(x['exit_code']==0 for x in r['checks'])
 for x in r['checks']:assert sha(root/Path(x['log']).name)==x['sha256']
 assert (root/'check-2.log').read_text().count('SDP_ORACLE_PASS')==passes
 helper=subprocess.check_output(['git','-C',S,'show',r['spark_source_commit']+':sql/pipelines/src/test/scala/org/apache/spark/sql/pipelines/utils/TestGraphRegistrationContext.scala'])
 assert (root/'TestGraphRegistrationContext.scala').read_bytes()==helper
pub=json.loads((E/'public/receipt.json').read_text());assert pub['outcome']=='passed' and pub['sail_commit']==c['commit'] and pub['remaining_listener_pids']==[]
tests=list(ET.parse(E/'public/pytest.xml').iter('testcase'));assert len(tests)==300 and all(not list(t)for t in tests)
u=json.loads((E/'public/upstream.json').read_text());assert u['tests_run']==67 and u['failures']==u['errors']==u['skipped']==0 and u['server_spark_version']=='4.2.1'
delta=json.loads((E/'inventory-delta.json').read_text());assert len(delta['changed_ids'])==2 and delta['after']=={'partial-behavioral-port':65,'unmapped':397} and not delta['scala_suite_executed']
print('PASS internal metadata source/native189/control1pass3fail/Spark3 assertions/public300+67/two partial inventory ports')
