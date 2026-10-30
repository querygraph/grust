"""Nested schemas from Spark 4.2.1 MaterializeTablesSuite:735 and :780.

The original internal registerTable/materializeGraph fixture is exercised through
public materialized views and two complete runs of the same registered graph.
"""

import pytest
from pyspark import pipelines as dp
from pyspark.pipelines.graph_element_registry import graph_element_registration_context
from pyspark.sql.types import StructType


@pytest.mark.parametrize("nested", [False, True], ids=["arrays-and-maps", "nested-arrays-and-maps"])
def test_nested_table_schemas_after_two_materializations(pipeline_spark, pipeline, nested):
    _, registry, run = pipeline
    if nested:
        a_query = "select map(0, map(0, struct('a', 'b'))) m"
        b_query = "select array(array('a', 'b', 'c'), array('d', 'e', 'f')) arr"
        c_query = "select * from a join b where m[0][0].col1 = arr[0][0]"
        a_ddl = "m MAP<int, MAP<int, struct<col1: string, col2: string>>>"
        b_ddl = "arr ARRAY<ARRAY<string>>"
    else:
        a_query = "select map(1, struct('a', 'b')) m"
        b_query = None
        c_query = "select * from a join b where map_entries(m)[0].key = arr[0]"
        a_ddl = "m MAP<int, struct<col1: string, col2: string>>"
        b_ddl = "arr ARRAY<int>"

    with graph_element_registration_context(registry):
        dp.materialized_view(name="a")(lambda: pipeline_spark.sql(a_query))
        if nested:
            dp.materialized_view(name="b")(lambda: pipeline_spark.sql(b_query))
        else:
            dp.materialized_view(name="b")(
                lambda: pipeline_spark.createDataFrame([([1, 3, 5],), ([2, 4, 6],)], "arr ARRAY<int>")
            )
        dp.materialized_view(name="c")(lambda: pipeline_spark.sql(c_query))

    run()
    run()
    for name, ddl in [("a", a_ddl), ("b", b_ddl), ("c", a_ddl + ", " + b_ddl)]:
        assert pipeline_spark.table(name).schema == StructType.fromDDL(ddl)
