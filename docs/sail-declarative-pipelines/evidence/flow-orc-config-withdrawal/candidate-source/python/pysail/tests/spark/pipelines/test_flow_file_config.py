"""Supplemental file-source checks for isolated graph/flow SQL configuration.

Spark's source contract is ConnectValidPipelineSuite:625, :664 and :723:
https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/pipelines/src/test/scala/org/apache/spark/sql/pipelines/graph/ConnectValidPipelineSuite.scala
These ORC fixtures extend that contract; they are not exact ports of those tests.
"""

import hashlib
from contextlib import contextmanager
from uuid import uuid4

import pyarrow as pa
import pytest
from pyarrow import orc
from pysail.testing.spark.utils.common import is_jvm_spark
from pysail.testing.spark.utils.sql import escape_sql_string_literal
from pyspark.errors import PySparkException
from pyspark.sql import Row
from pyspark.sql import types as T
from pyspark.sql.connect import proto as pb

dp = pytest.importorskip("pyspark.pipelines")
registry_module = pytest.importorskip("pyspark.pipelines.spark_connect_graph_element_registry")
client = pytest.importorskip("pyspark.pipelines.spark_connect_pipeline")
registration = pytest.importorskip("pyspark.pipelines.graph_element_registry")

MERGE_SCHEMA = "spark.sql.orc.mergeSchema"
ORC_IMPL = "spark.sql.orc.impl"


@pytest.fixture
def native_orc_pipeline_session(pipeline_spark):
    settings = {MERGE_SCHEMA: "false", ORC_IMPL: "native"}
    previous = {key: pipeline_spark.conf.get(key) for key in settings}
    try:
        for key, value in settings.items():
            pipeline_spark.conf.set(key, value)
        yield pipeline_spark
    finally:
        for key, value in previous.items():
            pipeline_spark.conf.set(key, value)


@pytest.fixture
def evolving_orc_files(tmp_path):
    directory = tmp_path / "orc_input"
    directory.mkdir()
    for index in range(11):
        columns = {"id": pa.array([index], type=pa.int32())}
        if index == 10:
            columns["extra"] = pa.array([42], type=pa.int32())
        orc.write_table(pa.table(columns), directory / f"{index:02d}.orc")
    return directory


@contextmanager
def configured_graph(spark, sql_conf):
    graph_id = client.create_dataflow_graph(spark, None, None, sql_conf)
    try:
        yield graph_id, registry_module.SparkConnectGraphElementRegistry(spark, graph_id)
    finally:
        command = pb.Command()
        command.pipeline_command.drop_dataflow_graph.dataflow_graph_id = graph_id
        spark.client.execute_command(command)


def run_graph(spark, graph_id, tmp_path, refresh=None):
    client.handle_pipeline_events(
        client.start_run(spark, graph_id, None, False, refresh, False, (tmp_path / graph_id).as_uri())
    )


@pytest.mark.parametrize(
    "graph_merge, flow_merge, read_merge, merged",
    [
        pytest.param("true", None, None, True, id="graph-default"),
        pytest.param("true", "false", None, False, id="flow-overrides-graph"),
        pytest.param("false", "false", "true", True, id="read-option-overrides-flow"),
    ],
)
def test_orc_schema_merge_uses_graph_flow_and_read_precedence(
    native_orc_pipeline_session, evolving_orc_files, tmp_path, graph_merge, flow_merge, read_merge, merged
):
    spark = native_orc_pipeline_session
    output = "flow_file_config_" + uuid4().hex
    flow_conf = {} if flow_merge is None else {MERGE_SCHEMA: flow_merge}

    def read_input():
        reader = spark.read
        if read_merge is not None:
            reader = reader.option("mergeSchema", read_merge)
        return reader.orc(str(evolving_orc_files))

    try:
        with configured_graph(spark, {MERGE_SCHEMA: graph_merge}) as (graph_id, registry):
            with registration.graph_element_registration_context(registry):
                dp.materialized_view(name=output, spark_conf=flow_conf, format="parquet")(read_input)
            run_graph(spark, graph_id, tmp_path)
        assert spark.conf.get(MERGE_SCHEMA) == "false"
        assert spark.conf.get(ORC_IMPL) == "native"
        frame = spark.table(output)
        fields = [T.StructField("id", T.IntegerType())]
        expected = [Row(id=index) for index in range(11)]
        if merged:
            fields.append(T.StructField("extra", T.IntegerType()))
            expected = [Row(id=index, extra=None) for index in range(10)] + [Row(id=10, extra=42)]
        assert frame.schema == T.StructType(fields)
        assert frame.orderBy("id").collect() == expected
    finally:
        spark.sql(f"DROP TABLE IF EXISTS {output}")


@pytest.mark.skipif(is_jvm_spark(), reason="Sail only: Hive ORC reader is intentionally unsupported")
def test_persisted_orc_input_uses_consumer_flow_settings(native_orc_pipeline_session, evolving_orc_files, tmp_path):
    """Supplemental Sail capability guard, not a Spark reader-compatibility assertion."""
    spark = native_orc_pipeline_session
    suffix = uuid4().hex
    producer, consumer = "persisted_orc_" + suffix, "orc_consumer_" + suffix
    files = sorted(evolving_orc_files.glob("*.orc"))
    hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in files]
    try:
        location = escape_sql_string_literal(str(evolving_orc_files))
        spark.sql(f"CREATE TABLE {producer} (id INT) USING orc LOCATION '{location}'")
        assert spark.table(producer).orderBy("id").collect() == [Row(id=index) for index in range(11)]
        with configured_graph(spark, None) as (graph_id, registry):
            with registration.graph_element_registration_context(registry):
                # Analysis sees this definition. Consumer-only refresh must instead
                # read the existing ORC table, without executing this producer.
                dp.materialized_view(name=producer, format="orc")(
                    lambda: spark.range(1).selectExpr("CAST(999 AS INT) AS id")
                )
                dp.materialized_view(name=consumer, spark_conf={ORC_IMPL: "hive"}, format="parquet")(
                    lambda: spark.table(producer)
                )
            with pytest.raises(PySparkException, match="Hive ORC reader is not supported"):
                run_graph(spark, graph_id, tmp_path, refresh=[consumer])
        assert spark.conf.get(ORC_IMPL) == "native"
        assert spark.conf.get(MERGE_SCHEMA) == "false"
        assert spark.table(producer).orderBy("id").collect() == [Row(id=index) for index in range(11)]
    finally:
        spark.sql(f"DROP TABLE IF EXISTS {consumer}")
        spark.sql(f"DROP TABLE IF EXISTS {producer}")
    assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in files] == hashes
