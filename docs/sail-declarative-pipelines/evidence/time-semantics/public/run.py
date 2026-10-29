from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import sys
import traceback

parser = argparse.ArgumentParser()
parser.add_argument('--engine', required=True, choices=['spark', 'sail'])
parser.add_argument('--remote', required=True)
parser.add_argument('--label', required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parent
output = root / args.label
output.mkdir(exist_ok=True)
for key in ('SPARK_REMOTE', 'SPARK_CONNECT_MODE_ENABLED', 'SPARK_LOCAL_REMOTE'):
    os.environ.pop(key, None)
os.environ['SPARK_LOCAL_IP'] = '127.0.0.1'
os.environ['SPARK_LOCAL_DIRS'] = str(output / 'spark-local')
import pyspark
from pyspark.sql import SparkSession

test_source = root / 'test_time_precision.py'
spec = importlib.util.spec_from_file_location('time_precision_cases', test_source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
report = {
    'recorded_at': datetime.now(timezone.utc).isoformat(),
    'engine': args.engine,
    'remote': args.remote,
    'python': sys.executable,
    'pyspark_version': pyspark.__version__,
    'test_source_sha256': hashlib.sha256(test_source.read_bytes()).hexdigest(),
    'scope': 'Eight unchanged public regression functions; no full SDP qualification.',
    'cases': [],
}
def save():
    (output / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
save()
spark = None
try:
    builder = SparkSession.builder.remote(args.remote).appName('sail-time-public-' + args.label)
    if args.engine == 'spark':
        builder = (builder.config('spark.ui.enabled', 'false')
                   .config('spark.driver.memory', '512m')
                   .config('spark.executor.memory', '512m')
                   .config('spark.sql.shuffle.partitions', '1')
                   .config('spark.default.parallelism', '1')
                   .config('spark.sql.warehouse.dir', (output / 'warehouse').as_uri()))
    spark = builder.getOrCreate()
    report['server_spark_version'] = spark.version
    assert spark.version == '4.2.1'
    spark.conf.set('spark.sql.session.timeZone', 'UTC')
    spark.conf.set('spark.sql.ansi.enabled', 'true')
    save()
    for name in sorted(n for n in vars(module) if n.startswith('test_')):
        case = {'name': name}
        report['cases'].append(case)
        fixture = module.time_spark.__wrapped__(spark)
        try:
            session = next(fixture)
            getattr(module, name)(session)
            case['outcome'] = 'passed'
        except Exception as error:
            case['outcome'] = 'failed'
            case['error'] = repr(error)
            failure = name + '.failure.txt'
            (output / failure).write_text(traceback.format_exc())
            case['traceback'] = failure
        finally:
            try:
                next(fixture)
            except StopIteration:
                pass
            save()
        print(case['outcome'], name, flush=True)
finally:
    if spark is not None:
        spark.stop()
    save()
assert len(report['cases']) == 8
assert all(case['outcome'] == 'passed' for case in report['cases']), report
