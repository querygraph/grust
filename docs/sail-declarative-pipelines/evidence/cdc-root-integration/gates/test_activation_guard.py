"""A public AutoCDC graph on the candidate binary: dry run accepted, real run refused, nothing written."""
import json
from pathlib import Path
import pytest
from pyspark.pipelines.spark_connect_graph_element_registry import SparkConnectGraphElementRegistry
from pyspark.pipelines.spark_connect_pipeline import create_dataflow_graph, start_run
from pyspark.pipelines.api import create_streaming_table, create_auto_cdc_flow
from pyspark.pipelines.graph_element_registry import graph_element_registration_context
from pyspark.sql.functions import col

def define(spark, schema, name):
    graph = create_dataflow_graph(spark, spark.catalog.currentCatalog(), schema, None)
    registry = SparkConnectGraphElementRegistry(spark, graph)
    registry.register_sql("CREATE MATERIALIZED VIEW source AS SELECT 1 AS id, 1 AS seq", Path("s.sql"))
    with graph_element_registration_context(registry):
        create_streaming_table("target")
        create_auto_cdc_flow(target="target", source="source", keys=["id"], sequence_by=col("seq"), stored_as_scd_type=1)
    return graph

def test_public_autocdc_run_is_refused(spark, tmp_path):
    spark.sql("CREATE SCHEMA IF NOT EXISTS guard_cdc")
    graph = define(spark, "guard_cdc", "x")
    stream = start_run(spark, graph, None, False, None, False, (tmp_path / "s").as_uri())
    with pytest.raises(Exception) as e:
        list(stream)
    print("REFUSED:", str(e.value)[:300])
    assert "incremental pipeline execution" in str(e.value)
    assert not spark.catalog.tableExists("guard_cdc.target")
