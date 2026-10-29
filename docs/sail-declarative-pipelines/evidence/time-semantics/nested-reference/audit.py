"""Verify retained nested TIME reference without executing Spark or Sail."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import subprocess

root = Path(__file__).resolve().parent
r = json.loads((root / 'results.json').read_text())
checks = []
def check(name, condition):
    checks.append({'name': name, 'passed': bool(condition)})
    assert condition, name
check('one bounded completed Spark4.2.1 run', r['completed'] and r['master']=='local[1]' and r['spark_version']=='4.2.1')
check('default TIME false then explicitly true', r['initial_time_enabled']=='false' and r['config']['spark.sql.timeType.enabled']=='true')
check('ten cases retained', len(r['cases'])==10)
for c in r['cases']:
    check(c['name']+' completed', c['outcome']=='passed')
    check(c['name']+' values', c['integer_values']==[c['expected_integer_value']])
    check(c['name']+' schemas retained', bool(c['schema']) and bool(c['schema_ddl']) and 'time64[ns]' in c['arrow_schema'])
for source in r['sources']:
    data = (root / source['file']).read_bytes()
    if 'commit' in source:
        raw = subprocess.check_output(['git','-C',source['repository'],'show',source['commit']+':'+source['path']],env={**os.environ,'GIT_NO_LAZY_FETCH':'1'})
        excerpt = b''.join(raw.splitlines(keepends=True)[source['first_line']-1:source['last_line']])
        blob = subprocess.check_output(['git','-C',source['repository'],'rev-parse',source['commit']+':'+source['path']]).decode().strip()
        check(source['file']+' pinned source', hashlib.sha256(raw).hexdigest()==source['source_sha256'] and blob==source['git_blob'])
        check(source['file']+' exact excerpt', data==excerpt and hashlib.sha256(data).hexdigest()==source['excerpt_sha256'])
    else:
        check(source['file']+' captured working-file hash', hashlib.sha256(data).hexdigest()==source['sha256'])
validation = {'created_at':datetime.now(timezone.utc).isoformat(),'runtime_runs_in_this_audit':0,'checks':checks}
(root/'validation.json').write_text(json.dumps(validation,indent=2)+'\n')
files=[]
for p in sorted(root.rglob('*')):
    if p.is_file() and p.name!='files.json':
        data=p.read_bytes()
        files.append({'path':p.relative_to(root).as_posix(),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
(root/'files.json').write_text(json.dumps({'created_at':datetime.now(timezone.utc).isoformat(),'files':files},indent=2)+'\n')
print(json.dumps({'checks_passed':len(checks),'retained_files_excluding_manifest':len(files),'bytes':sum(x['bytes'] for x in files),'runtime_runs':0}))
