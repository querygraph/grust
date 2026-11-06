# Streaming projection: Spark semantics and correctness review

## Review boundary

Read the saved request and applicable AGENTS, LAKESAIL, SHEHAB, CLARITY and
WRITING-RULES governance. The selected increment must preserve supported data
expression behavior while keeping Sail control rows outside user evaluation.
This report is independent source inspection before implementation; final cumulative
review and execution evidence remain pending. No source edit, build or test was run.

Source starting point: `06dd7e237eb5a343dcc6a6145e775f495e6c30de` in
`/Users/alexy/src/sail/tmp/streamsource-projection-20261105-06dd7e237`.
Upstream reference: `b52144955b629314a000b1fe49eeea97fa3d0c5c`.
The complete expression-isolation design was read, SHA-256
`f63fe0715985d9b063cd2ff3fad75052d552d992035dbbfba6c3edcbdcc77c8a` at inspection.

## Verified Spark source behavior

Inspected Spark 4.2.1 Git objects at
`617618396087429b5627a86ce933bb0f5d6645cb` in
`/Users/alexy/src/spark-sdp-4.2.1`, rather than relying on sparse filesystem files.

`basicPhysicalOperators.scala` defines ProjectExec output from its named expressions.
Its generated path binds those expressions to child output, optionally eliminates
common subexpressions, and requires evaluation of nondeterministic output attributes.
Its interpreted execution uses a partition evaluator over actual InternalRows.
`expressions/Projection.scala` similarly binds interpreted expressions, initializes
them per partition and evaluates each over an input row. Neither source models
Sail’s marker placeholders as user records. Marker isolation is therefore Sail’s
responsibility; preserving Spark expression semantics does not mean evaluating
functions on internal control rows.

`ScalaUDF.scala` explicitly combines declared function determinism with deterministic
children. Projection changes must not reclassify volatile functions or evaluate
them twice to preserve retraction columns. These inspections are not a Spark runtime
or optimizer parity verdict. The design proposes no new Spark parity feature.

## Existing Sail and DataFusion risks

The Sail logical rewriter prepends `_marker` and `_retracted` to ordinary projection
expressions. Input columns therefore retain encoded indexing. Removing those two
columns before using an already compiled expression would access the wrong values.
Keep the control columns positional and preserve output aliases, argument fields,
field metadata and schema metadata explicitly. Qualified column resolution and
derived-column names need planner coverage, not only direct operator tests.

DataFusion 55.2.0 physical planning derives a pure Column’s physical name from the
corresponding logical/physical field index. Other expressions use physical naming.
A custom extension planner must preserve that distinction where applicable.
The planner’s asynchronous extraction locates AsyncFuncExprs, appends their result
columns after the full input width and rewrites references. For encoded input that
width includes both controls. Generated async columns must not collide with user
columns or leak into output schema. Preserve the actual asynchronous interface;
do not replace its UDFs with synchronous invocation.

DataFusion AsyncFuncExec coalesces input batches to its configured batch size before
calling asynchronous expressions. An ordinary instance beneath an encoded-stream
boundary can therefore evaluate placeholders and move evaluation across markers.
Use the public async mapper/evaluator only inside a data run. Finish that run before
forwarding its following marker. A pending future must not let the next marker
escape early, and an error after an earlier marker must not erase that earlier
marker. Dropping a pending run should release its future/input; arbitrary external
side effects are not made cancellable by dropping a Rust future.

The public Projector uses precomputed fields and RecordBatchOptions to retain
positive row counts for zero projected columns. Reuse it for data; use exact output
schema placeholder construction for markers. Do not widen declared fields merely
to make placeholders easy to encode. Nested fields, decimal parameters and schema
metadata belong to the contract. Marker-only input must invoke no user expression,
including literal or zero-argument volatile functions.

Preserve each data row’s retraction flag without reevaluating its expression.
Deterministic row transforms can reproduce matching retractable output; volatile
reevaluation need not cancel an earlier value. This increment preserves flags
but cannot promise general volatile retractable semantics or replay determinism.
The design accurately leaves that contract separate.

Ordinary projection equivalences and constant properties need conservative treatment.
A data value may always be one while its marker placeholder is zero; advertising
constant one for all encoded rows permits unsound simplification. Preserve partition
count and order without asserting unproved hash, sort or value properties. Test a
constant projection followed by a contradictory filter on the optimized physical
plan and after worker reconstruction. Codec round trips must preserve the streaming
operator, not merely return the same schema through an ordinary ProjectionExec.

## Pre-existing logical-optimization boundary

`resolve_and_execute_plan` optimizes the ordinary logical plan before calling
`is_streaming_plan` on that optimized tree. A constant-false or contradictory
filter may remove the source before streaming detection. A physical projection
repair cannot preserve a source’s markers after that source has already disappeared.
This is a source-backed risk, not a reproduced runtime result in this review.
Distinguish it from the physical property issue above. Retain a counterexample if
reproduced and avoid claiming complete logical-optimizer marker preservation from
only direct-node tests. The integration owner was informed before implementation.

