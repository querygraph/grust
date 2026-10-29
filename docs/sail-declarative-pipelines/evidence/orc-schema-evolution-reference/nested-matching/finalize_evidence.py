"""Validate retained observations and capture exact installed class/source evidence."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent
SPARK = Path('/Users/alexy/src/spark-sdp-4.2.1')
PIN = '617618396087429b5627a86ce933bb0f5d6645cb'
JAR = Path('/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages/pyspark/jars/orc-core-2.3.0-shaded-protobuf.jar')
JAVAP = '/Library/Java/JavaVirtualMachines/jdk-20.jdk/Contents/Home/bin/javap'

def sha(data): return hashlib.sha256(data).hexdigest()
def save(name, value): (ROOT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
def git(*args): return subprocess.check_output(['git', '-C', str(SPARK), *args])

classes = []
with zipfile.ZipFile(JAR) as archive:
    assert not any(name.endswith('.java') for name in archive.namelist())
    pom_path = 'META-INF/maven/org.apache.orc/orc-core/pom.properties'
    pom = archive.read(pom_path)
    (ROOT / 'orc-core-pom.properties').write_bytes(pom)
    assert 'version=2.3.0' in pom.decode()
    for name, output in [('org.apache.orc.impl.SchemaEvolution', 'SchemaEvolution.javap.txt'),
                         ('org.apache.orc.impl.SchemaEvolution$CaseInsensitiveMap', 'CaseInsensitiveMap.javap.txt')]:
        member = name.replace('.', '/') + '.class'
        raw = archive.read(member)
        target = Path('classes') / Path(member).name
        (ROOT / target).parent.mkdir(exist_ok=True)
        (ROOT / target).write_bytes(raw)
        command = [JAVAP, '-classpath', str(JAR), '-c', '-p', name]
        # Read-only disassembly, not an additional Spark runtime observation.
        observed = subprocess.check_output(command)
        assert observed == (ROOT / output).read_bytes()
        classes.append({'class': name, 'jar_member': member, 'file': str(target), 'sha256': sha(raw),
                        'javap_command': command, 'javap_file': output, 'javap_sha256': sha(observed)})
sources = []
for label, path, first, last in [
    ('spark-orc-case-setting', 'sql/core/src/main/scala/org/apache/spark/sql/execution/datasources/orc/OrcFileFormat.scala', 141, 182),
    ('spark-top-name-check', 'sql/core/src/main/scala/org/apache/spark/sql/execution/datasources/orc/OrcUtils.scala', 247, 303)]:
    raw = git('show', f'{PIN}:{path}')
    lines = raw.splitlines(keepends=True)
    assert 1 <= first <= last <= len(lines)
    target = Path('sources') / f'{label}-{first}-{last}.txt'
    (ROOT / target).parent.mkdir(exist_ok=True)
    excerpt = b''.join(lines[first - 1:last])
    (ROOT / target).write_bytes(excerpt)
    sources.append({'path': path, 'commit': PIN, 'git_blob': git('rev-parse', f'{PIN}:{path}').decode().strip(),
                    'source_sha256': sha(raw), 'first_line': first, 'last_line': last,
                    'file': str(target), 'excerpt_sha256': sha(excerpt)})
save('source-audit.json', {'recorded_at_utc': datetime.now(timezone.utc).isoformat(), 'spark_sources': sources,
                          'orc_evidence_kind': 'Installed compiled artifact disassembly, not Java source or instrumented loaded-class origin',
                          'jar': {'path': str(JAR), 'sha256': sha(JAR.read_bytes()), 'size': JAR.stat().st_size,
                                  'maven_properties_member': pom_path, 'maven_properties_file': 'orc-core-pom.properties',
                                  'maven_properties_sha256': sha(pom)},
                          'javap_version': subprocess.check_output([JAVAP, '-version']).decode().strip(), 'classes': classes})
r = json.loads((ROOT / 'results.json').read_text())
assert r['status'] == 'completed' and r['owned_gateway_exit_code'] == 0
assert r['spark_version'] == '4.2.1' and sha((ROOT / 'probe.py').read_bytes()) == r['script_sha256']
assert len(r['cases']) == 4
assert r['config']['spark.sql.caseSensitive'] == 'false'
assert r['config']['spark.sql.orc.enableVectorizedReader'] == 'true'
assert r['config']['spark.sql.timeType.enabled'] == 'false'
expected = [('original', 'BAR', 22), ('original', 'Bar', 22), ('reverse', 'bar', 11), ('reverse', 'BAR', 11)]
for case, (fixture, name, value) in zip(r['cases'], expected):
    assert case['fixture'] == fixture and case['requested_name'] == name
    assert case['status'] == 'success' and case['stage'] == 'materialize_to_arrow'
    assert case['arrow']['num_rows'] == 1
    assert case['arrow']['columns'][0]['values'] == [{name: value}]
    assert case['read_schema']['fields'][0]['type']['fields'][0]['name'] == name
    assert 'Batched: true' in case['physical_plan']
for name, receipt in r['fixtures'].items():
    path = ROOT / ('inputs/original.orc' if name == 'original' else 'data/reverse/' + Path(receipt['path']).name)
    assert sha(path.read_bytes()) == receipt['sha256']
assert r['fixtures']['original']['sha256'] == r['fixtures']['original']['original_sha256']
save('summary.json', {'recorded_at_utc': datetime.now(timezone.utc).isoformat(), 'scope': 'Four nested ASCII cases only, no Sail runtime or Unicode policy',
                      'cases_total': 4, 'successful_reads': 4, 'runtime_attempts': 1,
                      'owned_gateway_pid': r['java']['gateway_pid'], 'owned_gateway_exit_code': r['owned_gateway_exit_code'],
                      'observed_rule': 'Last physical field after case normalization wins for these nested ASCII cases, without exact-case preference',
                      'cases': [{'fixture': f, 'requested_name': n, 'value': v} for f, n, v in expected]})
files, excluded = [], []
for path in sorted(ROOT.rglob('*')):
    if not path.is_file() or path.name == 'MANIFEST.json': continue
    relative = path.relative_to(ROOT)
    entry = {'file': str(relative), 'sha256': sha(path.read_bytes()), 'size': path.stat().st_size}
    if path.suffix == '.crc' or path.name == '_SUCCESS' or relative.parts[0] in ['spark-local', 'warehouse']:
        excluded.append({**entry, 'reason': 'Generated Hadoop bookkeeping/runtime state, not used as evidence'})
    else: files.append(entry)
save('MANIFEST.json', {'recorded_at_utc': datetime.now(timezone.utc).isoformat(), 'original_root': str(ROOT),
                      'portable_mapping': 'Manifest paths are relative; original absolute paths in raw receipts are preserved',
                      'files': files, 'excluded': excluded, 'excluded_directory_rules': ['spark-local/**', 'warehouse/**']})
print('Validated four observations, two fixtures, exact class disassembly, source anchors and owned JVM exit;', len(files), 'retained files')
