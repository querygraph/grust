"""Read-only offline validation of ten retained Spark partition observations."""
import hashlib
import json
from pathlib import Path
import subprocess

import pyarrow.orc as orc

ROOT=Path(__file__).resolve().parent
PIN='617618396087429b5627a86ce933bb0f5d6645cb'


def sha(data):
    return hashlib.sha256(data).hexdigest()


manifest=json.loads((ROOT/'MANIFEST.json').read_text())
for f in manifest['files']:
    data=(ROOT/f['path']).read_bytes()
    assert len(data)==f['size'] and sha(data)==f['sha256'],f['path']
r=json.loads((ROOT/'results.json').read_text())
s=json.loads((ROOT/'summary.json').read_text())
assert r['status']=='completed' and r['spark_version']=='4.2.1'
assert r['spark_source_pin']==PIN
assert r['script_sha256']==sha((ROOT/'probe.py').read_bytes())
assert r['owned_gateway_exit_code']==s['harness_exit_code']==0
assert r['java']['gateway_pid']==r['java']['actual_pid']==16218
assert r['spark_context']=={'master':'local[1]','driver_memory':'512m'}
assert s['owned_gateway_absence_check']['exit_code']==1
assert not s['owned_gateway_absence_check']['stdout']
assert len(r['fixtures'])==2 and len(r['cases'])==10
for part,ids in [('west',[11,12]),('east',[21])]:
    f=r['fixtures'][part]
    assert f['status']=='success'
    p=ROOT/'inputs'/f'part={part}'/'data.orc'
    assert sha(p.read_bytes())==f['sha256']
    table=orc.ORCFile(p).read()
    assert table.column_names==['id'] and table.column(0).to_pylist()==ids
filters=0
for c in r['cases']:
    assert c['status']=='success' and c['arrow']['num_rows']==3
    label=c['name'].split('_sensitive_')[0]
    cs=c['config']['spark.sql.caseSensitive']=='true'
    expected_names=['part'] if label=='empty' else ['id','part']
    if label=='alias':
        expected_names=['PART','id','part'] if cs else ['id','PART']
    fields=c['read_schema']['fields']
    assert [f['name'] for f in fields]==expected_names
    assert all(f['nullable'] for f in fields)
    assert c['output_schema']==c['read_schema']
    cols={f['name']:f['values'] for f in c['arrow']['columns']}
    if label!='empty':
        assert cols['id']==[11,12,21]
    partition='PART' if label=='alias' and not cs else 'part'
    assert cols[partition]==['west','west','east']
    if label=='alias' and cs:
        assert cols['PART']==[None,None,None]
    for f in c['filters']:
        filters+=1
        assert f['status']=='success'
        if label=='alias' and cs and f['field']=='PART':
            assert f['arrow']['num_rows']==0
            assert 'PartitionFilters:' not in f['physical_plan']
            assert 'PushedFilters: [IsNotNull(PART), EqualTo(PART,west)]' in f['physical_plan']
        else:
            assert f['arrow']['num_rows']==2
            assert 'PartitionFilters:' in f['physical_plan']
            assert all(row[partition]=='west' for row in f['arrow']['rows'])
        if label=='empty':
            assert 'ReadSchema: struct<>' in f['physical_plan']
    assert c['config']['spark.sql.orc.enableVectorizedReader']=='true'
    assert c['config']['spark.sql.session.timeZone']=='UTC'
assert filters==11
audit=json.loads((ROOT/'source-audit.json').read_text())
assert audit['commit']==PIN
for source in audit['sources']:
    data=(ROOT/source['file']).read_bytes()
    assert sha(data)==source['sha256']
    assert data==subprocess.check_output(['git','show',f'{PIN}:{source["path"]}'],cwd=audit['repository'])
    for e in source['excerpts']:
        expected=b''.join(data.splitlines(keepends=True)[e['first_line']-1:e['last_line']])
        assert (ROOT/e['file']).read_bytes()==expected
        assert sha(expected)==e['sha256']
print('PASS: ten cases, eleven filters, two ORC fixtures, four pinned source files; no Spark execution')