## Discriminating checks for final review

Mixed schedules need all marker kinds, adjacent and marker-only batches, slices,
real bad data before/after markers, strict casts, scalar expansion and zero payload
columns. Check output bytes/schema and retractions. Counting or deliberately failing
functions should prove zero marker invocations and one evaluation per admitted data
run. Asynchronous checks need a held future, error, cancellation and a following
marker with deterministic synchronization. Constants and nulls must retain ordinary
data behavior without exposing placeholders. Whole optimizer and codec tests must
verify physical node placement and field identities. Ordinary batch plans should
continue using their ordinary operators. These checks qualify expression isolation,
not distributed checkpoint alignment or durable source/sink recovery.


## Pre-freeze implementation review and public order contract

Reviewed the current projection operator, logical node, physical planner and codec,
plus direct/async/session/public tests. This is a WIP inspection before the final
source snapshot, not a verdict on an immutable final cumulative tree. Selected
source hashes at this pass:

- `crates/sail-physical-plan/src/streaming/projection.rs` SHA-256 `cbab2dbd17beb5a52437c07a60c4d288bd4a3be15b470824bc143f972085f9f2`.
- `crates/sail-logical-plan/src/streaming/projection.rs` SHA-256 `f43576eb9124d213790ab099803eedc38f0a662da9381f821e53299b3aeec9db`.
- `crates/sail-session/src/streaming_projection_tests.rs` SHA-256 `f7da7f6f34581d53b910251db84696c0c9340b5dfca97ef987db3ebf4fdf529f`.
- `python/pysail/tests/_dev/spark/streaming/test_projection.py` SHA-256 `057433ca67a54f3c45d8c5a3ca17e18914088a560e838440ebdeced1584d76db`.

No new source-correctness blocker was found. DataProjector maps asynchronous
references against the full encoded input width, preserves actual projected fields
and only invokes asynchronous functions on a data run. Its final projection uses
the appended fields without leaking them. The execution stream retains a pending
input slice, awaits the current data run, then emits following markers. Marker
runs directly preserve both controls and construct payload placeholders under the
output schema. Ordinary data batches avoid a boundary scan. The conservative
partition/equivalence properties avoid asserting computed constants for marker
payloads, while explicit control-column validation protects their positional role.

The extension planner preserves the ordinary logical/physical column-name mapping
and encoded expression indices. Codec decoding reconstructs StreamProjectionExec
and its projected schema rather than an ordinary projection. The new logical node
keeps its schema across child/expression replacement. The session tests exercise
actual planning and optimized execution, including metadata, no-payload row counts
and the contradictory computed-constant filter case after streaming rewrite.
The pre-existing logical optimization/source-detection boundary remains explicitly
separate.

The two added asynchronous session regressions are appropriate discriminators:
independent calls need distinct result columns, and a nested call must retain its
existing named refusal instead of falling back to synchronous evaluation. This
pass inspected those tests but did not execute them; compilation was pending.
Data-only empty batches and pure marker batches remain different paths. Retractions
stay under operator control. No volatile retraction or durable replay guarantee
is inferred from preserving their flags.

The public data-only projection assertion currently assumes collection order for
a query with LIMIT followed by arithmetic projection and no ORDER BY. Spark 4.2.1’s
`docs/sql-ref-syntax-qry-select-limit.md`, read directly from the pinned Git object,
states that LIMIT is normally paired with ORDER BY for deterministic results.
Its physical limit implementations constrain rows; they do not introduce a sort.
The retained baseline v2 run returned exactly the expected tuples in the sequence
2,1,3; baseline v3 returned 1,2,3. Values, duplicate columns and labels were equal.
The result-order assertion therefore exceeds this public query’s stated contract.

Compare the exact sorted list or exact multiset for that public check, preserving
every expected tuple and its multiplicity. That corrects the fixture’s ordering
assumption rather than weakening data correctness. Keep strict order assertions
in direct operator tests that establish per-partition marker/data sequencing.
The empty-tuple row-count check remains exact and unaffected.

DataFusion ProjectionExec reports a benefit from partitioning when an expression
has KeepInPlace placement; the new streaming node deliberately returns false.
This supplies a plausible mechanism for baseline global row reordering. It is not
an observed cause in these public logs: EXPLAIN’s physical planning failed with
“stream source should be rewritten during logical planning,” so those logs contain
no actual RoundRobin or coalescing node. Do not label the mechanism proven without
capturing a successfully planned execution tree. The unstable order and the query
contract are sufficient to correct this public assertion independently.

