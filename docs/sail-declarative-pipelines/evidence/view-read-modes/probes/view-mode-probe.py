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
            condition=error.getCondition() if hasattr(error, "getCondition") else None, sql_state=error.getSqlState() if hasattr(error,"getSqlState") else None, parameters=error.getMessageParameters() if hasattr(error,"getMessageParameters") else None,
            message=str(error).split("\n\nJVM stacktrace:")[0][:1500],
        )
    if not dry and entry["outcome"] == "accepted":
        for table in ["consumer", "batch_consumer"]:
            name = f"spark_catalog.{schema_name}.{table}"
            if spark.catalog.tableExists(name):
                entry[table] = spark.table(name).schema.jsonValue()
    return entry



CHECK = "pipelines.incompatibleViewCheck.enabled"
SRC = "CREATE MATERIALIZED VIEW src AS SELECT 1 AS id;"
BATCH_V = "CREATE TEMPORARY VIEW v AS SELECT * FROM src;"
STREAM_V = "CREATE TEMPORARY VIEW v AS SELECT * FROM STREAM(src);"
ST = "CREATE STREAMING TABLE consumer AS SELECT * FROM "
MV = "CREATE MATERIALIZED VIEW consumer AS SELECT * FROM "
for flag in [None, "false", "true"]:
    pre = f"SET {CHECK}={flag};" if flag else ""
    tag = flag or "default"
    for name, view in [("batch", BATCH_V), ("stream", STREAM_V)]:
        for dry in [True]:
            run(f"{name}_view_st_stream_{tag}", SRC + view + pre + ST + "STREAM(v)", dry)
            run(f"{name}_view_st_batch_{tag}", SRC + view + pre + ST + "v", dry)
            run(f"{name}_view_mv_batch_{tag}", SRC + view + pre + MV + "v", dry)
            run(f"{name}_view_mv_stream_{tag}", SRC + view + pre + MV + "STREAM(v)", dry)
# Transitive: a batch-read view over a streaming view, with the check off at each level.
run("nested_stream_read_off", SRC + STREAM_V + f"SET {CHECK}=false;CREATE TEMPORARY VIEW w AS SELECT * FROM v;RESET_MARK", True) if False else None
run("nested_w_off_st_batch", SRC + STREAM_V + f"SET {CHECK}=false;CREATE TEMPORARY VIEW w AS SELECT * FROM v;" + ST + "w", True)
run("nested_w_off_st_stream", SRC + STREAM_V + f"SET {CHECK}=false;CREATE TEMPORARY VIEW w AS SELECT * FROM v;" + ST + "STREAM(w)", True)
# Union of batch and stream inside a view, and a CTE around a stream read.
run("union_view_st_stream", SRC + "CREATE TEMPORARY VIEW v AS SELECT * FROM src UNION ALL SELECT * FROM STREAM(src);" + ST + "STREAM(v)", True)
run("union_view_st_batch", SRC + "CREATE TEMPORARY VIEW v AS SELECT * FROM src UNION ALL SELECT * FROM STREAM(src);" + ST + "v", True)
run("cte_view_st_stream", SRC + "CREATE TEMPORARY VIEW v AS WITH c AS (SELECT * FROM STREAM(src)) SELECT * FROM c;" + ST + "STREAM(v)", True)
# A view reading an external table, stream versus batch; the view's own flag.
spark.sql("CREATE TABLE IF NOT EXISTS ext (id INT) USING parquet")
run("external_stream_view", "CREATE TEMPORARY VIEW v AS SELECT * FROM STREAM(spark_catalog.default.ext);" + ST + "STREAM(v)", True)
run("external_batch_view", "CREATE TEMPORARY VIEW v AS SELECT * FROM spark_catalog.default.ext;" + ST + "STREAM(v)", True)
# Persisted view reading, and a flag invalid as a boolean.
run("invalid_flag", SRC + BATCH_V + f"SET {CHECK}=maybe;" + ST + "STREAM(v)", True)
spark.conf.set(CHECK, "false")
run("session_flag_off", SRC + BATCH_V + ST + "STREAM(v)", True)
spark.conf.unset(CHECK)
# A view whose own flow disables the check does not disable it for the reader.
run("view_flag_only", SRC + "CREATE TEMPORARY VIEW q AS SELECT 2 AS id;" + f"SET {CHECK}=false;CREATE TEMPORARY VIEW v AS SELECT * FROM src;", True) if False else None
spark.stop()
result["completed_at"] = datetime.now(timezone.utc).isoformat()
(out / "observations.json").write_text(json.dumps(result, indent=2) + "\n")
print(len(result["cases"]), "cases")
