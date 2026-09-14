# Typed DataFusion plan qualification

Source `7d74e26`, Capitola, DataFusion 55.1.0. Command:
`cargo test --locked -p grust-datafusion typed_relational_plans_execute_without_sql_serialization`.
One test passed; five were filtered out. The log retains the build and result.

The existing upstream context accepts a typed logical plan and returns a native
Arrow stream. This regression filters and projects two input batches and checks
schema naming and duplicate preservation without SQL serialization. It is not
Cypher lowering, a full DataFusion suite, or a performance measurement.
