# Project streaming data without evaluating markers

Streaming queries need casts, calculated columns and native functions to see only
actual records. Sail also carries ordered control markers through the same Arrow
batches. Add a flow-aware projection within Sail's existing planner and worker
codec, preserving supported synchronous and asynchronous expressions.

This increment does not provide checkpoint alignment, durable recovery, volatile
retraction semantics or a native package loader.

## Why projection needs an event boundary

A flow-event batch starts with a binary marker column and a Boolean retraction
column. A non-null marker denotes a control row; its remaining values are schema
placeholders. Retraction flags on data rows cancel earlier records. Sail's upstream streaming
rewriter prepends these control columns to an ordinary projection.

For example, a string column can contain valid integers while a checkpoint carries
an empty-string placeholder. An ordinary strict cast fails on that checkpoint.
Native and asynchronous functions can also perform work on it. Changing placeholder
values cannot make arbitrary user expressions safe.

The reference foundation's `StreamFilterExec` already isolates contiguous data runs. Use the same
ordering contract for projection: finish a data run, forward its following marker,
then evaluate later data. A later error must not hide an earlier marker. Adjacent
markers may share an output batch because their relative order remains unchanged.

## Fit to Sail and DataFusion

Replace rewritten projections with `StreamProjectionNode` and plan them through
Sail's existing extension planner as `StreamProjectionExec`. Keep encoded expression
indices, including the two leading control columns. Preserve qualified logical
names, physical column aliases, projected field metadata and schema metadata.
Ordinary batch projections keep their existing planning path.
The bounded-source adapter currently rebuilds a logical schema from Arrow and
drops table qualifiers. For example, a local string relation still has expressions
bound to its qualified column, which can no longer resolve after wrapping. Preserve
the original qualified fields and metadata when prepending control fields. Changing
user expressions to unqualified names would make scoped resolution ambiguous.

Use DataFusion 55.2's public `ProjectionExprs` and `Projector` for data evaluation.
Its public `AsyncMapper` extracts supported asynchronous calls. Invoke those calls
on each data run using `AsyncFuncExpr`, append their results for the final projector,
and await completion before a following marker. Keep the original expressions on
the node; worker decoding reconstructs the same mapping from those expressions.
The codec carries the child, expressions, aliases and metadata schema.
Expose existing streaming detection and rewrite functions from the plan crate for
programmatic planning, sharing the implementation used by the request resolver.

The first two projection expressions must preserve the control columns positionally.
For marker runs, copy those columns and construct payload placeholders under the
projected schema without invoking any expression. Use Sail's existing Arrow
non-null placeholder implementation and a narrowly owned fallible Arrow null
constructor. Preserve nullable encodings such as dictionaries with no values; replacing
them with non-null values can refuse valid schemas. Check each buffer and child
capacity during recursive construction, before its allocation. Data-only batches
retain one projection call, with no row-by-row boundary scan. Keep at most the current input batch and pending output.
Release exhausted input before returning output, while acknowledging that slices
can retain shared Arrow buffers.

Do not advertise computed constants or hash expressions as properties of the whole
encoded stream: marker placeholders can differ. Preserve partition count, boundedness
and partition-local sequence, with conservative equivalences and partitioning.
Expose original expressions to existing traversal and rebuild safely on child replacement.
Preserve baseline output statistics and expression telemetry through existing Sail
exporters. Count encoded output, including markers, and time active computation
without including asynchronous suspension. Keep one metrics owner until completion.

## Asynchronous evaluation has a bounded scope

Ordinary `AsyncFuncExec` coalesces input before invocation, which can cross marker
boundaries. Reusing that whole operator would break event ordering. Its public
per-batch evaluator avoids copying the planner or creating another scheduling service.
The cost is smaller function batches near markers; measure it rather than filling
a batch across a checkpoint.

Sail already rejects nested asynchronous calls during expression preparation. Keep
that refusal. The built-in asynchronous function inspected uses array results and
no requested ideal batch size. The pinned helper has limitations for scalar results
and empty ideal-sized batches; this increment must not claim broader async coverage.
For an empty data batch, produce empty output arrays under the planned schema
without invocation. Refuse a zero requested ideal size before execution because
the helper would otherwise loop without progress. Positive ideal sizes remain
handled by the existing helper. Any further helper correction requires a separate
counterexample and dependency-ownership decision.

Dropping the stream must drop a pending asynchronous future. This is local task
cancellation, not proof that an external service cancelled its side effects.
Retain the mapper's existing call-site behavior; this is not a new deduplication
policy. One pending run limits scheduling, not retained bytes: the evaluator can
collect chunk results and concatenate them. Resource admission still needs a budget.
Retraction flags remain attached to their rows. Re-evaluating volatile functions on
retractions or replay is a separate semantic problem, unchanged by isolation.

## Alternatives and decision

Conditional expressions spread event semantics into every expression and depend on
evaluation transformations. Widening user fields to permit all-null placeholders
changes schemas without preventing invocation. A separate marker channel requires ordering and rejoining machinery.
Copying DataFusion's whole projection operator would also copy properties that are
not valid for encoded markers. Its public evaluators already supply the required
batch operations, so keep event scheduling in a small Sail-owned node.

Proceed with this node and existing evaluators. Verify the real rewrite, physical
optimizer and worker reconstruction before claiming integrated expression isolation.
A separate existing issue is that logical optimization may remove a streaming source
before Sail detects streaming; this projection node cannot repair a source it never
receives. Record that boundary explicitly and reproduce it before choosing its fix.

## Evidence required before qualification

Use a strict cast and a counting expression that fail on marker placeholders.
Exercise every marker kind, adjacent markers, sliced and marker-only batches,
retractions, real data errors and markers preceding errors. Cover reordered and
repeated columns, aliases, literals, empty payload projections, nested Arrow values
and metadata. Positive row counts must survive when no payload columns remain.

Use controlled futures to test asynchronous pending, completion, error and drop
without clock races. Test supported positive ideal sizes and empty inputs. Verify
that optimizer-inserted ordinary evaluators cannot reach markers, including a
computed constant followed by a contradictory physical predicate. Round-trip the
worker codec and execute the reconstructed plan. Test child replacement and
expression traversal. Preserve unchanged-source negative controls.

Run public streaming queries against the newly built server and ordinary batch
controls. Compare equivalent no-marker and mixed-marker workloads with exact ordered
outputs before measuring; retain every cell and shared-host limitations. Component
tests and codec checks do not establish distributed barrier alignment or recovery.

Spark 4.2.1's projection evaluates data rows. This plan preserves that data behavior
while isolating Sail's own control representation. Spark and DataFusion source
inspection supports the integration choices; executed parity remains a separate claim.
