"""Schema acquisition follows actual reads before final validation (Spark 4.2.1)."""

import pytest
from pyspark.errors.exceptions.connect import AnalysisException, SparkException

CASES = [
    (declared, read, missing)
    for declared in (False, True)
    for read in (False, True)
    for missing in ("none", "first", "last")
    if missing != "none" or (read and not declared)
]


@pytest.mark.parametrize(("declared", "read", "missing"), CASES)
def test_virtual_schema_acquisition_does_not_mask_unresolved_flows(
    pipeline_factory, pipeline_spark, tmp_path, declared, read, missing
):
    _, registry, run = pipeline_factory()
    statements = [
        "CREATE MATERIALIZED VIEW events_int AS SELECT 1 AS id",
        "CREATE MATERIALIZED VIEW events_str AS SELECT 'x' AS id",
        "CREATE STREAMING TABLE merged" + (" (id INT)" if declared else ""),
        "CREATE FLOW merged_int AS INSERT INTO merged BY NAME SELECT * FROM STREAM(events_int)",
        "CREATE FLOW merged_str AS INSERT INTO merged BY NAME SELECT * FROM STREAM(events_str)",
    ]
    if read:
        statements.append("CREATE MATERIALIZED VIEW consumer AS SELECT id FROM merged")
    bad = "CREATE MATERIALIZED VIEW late AS SELECT * FROM missing_source"
    if missing == "first":
        statements.insert(0, bad)
    elif missing == "last":
        statements.append(bad)
    registry.register_sql(";".join(statements), tmp_path / "schema.sql")
    with pytest.raises(AnalysisException) as error:
        run(dry=True)
    assert error.value.getCondition() is None
    assert error.value.getSqlState() is None
    assert error.value.getMessageParameters() is None
    namespace = f"{pipeline_spark.catalog.currentCatalog()}.{pipeline_spark.catalog.currentDatabase()}"
    expected = []
    if read and not declared:
        expected.append(f"{namespace}.consumer")
    if missing != "none":
        expected.append(f"{namespace}.late")
    message = error.value.getMessage()
    direct = next(line for line in message.splitlines() if line.startswith("Flows with errors: "))
    assert direct == "Flows with errors: " + ", ".join(expected)
    downstream = next(
        line for line in message.splitlines() if line.startswith("Flows that failed due to upstream errors:")
    )
    assert downstream == "Flows that failed due to upstream errors: "
    assert not pipeline_spark.catalog.tableExists("merged")


@pytest.mark.parametrize(("declared", "read"), [(False, False), (True, False), (True, True)])
def test_final_schema_merge_preserves_structured_error(pipeline_factory, tmp_path, declared, read):
    _, registry, run = pipeline_factory()
    statements = [
        "CREATE MATERIALIZED VIEW events_int AS SELECT 1 AS id",
        "CREATE MATERIALIZED VIEW events_str AS SELECT 'x' AS id",
        "CREATE STREAMING TABLE merged" + (" (id INT)" if declared else ""),
        "CREATE FLOW merged_int AS INSERT INTO merged BY NAME SELECT * FROM STREAM(events_int)",
        "CREATE FLOW merged_str AS INSERT INTO merged BY NAME SELECT * FROM STREAM(events_str)",
    ]
    if read:
        statements.append("CREATE MATERIALIZED VIEW consumer AS SELECT id FROM merged")
    registry.register_sql(";".join(statements), tmp_path / "final-schema.sql")
    with pytest.raises(SparkException) as error:
        run(dry=True)
    _assert_merge_error(error.value, '"INT"', '"STRING"')


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("ARRAY<INT>", "ARRAY<STRING>"),
        ("STRUCT<x: INT>", "STRUCT<x: STRING>"),
        ("MAP<STRING, INT>", "MAP<STRING, STRING>"),
        ("DECIMAL(8,2)", "DECIMAL(9,3)"),
        ("INTERVAL YEAR TO MONTH", "INTERVAL DAY TO SECOND"),
        ("STRUCT<`Mixed Case`: INT>", "STRUCT<`Mixed Case`: STRING>"),
    ],
)
def test_final_merge_reports_enclosing_field_types(pipeline_factory, tmp_path, left, right):
    _, registry, run = pipeline_factory()
    registry.register_sql(
        ";".join(
            [
                f"CREATE MATERIALIZED VIEW events_left AS SELECT CAST(NULL AS {left}) AS id",
                f"CREATE MATERIALIZED VIEW events_right AS SELECT CAST(NULL AS {right}) AS id",
                "CREATE STREAMING TABLE merged",
                "CREATE FLOW merged_left AS INSERT INTO merged BY NAME SELECT * FROM STREAM(events_left)",
                "CREATE FLOW merged_right AS INSERT INTO merged BY NAME SELECT * FROM STREAM(events_right)",
            ]
        ),
        tmp_path / "nested-schema.sql",
    )
    with pytest.raises(SparkException) as error:
        run(dry=True)
    _assert_merge_error(error.value, f'"{left}"', f'"{right}"')


def _assert_merge_error(error, left, right):
    assert error.getCondition() == "CANNOT_MERGE_INCOMPATIBLE_DATA_TYPE"
    assert error.getSqlState() == "42825"
    parameters = error.getMessageParameters()
    # Producer scheduling is not an ordered contract. Check both original
    # types and require the message to preserve the actual parameter order.
    assert set(parameters) == {"left", "right"}
    assert {parameters["left"], parameters["right"]} == {left, right}
    assert error.getMessage().split("\n\nJVM stacktrace:")[0] == (
        "[CANNOT_MERGE_INCOMPATIBLE_DATA_TYPE] Failed to merge incompatible data types "
        f"{parameters['left']} and {parameters['right']}. Please check the data types "
        "of the columns being merged and ensure that they are compatible. If necessary, "
        "consider casting the columns to compatible data types before attempting the merge. "
        "SQLSTATE: 42825"
    )
