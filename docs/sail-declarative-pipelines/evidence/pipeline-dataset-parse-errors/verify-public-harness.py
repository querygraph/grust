from pathlib import Path
import hashlib,json,subprocess
E=Path(__file__).resolve().parent;H=E/'public-harness';S='/Users/alexy/src/sail-pipelines-proposal'
def sha(data):return hashlib.sha256(data).hexdigest()
old=json.loads((H/'preparation-before-parser-alignment.json').read_text());new=json.loads((H/'preparation.json').read_text());a=new['oracle_alignment'];commit=new['sail_commit']
assert sha((H/'preparation-before-parser-alignment.json').read_bytes())==a['previous_preparation_sha256']
assert all(new['source_sha256'][p]==h for p,h in old['source_sha256'].items())
assert set(new['source_sha256'])-set(old['source_sha256'])==set(a['newly_bound_indirect_inputs']) and len(a['newly_bound_indirect_inputs'])==23
assert new['selected_nodes_sha256']==old['selected_nodes_sha256']==sha((H/'selected-nodes.json').read_bytes())
assert len(json.loads((H/'selected-nodes.json').read_text()))==300
for path,h in new['source_sha256'].items():assert sha(subprocess.check_output(['git','-C',S,'show',commit+':'+path]))==h,path
path=a['changed_assertion_source'];before=subprocess.check_output(['git','-C',S,'show','19b7e9c0527a1c48790909d7d0631b194f4fddb7:'+path]);after=subprocess.check_output(['git','-C',S,'show',commit+':'+path])
assert before.replace(b'Given pipeline SQL file location.sql fails with location.sql',b'Given pipeline SQL file location.sql fails with Specifying location is not supported')==after
assert sha(before)==a['previous_source_sha256'] and sha(after)==a['current_source_sha256']
print('PASS same300 nodes and every old source hash;23 newly bound fixture sources;one exact oracle-aligned BDD line')

for path,h in json.loads((H/"MANIFEST.json").read_text()).items():assert sha((H/path).read_bytes())==h,path
