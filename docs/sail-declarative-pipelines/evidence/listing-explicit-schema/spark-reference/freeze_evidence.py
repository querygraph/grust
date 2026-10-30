"""One-time packet finalization; use validate_evidence.py for read-only validation."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
REPO = Path('/Users/alexy/src/spark-sdp-4.2.1')
PIN = '617618396087429b5627a86ce933bb0f5d6645cb'
BASE = 'sql/core/src/main/scala/org/apache/spark/sql/execution/datasources/'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, obj):
    path.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')


assert not (ROOT / 'MANIFEST.json').exists(), 'frozen packet must not be rewritten'
results=json.loads((ROOT/'results.json').read_text())
assert results['status']=='completed' and results['owned_gateway_exit_code']==0
sources=ROOT/'sources'
sources.mkdir()
audit={'repository':str(REPO),'commit':PIN,'sources':[],
       'interpretation':'Source mechanisms support the ten observed cases. These are pinned source blobs, not loaded-class instrumentation or proof that a binary was built from this commit.'}
for filename,ranges in [
    ('PartitioningUtils.scala',[(126,142),(182,213),(649,675)]),
    ('DataSource.scala',[(180,246),(435,449)]),
    ('PartitioningAwareFileIndex.scala',[(152,213)]),
    ('HadoopFsRelation.scala',[(54,59)]),
]:
    data=subprocess.check_output(['git','show',f'{PIN}:{BASE}{filename}'],cwd=REPO)
    target=sources/filename
    target.write_bytes(data)
    item={'path':BASE+filename,'file':str(target.relative_to(ROOT)),
          'git_blob':subprocess.check_output(['git','rev-parse',f'{PIN}:{BASE}{filename}'],cwd=REPO,text=True).strip(),
          'sha256':sha(data),'excerpts':[]}
    for first,last in ranges:
        excerpt=b''.join(data.splitlines(keepends=True)[first-1:last])
        dest=sources/f'{target.stem}.{first}-{last}.scala.txt'
        dest.write_bytes(excerpt)
        item['excerpts'].append({'first_line':first,'last_line':last,'file':str(dest.relative_to(ROOT)),'sha256':sha(excerpt)})
    audit['sources'].append(item)
for name in ['LICENSE','NOTICE']:
    data=subprocess.check_output(['git','show',f'{PIN}:{name}'],cwd=REPO)
    (sources/f'SPARK-{name}').write_bytes(data)
write_json(ROOT/'source-audit.json',audit)
ps=subprocess.run(['ps','-p',str(results['java']['actual_pid']),'-o','pid=,command='],capture_output=True,text=True)
assert ps.returncode==1 and ps.stdout==''
jars=Path('/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages/pyspark/jars')
artifacts=[]
for name in ['spark-sql_2.13-4.2.1.jar','spark-sql-api_2.13-4.2.1.jar']:
    p=jars/name
    artifacts.append({'path':str(p),'sha256':sha(p.read_bytes()),'size':p.stat().st_size})
summary={'recorded_at_utc':datetime.now(timezone.utc).isoformat(),
         'spark_source_pin':PIN,'harness_exit_code':0,'owned_gateway_exit_code':results['owned_gateway_exit_code'],
         'owned_gateway_absence_check':{'command':ps.args,'exit_code':ps.returncode,'stdout':ps.stdout,'stderr':ps.stderr},
         'installed_artifact_hashes':artifacts,
         'launcher_attempts':[{'status':'not_started','reason':'Initial exec requested not-yet-created working directory; process creation failed before shell, fixtures, or JVM started.'},
                              {'status':'success','session_id':31710,'exit_code':0}],
         'observations':{'cases':10,'filters':11,'fixtures':2,'all_spark_operations_succeeded':True},
         'scope_limits':['Two same-spelling partition directories, one non-null INT file field, vectorized native V1 ORC reader.',
                         'No mixed directory-key casing, duplicate partition keys, alternate types, nested partitions, null markers or non-vectorized qualification.',
                         'PartitionFilters and rows qualify planning/results; no runtime file-open instrumentation or scan byte-count guarantee.']}
write_json(ROOT/'summary.json',summary)
files=[]
for p in sorted(ROOT.rglob('*')):
    if p.is_file() and p.name!='MANIFEST.json':
        data=p.read_bytes()
        files.append({'path':str(p.relative_to(ROOT)),'size':len(data),'sha256':sha(data)})
write_json(ROOT/'MANIFEST.json',{'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'files':files})
print('Frozen',len(files),'files; MANIFEST SHA256',sha((ROOT/'MANIFEST.json').read_bytes()))