No new runtime, build, source edit or test was performed in this review. Root owns
assertion changes and execution evidence. Final source freeze and cumulative
qualification remain pending; saved request/governance compliance is confirmed.


## Final frozen cumulative assessment

Verified the final snapshot in the implementation worktree against all fifty-four
recorded file hashes and twenty-six increment paths. The index tree is
`b67d1a9416d22241ab0359e2ef96dcdf3c678757`, based on
`06dd7e237eb5a343dcc6a6145e775f495e6c30de`. The exact increment hashes to
`0a556ee174bbd47da7148e8ae8f999707482b8078b6fcabed553882fa015bea3`;
the cumulative source diff against `b52144955b629314a000b1fe49eeea97fa3d0c5c`
hashes to `c34dcc56ba6d8f7260e7d6eb0997a7dd016fd07de6e79d5a2424da574d6cf1bf`.
This supersedes earlier WIP hashes as the reviewed source pin.

No new correctness blocker was found. The added logical projection preserves
qualified fields and metadata through the streaming rewrite. Bounded-source
adaptation now retains input qualifiers and schema metadata instead of flattening
them. This is necessary for qualified expression binding across a bounded branch
inside a streaming plan. It does not add a different Spark name-resolution policy.
The physical planner, encoded field indexing and codec preserve the same streaming
projection boundary. Existing foundation and scalar-adapter files in the cumulative
snapshot retain their previously reviewed content except for the declared increment.

The fallible null constructor retains the supplied Arrow DataType, including nested
field definitions, decimal parameters and schema-facing representation. The pinned
Arrow constructor layout is carried with attribution; checked capacity arithmetic
and run-end conversion replace panicking paths. Empty children and compressed run
values remain structural rather than expanded per logical row. Recursive calls use
the repaired constructor, so direct and nested run-end forms do not silently fall
back to the original panicking helper. The constructor does not restrict every
marker payload to nonnullable values or widen fields merely to satisfy placeholders.

For projection, marker payloads remain internal values, not evaluated scalar
results. The exact projected schema must survive even when placeholders carry
logical nulls in an encoding whose parent physical validity has no bitmap. The
scalar adapter’s stronger nonnullable user-result contract is therefore not a
reason to impose that contract on private marker placeholders. Allocation exhaustion
still depends on the caller’s resource envelope; the fallible capacity checks are
not a complete memory budget or arbitrary foreign-data validator.

The four public tests now use table/select/limit APIs and compare exact sorted
values where the query gives no global ordering contract. Duplicate tuple
multiplicity remains checked. Internal direct/operator/session/codec tests retain
strict marker/data sequence assertions, so the public fixture correction does not
weaken event-order coverage. Real invalid data still raises, and bounded end-marker
placeholders remain a separate counterexample. Multiple independent asynchronous
calls and the existing named nested-call refusal have explicit session regressions.

The retained production source-erasure probe confirms the previously identified
boundary: optimization transforms a streaming-source query with a false condition
into EmptyRelation, followed by ordinary EmptyExec. That is observed production
planner behavior, not merely a direct-node model. The current projection change
cannot restore markers from a source erased before streaming detection. Keep this
as an open whole-pipeline correctness limitation; do not count the projection’s
component and public checks as recovery or global marker-preservation readiness.

The integration owner reports 334 affected tests passed with production optimizer
lists and typed marker cases. The four public tests passed on the preceding
candidate; the latest nullable-helper public rerun and full final gate remain
pending at this review. Those earlier results do not qualify an unchecked later
revision. This reviewer performed no build, test, cleanup or source edit. The
actual new source and tests were inspected. Saved request and governance compliance
remain confirmed; no Spark-engine differential execution was performed. Full goal
completion, distributed checkpoint alignment, volatile retractable semantics,
package/worker integration and durable CDC remain outside this verdict.


## Final observability repair confirmation

Independently verified the revised final index tree
`5a8f4f67535644e0cb8e4eb52389cfb4395bc3d9`, all fifty-eight recorded cumulative
file hashes and thirty-one increment paths. Its increment against parent
`06dd7e237eb5a343dcc6a6145e775f495e6c30de` hashes to
`e0ed57aa267daafbc6c4517a2712c4b1e9cbc050bf544bc62e4f7a1e9e4200f5`;
its cumulative diff against upstream `b52144955b629314a000b1fe49eeea97fa3d0c5c`
hashes to `450642c939973266f80b2e7bcb52fe60dad7bc0f69fac5d733b9e18f34c77023`.
These pins supersede the preceding frozen-tree pins. No new correctness blocker
was found in the cumulative source or observability repair.

The projection now owns BaselineMetrics once in its stream state. It does not
create and drop a baseline owner per output run. Successful data and marker outputs
call RecordOutput once; an input or expression error does not increment successful
output counts. The counters describe encoded rows, batches and bytes, including
markers and retractions, rather than pretending to count only visible user rows.
The row/byte test independently derives emitted batch sizes and counts.

