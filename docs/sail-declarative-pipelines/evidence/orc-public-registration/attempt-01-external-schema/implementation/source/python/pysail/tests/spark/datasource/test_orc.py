"""Public ORC read entry points and focused Spark 4.2.1 schema contracts."""

import hashlib
from pathlib import Path

import pyarrow as pa
import pytest
from pyarrow import orc
from pyspark.sql import Row
from pyspark.sql import types as T

from pysail.testing.spark.utils.sql import escape_sql_identifier, escape_sql_string_literal


@pytest.fixture
def orc_spark(spark):
    settings = {
        "spark.sql.orc.impl": "native",
        "spark.sql.orc.mergeSchema": "false",
        "spark.sql.caseSensitive": "false",
        "spark.sql.timeType.enabled": "true",
    }
    previous = {key: spark.conf.get(key) for key in settings}
    try:
        for key, value in settings.items():
            spark.conf.set(key, value)
        yield spark
    finally:
        for key, value in previous.items():
            spark.conf.set(key, value)


def write_ids(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    orc.write_table(pa.table({"id": pa.array(values, type=pa.int32())}), path)


def test_orc_dataframe_and_sql_path_read(orc_spark, tmp_path):
    path = tmp_path / "input.orc"
    orc.write_table(
        pa.table({"id": pa.array([1, 2], type=pa.int32()), "label": pa.array(["one", None], type=pa.string())}),
        path,
    )
    frames = [
        orc_spark.read.orc(str(path)),
        orc_spark.read.format("orc").load(str(path)),
        orc_spark.sql(f"SELECT * FROM orc.`{escape_sql_identifier(str(path))}`"),
    ]
    schema = T.StructType([T.StructField("id", T.IntegerType()), T.StructField("label", T.StringType())])
    for frame in frames:
        assert frame.schema == schema
        assert frame.orderBy("id").collect() == [Row(id=1, label="one"), Row(id=2, label=None)]


def test_orc_external_catalog_table_reads_existing_files(orc_spark, tmp_path):
    directory = tmp_path / "external_orc"
    path = directory / "part.orc"
    write_ids(path, [3, 1])
    original_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    name = "orc_external_reader"
    try:
        orc_spark.sql(f"CREATE TABLE {name} USING orc LOCATION '{escape_sql_string_literal(str(directory))}'")
        assert orc_spark.catalog.tableExists(name)
        frame = orc_spark.table(name)
        assert frame.schema == T.StructType([T.StructField("id", T.IntegerType())])
        assert frame.orderBy("id").collect() == [Row(id=1), Row(id=3)]
    finally:
        orc_spark.sql(f"DROP TABLE IF EXISTS {name}")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == original_hash


def test_orc_merge_schema_includes_the_eleventh_file(orc_spark, tmp_path):
    directory = tmp_path / "merge"
    for index in range(10):
        write_ids(directory / f"{index:02d}.orc", [index])
    orc.write_table(
        pa.table({"id": pa.array([10], type=pa.int32()), "extra": pa.array([42], type=pa.int32())}),
        directory / "10.orc",
    )
    frame = orc_spark.read.option("mergeSchema", "true").orc(str(directory))
    assert frame.schema == T.StructType([T.StructField("id", T.IntegerType()), T.StructField("extra", T.IntegerType())])
    assert frame.orderBy("id").collect() == [Row(id=index, extra=None) for index in range(10)] + [Row(id=10, extra=42)]
    orc_spark.conf.set("spark.sql.orc.mergeSchema", "true")
    inherited = orc_spark.read.orc(str(directory))
    assert inherited.schema == frame.schema
    assert inherited.orderBy("id").collect() == frame.orderBy("id").collect()


@pytest.mark.parametrize("case_sensitive", [False, True])
@pytest.mark.parametrize("requested", ["alias", "omitted", "empty"])
def test_orc_supplied_schema_retains_discovered_partitions(orc_spark, tmp_path, case_sensitive, requested):
    # Retained Spark reference: supplied schemas do not whitelist discovered
    # partitions; CI aliases bind directory keys, while CS aliases are file fields.
    directory = tmp_path / "partitioned"
    write_ids(directory / "part=west" / "part.orc", [1, 2])
    write_ids(directory / "part=east" / "part.orc", [3])
    orc_spark.conf.set("spark.sql.caseSensitive", str(case_sensitive).lower())
    requested_fields = [] if requested == "empty" else [T.StructField("id", T.IntegerType(), False)]
    if requested == "alias":
        requested_fields.insert(0, T.StructField("PART", T.StringType(), False))
    frame = orc_spark.read.schema(T.StructType(requested_fields)).orc(str(directory))
    if requested == "empty":
        assert frame.schema == T.StructType([T.StructField("part", T.StringType())])
        assert frame.orderBy("part").collect() == [Row(part="east"), Row(part="west"), Row(part="west")]
    elif requested == "alias" and case_sensitive:
        assert frame.schema == T.StructType(
            [
                T.StructField("PART", T.StringType()),
                T.StructField("id", T.IntegerType()),
                T.StructField("part", T.StringType()),
            ]
        )
        assert frame.orderBy("id").collect() == [
            Row(PART=None, id=1, part="west"),
            Row(PART=None, id=2, part="west"),
            Row(PART=None, id=3, part="east"),
        ]
        assert frame.filter("PART = 'west'").collect() == []
    else:
        partition = "PART" if requested == "alias" else "part"
        assert frame.schema == T.StructType(
            [T.StructField("id", T.IntegerType()), T.StructField(partition, T.StringType())]
        )
        assert [tuple(row) for row in frame.orderBy("id").collect()] == [(1, "west"), (2, "west"), (3, "east")]
    partition = "PART" if requested == "alias" and not case_sensitive else "part"
    assert frame.filter(f"{partition} = 'west'").count() == 2


def test_orc_time_schema_and_requested_precision_preserve_stored_nanoseconds(orc_spark):
    # Frozen Spark-written file, including fractional bits in declared TIME(0).
    path = Path(__file__).with_name("orc_data") / "time_precisions.orc"
    assert (
        hashlib.sha256(path.read_bytes()).hexdigest()
        == "7504f8007af001893ccd60b873ded01bffae4b4cf4af95b1e054e7b07ff92986"
    )
    expected = [0, 45_296_123_456_000, 86_399_999_999_000, None]
    frame = orc_spark.read.orc(str(path))
    assert frame.schema == T.StructType(
        [T.StructField("id", T.IntegerType())]
        + [T.StructField(f"t{precision}", T.TimeType(precision)) for precision in (0, 3, 6)]
    )
    table = frame.orderBy("id").toArrow()
    for precision in (0, 3, 6):
        values = table.column(f"t{precision}")
        assert values.type == pa.time64("ns")
        assert values.cast(pa.int64()).to_pylist() == expected
    # Requested-schema reinterpretation differs from an SQL TIME precision cast.
    requested = T.StructType([T.StructField("id", T.IntegerType()), T.StructField("t0", T.TimeType(3))])
    reinterpreted = orc_spark.read.schema(requested).orc(str(path))
    assert reinterpreted.schema == requested
    assert reinterpreted.orderBy("id").toArrow().column("t0").cast(pa.int64()).to_pylist() == expected
