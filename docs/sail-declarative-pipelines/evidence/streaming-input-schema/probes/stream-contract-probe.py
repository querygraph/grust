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


# 1. Metadata and nullability through a real run: STREAM versus batch control.
DECLARED = (
    "id INT NOT NULL COMMENT 'top', "
    "s STRUCT<x: INT NOT NULL COMMENT 'nested'>, "
    "a ARRAY<STRUCT<y: INT COMMENT 'element'>>, "
    "m MAP<STRING, STRUCT<z: INT COMMENT 'value'>>"
)
BODY = (
    "SELECT 1 AS id, named_struct('x', 1) AS s, "
    "array(named_struct('y', 1)) AS a, "
    "map('k', named_struct('z', 1)) AS m"
)
run(
    "metadata_real",
    f"CREATE MATERIALIZED VIEW source ({DECLARED}) AS {BODY};"
    "CREATE STREAMING TABLE consumer AS SELECT * FROM STREAM(source);"
    "CREATE MATERIALIZED VIEW batch_consumer AS SELECT * FROM source",
    False,
)

# 2. Nullability: a NOT NULL consumer declaration accepts only a non-null input.
for mode, read in [("stream", "STREAM(source)"), ("batch", "source")]:
    kind = "STREAMING TABLE" if mode == "stream" else "MATERIALIZED VIEW"
    run(
        f"nullable_{mode}",
        f"CREATE MATERIALIZED VIEW source (id INT NOT NULL) AS SELECT 1 AS id;"
        f"CREATE {kind} consumer (id INT NOT NULL) AS SELECT id FROM {read}",
        True,
    )

# 3. Error-based input types, including map recursion and string constraints.
TYPES = [
    "MAP<STRING, TIME(3)>",
    "MAP<TIME(3), STRING>",
    "MAP<STRING, INTERVAL YEAR>",
    "MAP<INTERVAL HOUR, STRING>",
    "ARRAY<MAP<STRING, STRUCT<t: TIME(3)>>>",
    "CHAR(3)",
    "VARCHAR(3)",
    "STRING COLLATE UTF8_LCASE",
    "ARRAY<VARCHAR(3)>",
    "TIMESTAMP_NTZ",
    "DECIMAL(10, 2)",
]
for framework in ["false", "true"]:
    spark.conf.set("spark.sql.types.framework.enabled", framework)
    for index, data_type in enumerate(TYPES):
        for declared in [False, True]:
            for mode, read in [("stream", "STREAM(source)"), ("batch", "source")]:
                head = f"source (id {data_type})" if declared else "source"
                run(
                    f"types_{framework}_{index}_{declared}_{mode}",
                    f"CREATE MATERIALIZED VIEW {head} AS "
                    f"SELECT CAST(NULL AS {data_type}) AS id;"
                    f"CREATE MATERIALIZED VIEW consumer AS SELECT sqrt(id) FROM {read}",
                    True,
                )

# 4. Precedence: whose configuration governs TIME at the streaming read?
FRAMEWORK = "spark.sql.types.framework.enabled"
SOURCE = "CREATE MATERIALIZED VIEW source AS SELECT CAST(NULL AS TIME(3)) AS id;"
READER = "CREATE MATERIALIZED VIEW consumer AS SELECT sqrt(id) FROM STREAM(source)"
for session, graph_conf, flow_conf in [
    ("false", None, None),
    ("true", None, None),
    ("false", "true", None),
    ("true", "false", None),
    ("false", None, "true"),
    ("true", None, "false"),
    ("false", "false", "true"),
    ("true", "true", "false"),
]:
    spark.conf.set(FRAMEWORK, session)
    label = f"precedence_{session}_{graph_conf}_{flow_conf}"
    flow_set = f"SET {FRAMEWORK}={flow_conf};" if flow_conf else ""
    confs = {FRAMEWORK: graph_conf} if graph_conf else None
    run(label, SOURCE + flow_set + READER, True, confs)

# 5. A view contribution reaches the consumer only on Spark's second call.
for view_value in ["true", "false"]:
    for session in ["true", "false"]:
        spark.conf.set(FRAMEWORK, session)
        run(
            f"view_second_call_{view_value}_{session}",
            SOURCE
            + f"SET {FRAMEWORK}={view_value};"
            + "CREATE TEMPORARY VIEW v AS SELECT 1 AS k;"
            + f"RESET {FRAMEWORK};"
            + "CREATE MATERIALIZED VIEW consumer AS "
            + "SELECT sqrt(id), k FROM STREAM(source), v",
            True,
        )

spark.stop()
result["completed_at"] = datetime.now(timezone.utc).isoformat()
(out / "observations.json").write_text(json.dumps(result, indent=2) + "\n")
print(len(result["cases"]), "cases")
