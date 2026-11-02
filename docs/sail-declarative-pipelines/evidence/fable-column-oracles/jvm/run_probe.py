"""Compile/run one isolated JVM fixture and retain reproducible provenance."""

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import ast
import json
import shlex
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent
CLASSES = ROOT.with_name(ROOT.name + '-classes')
JDK = Path('/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home')
PYSPARK = Path('/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages/pyspark')
SPARK_SOURCE = Path('/Users/alexy/src/spark-sdp-4.2.1')
JARS = PYSPARK / 'jars'

def digest(path):
    with path.open('rb') as stream:
        result = sha256()
        while block := stream.read(1024 * 1024):
            result.update(block)
        return result.hexdigest()

commands = []

def run(label, argv):
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
    (ROOT / (label + '.stdout.txt')).write_text(result.stdout)
    (ROOT / (label + '.stderr.txt')).write_text(result.stderr)
    entry = dict(label=label, argv=argv, shell_display=shlex.join(argv), cwd=str(ROOT), exit_code=result.returncode)
    commands.append(entry)
    (ROOT / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
    if result.returncode:
        raise RuntimeError(f'{label} failed with {result.returncode}: {result.stderr}')
    return result.stdout

run('java-version', [str(JDK / 'bin/java'), '-version'])
run('javac-version', [str(JDK / 'bin/javac'), '-version'])
spark_head = run('spark-source-head', ['git', '-C', str(SPARK_SOURCE), 'rev-parse', 'HEAD']).strip()
version_tree = ast.parse((PYSPARK / 'version.py').read_text())
version = next(ast.literal_eval(node.value) for node in version_tree.body
               if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
               and node.target.id == '__version__')
jars = sorted(JARS.glob('*.jar'))
jar_manifest = [dict(name=p.name, path=str(p), size=p.stat().st_size, sha256=digest(p)) for p in jars]
(ROOT / 'classpath-jars.json').write_text(json.dumps(jar_manifest, indent=2) + '\n')

build_properties = {}
for jar in jars:
    if jar.name.startswith(('spark-core_', 'spark-sql-api_', 'spark-common-utils_')):
        with zipfile.ZipFile(jar) as archive:
            for name in archive.namelist():
                if 'version' in name.lower() and name.endswith('.properties'):
                    build_properties[jar.name + ':' + name] = archive.read(name).decode('utf-8', errors='replace')
(ROOT / 'spark-build-properties.json').write_text(json.dumps(build_properties, indent=2) + '\n')
spark_properties_text = next(value for key, value in build_properties.items()
                             if key.endswith(':spark-version-info.properties'))
spark_properties = dict(line.split('=', 1) for line in spark_properties_text.splitlines() if '=' in line)

classpath = str(JARS / '*')
CLASSES.mkdir(exist_ok=True)
run('javac', [str(JDK / 'bin/javac'), '-encoding', 'UTF-8', '-cp', classpath,
              '-d', str(CLASSES), str(ROOT / 'KernelProbe.java')])
raw = run('java', [str(JDK / 'bin/java'), '-cp', str(CLASSES) + ':' + classpath, 'KernelProbe'])
records = [json.loads(line) for line in raw.splitlines()]
(ROOT / 'results.json').write_text(json.dumps(records, indent=2) + '\n')
receipt = {
    'recorded_at': datetime.now(timezone.utc).isoformat(),
    'scope': 'Direct StructType helper and Java Locale.ROOT oracle only; no Spark server, CDC flow, analyzer reachability, or end-to-end CDC execution.',
    'pyspark_version': version,
    'pyspark_version_file': str(PYSPARK / 'version.py'),
    'pyspark_version_file_sha256': digest(PYSPARK / 'version.py'),
    'spark_reference_git_head': spark_head,
    'spark_jar_build_version': spark_properties['version'],
    'spark_jar_build_revision': spark_properties['revision'],
    'jar_revision_matches_source': spark_properties['revision'] == spark_head,
    'jar_version_matches_pyspark': spark_properties['version'] == version,
    'jdk_home': str(JDK),
    'runtime': next(x for x in records if x['kind'] == 'runtime'),
    'java_binary_sha256': digest(JDK / 'bin/java'),
    'javac_binary_sha256': digest(JDK / 'bin/javac'),
    'classpath_jar_count': len(jars),
    'source_sha256': digest(ROOT / 'KernelProbe.java'),
    'runner_sha256': digest(Path(__file__)),
    'compiled_classes_directory_not_archived': str(CLASSES),
    'class_sha256': digest(CLASSES / 'KernelProbe.class'),
    'raw_results_sha256': digest(ROOT / 'java.stdout.txt'),
    'lookup_records': sum(x['kind'] == 'lookup' for x in records),
    'lowercase_records': sum(x['kind'] == 'lowercase' for x in records),
    'result': 'compiled and ran successfully',
    'commands': commands,
}
(ROOT / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps({k: receipt[k] for k in ('pyspark_version', 'spark_reference_git_head', 'classpath_jar_count', 'lookup_records', 'lowercase_records', 'result')}, indent=2))
