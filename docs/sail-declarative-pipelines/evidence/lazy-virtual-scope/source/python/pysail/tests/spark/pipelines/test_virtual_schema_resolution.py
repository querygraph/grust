"""Schema acquisition follows actual reads before final validation (Spark 4.2.1)."""

import pytest
from pyspark.errors.exceptions.connect import AnalysisException

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
