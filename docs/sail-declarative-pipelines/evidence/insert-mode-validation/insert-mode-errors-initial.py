"""INSERT INTO IF NOT EXISTS is a shared parse error, before pipeline policy."""

from pathlib import Path

import pytest
from pyspark.errors.exceptions.connect import ParseException


SINGLE_STATEMENTS = [
    "INSERT INTO missing IF NOT EXISTS SELECT 1",
    "INSERT INTO missing IF NOT EXISTS BY NAME SELECT 1",
    "INSERT INTO missing PARTITION(p=1) IF NOT EXISTS SELECT 1",
    "CREATE FLOW f AS INSERT INTO missing IF NOT EXISTS BY NAME SELECT 1",
    "CREATE FLOW a.f AS INSERT INTO missing IF NOT EXISTS SELECT 1",
    "EXPLAIN INSERT INTO missing IF NOT EXISTS SELECT 1",
]


def _check(error):
    assert error.getCondition() == "INVALID_STATEMENT_OR_CLAUSE"
    assert error.getSqlState() == "42601"
    assert error.getMessageParameters() == {"operation": "INSERT INTO ... IF NOT EXISTS"}
    assert "The statement or clause: INSERT INTO ... IF NOT EXISTS is not valid." in str(error)
    assert "insert-mode.sql" not in str(error)


@pytest.mark.parametrize("api", ["ordinary", "pipeline"])
@pytest.mark.parametrize("sql", SINGLE_STATEMENTS)
def test_insert_mode_parse_error_is_shared(pipeline_spark, pipeline, api, sql):
    _, registry, _ = pipeline
    with pytest.raises(ParseException) as captured:
        if api == "ordinary":
            pipeline_spark.sql(sql).collect()
        else:
            registry.register_sql(sql, Path("insert-mode.sql"))
    _check(captured.value)


@pytest.mark.parametrize(
    "first",
    [
        "CREATE FLOW a.f AS INSERT INTO st BY NAME SELECT 1",
        "CREATE TABLE t AS SELECT 1",
        "SET CATALOG CAST(CAST('bad' AS INT) AS STRING)",
    ],
)
def test_whole_file_parse_error_precedes_registration_and_evaluation(pipeline, first):
    _, registry, _ = pipeline
    with pytest.raises(ParseException) as captured:
        registry.register_sql(first + "; INSERT INTO missing IF NOT EXISTS SELECT 1", Path("insert-mode.sql"))
    _check(captured.value)
