# Evaluate streaming expressions only on data

A streaming projection or filter must evaluate actual records without interpreting
control markers as user data. A valid cast must not fail because a checkpoint
carries an empty-string placeholder, and a function must not run on that placeholder.
Add small flow-aware operators within Sail's existing planner and execution model.

This design isolates expression evaluation. It does not implement checkpoint
alignment, durable sinks, new event-time rules or general stateful streaming.

## Existing execution and the failure

Sail encodes a flow event as an Arrow record batch with two leading control
columns. A non-null marker value identifies a control row; otherwise the row is
data and its retraction flag says whether it cancels a previously emitted row.
Marker payload fields contain placeholders solely to satisfy the batch schema.

The streaming rewriter at the inspected baseline runs after logical optimization.
It retains an ordinary projection and prepends the two control columns. For filters, it builds
`user_predicate OR marker_present` inside `StreamFilterExec`. That physical node
calls DataFusion's batch filter on the whole encoded batch.

Neither baseline path isolates user expressions. A strict integer cast of a
nonnullable string sees the marker's empty string and fails. Checking the marker first in
one Boolean expression is insufficient: projections and arbitrary functions
remain exposed, and evaluation transformations must not become safety assumptions.

The inspected baseline is Sail
[`b52144955`](https://github.com/lakehq/sail/blob/b52144955b629314a000b1fe49eeea97fa3d0c5c/crates/sail-plan/src/streaming/rewriter.rs#L69),
with DataFusion 55.2.0. Earlier component probes reproduced strict-cast failures
on marker placeholders using the same expression/filter mechanism. They did not
execute this proposed operator or the complete optimizer and worker path.

## Decision: preserve events, reuse expression evaluators

Introduce a dedicated streaming projection node and correct the existing streaming
filter. Both consume contiguous data runs and individual markers in their original
order. A data run is a slice containing only rows whose marker column is null.
Never gather all data around a marker and move the marker afterward.

| Input | Projection | Filter |
| --- | --- | --- |
| Data run | Evaluate the selected expressions once and preserve each row's retraction flag | Evaluate the predicate once; apply its selection to data and retraction columns together |
| Marker | Forward its marker value under the projected output schema without evaluating user expressions | Forward unchanged without evaluating the predicate |
| Input or expression error | Propagate the error | Propagate the error |

Use DataFusion's public `Projector` for data projection and its batch-filter
kernel for filtering. These already handle scalar expansion, expression errors
and ordinary Arrow evaluation. The public projector preserves positive row counts
for an empty projection. Use the repaired event encoder to construct output
marker placeholders with the exact projected types and metadata.

Retain encoded column indexing for this small increment. Expressions remain bound
to the encoded input schema, as existing filter planning and worker decoding
expect. Only data runs reach those expressions. The physical projection preserves
the leading control columns positionally, followed by its user expressions.
This avoids a second expression-index convention and a changed filter wire contract.
Do not strip control columns and then run expressions compiled against their offsets.

Use one small shared traversal of encoded runs where it removes duplication.
It should retain at most the current input batch and output in progress, not
collect an interval. Arrow slices can share buffers; no full payload copy is
required merely to identify marker boundaries. Empty data output must not prevent
the following marker from progressing.

## Why not another representation or a dependency fork

Making placeholders nullable or wrapping each expression in a conditional spreads
control semantics through the expression tree. It changes schemas or relies on
evaluation behavior rather than preventing evaluation. A separate marker side
channel adds ordering and rejoining machinery that this unary transformation
does not need.

Taking ownership of the narrow DataFusion implementation is a reasonable alternative
if public APIs cannot preserve necessary behavior. It is unnecessary for synchronous
batch evaluation: `ProjectionExprs`, `Projector` and `batch_filter` are public.
Keep Sail's event scheduling in its own physical nodes and reuse those evaluators.
If a private planning helper must be copied, retain its pinned attribution and
comparison diff rather than copying the entire projection optimizer or vendoring
DataFusion.

## Planner, optimizer and worker integration

Replace rewritten logical projections with `StreamProjectionNode`, retaining their
expressions, output aliases and field/schema metadata. The existing extension
planner creates `StreamProjectionExec`. Remove the synthetic marker predicate
from streaming filters; marker retention becomes operator behavior.

Use the existing physical-expression planner and preserve qualified name resolution.
Preserve the current narrow filter policy that avoids optimizer-inserted repartitions.
Ordinary batch queries remain on their existing operators. Pure column renaming
around sources may remain ordinary projection only where it demonstrably preserves
both control columns and performs no user computation.

Do not copy ordinary projection properties indiscriminately. A computed data
column may be constant while its marker placeholder is different. Advertising
that constant for every encoded row could let a later optimizer erase markers.
Similarly, a data predicate is not true of marker payloads simply because the
filter forwards them. Publish only properties valid for the encoded stream.
Retain partition count and per-partition order; conservatively omit unproved
expression equivalences, value ordering and hash partition expressions.

Validate the physically optimized plan, not just the logical rewrite. Projection
fusion, filter pushdown, repartition insertion and source pushdown must not create
an ordinary user-expression operator over marker rows. Source filter pushdown
still operates under the source's own data-only contract. This increment does
not qualify exchanges for checkpoint alignment.

Add a physical-plan codec case carrying the streaming projection's child,
expressions, aliases and output metadata. Reconstruct the same node on workers.
Child replacement and expression traversal must preserve the node's event boundary
and expose expressions needed by existing planning machinery. A codec round-trip
that silently produces an ordinary projection is incorrect even if schemas match.

## Preserve asynchronous expression behavior

DataFusion's ordinary projection planner can extract asynchronous calls into
`AsyncFuncExec`. Replacing that planner branch with a synchronous projector alone
would lose this behavior or leave an unsafe ordinary evaluator below the boundary.
The relevant
[planner](https://github.com/apache/datafusion/blob/55.2.0/datafusion/core/src/physical_planner.rs#L2990)
and public `AsyncMapper` and `AsyncFuncExpr` APIs provide the reuse points.

For asynchronous expressions, prepare their expression mapping during planning,
then invoke them only on data runs before the final projection. Await each run's
result before forwarding a following marker. Preserve cancellation and errors;
never coalesce across a marker while waiting to fill an ideal function batch.
Serialize the required expressions and reconstruction information with the node.
This preserves marker ordering without introducing a new scheduling service.

The filter repair can land independently. Projection isolation is complete only
when synchronous and currently supported asynchronous paths are covered. Do not
silently fall back to marker-unsafe evaluation or remove working asynchronous
queries to make the synchronous tests pass. If the public APIs prove inadequate,
choose a narrowly attributed implementation with explicit behavior and cost.

Retractions require additional caution: deterministic row transformations can
transform a retracted row consistently, while volatile reevaluation may not cancel
the earlier output. This increment preserves flags and does not claim to solve
volatile retractable computation or replay determinism. Any restriction or stateful
solution for that behavior needs a separate contract.

## Tests that distinguish the repair

Construct mixed data and every marker kind directly, including marker-only batches,
adjacent markers, sliced batches and data before and after a marker. Use a strict
cast and a counting function that fails on marker placeholders. Markers must never
reach the function; real invalid data must still fail normally.

For filters, test true, false and null results, scalar predicates and mixed
retraction flags. Apply the same selection to the payload and flags without
evaluating a volatile predicate twice. A false predicate must remove every data
row while preserving all markers in order.

For projections, cover aliases, repeated and reordered columns, literals,
zero-column results, nested values and metadata. Check exact output schemas and
positive zero-column row counts. Assert that the two control fields survive even
when all user columns are removed. Test asynchronous completion, failure and
cancellation with a following marker and verify no placeholder invocation.

Exercise the actual streaming rewrite, physical optimizer, child replacement,
codec round-trip and reconstructed worker plan. Check optimizer-sensitive cases
such as a constant projection followed by a contradictory filter. Compare ordinary
batch results on data-only controls. Run focused regressions against unchanged
source, then public streaming projection/filter tests against the newly built binary.

Measure no-marker throughput and alternating data/marker overhead against the
same baseline. Conservative plan properties can affect optimization, so inspect
the resulting plans and measure affected cases rather than assuming neutrality.
These tests qualify expression isolation, not durable recovery or distributed barriers.

## Decision and remaining boundary

Proceed with dedicated flow-aware operators, existing batch evaluators and unchanged
encoded expression indexing. This restores the existing event contract without
choosing a new execution architecture. The implementation question to settle with
tests is whether the public asynchronous APIs preserve supported behavior without
copying a narrow helper. Reserved control-name collisions and broader retractable
semantics remain separate issues; this repair must not silently reinterpret either.

No deliberate Spark data-expression change is proposed. Spark 4.2.1's
[projection and filter operators](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/core/src/main/scala/org/apache/spark/sql/execution/basicPhysicalOperators.scala#L46)
evaluate data rows. Sail's own control representation must stay outside that
evaluation. That comparison is source inspection, not an executed parity result.

The local reference now implements filter and supported projection boundaries,
with immutable workspace and selected public checks recorded in the
[projection results](STREAMSOURCE-PROJECTION-RESULTS.md). Logical source erasure
before streaming detection remains outside these operators; preserving source
participation is required before a global isolation or recovery claim.
