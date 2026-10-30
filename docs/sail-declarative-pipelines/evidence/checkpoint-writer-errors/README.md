# Commit uncertainty through checkpoint writer errors

Sail `47c473e6b9af7b5e2e5fbe30070ab2fe407def49` preserves nested nonretryable
causes while classifying DataFusion ObjectStore/Parquet/I/O and direct Arrow I/O
errors. Existing ordinary categories/messages remain unchanged. The private helper
uses the existing typed cause traversal and cycle detection; no error object is
rewritten, and no unknown-commit marker is invented for ordinary provider errors.
No dependency, registry, checkpoint routing, session or API activation change.

## Actual writer control

Test-only source `1c86bdc4008239b878a4a75aba29bc0d189bed5a` on the unchanged
9579a7e8d base fails all four regressions: sequential/parallel Parquet serialization
and PUT/multipart completion. Each executes RemoteCheckpointWriteExec and its real
ParquetSink, publishes to InMemory, verifies one object with PAR1 header/footer and
actual PUT/complete counters, then observes an erroneous retryable classification.
The provider returns an object-store Generic error whose typed DataFusion Collection
contains both an injected lost-response error and a CommitStateUnknown marker.
The first display cause is insufficient; the retained second policy cause matters.

Identical writer test blobs pass the fixed tree. Sequential failures arrive as
DataFusion ParquetError; parallel failures arrive as IoError. Helper tests cover
ObjectStore, I/O, Parquet and Arrow wrappers, including direct Arrow I/O.
These tests qualify classification when a typed unknown marker exists, not a rule
that every failed provider call has unknown visibility or that publication is durable.

## Ordinary compatibility baseline and retained fixture failure

Initial candidate `c0d484a999a6e272900797aa6acb4708f41624aa` passed fmt/Clippy
but failed its ordinary Arrow-wrapper fixture (116 passed/1 failed before execution
library tests). It assumed the DataFusion-boxed Arrow I/O case classified as Io.
The test-only unchanged-production probe `8bf79af86d36d23cdb7fe83354a3760ebb045798`
measures four actual baselines: Io, Io, Unknown, FormatParquet. The corrected test
pins those exact categories/messages and separately preserves direct Arrow Io.
This corrects a fixture assumption; all four unknown-commit writer assertions are
unchanged. Raw failed and observed-baseline logs/receipts are retained here.

## Exact validation

Detached fmt, strict all-target/all-feature Clippy,117 common-datafusion and202
execution library tests pass. Optimized CPU-load runs pass all117 common tests
and the four actual writer regressions; each run's ten workers were stopped/joined.
The rebuilt CLI passes300 selected public cases and67 upstream Python executions
on Spark4.2.1. Exact source/log/binary hashes, original control test blobs and
server exit/no remaining listeners were checked before conditional advancement.

SHA256.json covers all archived evidence except itself. qualify.py captures the
advancement-time checks; its historical absolute /tmp paths and binary hashes can
be superseded by later builds, so use fresh paths/source pins when reproducing.
The Apple linker reports its existing unwind-size warning; builds/tests complete
and strict Clippy passes without lint suppression.

[Routing follow-up](routing-followup.md) records why context routing alone does not
cover planning effects or writer children. No whole-session, distributed-provider,
cleanup/deletion, streaming/CDC durability or full original Scala SDP verdict follows
from this fix. The462-site Spark inventory remains61 partial/401 unmapped.
