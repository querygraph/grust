from pathlib import Path
import json, os, subprocess, pyspark
from pyarrow import orc
from pyspark.sql import SparkSession

root = Path('/tmp/sail-sdp-orc-bridge-reference')
path = root / 'data/foreign_submicro/foreign.orc'
path.parent.mkdir(exist_ok=True)
cp = str(Path(pyspark.__file__).parent / 'jars/*')
cmd = ['java', '--class-path', cp, str(root / 'ForeignSubmicro.java'), str(path)]
result = subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=root)
(root / 'foreign-submicro-java.log').write_text(result.stdout + result.stderr)
for key in ('SPARK_REMOTE', 'SPARK_CONNECT_MODE_ENABLED', 'SPARK_LOCAL_REMOTE'):
    os.environ.pop(key, None)
os.environ['SPARK_LOCAL_IP'] = '127.0.0.1'
os.environ['SPARK_LOCAL_DIRS'] = str(root / 'spark-local')
s = SparkSession.builder.remote('local[2]').config('spark.sql.warehouse.dir', (root / 'warehouse').as_uri()).config('spark.sql.session.timeZone', 'UTC').getOrCreate()
report = json.loads((root / 'expected.json').read_text())
case = {'name': 'foreign_submicro', 'writer': 'Apache ORC Java; ForeignSubmicro.java', 'fixture_path': str(path), 'fixture_directory': str(path.parent), 'session_timezone': 'UTC'}
try:
    frame = s.read.orc(str(path))
    case['read_schema'] = frame.schema.jsonValue()
    case['read_strings'] = [r.asDict() for r in frame.selectExpr('id', 'CAST(ts AS STRING) AS ts').collect()]
    case['read_numeric'] = [r.asDict() for r in frame.selectExpr('id', 'unix_micros(ts) AS ts_micros').collect()]
    case['spark_arrow_schema'] = str(frame.toArrow().schema)
    physical = orc.ORCFile(path).read()
    case['physical_arrow_schema'] = str(physical.schema)
    case['physical_arrow_rows'] = physical.to_pylist()
    case['physical_arrow_ts_nanos'] = physical['ts'].cast('int64').to_pylist()
    native = subprocess.run(['/Users/alexy/src/orc-rust-sdp-gate/target/debug/bounded', 'sync', str(path)], capture_output=True, text=True)
    (root / 'native-foreign_submicro.stdout.json').write_text(native.stdout)
    (root / 'native-foreign_submicro.stderr.log').write_text(native.stderr)
    case['native_default_nanos_exitcode'] = native.returncode
    case['native_microseconds_decode'] = {'outcome': 'not executed', 'source_expected': 'DecodeTimestamp error for nonmultiples of 1000 nanoseconds', 'reason': 'Existing bounded executable fixes default nanosecond decoder; no cargo or repo edits authorized.'}
finally:
    s.stop()
    report['cases'] = [c for c in report['cases'] if c['name'] != case['name']] + [case]
    (root / 'expected.json').write_text(json.dumps(report, indent=2, default=str) + '\n')
    print(json.dumps(case, indent=2, default=str))