Compute timers cover boundary scanning, placeholder construction and active data
projection work. The async wrapper times individual future polls, dropping the
scope guard before a Pending suspension. Input polling precedes the boundary timer.
Thus input waiting and asynchronous suspension do not become this operator’s compute
time. This is a source-level accounting conclusion, not a timing benchmark.

The lifecycle test holds the returned stream between polls and checks that its
single end timestamp remains unset after a nonterminal output. EOF, expression
error and explicit drop then set it. These deterministic state checks avoid an
unstated elapsed-time tolerance. Existing BaselineMetrics drop semantics, rather
than a second terminal-state subsystem, handle cleanup.

The telemetry dispatcher explicitly recognizes StreamProjectionExec and applies
the established projection expression emitter. Its positive test executes actual
nonempty data and a checkpoint marker; it is stronger than checking metric names
on an unused empty operator. The isolated dispatcher and baseline controls are
retained separately. Their results are inspected lead execution evidence, not
runs performed by this reviewer.

The current empty-data branch constructs a schema-correct empty result without
calling user expressions. This represents no user rows and invokes no function
on synthetic placeholders. The ordinary batch operator is unchanged. Marker/data
ordering, argument fields, retractions and asynchronous mapping remain as reviewed
above; instrumentation adds no marker reordering or function reevaluation.

Public query APIs and exact value/multiset assertions are unchanged from the
previous reviewed snapshot. Partition-local tests retain strict event order.
The production source-erasure defect remains open and is not covered by this
projection verdict. The scalar producer’s unsafe obligations, cancellation of
external side effects, volatile retraction semantics, package integration and
durable recovery remain separate contracts.

The integration owner reports 347 affected tests passed. The instrumentation
change requires the benchmark rerun and final cumulative gate now pending; the
preceding timing run alone does not qualify this revised tree. Rustdoc link fixes
are non-runtime changes. No source edit, build, test or timing run was performed
for this review. Saved request and governance compliance remain confirmed.


## Final v7 synchronous-polling confirmation

Verified the final v7 index tree
`bb8699fdfbc4ca88fa6c0e816e189af80e560efd`, all fifty-eight recorded cumulative
file hashes and thirty-one increment paths. Against parent
`06dd7e237eb5a343dcc6a6145e775f495e6c30de`, the increment SHA-256 is
`9414d2b00491eedfd76e52e212459f92735963e46a6eb0d3c9f79b444e4693a2`;
against upstream `b52144955b629314a000b1fe49eeea97fa3d0c5c`, the cumulative
SHA-256 is `7f2cf1d64419f8968e311f04b4b132bed8ee05e5e94be995dcf083b10dd9f8aa`.
This pin supersedes earlier reviewed frozen trees. No new correctness blocker was
found in the complete cumulative source and direct synchronous polling change.

The synchronous path now polls input directly rather than wrapping each run in
an async state machine. It shares input polling, marker-run extraction, projector
and placeholder evaluation with the asynchronous path. Both retain encoded field
positions, schema metadata and the exact per-partition marker/data sequence. Each
successful synchronous poll emits one run; no unbounded ready-input draining loop
was added. Input Pending passes the caller’s task context to the upstream stream,
so notification remains connected to the waiting consumer.

Input errors, expression errors and EOF remove the stream state. A subsequent
poll returns None rather than reading more input after a terminal failure. This
also releases unread upstream payload and pending encoded input while preserving
the one-owner baseline metric lifecycle. Successful output is counted once. The
sync timing scope covers extraction and evaluation after input polling; async
future polling retains its active-poll timers without including suspension.

The new channel-backed regression is independent of the operator’s extraction
code: it polls Pending, sends input, observes a waker notification, verifies the
first projected data, injects an upstream failure and buffers unread data behind
it. It then checks the original error, closed producer channel, released weak
payload reference, terminal timestamp, output count and repeated None polls. This
protects wakeup, fused termination and retention semantics beyond the ordinary
memory-source fixtures. Existing direct and async error/marker tests remain intact.

The integration owner reports fifty-three affected physical-plan and telemetry tests and the exact
three-way/eight-cell comparison passed on v7. The reported no-marker medians are
1.0303 and 0.9580; these are component ratios under disclosed host/profile conditions,
not a production throughput claim. Mixed marker fragmentation remains unresolved.
No source change or test execution was performed by this reviewer.

The full gate is still pending. The production logical source-erasure defect remains
an open pipeline correctness limitation, and this operator verdict does not qualify
volatile retractable transformations, async external-effect cancellation, distributed
checkpoint alignment or durable recovery. Existing extension package and worker
integration remain separate work. REQUEST and governance compliance remain confirmed;
no context compaction occurred during this pass.
