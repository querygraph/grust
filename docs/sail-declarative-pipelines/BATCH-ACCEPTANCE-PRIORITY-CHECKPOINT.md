# Original batch SDP acceptance checkpoint

The user goal is Sail SDP support that passes every Spark4.2.1 SDP test, with
batch first, followed by streaming/Iggy and CDC, in reviewable commits.
The user was notified before this next design phase at CF-0426 so they can
switch to Astra. Use this checkpoint to select the next implementation work
from original assertion dependencies.

## Current acceptance evidence

Product HEADdb650c40e7605658b047fafac2fc721a395c4a0c and its rebuilt CLI are
qualified by337 analyzer/plan/Connect tests,300 selected public,67 upstream
Python and19 paired focused tests. Shared diagnostics60a separately passes173
common library tests. The [inventory](spark-4.2.1-inventory.json) is462 static
registrations,97 assertion-reviewed,63 partial behavioral ports and399 unmapped.
None is fully qualified by original Scala-suite execution; selections and
behavioral ports must stay distinct from that full goal.

The scalar, decimal, worker, config and conditional units are useful Sail
improvements. Their additional conformance matrices remain retained, including
all known failures. A new generic SQL-parity prerequisite for SDP needs a concrete
original assertion dependency. Those broader matrices do not replace completing
the original graph, catalog, event, session and streaming assertions.

Peer review d3d18043, SDP-ASSERTION-DEPENDENCIES.md in the Fable Grust worktree,
reports construct searches with hit-context review across47 Scala suites and9
PySpark modules. It found no direct original SDP assertion requiring the broad
string-cast/CASE/decimal/folding/replay work. This is a prioritization finding;
absence of a token is not proof about arbitrary generated expressions or helper
behavior. Per-assertion dependency review remains necessary.

## Original source checked by the coordinator

All references use Spark617618396087429b5627a86ce933bb0f5d6645cb,
sql/pipelines/src/test/scala/org/apache/spark/sql/pipelines/graph/SqlPipelineSuite.scala.

| Registration | Assertions and boundary |
| --- | --- |
| :44–88, simple SQL dataset registration | Mixed batch/STREAM/external-input/CREATE FLOW graph. Four flows, two tables, one view; exact inputs, destinations and external-input sets. Partial batch portions cannot qualify the whole fixture. |
| :403–432, arbitrary schemas | Both materialized view and streaming table read an external namespace; both must return1,2,3. This is also a mixed fixture. |
| :540–559, declared table schema | Materialized-view graph resolves and validates; LONG range schema must be non-nullable. This is a concrete schema assertion, without string casts or CASE. |
| :562–579, multipart table names | Two schemas, cross-schema materialized-view dependency; both outputs return1. Now paired-qualified as a public assertion port with both answers and owned cleanup; original Scala remains unexecuted. |
| :599–615, multipart temporary view | Now paired-qualified: ParseException/INVALID_TEMP_OBJ_QUALIFIER with structured42602/parameters. SESSION/SYSTEM.SESSION normalization is separately checked; original Scala remains unexecuted. |
| :634–734, catalog/database directives | Two SQL files, per-file reset, current namespace capture, fixed temp-view namespace, cross-catalog inputs, STREAM over CTE, five output checks. STREAM is a batch CTE here, already handled by substitution; this case does not require a streaming runtime. |
| :739–757, invalid catalog expression grid | CONCAT(foo,'1') and test.cat must fail registration with the Failed to resolve catalog expression prefix. Existing behavioral ports cover that narrow requirement; extra arithmetic matrices are separate. |

## Existing catalog fixture: historical and current qualification

The previous checkpoint missed existing evidence in CATALOG-ACCEPTANCE.md and
the canonical inventory. At Sail8d044db386, catalog_scope.py already preserves
both SQL files and all five assertions with memory/memory and memory/LakeCat
profiles, including STREAM(batch CTE). It is a public assertion port, not an
unmet streaming runtime case. The old parent failure and its CTE fix are retained.

A fresh current run now passes the seven-output memory/memory runner, provider/
schema metadata, hidden private views, session defaults and cleanup. Four isolated
batch-CTE cases also pass unchanged on Spark4.2.1 and Sail. Reuse that runner.
Unique namespaces, explicit storage providers and configured catalogs are
documented fixture adaptations; the SQL is not literally unchanged text.

| Target | Expected id rows |
| --- | --- |
| pipelineCatalog.otherDatabase2.mv3 | 1,2 |
| otherCatalog.otherDatabase.mv4 | 2,4 |
| otherDatabase2.mv5 | 1,2,3,4 |
| otherDatabase2.mv6 | 0,1,2 |
| pipelineCatalog.pipelineDatabase.mv6 | 1,2,3,4 |

Pinned TestGraphRegistrationContext defaults are spark_catalog and test_db.
The two files' mv6 outputs remain distinct because each file begins in the
pipeline namespace. The original two-catalog JVM substrate and original Scala
suite execution remain unqualified. The memory/LakeCat run is historical, not a
new qualification of today's runtime.

## Newly covered original batch site and next work

[SqlPipelineSuite:562](evidence/original-multipart/README.md) now has a paired
public test: two database-qualified materialized views, one registration/run,
cross-namespace dependency and both Row(1) answers. Exact9 namespace/CTE tests
pass on both engines. The initial Spark setup error and narrowly corrected
static-warehouse fixture are retained. Only this site's inventory status moves
from unmapped to partial. Fable04eb37ac accepts the port.

[SqlPipelineSuite:599](evidence/temporary-view-qualifiers/README.md) now has
a product fix and paired assertion port. Query-defined views use Spark namespace
normalization, shared diagnostics and typed parse-error propagation; arbitrary
qualifiers fail with the original exception class/condition. Thirty direct/API
cases match, including diagnostic quoting, and both unchanged counterfactual
tests fail when their production behavior is disabled. CREATE USING and DROP
follow separate paths and are outside this assertion's coverage.

The six still-unmapped SQL registrations are streaming/mixed cases (:44, :197,
:270, :403, :808, :1030). Existing partial sites still have internal/metadata/
lifecycle assertions to qualify. Do not mistake32 SQL partial ports for complete
batch or Scala-suite acceptance.

Next design checkpoint: metadata-only materialization. MaterializeTablesSuite:125
uses two internal registerFlow/registerTable definitions, then materializeGraph;
it checks nullable INT x and STRING y catalog columns. :374 checks declared
two-column schema plus identity partition x2. Inspect the original table/flow
kinds and Sail's existing materialization/ownership seam before choosing native
or public fixtures. An internal metadata assertion and a public streaming-query
contract are different entry points; do not relabel the tables or weaken runtime
guards to obtain a pass. CF-0440 explicitly rejects moving the public Table|Sink
guard after catalog materialization: that would introduce side effects before
the existing rejection. Use the internal metadata seam under its ownership
contract; verify streaming merge/truncate/property/failure branches separately. Original Source is graph/MaterializeTablesSuite.scala
at the same Spark pin. Batch event/failure-handler assertions remain open too.

Record setup, registration, preparation/start, answers, structured failure
metadata and cleanup separately. Existing incremental/sink guards remain until
their effect paths are qualified. Do not infer streaming activation authority
from a fixture or count batch portions as full mixed-case coverage.

## Design phase deliverables

Choose the adapter/harness path needed to exercise the actual original
assertions and expose the first missing product behavior. Keep public behavioral
ports, native internal-graph checks and original-suite execution distinct.
Then make the next source fix in a small commit with direct failing/passing
evidence for that original assertion. Preserve mixed-case streaming obligations
and every known scalar regression while prioritizing direct batch progress.
