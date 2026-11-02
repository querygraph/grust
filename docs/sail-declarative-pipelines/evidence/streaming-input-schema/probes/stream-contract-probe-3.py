"""Spark 4.2.1 oracle: what schema does a STREAM read of a virtual table expose?

Measures metadata, nullability, map recursion, CHAR/VARCHAR and collation, and
flow/session precedence plus the second call. Each observation goes through a
real run (published consumer schema) or a dry run (error-based input types).
Usage: stream-contract-probe.py FRESH_OUTPUT_DIR
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from pyspark.sql import SparkSession

out = Path(sys.argv[1])
out.mkdir(exist_ok=False)
for key in ["SPARK_REMOTE", "SPARK_CONNECT_MODE_ENABLED", "SPARK_LOCAL_REMOTE"]:
    os.environ.pop(key, None)
os.environ["SPARK_LOCAL_IP"] = "127.0.0.1"
spark = (
    SparkSession.builder.remote("local[2]")
    .appName("sdp-stream-contract")
    .config("spark.sql.warehouse.dir", (out / "warehouse").as_uri())
    .getOrCreate()
)
assert spark.version == "4.2.1"
from pyspark.pipelines.spark_connect_graph_element_registry import (  # noqa: E402
    SparkConnectGraphElementRegistry,
)
from pyspark.pipelines.spark_connect_pipeline import (  # noqa: E402
    create_dataflow_graph,
    start_run,
)

spark.conf.set("spark.sql.timeType.enabled", "true")
result = {
    "started_at": datetime.now(timezone.utc).isoformat(),
    "version": spark.version,
    "framework_default": spark.conf.get("spark.sql.types.framework.enabled"),
    "cases": [],
}


def run(label, sql, dry, confs=None):
    entry = {"label": label, "sql": sql, "dry": dry, "confs": confs or {}, "events": []}
    result["cases"].append(entry)
    schema_name = "p" + re.sub(r"\W", "_", label)
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
    graph = create_dataflow_graph(spark, "spark_catalog", schema_name, confs)
    registry = SparkConnectGraphElementRegistry(spark, graph)
    try:
        registry.register_sql(sql, Path(f"{schema_name}.sql"))
        stream = start_run(spark, graph, None, False, None, dry, (out / schema_name).as_uri())
        for item in stream:
            if "pipeline_event_result" in item:
                entry["events"].append(item["pipeline_event_result"].event.message)
        entry["outcome"] = "accepted"
    except Exception as error:  # every outcome is an observation
        entry.update(
            outcome="error",
            error_type=type(error).__name__,
            condition=error.getCondition() if hasattr(error, "getCondition") else None,
            message=str(error).split("\n\nJVM stacktrace:")[0][:1500],
        )
    if not dry and entry["outcome"] == "accepted":
        for table in ["consumer", "batch_consumer"]:
            name = f"spark_catalog.{schema_name}.{table}"
            if spark.catalog.tableExists(name):
                entry[table] = spark.table(name).schema.jsonValue()
    return entry



FRAMEWORK = "spark.sql.types.framework.enabled"
SOURCE = "CREATE MATERIALIZED VIEW source AS SELECT CAST(NULL AS TIME(3)) AS id;"
# First call succeeds under the session; only schema validation discriminates.
for declared in [3, 6]:
    for view_value in ["true", "false"]:
        for session in ["true", "false"]:
            spark.conf.set(FRAMEWORK, session)
            run(f"second_call_d{declared}_view_{view_value}_session_{session}",
                SOURCE
                + f"CREATE STREAMING TABLE consumer (id TIME({declared}), k INT) AS "
                + "SELECT id, k FROM STREAM(source), v;"
                + f"SET {FRAMEWORK}={view_value};"
                + "CREATE TEMPORARY VIEW v AS SELECT 1 AS k", True)
spark.conf.set(FRAMEWORK, "false")
for preserve in ["false", "true"]:
    spark.conf.set("spark.sql.preserveCharVarcharTypeInfo", preserve)
    for declared in [False, True]:
        head_ = "source (id CHAR(3))" if declared else "source"
        run(f"char_preserve_{preserve}_declared_{declared}",
            f"CREATE MATERIALIZED VIEW {head_} AS SELECT CAST('a' AS CHAR(3)) AS id;"
            "CREATE MATERIALIZED VIEW consumer AS SELECT sqrt(array(id)) FROM STREAM(source)", True)
spark.stop()
result["completed_at"] = datetime.now(timezone.utc).isoformat()
(out / "observations.json").write_text(json.dumps(result, indent=2) + "\n")
print(len(result["cases"]), "cases")
