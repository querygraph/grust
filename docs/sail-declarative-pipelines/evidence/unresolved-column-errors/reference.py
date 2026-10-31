"""Observe missing-column conditions and suggestions through public Connect SQL."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess
import sys

for key in ('SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE'):
    os.environ.pop(key,None)
os.environ['SPARK_LOCAL_IP'] = '127.0.0.1'
from pyspark.sql import SparkSession
import pyspark

OUT = Path(sys.argv[1])
ENGINE = sys.argv[2]
assert ENGINE in ('spark','sail')
OUT.mkdir(exist_ok=False)
CASES = [
    ('one_suggestion','SELECT Foo FROM (SELECT 1 AS foo) a'),
    ('no_suggestion','SELECT missing'),
    ('join_aliases','SELECT z1.Foo FROM (SELECT 1 AS foo) z1 CROSS JOIN (SELECT 2 AS bar) a_insensitive CROSS JOIN (SELECT 3 AS foo) z2'),
    ('two_qualifiers','SELECT ext.Foo FROM (SELECT 1 AS foo) z_sensitive CROSS JOIN (SELECT 2 AS foo) ext'),
    ('limit_five','SELECT missing FROM (SELECT 1 AS aaa,2 AS bbb,3 AS ccc,4 AS ddd,5 AS eee,6 AS fff,7 AS ggg) q'),
    ('dotted_name','SELECT `A.B` FROM (SELECT 1 AS `a.b`) q'),
    ('escaped_backtick','SELECT `A``B` FROM (SELECT 1 AS `a``b`) q'),
    ('unicode_distance','SELECT `😀` FROM (SELECT 1 AS `😁`,2 AS a,3 AS `雪`) q'),
    ('qualified_missing','SELECT q.Foo FROM (SELECT 1 AS foo,2 AS bar) q'),
    ('unknown_qualifier','SELECT x.foo FROM (SELECT 1 AS foo,2 AS bar) q'),
    ('duplicate_output','SELECT Foo FROM (SELECT 1 AS foo) q CROSS JOIN (SELECT 2 AS bar) b'),
    ('case_insensitive_success','SELECT Foo FROM (SELECT 1 AS foo) q'),
]
report = {'engine':ENGINE,'started_at':datetime.now(timezone.utc).isoformat(),'spark_source_commit':subprocess.check_output(['git','-C','/Users/alexy/src/spark-sdp-4.2.1','rev-parse','HEAD'],text=True).strip(),'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':'ordinary public SQL missing-column metadata; not Scala acceptance','cases':[]}
spark = None
try:
    if ENGINE == 'spark':
        check = subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:15002','-sTCP:LISTEN','-Fp'],capture_output=True,text=True)
        assert check.returncode == 1 and not check.stdout, 'reference port already owned'
    spark = SparkSession.builder.remote('local[1]' if ENGINE=='spark' else 'sc://localhost:50094').appName('missing column metadata').config('spark.ui.enabled','false').getOrCreate()
    report['spark_version'] = spark.version
    report['pyspark_version'] = pyspark.__version__
    assert spark.version == pyspark.__version__ == '4.2.1'
    for name, sql in CASES:
        sensitive = name != 'case_insensitive_success'
        spark.conf.set('spark.sql.caseSensitive',str(sensitive).lower())
        case = {'name':name,'sql':sql,'case_sensitive':sensitive}
        try:
            case['rows'] = [row.asDict() for row in spark.sql(sql).collect()]
            case['outcome'] = 'success'
        except Exception as error:
            case.update(outcome='error',exception_type=type(error).__name__,condition=error.getCondition(),sql_state=error.getSqlState(),parameters=error.getMessageParameters(),message=str(error))
        report['cases'].append(case)
finally:
    if spark is not None:
        spark.stop()
    report['completed_at'] = datetime.now(timezone.utc).isoformat()
    (OUT/'observations.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
print('Recorded',ENGINE,len(report['cases']),'ordinary SQL observations',flush=True)
