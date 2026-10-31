import json, os, sys
os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable
from pyspark.sql import SparkSession
spark = SparkSession.builder.master("local[1]").config("spark.ui.enabled", "false").getOrCreate()
cases = [
    "/* 雪🦀 */ CREATE FLOW f AS /* SELECT */ select 1",
    "SELECT",
    "SELECT 1 FROM t WHERE x = 'a\tb",
    "CREATE FLOW f AS INSERT INTO output BY NAME SELECT 1 )",
    "   ",
]
for sql in cases:
    try:
        spark.sql(sql)
        out = {"sql": sql, "result": "no error"}
    except Exception as e:
        out = {"sql": sql, "class": type(e).__name__, "condition": e.getCondition(), "params": e.getMessageParameters(), "message": str(e)[:200]}
    print(json.dumps(out, ensure_ascii=False))
spark.stop()
