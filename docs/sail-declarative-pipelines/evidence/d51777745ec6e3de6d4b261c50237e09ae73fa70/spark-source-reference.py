import json
import os
from pathlib import Path
for key in ('SPARK_REMOTE', 'SPARK_CONNECT_MODE_ENABLED', 'SPARK_LOCAL_REMOTE'):
    os.environ.pop(key, None)
os.environ['SPARK_LOCAL_IP'] = '127.0.0.1'
from pyspark.sql import SparkSession
spark = SparkSession.builder.master('local[1]').appName('view source boundaries').config('spark.ui.enabled', 'false').getOrCreate()
cases = [
    ('basic', "CREATE VIEW b COMMENT 'my persisted comment' AS SELECT * FROM range(1, 4);", 'SELECT * FROM range(1, 4)'),
    ('trivia', 'CREATE VIEW b AS /* leading */ SELECT  1 /* inside */ + 2 /* trailing */ ;', 'SELECT  1 /* inside */ + 2'),
    ('unicode_and_delimiters', "CREATE VIEW `雪` AS SELECT 'é;雪' AS `值`; -- after", "SELECT 'é;雪' AS `值`"),
    ('cte_and_newlines', 'CREATE VIEW b AS\nWITH c AS (SELECT 1 AS x)\nSELECT x FROM c\n-- trailing\n;', 'WITH c AS (SELECT 1 AS x)\nSELECT x FROM c'),
    ('hint', 'CREATE VIEW b AS SELECT /*+ REPARTITION(1) */ * FROM range(2);', 'SELECT /*+ REPARTITION(1) */ * FROM range(2)'),
]
result = {'spark_version': spark.version, 'cases': []}
try:
    parser = spark._jsparkSession.sessionState().sqlParser()
    for name, sql, expected in cases:
        try:
            plan = parser.parsePlan(sql)
            actual = plan.originalText().get()
            result['cases'].append({'name': name, 'sql': sql, 'expected': expected, 'actual': actual, 'outcome': 'passed' if actual == expected else 'failed'})
        except Exception as error:
            result['cases'].append({'name': name, 'sql': sql, 'expected': expected, 'outcome': 'failed', 'error': str(error)})
finally:
    spark.stop()
Path('/tmp/sail-sdp-view-source-reference.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
assert result['spark_version'] == '4.2.1'
assert all(case['outcome'] == 'passed' for case in result['cases']), result
