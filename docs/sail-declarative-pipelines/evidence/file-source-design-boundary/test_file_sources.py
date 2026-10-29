"""Batch file-input assertions from Spark's SqlPipelineSuite."""

import json

import pyarrow as pa
import pytest
from pyarrow import orc, parquet
from pyspark.errors.exceptions.connect import AnalysisException

pytest.importorskip("pyspark.pipelines")


@pytest.mark.parametrize("file_format", ["parquet", "orc", "json", "csv"])
def test_batch_pipeline_reads_file_source(pipeline_spark, pipeline, tmp_path, file_format):
    directory = tmp_path / ("input_" + file_format)
    directory.mkdir()
    table = pa.table({"id": pa.array([0, 1, 2], type=pa.int64())})
    if file_format == "parquet":
        parquet.write_table(table, directory / "part.parquet")
    elif file_format == "orc":
        orc.write_table(table, directory / "part.orc")
    elif file_format == "json":
        (directory / "part.json").write_text("".join(json.dumps({"id": value}) + "\n" for value in range(3)))
    else:
        (directory / "part.csv").write_text("0\n1\n2\n")
    _, registry, run = pipeline
    output = "file_output_" + file_format
    path = str(directory).replace("`", "``")
    registry.register_sql(
        f"CREATE MATERIALIZED VIEW {output} AS SELECT * FROM {file_format}.`{path}`",
        tmp_path / "files.sql",
    )
    run()
    frame = pipeline_spark.table(output)
    expected = ["0", "1", "2"] if file_format == "csv" else [0, 1, 2]
    assert [row[0] for row in frame.orderBy(frame.columns[0]).collect()] == expected


@pytest.mark.parametrize("context", ["query", "pipeline"])
def test_empty_sql_file_location_is_rejected(pipeline_spark, pipeline, tmp_path, context):
    if context == "pipeline":
        _, registry, run = pipeline
        registry.register_sql("CREATE MATERIALIZED VIEW empty_location AS SELECT * FROM csv.``", tmp_path / "empty.sql")
    with pytest.raises(AnalysisException, match="The location name cannot be empty string"):
        if context == "pipeline":
            run()
        else:
            pipeline_spark.sql("SELECT * FROM csv.``").collect()
    assert not pipeline_spark.catalog.tableExists("empty_location")
