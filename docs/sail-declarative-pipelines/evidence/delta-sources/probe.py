"""Delta streaming sources through pipelines, one script for Spark and Sail.

Usage: probe.py FRESH_OUT_DIR [sc://host:port] [case-substring]
Without a remote it runs Spark 4.2.1 with Delta 4.4.1 in local mode.
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import session  # noqa: E402

out = Path(sys.argv[1])
out.mkdir(exist_ok=False)
remote = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else None
only = sys.argv[3] if len(sys.argv) > 3 else None
if remote:
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.remote(remote).getOrCreate()
else:
    spark = session(out)

import pyspark.pipelines as dp  # noqa: E402
from pyspark.pipelines.add_pipeline_analysis_context import add_pipeline_analysis_context  # noqa: E402
from pyspark.pipelines.graph_element_registry import graph_element_registration_context  # noqa: E402
from pyspark.pipelines.spark_connect_graph_element_registry import SparkConnectGraphElementRegistry  # noqa: E402
from pyspark.pipelines.spark_connect_pipeline import create_dataflow_graph, start_run  # noqa: E402

results = []


def text(error):
    return str(error).split("\n\nJVM stacktrace:")[0][:700]


class Case:
    def __init__(self, label):
        self.label = label
        self.schema = "d_" + re.sub(r"\W", "_", label)[:40]
        self.dir = out / self.schema
        self.dir.mkdir()
        self.path = (self.dir / "src").as_uri()
        self.storage = (self.dir / "storage").as_uri()
        self.log = []
        spark.sql(f"CREATE SCHEMA {self.schema}")
        spark.catalog.setCurrentDatabase(self.schema)

    def sql(self, statement):
        statement = statement.replace("{path}", self.path)
        try:
            rows = spark.sql(statement).collect()
            self.log.append({"sql": statement, "ok": True})
            return rows
        except Exception as error:  # every outcome is an observation
            self.log.append(
                {
                    "sql": statement,
                    "error": type(error).__name__,
                    "condition": error.getCondition() if hasattr(error, "getCondition") else None,
                    "message": text(error),
                }
            )
            return None

    def run(self, body, full=False, read_table="t"):
        body = body.replace("{path}", self.path)
        entry = {"run": True, "full": full}
        events = []
        try:
            graph = create_dataflow_graph(spark, spark.catalog.currentCatalog(), self.schema, {"spark.sql.pipelines.maxFlowRetryAttempts": "0"})
            registry = SparkConnectGraphElementRegistry(spark, graph)
            with (
                add_pipeline_analysis_context(spark=spark, dataflow_graph_id=graph, flow_name=None),
                graph_element_registration_context(registry),
            ):
                exec(body, {"spark": spark, "dp": dp})  # noqa: S102
            stream = start_run(spark, graph, None, full, None, False, self.storage)
            for item in stream:
                if "pipeline_event_result" in item:
                    message = item["pipeline_event_result"].event.message
                    if re.search(r"fail|skip|error", message, re.I):
                        events.append(message[:400])
            entry["outcome"] = "ok"
        except Exception as error:  # every outcome is an observation
            entry.update(
                outcome="error",
                error=type(error).__name__,
                condition=error.getCondition() if hasattr(error, "getCondition") else None,
                message=text(error),
            )
        entry["events"] = events
        try:
            frame = spark.table(f"{self.schema}.{read_table}")
            entry["columns"] = frame.columns
            entry["rows"] = sorted(repr(tuple(row)) for row in frame.collect())
        except Exception as error:  # every outcome is an observation
            entry["rows"] = None
            entry["rows_error"] = text(error)[:200]
        self.log.append(entry)
        return entry

    def done(self):
        results.append({"label": self.label, "log": self.log})
        (out / "observations.json").write_text(json.dumps(results, indent=1) + "\n")
        last = [item for item in self.log if "run" in item]
        print(self.label, [(x["outcome"], x.get("condition"), len(x["rows"] or [])) for x in last], flush=True)


def table(read):
    return f"@dp.table\ndef t():\n  return {read}\n"


TABLE = table('spark.readStream.table("src")')
PATH = table('spark.readStream.format("delta").load("{path}")')


def opts(**kwargs):
    chain = "".join(f'.option("{k}", {v!r})' for k, v in kwargs.items())
    return table(f'spark.readStream.format("delta"){chain}.load("{{path}}")')


CREATE = "CREATE TABLE src (id INT, v STRING) USING delta LOCATION '{path}'"


def scenario(label, steps, create=CREATE):
    if only and only not in label:
        return
    c = Case(label)
    c.sql(create)
    for step in steps:
        if isinstance(step, str):
            c.sql(step)
        else:
            c.run(*step[0:1], **(step[1] if len(step) > 1 else {}))
    c.done()


ONE = "INSERT INTO src VALUES (1, 'a'), (2, 'b')"
ONEA = "INSERT INTO src VALUES (1, 'a')"
ONEB = "INSERT INTO src VALUES (2, 'b')"
TWO = "INSERT INTO src VALUES (3, 'c')"
THREE = "INSERT INTO src VALUES (4, 'd')"

# Basics
for name, read in [("table", TABLE), ("path", PATH)]:
    scenario(f"basic_{name}", [ONE, (read,), TWO, THREE, (read,), (read,)])
scenario("empty_first", [(PATH,), ONE, (PATH,)])
scenario("full_refresh", [ONE, (PATH,), TWO, (PATH,), (PATH, {"full": True}), THREE, (PATH,)])
scenario(
    "sql_stream",
    [ONE],
)
if not only or "sql_stream" in only:
    pass


# Source changes
def changes(label, change, *variants):
    for name, options in variants:
        read = opts(**options) if options else PATH
        scenario(f"{label}_{name}", [ONE, TWO, (read,), change, THREE, (read,), (read,)])


NONE = ("none", {})
IC = ("ignoreChanges", {"ignoreChanges": "true"})
SC = ("skipChangeCommits", {"skipChangeCommits": "true"})
ID = ("ignoreDeletes", {"ignoreDeletes": "true"})
changes("update", "UPDATE src SET v = 'z' WHERE id = 1", NONE, IC, SC, ID)
changes("delete_part", "DELETE FROM src WHERE id = 1", NONE, IC, SC, ID)
changes("delete_all", "DELETE FROM src", NONE, IC, SC, ID)
changes("delete_file", "DELETE FROM src WHERE id = 3", NONE, IC, SC, ID)
changes("truncate", "TRUNCATE TABLE src", NONE, ID)
changes("overwrite", "INSERT OVERWRITE src VALUES (9, 'o')", NONE, IC, SC, ID)
changes(
    "merge",
    "MERGE INTO src USING (SELECT 1 AS id, 'm' AS v) s ON src.id = s.id WHEN MATCHED THEN UPDATE SET v = s.v "
    "WHEN NOT MATCHED THEN INSERT *",
    NONE,
    IC,
    SC,
)
changes("optimize", "OPTIMIZE src", NONE)
changes("vacuum", "VACUUM src RETAIN 0 HOURS", NONE)
changes("set_property", "ALTER TABLE src SET TBLPROPERTIES ('x.y' = '1')", NONE)
changes("add_column", "ALTER TABLE src ADD COLUMN w INT", NONE, IC)
scenario(
    "delete_partition",
    [
        "INSERT INTO src VALUES (1, 'a'), (2, 'b')",
        (opts(ignoreDeletes="true"),),
        "DELETE FROM src WHERE v = 'a'",
        "INSERT INTO src VALUES (3, 'c')",
        (opts(ignoreDeletes="true"),),
    ],
    "CREATE TABLE src (id INT, v STRING) USING delta PARTITIONED BY (v) LOCATION '{path}'",
)

# Deletion vectors
DV = "CREATE TABLE src (id INT, v STRING) USING delta LOCATION '{path}' TBLPROPERTIES ('delta.enableDeletionVectors' = 'true')"
scenario("dv_initial", [ONE, "DELETE FROM src WHERE id = 1", (PATH,), TWO, (PATH,)], DV)
for name, options in [NONE, IC, SC, ID]:
    read = opts(**options) if options else PATH
    scenario(f"dv_after_{name}", [ONE, (read,), "DELETE FROM src WHERE id = 1", TWO, (read,)], DV)

# Starting points
for value in ["0", "1", "2", "latest", "5", "99"]:
    read = opts(startingVersion=value)
    scenario(f"starting_version_{value}", [ONE, TWO, THREE, (read,), "INSERT INTO src VALUES (5, 'e')", (read,)])
for value in ["2000-01-01", "2999-01-01", "garbage"]:
    read = opts(startingTimestamp=value)
    scenario(f"starting_timestamp_{value}", [ONE, TWO, (read,), THREE, (read,)])
scenario("starting_both", [ONE, (opts(startingVersion="0", startingTimestamp="2000-01-01"),)])
scenario("starting_bad", [ONE, (opts(startingVersion="-1"),), (opts(startingVersion="abc"),)])
scenario(
    "starting_past_change",
    [ONE, "UPDATE src SET v = 'z' WHERE id = 1", TWO, (opts(startingVersion="1"),), (opts(startingVersion="1"),)],
)
scenario(
    "starting_after_change",
    [ONE, "UPDATE src SET v = 'z' WHERE id = 1", TWO, (opts(startingVersion="3"),)],
)
scenario(
    "starting_changed_on_rerun",
    [ONE, (opts(startingVersion="0"),), TWO, (opts(startingVersion="latest"),), THREE, (PATH,)],
)

# Rate limits and other options
for key, value in [
    ("maxFilesPerTrigger", "1"),
    ("maxFilesPerTrigger", "0"),
    ("maxFilesPerTrigger", "x"),
    ("maxBytesPerTrigger", "1b"),
    ("maxBytesPerTrigger", "x"),
    ("ignoreChanges", "x"),
    ("skipChangeCommits", "x"),
    ("ignoreDeletes", "x"),
    ("failOnDataLoss", "x"),
    ("failOnDataLoss", "false"),
    ("excludeRegex", ".*"),
    ("no_such_option", "x"),
    ("withEventTimeOrder", "true"),
]:
    scenario(f"option_{key}_{value}", [ONE, TWO, (opts(**{key: value}),), THREE, (opts(**{key: value}),)])
scenario("batch_time_travel_option", [ONE, TWO, (opts(versionAsOf="1"),)])
scenario("batch_timestamp_option", [ONE, TWO, (opts(timestampAsOf="2000-01-01"),)])

# Change data feed
CDF = "CREATE TABLE src (id INT, v STRING) USING delta LOCATION '{path}' TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true')"
FEED = opts(readChangeFeed="true")
scenario("cdf_stream", [ONE, (FEED,), "UPDATE src SET v = 'z' WHERE id = 1", "DELETE FROM src WHERE id = 2", (FEED,), (FEED,)], CDF)
scenario("cdf_starting", [ONE, TWO, (opts(readChangeFeed="true", startingVersion="2"),), THREE, (opts(readChangeFeed="true", startingVersion="2"),)], CDF)
scenario("cdf_not_enabled", [ONE, (FEED,), "UPDATE src SET v = 'z' WHERE id = 1", (FEED,)])
scenario("cdf_not_enabled_start", [ONE, (opts(readChangeFeed="true", startingVersion="0"),)])

# Table shapes
scenario(
    "partitioned",
    [ONE, (PATH,), TWO, (PATH,)],
    "CREATE TABLE src (id INT, v STRING) USING delta PARTITIONED BY (v) LOCATION '{path}'",
)
MAPPED = (
    "CREATE TABLE src (id INT, v STRING) USING delta LOCATION '{path}' TBLPROPERTIES ("
    "'delta.columnMapping.mode' = 'name', 'delta.minReaderVersion' = '2', 'delta.minWriterVersion' = '5')"
)
scenario("mapped", [ONE, (PATH,), TWO, (PATH,)], MAPPED)
scenario("mapped_rename", [ONE, (PATH,), "ALTER TABLE src RENAME COLUMN v TO w", TWO, (PATH,), (PATH,)], MAPPED)
scenario("mapped_drop", [ONE, (PATH,), "ALTER TABLE src DROP COLUMN v", "INSERT INTO src VALUES (3)", (PATH,)], MAPPED)
scenario(
    "recreated",
    [ONE, (PATH,), "DROP TABLE src", f"CREATE OR REPLACE TABLE delta.`{{path}}` (id INT, v STRING) USING delta", (PATH,)],
)
scenario("replace_table", [ONE, (PATH,), "CREATE OR REPLACE TABLE src (id INT, v STRING) USING delta LOCATION '{path}'", TWO, (PATH,)])
scenario("not_delta", [(table('spark.readStream.format("delta").load("{path}_missing")'),)])
scenario("plain_parquet_dir", [(table('spark.readStream.format("delta").load("{path}/_delta_log")'),)])

# Graph shapes
scenario("in_view", [ONE, ('@dp.temporary_view\ndef v():\n  return spark.readStream.format("delta").load("{path}")\n' + table('spark.readStream.table("v")'),), TWO, ('@dp.temporary_view\ndef v():\n  return spark.readStream.format("delta").load("{path}")\n' + table('spark.readStream.table("v")'),)])
JOIN = table('spark.readStream.format("delta").load("{path}").join(spark.read.table("dim"), "id")')
scenario(
    "stream_static_join",
    ["CREATE TABLE dim (id INT, n STRING) USING parquet", "INSERT INTO dim VALUES (1, 'x'), (3, 'y')", ONE, (JOIN,), TWO, (JOIN,)],
)
TWO_SOURCES = table(
    'spark.readStream.format("delta").load("{path}").union(spark.readStream.format("delta").load("{path}"))'
)
scenario("same_source_twice", [ONE, (TWO_SOURCES,), TWO, (TWO_SOURCES,)])
MV_SOURCE = (
    '@dp.materialized_view(format="delta")\ndef mv():\n  return spark.read.table("src").filter("id > 1")\n'
    + table('spark.readStream.table("mv")')
)
scenario("graph_delta_mv", [ONE, (MV_SOURCE,), TWO, (MV_SOURCE,), (MV_SOURCE,)])
scenario(
    "graph_delta_streaming_table",
    [
        ONE,
        (
            '@dp.table(format="delta")\ndef s():\n  return spark.readStream.format("delta").load("{path}")\n'
            + table('spark.readStream.table("s")'),
        ),
        TWO,
        (
            '@dp.table(format="delta")\ndef s():\n  return spark.readStream.format("delta").load("{path}")\n'
            + table('spark.readStream.table("s")'),
        ),
    ],
)
DELTA_TARGET = '@dp.table(format="delta")\ndef t():\n  return spark.readStream.table("src")\n'
scenario("delta_target", [ONE, (DELTA_TARGET,), TWO, (DELTA_TARGET,)])
WINDOW = table(
    'spark.readStream.format("delta").load("{path}").selectExpr("CAST(id AS TIMESTAMP) AS ts", "id")'
    '.withWatermark("ts", "1 second").groupBy(__import__("pyspark").sql.functions.window("ts", "2 seconds")).count()'
)
scenario("windowed", [ONE, (WINDOW,), "INSERT INTO src VALUES (9, 'z')", (WINDOW,)])

# Schema changes and repeated rewrites
FOUR = "INSERT INTO src VALUES (4, 'd', 7)"
scenario("schema_add", [ONE, (PATH,), "ALTER TABLE src ADD COLUMN w INT", FOUR, (PATH,), "INSERT INTO src VALUES (5, 'e', 8)", (PATH,)])
scenario("schema_add_table", [ONE, (TABLE,), "ALTER TABLE src ADD COLUMN w INT", FOUR, (TABLE,)])
scenario("schema_add_before_first", [ONE, "ALTER TABLE src ADD COLUMN w INT", FOUR, (opts(startingVersion="0"),)])
scenario("schema_drop_not_null", [ONE, (PATH,), "ALTER TABLE src ALTER COLUMN id DROP NOT NULL", TWO, (PATH,)], "CREATE TABLE src (id INT NOT NULL, v STRING) USING delta LOCATION '{path}'")
scenario("dv_two_versions", [ONE, (opts(ignoreChanges="true"),), "DELETE FROM src WHERE id = 1", "DELETE FROM src WHERE id = 2", (opts(ignoreChanges="true"),)], DV)
scenario("dv_snapshot_after_update", [ONE, "UPDATE src SET v = 'z' WHERE id = 1", (PATH,)], DV)

# One row per file, so a delete of a row is a delete of a file on both engines
def layout(label, change, *variants):
    for name, options in variants:
        read = opts(**options) if options else PATH
        scenario(f"layout_{label}_{name}", [ONEA, ONEB, (read,), change, THREE, (read,), (read,)])
layout("delete", "DELETE FROM src WHERE id = 1", NONE, IC, SC, ID)
layout("update", "UPDATE src SET v = 'z' WHERE id = 1", NONE, IC, SC, ID)
ONER = "INSERT INTO src VALUES (1, 'a'), (2, 'b'), (3, 'c')"
scenario("rewrite_partial_delete", ["INSERT INTO src SELECT id, 'x' FROM range(1, 3) ORDER BY id", "OPTIMIZE src", (PATH,), "DELETE FROM src WHERE id = 1", (PATH,)])
scenario("dv_layout", [ONEA, ONEB, (PATH,), "DELETE FROM src WHERE id = 1", TWO, (PATH,)], DV)
scenario("dv_rewrite_partial", ["INSERT INTO src SELECT id, 'x' FROM range(1, 3)", "OPTIMIZE src", (PATH,), "DELETE FROM src WHERE id = 1", (PATH,)], DV)
for name, options in [("skip", {"skipChangeCommits": "true"}), ("deletes", {"ignoreDeletes": "true"}), ("changes", {"ignoreChanges": "true"})]:
    scenario(f"dv_rewrite_{name}", ["INSERT INTO src SELECT id, 'x' FROM range(1, 3)", "OPTIMIZE src", (opts(**options),), "DELETE FROM src WHERE id = 1", TWO, (opts(**options),)], DV)
WTS = "CREATE TABLE src (ts TIMESTAMP, id INT) USING delta LOCATION '{path}'"
WT = table('spark.readStream.table("src").withWatermark("ts", "1 second").groupBy(__import__("pyspark").sql.functions.window("ts", "2 seconds")).count()')
WP = table('spark.readStream.format("delta").load("{path}").withWatermark("ts", "1 second").groupBy(__import__("pyspark").sql.functions.window("ts", "2 seconds")).count()')
for name, w in [("table", WT), ("path", WP)]:
    scenario(f"window_{name}", ["INSERT INTO src VALUES (CAST(1 AS TIMESTAMP), 1)", "INSERT INTO src VALUES (CAST(2 AS TIMESTAMP), 2)", (w,), "INSERT INTO src VALUES (CAST(9 AS TIMESTAMP), 9)", (w,)], WTS)
for label, read in [("mv", MV_SOURCE), ("st_target", DELTA_TARGET)]:
    scenario(f"run_twice_{label}", [ONE, (read,)])

spark.stop()
(out / "done.txt").write_text(datetime.now(timezone.utc).isoformat() + "\n")
print(len(results), "cases")
