from pathlib import Path
import hashlib,json,re,subprocess
p=Path(__file__).resolve().parent
r=json.loads((p/'observations.json').read_text())
assert r['engine']=='spark' and r['spark_version']=='4.2.1' and r['outcome']=='observed'
assert r['source_commit']=='617618396087429b5627a86ce933bb0f5d6645cb'
assert r['harness_sha256']==hashlib.sha256((p/'reference.py').read_bytes()).hexdigest()
assert r['listener_probe_after_stop']=={'exit_code':1,'stdout':''}
expected={
 'cte_shadows_graph':None,
 'cte_case_insensitive_shadow':None,
 'cte_unused_definition':'DUPLICATE_FLOW_SQL_CONF',
 'cte_used_definition':'UNRESOLVED_COLUMN.WITH_SUGGESTION',
 'cte_qualified_bypasses_shadow':'TABLE_OR_VIEW_NOT_FOUND',
 'cte_nested_shadow_unused_outer':'UNRESOLVED_COLUMN.WITH_SUGGESTION',
 'filter_subquery_before_child':'DUPLICATE_FLOW_SQL_CONF',
 'union_left_then_right':'DUPLICATE_FLOW_SQL_CONF',
 'union_right_then_left':'UNRESOLVED_COLUMN.WITH_SUGGESTION',
 'defaults_overridden_every_flow':None,
 'defaults_conflict_view_table':'DUPLICATE_FLOW_SQL_CONF',
 'defaults_same_value':None,
}
assert len(r['cases'])==12 and {c['name']for c in r['cases']}==set(expected)
for c in r['cases']:
 assert 'probe_error'not in c and c['session_case_sensitive']=='false'
 text=c.get('run_error','')+'\n'+'\n'.join(e['message']for e in c['events'])
 conditions=sorted(set(re.findall(r'\[([A-Z][A-Z_.]+)\]',text)))
 condition=expected[c['name']]
 assert conditions==([]if condition is None else[condition]),(c['name'],conditions)
 assert c['run_returned']==c['result_exists']==(condition is None)
 if condition is None:assert c['rows']==[{'foo'if c['name']=='defaults_same_value'else'Foo':1}]
source=json.loads((p/'source-audit.json').read_text())
assert source['source_commit']==r['source_commit']
for f in source['files']:
 data=subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','show',r['source_commit']+':'+f['path']])
 assert hashlib.sha256(data).hexdigest()==f['sha256']
 a,b=f['lines'];assert '\n'.join(data.decode().splitlines()[a-1:b])==f['excerpt']
print('PASS twelve exact Spark4.2.1 CTE/default probes and pinned source excerpts; no Sail parity verdict')
