# Shared file-source support checkpoint

The operator requests notice before a new design phase to switch to Astra.
ORC support reaches that boundary. This note records a required format gap and
existing constraints; it selects no reader/writer implementation or dependency.

## Evidence and scope

SqlPipelineSuite:434 declares Parquet, ORC, JSON and CSV instances. It writes files,
creates an external table, then verifies a direct batch MV and a streaming-table
consumer. The [retained baseline](evidence/file-source-design-boundary/provenance.json)
shows three batch formats passing and ORC failing in Sail. The same generated ORC
fixture reads successfully on Spark 4.2.1, so the format gap is not explained by
an invalid file. A final Sail counterprobe still fails after the empty-location fix.
ORC is not counted as skipped or passing Sail coverage.

Sail's data-source registry currently registers Arrow, Avro, binary, CSV, JSON,
Parquet, text and streaming/utility/lake sources, but no ORC source. Direct SQL
format/path reads reuse this registry before catalog resolution. ORC support must
therefore live in shared Sail data-source machinery, not a pipeline-only evaluator
or LakeCat adapter. Reader/schema/scan execution must follow existing resolver,
optimizer, physical-planner, codecs and JobService conventions.

## Decisions for the next design pass

- Review reader/writer options against the actual Arrow/DataFusion versions and
  their dependency/import cost. No unverified library/version recommendation is
  selected here. Preserve the original format requirement rather than substituting
  Parquet for ORC.
- Establish the general read/schema/partition/path/options contract and distributed
  execution/serialization coverage through Sail's existing data-source interfaces.
- Preserve the original writer prerequisite and streaming-table consumer as separate
  acceptance work. Current ports use external PyArrow/stdlib input generation and
  cannot establish the unmodified fixture's writer or streaming behavior.
- Keep invalid input causes, per-flow attribution and run-summary errors distinct.
  Spark exposes the empty-location cause in preceding events while the outer
  pipeline exception summarizes unresolved flows. That overlaps the existing
  [failure/event handoff](BATCH-EVENT-DESIGN-HANDOFF.md).

Parquet/JSON/CSV and empty SQL location tests now pass on Sail. Full four-format,
original Scala-suite, missing-file attribution and streaming assertions remain open.

## Completed architecture pass

The announced Astra pass now has a [shared ORC source design](ORC-SOURCE-DESIGN.md)
with exact dependency compilation, bidirectional Spark 4.2.1 fixtures, raw type-
metadata recovery and explicit source/sink codec boundaries. Implementation starts
with a retained malformed-block regression and dependency hardening, followed by
the metadata/type bridge. Native ZSTD probe success does not implement ORC
in Sail; the four current Sail failures and broader type limitations are retained.
