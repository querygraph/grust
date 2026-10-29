import json
import os
import tempfile
from pathlib import Path

for key in ("SPARK_REMOTE", "SPARK_CONNECT_MODE_ENABLED", "SPARK_LOCAL_REMOTE"):
    os.environ.pop(key, None)
os.environ["SPARK_LOCAL_IP"] = "127.0.0.1"

from pyspark.sql import SparkSession
from pyspark.pipelines.spark_connect_graph_element_registry import SparkConnectGraphElementRegistry
from pyspark.pipelines.spark_connect_pipeline import create_dataflow_graph, handle_pipeline_events, start_run

root = Path(tempfile.mkdtemp(prefix="sail-sdp-spark-pipeline-reference-"))
spark = (
    SparkSession.builder.remote("local[2]")
    .appName("Sail SDP pipeline reference")
    .config("spark.ui.enabled", "false")
    .config("spark.sql.warehouse.dir", (root / "warehouse").as_uri())
    .getOrCreate()
)
results = {"spark_version": spark.version, "cases": []}
try:
    for name, definition, execute in (
        ("unknown_format", "USING missing_format AS SELECT id FROM range(2)", False),
        ("missing_nullable", "(id BIGINT, optional STRING) AS SELECT id FROM range(2)", True),
        ("wider_decimal", "(value DECIMAL(8, 2)) AS SELECT CAST(1 AS DECIMAL(4, 2)) AS value", True),
        (
            "missing_nested_nullable",
            "(value STRUCT<amount: DECIMAL(8, 2), optional: STRING>) "
            "AS SELECT named_struct('amount', CAST(1 AS DECIMAL(4, 2))) AS value",
            True,
        ),
    ):
        for dry in ((True, False) if execute else (True,)):
            graph = create_dataflow_graph(spark, None, None, None)
            registry = SparkConnectGraphElementRegistry(spark, graph)
            registry.register_sql(f"CREATE MATERIALIZED VIEW {name} {definition}", Path(name + ".sql"))
            try:
                handle_pipeline_events(start_run(spark, graph, None, False, None, dry, (root / name).as_uri()))
                outcome = {"name": name, "dry": dry, "outcome": "success"}
            except Exception as error:
                outcome = {
                    "name": name,
                    "dry": dry,
                    "outcome": "error",
                    "condition": error.getCondition() if hasattr(error, "getCondition") else None,
                    "message": str(error),
                }
            outcome["published"] = spark.catalog.tableExists(name)
            if not dry and outcome["outcome"] == "success":
                outcome["schema"] = spark.table(name).schema.jsonValue()
                outcome["rows"] = spark.table(name).count()
            results["cases"].append(outcome)
finally:
    spark.stop()
Path("/tmp/sail-sdp-spark-pipeline-reference.json").write_text(json.dumps(results, indent=2) + "\n")
print(json.dumps(results, indent=2))
