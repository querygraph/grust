# Structured metadata partition diagnostics

Sail `604a91f8d65076d142866095c5cd62999319c20d`, parent
`a9eecf5f539115ceb2b604d26d72b058cf9c435d`.

The materializer now retains structured Spark diagnostic data for changed or
omitted partition declarations and partition-plus-clustering conflicts. The
existing Connect codec preserves AnalysisException class, condition, SQL state
and parameters. The partition-conflict body includes Spark's template newline.
Catalog commands and their order, execution analysis, and the public streaming
rejection guard are unchanged. This does not add clustering support.

- Exact detached fmt/strict Clippy and [native library](native/rust.log):191 pass.
  Two added tests check native error data and Connect ErrorInfo, original retained
  identity partitioning, and absence of the rejected new target.
- [Production-only control](control/control.json): unchanged tests fail0/2 when
  both guards return the old message-only diagnostics. Only materialize.rs changes.
- [Fresh public receipt](public/receipt.json):300 selected tests +67 upstream
  Python executions pass against the exact rebuilt CLI; owned server stopped.
- [Spark reference](spark/PartitionErrorsOracle.scala): unmodified original
  registration helper and production DatasetManager4.2.1, with SQL-created
  existing table. Three cases pass exact cause class/condition/state/parameters
  and catalog-state assertions. Raw outer wrapper classes are retained in the log.

Original MaterializeTablesSuite:467 and :1050 now have partial native ports.
:402 also becomes partial for its omitted-partition rejection and retained
transform only; its initial/same-partition success schema and catalog-reordered
exact column assertions are still unported. Native existing-table seeding uses
MV metadata rather than the original SQL DDL fixture.

All three keep the original-Scala-suite flag false. The outer
TableMaterializationException(tableName,cause), source origins and original JVM
fixture execution against Sail remain open. Matching diagnostic data does not
establish that wrapper or full client exception/message hierarchy parity.
Current inventory:68 partial/394 unmapped among462 static sites,97 reviewed.

Fable CF-0448/Grust689582be accepted the initial source pending gates and found
the template newline difference; CF-0449 records folding that correction into
the final candidate. The initial8c442 source's passing191/native and300+67 public
receipts are retained separately. Its control preflight initially failed a
literal source-format assertion before mutation; the initial script is retained.
Final gates/control/public receipts above qualify the corrected source.

Run `python verify.py` with the local Sail/Spark Git object stores available.
