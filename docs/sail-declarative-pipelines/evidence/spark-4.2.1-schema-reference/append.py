import json
import os
import tempfile
from pathlib import Path

for key in ("SPARK_REMOTE", "SPARK_CONNECT_MODE_ENABLED", "SPARK_LOCAL_REMOTE"):
    os.environ.pop(key, None)
os.environ["SPARK_LOCAL_IP"] = "127.0.0.1"

from pyspark.sql import SparkSession

root = Path(tempfile.mkdtemp(prefix="sail-sdp-spark-reference-"))
spark = (
    SparkSession.builder.master("local[2]")
    .appName("Sail SDP schema reference")
    .config("spark.ui.enabled", "false")
    .config("spark.sql.warehouse.dir", (root / "warehouse").as_uri())
    .getOrCreate()
)
spark.sparkContext.setLogLevel("ERROR")
results = {"spark_version": spark.version, "cases": []}
try:
    for name, schema, query in (
        ("missing_nullable", "id BIGINT, optional STRING", "SELECT id FROM range(2)"),
        ("wider_decimal", "value DECIMAL(8, 2)", "SELECT CAST(1 AS DECIMAL(4, 2)) AS value"),
        (
            "missing_nested_nullable",
            "value STRUCT<amount: DECIMAL(8, 2), optional: STRING>",
            "SELECT named_struct('amount', CAST(1 AS DECIMAL(4, 2))) AS value",
        ),
    ):
        spark.sql(f"CREATE TABLE {name} ({schema}) USING parquet")
        try:
            spark.sql(query).write.mode("append").saveAsTable(name)
            result = {"name": name, "outcome": "success", "rows": spark.table(name).count()}
        except Exception as error:
            result = {
                "name": name,
                "outcome": "error",
                "condition": error.getCondition() if hasattr(error, "getCondition") else None,
                "message": str(error),
            }
        results["cases"].append(result)
finally:
    spark.stop()
Path("/tmp/sail-sdp-spark-schema-reference.json").write_text(json.dumps(results, indent=2) + "\n")
print(json.dumps(results, indent=2))
