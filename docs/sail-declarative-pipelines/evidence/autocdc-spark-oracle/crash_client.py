import json, sys
from pathlib import Path
from pyspark import pipelines as dp
from pyspark.pipelines.graph_element_registry import graph_element_registration_context
from pyspark.pipelines import spark_connect_pipeline as client
from pyspark.pipelines.spark_connect_graph_element_registry import SparkConnectGraphElementRegistry
from pyspark.sql import SparkSession
root = Path(sys.argv[1]); port = sys.argv[2]; show = sys.argv[3] == "show"
SCHEMA = "id INT, name STRING, seq BIGINT"
s = SparkSession.builder.remote(f"sc://localhost:{port}").create()
s.conf.set("spark.sql.warehouse.dir", (root / "wh").as_uri())
s.sql(f"CREATE TABLE IF NOT EXISTS target (id INT, name STRING, seq BIGINT, __spark_autocdc_metadata STRUCT<deleteSequence:BIGINT,upsertSequence:BIGINT>) USING delta LOCATION '{root}/target' TBLPROPERTIES ('delta.enableInCommitTimestamps'='true')")
def run():
    g = client.create_dataflow_graph(s, None, None, None)
    r = SparkConnectGraphElementRegistry(s, g)
    with graph_element_registration_context(r):
        @dp.temporary_view
        def changes():
            return s.readStream.format("json").schema(SCHEMA).load(str(root / "landing"))
        dp.create_streaming_table("target", format="delta")
        dp.create_auto_cdc_flow(target="target", source="changes", keys=["id"], sequence_by="seq")
    client.handle_pipeline_events(client.start_run(s, g, None, False, None, False, (root / "st").as_uri()))
run()
if show:
    run()
    print("ROWS " + json.dumps({r.id: [r.name, r.seq] for r in s.table("target").collect()}))
