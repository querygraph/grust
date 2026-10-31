import json, os, sys
os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable
from pyspark.sql import SparkSession
spark = SparkSession.builder.master("local[1]").config("spark.ui.enabled", "false").getOrCreate()
cases = [
    "INSERT OVERWRITE output IF NOT EXISTS BY NAME SELECT 1",
    "INSERT OVERWRITE output IF NOT EXISTS SELECT 1",
    "INSERT OVERWRITE output PARTITION(p=1) IF NOT EXISTS BY NAME SELECT 1",
    "INSERT INTO output PARTITION(p) IF NOT EXISTS BY NAME SELECT 1",
    "INSERT OVERWRITE output BY NAME SELECT 1",
]
for sql in cases:
    try:
        spark.sql(sql)
        out = {"sql": sql, "result": "no error"}
    except Exception as e:
        cond = getattr(e, "getCondition", lambda: None)()
        out = {"sql": sql, "class": type(e).__name__, "condition": cond, "message": str(e).splitlines()[0][:200]}
    print(json.dumps(out))
spark.stop()
