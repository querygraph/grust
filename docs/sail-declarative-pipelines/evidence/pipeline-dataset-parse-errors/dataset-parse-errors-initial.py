"""Original pipeline dataset parser rejection cases, through SQL normalization."""

import pytest
from pyspark.errors.exceptions.connect import ParseException


@pytest.mark.parametrize("kind", ["MATERIALIZED VIEW", "STREAMING TABLE"])
@pytest.mark.parametrize(
    ("clause", "message"),
    [
        (
            "LOCATION 'dbfs:/path/to/table'",
            "Specifying location is not supported for CREATE {kind} statements. "
            "The storage location for a pipeline dataset is managed by the pipeline itself.",
        ),
        (
            "STORED AS TEXTFILE",
            "The STORED AS syntax is not supported for CREATE {kind} statements. "
            "Consider using the Data Source based USING clause instead.",
        ),
        (
            "ROW FORMAT DELIMITED FIELDS TERMINATED BY ','",
            "Hive SerDe format options are not supported for CREATE {kind} statements.",
        ),
        (
            "CLUSTERED BY (a) INTO 5 BUCKETS",
            "Bucketing is not supported for CREATE {kind} statements. "
            "Please remove any bucket spec specified in the statement.",
        ),
        (
            "OPTIONS ('key' = 'value')",
            "Options are not supported for CREATE {kind} statements. "
            "Please remove any OPTIONS lists specified in the statement.",
        ),
    ],
    ids=["location", "stored-as", "serde", "bucket", "options"],
)
def test_pipeline_dataset_rejects_table_storage_clauses(spark, kind, clause, message):
    with pytest.raises(ParseException) as captured:
        spark.sql(f"CREATE {kind} table1 {clause} AS SELECT * FROM input").collect()
    assert captured.value.getCondition() == "_LEGACY_ERROR_TEMP_0035"
    assert captured.value.getMessageParameters() == {"message": message.format(kind=kind)}
    assert captured.value.getSqlState() is None


def test_materialized_view_requires_query(spark):
    with pytest.raises(ParseException) as captured:
        spark.sql("CREATE MATERIALIZED VIEW table").collect()
    assert "Unable to find query for CREATE MATERIALIZED VIEW statement." in str(captured.value)
