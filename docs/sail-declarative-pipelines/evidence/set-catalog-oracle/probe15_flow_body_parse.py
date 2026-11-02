import json, os, sys
os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable
from pyspark.sql import SparkSession
spark = SparkSession.builder.master("local[1]").config("spark.ui.enabled", "false").getOrCreate()
cases = [
    "CREATE FLOW f AS SELECT 1",
    "CREATE FLOW f AS WITH c AS (SELECT 1) INSERT INTO output BY NAME SELECT * FROM c",
    "CREATE FLOW f AS INSERT OVERWRITE DIRECTORY '/tmp/x' USING parquet SELECT 1",
    "CREATE FLOW f AS INSERT INTO output BY NAME REPLACE WHERE id > 0 SELECT 1",
    "CREATE FLOW f AS INSERT INTO output BY NAME SELECT 1",
    "CREATE FLOW f AS INSERT INTO output BY NAME WITH c AS (SELECT 1) SELECT * FROM c",
]
for sql in cases:
    try:
        spark.sql(sql)
        out = {"sql": sql, "result": "no error"}
    except Exception as e:
        cond = getattr(e, "getCondition", lambda: None)()
        out = {"sql": sql, "class": type(e).__name__, "condition": cond, "message": str(e).splitlines()[0][:160]}
    print(json.dumps(out))
spark.stop()
