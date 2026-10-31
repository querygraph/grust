# Original batch SDP acceptance checkpoint

The user goal is Sail SDP support that passes every Spark4.2.1 SDP test, with
batch first, followed by streaming/Iggy and CDC, in reviewable commits.
The user was notified before this next design phase at CF-0426 so they can
switch to Astra. Use this checkpoint to select the next implementation work
from original assertion dependencies.

## Current acceptance evidence

Product d99e8b86d4db7aa2c5f79848496e6f3bfad6acb2 is qualified by component
and public selections. The [inventory](spark-4.2.1-inventory.json) remains462
static registrations,97 assertion-reviewed,61 partial behavioral ports and401
unmapped. None is fully qualified by executing its original Scala suite against
Sail. These counts and the300 selected public/67 Python executions must stay
distinct from full acceptance.

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
| :562–579, multipart table names | Two schemas, cross-schema materialized-view dependency; both outputs return1. A batch-only candidate for direct qualification. |
| :599–615, multipart temporary view | Requires ParseException class and INVALID_TEMP_OBJ_QUALIFIER. |
| :634–734, catalog/database directives | Two SQL files, per-file reset, current namespace capture, fixed temp-view namespace, cross-catalog inputs, STREAM over CTE, five output checks. Contains streaming; batch-only adaptation is partial. |
| :739–757, invalid catalog expression grid | CONCAT(foo,'1') and test.cat must fail registration with the Failed to resolve catalog expression prefix. Existing behavioral ports cover that narrow requirement; extra arithmetic matrices are separate. |

## Next direct probe: catalog/database fixture

Run the original :634–734 setup and SQL files verbatim against pinned Spark and
the exact qualified Sail CLI. Keep source placeholders, file order and statement
boundaries explicit. The five checkAnswer targets are:

| Target | Expected id rows |
| --- | --- |
| pipelineCatalog.otherDatabase2.mv3 | 1,2 |
| otherCatalog.otherDatabase.mv4 | 2,4 |
| otherDatabase2.mv5 | 1,2,3,4 |
| otherDatabase2.mv6 | 0,1,2 |
| pipelineCatalog.pipelineDatabase.mv6 | 1,2,3,4 |

Resolve the actual TestGraphRegistrationContext defaults from the pin.
The second file's mv6 must use the reset pipeline namespace, distinct from the
first file's mv6. Preserve the original quoted identifiers and the STREAM/CTE
query; do not silently replace them with simpler batch queries.

The Spark setup uses its InMemoryTableCatalog class. Make Sail's equivalent
supported catalog-provider fixture explicit. If setup is unsupported, record
that phase as the first failure and retain the unexecuted SQL/assertion cells.
Do not report a setup failure as a query result or replace the multi-catalog
fixture with one catalog. Use isolated owned namespaces and retain cleanup.

Record separately: catalog setup, each file/statement registration, preparation,
start, graph inputs/destinations where observable, all five queries, error
condition/state/parameters/message and ownership/cleanup. Stop invasive work at
an existing activation guard; a probe does not authorize weakening the current
incremental/sink rejection before its effect path is qualified.

## Design phase deliverables

Choose the adapter/harness path needed to exercise the actual original
assertions and expose the first missing product behavior. Keep public behavioral
ports, native internal-graph checks and original-suite execution distinct.
Then make the next source fix in a small commit with direct failing/passing
evidence for that original assertion. Preserve mixed-case streaming obligations
and every known scalar regression while prioritizing direct batch progress.
