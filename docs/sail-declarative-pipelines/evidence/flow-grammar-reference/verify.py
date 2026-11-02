from pathlib import Path
import hashlib,json
E=Path(__file__).resolve().parent
for f,h in json.loads((E/'MANIFEST.json').read_text()).items():
    assert hashlib.sha256((E/f).read_bytes()).hexdigest()==h,f
s=json.loads((E/'summary.json').read_text())
assert not s['sail_implemented'] and not s['full_conformance'] and not s['inventory_changed']
r=json.loads((E/'spark/observations.json').read_text())
assert r['version']=='4.2.1' and not r['remaining_listeners'] and not r['cleanup_errors']
inputs=json.loads((E/'inputs.json').read_text());assert len(inputs)==len(r['cases'])==16
assert r['script_sha256']==hashlib.sha256((E/'probe.py').read_bytes()).hexdigest()
for a,b in zip(inputs,r['cases']):assert a['label']==b['label'] and a['sql']==b['sql']
for c in r['cases']:
    if c['label'] in ['ordinary-with','overwrite-partition-ifne','flow-directory-using','flow-directory-hive','flow-replace-where','flow-replace-using']:
        assert c['condition']=='PIPELINE_SQL_GRAPH_ELEMENT_REGISTRATION_ERROR' and c['sql_state']=='42000'
    elif c['label']=='flow-query-with':assert c['outcome']=='accepted'
    else:
        assert c['error_type']=='ParseException' and c['condition']=='PARSE_SYNTAX_ERROR' and c['sql_state']=='42601'
        token={'flow-query':'SELECT','flow-with':'WITH','flow-ddl':'CREATE','flow-explain':'EXPLAIN','flow-nested':'CREATE'}.get(c['label'],'IF')
        assert c['parameters']=={'error':"'"+token+"'",'hint':''}
assert inputs[:12]==json.loads((E/'inputs-initial12.json').read_text())
for c in r['cases'][12:]:
    expected='INSERT OVERWRITE flows not supported.' if c['label']=='flow-replace-using' else 'Unable flow type. Only INSERT INTO flows are supported.'
    assert c['parameters']['message']==expected
print('PASS sixteen Spark registration vectors;grammar/error design only,no Sail implementation claim')
