"""One-time provenance freeze. Does not run Spark or change retained observations."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
REPO = Path('/Users/alexy/src/spark-sdp-4.2.1')
PIN = '617618396087429b5627a86ce933bb0f5d6645cb'
DS = 'sql/core/src/main/scala/org/apache/spark/sql/execution/datasources/'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(name, value):
    (ROOT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


assert not (ROOT / 'MANIFEST.json').exists(), 'cannot rewrite a frozen packet'
r = json.loads((ROOT / 'results.json').read_text())
assert r['status'] == 'completed' and r['owned_gateway_exit_code'] == 0
sources = ROOT / 'sources'
sources.mkdir()
audit = {'repository': str(REPO), 'commit': PIN,
         'interpretation': 'Pinned source mechanisms match the observed nested case-policy reset and later duplicate validation; no installed-binary provenance claim.',
         'sources': []}
for path, ranges in [
    ('sql/api/src/main/scala/org/apache/spark/sql/types/StructType.scala', [(478,488),(592,663),(693,703)]),
    (DS + 'SchemaMergeUtils.scala', [(59,117)]),
    (DS + 'orc/OrcUtils.scala', [(181,218),(274,301)]),
    (DS + 'orc/OrcOptions.scala', [(62,69)]),
    (DS + 'DataSource.scala', [(455,470)]),
    ('sql/catalyst/src/main/scala/org/apache/spark/sql/util/SchemaUtils.scala', [(85,101),(146,155)]),
]:
    data = subprocess.check_output(['git', 'show', f'{PIN}:{path}'], cwd=REPO)
    target = sources / Path(path).name
    target.write_bytes(data)
    item = {'path': path, 'file': str(target.relative_to(ROOT)), 'sha256': sha(data),
            'git_blob': subprocess.check_output(['git','rev-parse',f'{PIN}:{path}'],cwd=REPO,text=True).strip(),
            'excerpts': []}
    lines = data.splitlines(keepends=True)
    for first, last in ranges:
        assert 0 < first <= last <= len(lines)
        excerpt = b''.join(lines[first-1:last])
        destination = sources / f'{target.stem}.{first}-{last}.scala.txt'
        destination.write_bytes(excerpt)
        item['excerpts'].append({'first_line': first, 'last_line': last,
                                'file': str(destination.relative_to(ROOT)), 'sha256': sha(excerpt)})
    audit['sources'].append(item)
for name in ['LICENSE','NOTICE']:
    (sources / f'SPARK-{name}').write_bytes(subprocess.check_output(['git','show',f'{PIN}:{name}'],cwd=REPO))
save('source-audit.json', audit)
ps = subprocess.run(['ps','-p',str(r['java']['actual_pid']),'-o','pid=,ppid=,lstart=,command='],capture_output=True,text=True)
assert ps.returncode == 1 and ps.stdout == ''
jars = Path('/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages/pyspark/jars')
artifacts = []
for name in ['spark-sql_2.13-4.2.1.jar','spark-sql-api_2.13-4.2.1.jar','spark-catalyst_2.13-4.2.1.jar']:
    path = jars / name
    artifacts.append({'path': str(path),'size': path.stat().st_size,'sha256': sha(path.read_bytes())})
save('summary.json', {'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
                     'spark_source_pin': PIN, 'harness_exit_code': 0, 'owned_gateway_exit_code': 0,
                     'owned_gateway_absence_check': {'command': ps.args,'exit_code':ps.returncode,'stdout':ps.stdout,'stderr':ps.stderr},
                     'installed_artifact_hashes': artifacts,
                     'launcher_attempts': [{'session_id':1642,'status':'completed','exit_code':0}],
                     'observations': {'fixtures':8,'file_read_cases':16,'successful_reads':13,'schema_analysis_errors':3,'direct_merge_diagnostics':8,'successful_merge_diagnostics':8},
                     'scope_limits': ['ASCII Value/value names; no general Unicode claim.',
                                      'Foreign PyArrow ORCs read with Spark native vectorized V1 path, not writer qualification.',
                                      'Direct merge outputs are labelled separately from file-read outcomes.',
                                      'Observed lower-case-first schema order is not a lexical file-ordering guarantee.',
                                      'No map-key struct, exact duplicate name, type-conflict, non-vectorized or Hive-reader coverage.',
                                      'Pre-execution formatted plans and returned rows, not physical I/O instrumentation.']})
files = []
for path in sorted(ROOT.rglob('*')):
    if path.is_file() and path.name != 'MANIFEST.json':
        data = path.read_bytes()
        files.append({'path':str(path.relative_to(ROOT)),'size':len(data),'sha256':sha(data)})
save('MANIFEST.json', {'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'files':files})
print(json.dumps({'files':len(files),'manifest_sha256':sha((ROOT/'MANIFEST.json').read_bytes())}))
