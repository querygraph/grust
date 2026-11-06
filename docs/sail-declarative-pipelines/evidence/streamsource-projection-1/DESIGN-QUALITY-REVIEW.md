# Streaming projection design quality review

Reviewed 2026-11-06T02:05:48.930338+00:00.
Source starting HEAD `06dd7e237eb5a343dcc6a6145e775f495e6c30de`; upstream base
`b52144955b629314a000b1fe49eeea97fa3d0c5c`.
Plan SHA-256 `c9dc845b856d2a6587ff089975f95ea1903c14a73118010ae2f466b2ea4ec2a4`.

## Verdict and architectural fit

Proceed with the dedicated logical/physical projection boundary described in
STREAMSOURCE-PROJECTION.md. The design solves a real representation mismatch:
encoded markers carry placeholders, while ordinary user expressions assume actual
records. Adjusting placeholders or adding conditional terms to arbitrary expressions
cannot supply a general isolation contract. A separate marker channel would add
ordering and rejoining machinery. A small Sail-owned event scheduler with existing
public batch evaluators is the simpler design.

The complete plan stands alone. It explains the failure, existing Sail components,
reasonable alternatives, recommendation, asynchronous limits and discriminating
verification. Codec, optimizer properties and qualified field naming are part of
the design rather than left as implementation details. The plan precedes code;
this report is not a verdict on an implemented cumulative candidate.

## Verified dependency reuse

Inspected resolved DataFusion 55.2.0 source rather than assuming that public helper
names establish their behavior:

- ProjectionExprs and Projector supply field-aware expression evaluation and explicit
  row-count construction for a zero-column output. Their metadata-aware constructor
  copies supplied field metadata by position and schema metadata, but derives names,
  types and nullability from physical expressions. The supplied schema is not an
  arbitrary override of those properties. Qualified logical column indices must
  still choose the corresponding physical name, as the ordinary planner does.
- AsyncMapper is a public extraction/remapping surface. It indexes appended results
  after the complete input width, including control columns. Final expressions must
  evaluate against that extended schema. Original expressions should be retained for
  traversal, child replacement and worker reconstruction.
- AsyncFuncExpr supplies per-batch invocation. Whole AsyncFuncExec adds coalescing,
  which cannot cross a marker boundary without moving evaluation. Using the helper
  only within the current data run preserves the intended boundary without copying
  the whole operator or adding another scheduling service.

The source inspection supports reuse with explicit limits. A zero ideal size makes
helper chunking nonprogressing; an ideal size on empty input collects no arrays for
concat. The plan's zero-size refusal and empty-output construction avoid those cases
without silently changing the dependency. Scalar helper results are expanded to one
row per chunk, so broader scalar-return support must not be inferred. Existing nested
async refusal remains necessary. A later helper correction needs its own failing
control and dependency-ownership assessment.

## Additional precision findings sent to the lead

AsyncMapper.find_references appends every encountered asynchronous expression;
map_expr then selects the first structurally equal expression. Repeated equal calls
can therefore cause duplicate invocations and unused appended results. Do not claim
helper deduplication or exactly one call per distinct expression. Counting controls
should expose the actual retained behavior. Introducing a new deduplication policy,
especially for volatile calls, would be another semantic change.

Keeping one current input run and one future is a scheduling bound, not a byte bound.
AsyncFuncExpr collects per-chunk results and concatenates them. Retained bytes depend
on input/output widths, expression count and chunking. The narrow scheduling design
is appropriate, but production resource qualification must account for those arrays.
The public Projector reuse itself does not introduce a new queue or state store.

These are implementation/evidence precision requirements, not reasons to copy the
full DataFusion operators or broaden this increment into general async repair.

## Final source review requirements

Forward marker runs without invoking synchronous or async user code. Evaluate each
data run before its following marker, and yield a preceding marker before starting
later data that may fail. A pending invocation must retain the current run only and
be dropped with the stream; external effects remain outside this cancellation proof.
Control columns must remain positional and flags aligned with transformed rows.

Do not advertise ordinary computed constants, hash partitioning or equivalences for
marker placeholders. Check the actual physical optimizer and codec rather than only
the direct operator. Child replacement and expression traversal must rebuild mapping
from original expressions consistently. Keep ordinary batch projections unchanged.
The separate pre-rewrite logical optimization/source-erasure issue requires its own
counterexample and must remain outside an integrated isolation claim until repaired.

Final cumulative review should inspect exact schema metadata, aliases, nested fields,
zero user columns, no-marker fast path, input lifetime, async error/pending/drop,
worker reconstruction and measured fragmentation. Component success will not prove
checkpoint alignment, volatile retraction semantics, distributed recovery or native
package integration.

## Compliance and limits

Read the saved full request and applicable AGENTS, LAKESAIL, SHEHAB, CLARITY and
WRITING-RULES instructions. Read source development/review instructions, the complete
projection plan and the independent Regression and Spark semantics reports. Existing
source and resolved dependency APIs were inspected. No builds, tests, source changes,
cleanup or remote actions were performed. Only this assigned evidence report was
written. Final implementation and immutable gate remain pending.

## Implemented projection review before the final freeze

Reviewed 2026-11-06T02:34:18.391547+00:00. This is the
in-progress implementation, not a final immutable-tree verdict. Reviewed source
identifiers at this pass:

- `crates/sail-physical-plan/src/streaming/projection.rs`: `cbab2dbd17beb5a52437c07a60c4d288bd4a3be15b470824bc143f972085f9f2`
- `crates/sail-logical-plan/src/streaming/projection.rs`: `f43576eb9124d213790ab099803eedc38f0a662da9381f821e53299b3aeec9db`
- `crates/sail-logical-plan/src/streaming/source_adapter.rs`: `0bc3c2a0db692159eb1530576154e2142cf442b04d3d48b38baabfc381ffbbc6`
- `crates/sail-session/src/planner.rs`: `2fc2747015fabb5b733e7ef80771ee3c0949be5a85ddafba91cf8e22a5b54bad`
- `crates/sail-execution/src/proto/codec.rs`: `40c10d9a3f5b42168c999e7b588edeeec90415913886e8944e80df69a8960cda`

The implementation follows the planned boundary without unnecessary scheduling
frameworks or a copied DataFusion operator. ProjectionStream keeps the current
encoded batch and offset, lazily selects contiguous marker/data runs, and owns
the pending asynchronous computation through try_unfold. It yields each completed
run before requesting the next. Marker reconstruction copies only controls and
uses the planned output schema for placeholders, with no user invocation.

DataProjector retains original ProjectionExprs on the plan and separately derives
the public mapper/projector evaluation state. Worker decoding reconstructs that
state from original expressions, aliases and metadata, avoiding serialization of
one task's pending run. First control expressions are checked positionally.
Conservative equivalences and UnknownPartitioning preserve partition count without
claiming computed values or hash expressions hold on marker placeholders. Child
replacement rebuilds the evaluator and expression traversal visits the originals.

The bounded-source qualifier repair is appropriately narrow: retain original
qualified Fields and schema metadata while prepending controls. A previous
conversion through Arrow erased logical qualifiers, while user expressions still
referred to them. Removing qualifiers from expressions would weaken scope/name
resolution. The revised plan explains this constraint, and a direct test protects
qualified fields, metadata and reconstruction. This addresses the demonstrated
binding defect without a general unqualifying rewrite.

One concrete plan/source mismatch was reported to the lead: project_data's
synchronous branch preceded its zero-row guard. Empty synchronous input could
therefore still invoke user expressions, despite the plan's empty-no-invocation
contract. Move the empty guard before both synchronous and async paths and retain
a counting/failing synchronous empty-input control. This is a small consistency
repair, not a reason to broaden the evaluator design.

The asynchronous path invokes supported helpers only on the current data run and
appends all results under the derived schema before final projection. The original
mapper's call-site behavior and helper limitations remain explicit. Sequential
helper calls introduce no detached tasks; dropping the stream drops its future.
This proves no cancellation of external side effects and no byte budget from
batch count alone.

The review found no other structural design blocker. Source hooks preserve the
ordinary batch route, the new protobuf case protects the custom execution boundary,
and zero user columns remain represented by the required two controls. Public
streaming tests exercise strict casts, metadata/aliases, empty payload and real
data errors; ordinary batch output remains a separate control. New async planner
checks exercise independent results and named nested-call refusal. Execution of
the latest tests and final source pin remain pending in this review.

No builds, tests, source edits, cleanup or remote actions were performed. Only
this report was appended. Saved request and governing instruction compliance
remains confirmed.

## Final frozen cumulative source review

Reviewed 2026-11-06T02:38:11.517211+00:00. Independently
verified starting parent `06dd7e237eb5a343dcc6a6145e775f495e6c30de`, staged tree
`52cbe5f4281bf74b9d54615504ce7eb9e062f80d`, every cumulative file hash, the exact nineteen
increment paths and the complete cumulative changed-path list. No unstaged tracked
source changes were present. The incremental binary diff has SHA-256
`5fa79cdd5f911e5449ffb64b0991ef7a21d3d3101e2311576cddb0f143022ecc`; the complete binary diff against upstream
`b52144955b629314a000b1fe49eeea97fa3d0c5c` has SHA-256
`70390f447d0b7425a49cc8cbec2649ec1a3a11a5f2cb5d5ea7a372c11dfc6b20`.

Reviewed the final projection/operator/planner/codec source and tests, the updated
source-adapter qualifier repair and plan, and their cumulative architectural fit
with the retained filter, event-fidelity, terminal-failure and native-scalar
increments. The previously reviewed scalar code and foundation remain unchanged
by this increment except the shared lockfile's added dev-dependency entry. The
complete cumulative source identity was checked rather than inferring it from
an increment-only patch. This is source inspection, not a cumulative runtime gate.

The empty synchronous-input finding is closed in source: project_data now builds
the planned empty RecordBatch before considering either synchronous or asynchronous
evaluation. The new counting test asserts zero calls and the exact planned empty
shape. Its retained negative control failed with one call versus zero on the
preceding candidate, directly demonstrating the failure that motivated the edit.
The latest complete qualification is still running, so this review does not claim
that its final execution has passed.

Other design requirements are preserved in the frozen source:

- Both logical and physical custom nodes protect the event boundary. The physical
  node retains original expressions for visitors/reconstruction and separately
  derives mapper/projector evaluation state. Marker-only runs invoke neither
  synchronous nor asynchronous user expressions.
- The run iterator advances lazily and yields each run before starting the next.
  A pending data future therefore cannot be overtaken by its following marker,
  while an earlier marker is observable before later data failure. It introduces
  no detached scheduling task. Exhausted input ownership is released before yield;
  output slices can still retain shared Arrow buffers.
- Conservative physical properties avoid asserting computed constants or input
  hash expressions over marker placeholders. Partition count, pipeline behavior,
  boundedness and partition-local order remain explicit. The node does not promise
  a graph-wide barrier protocol or volatile-retraction correctness.
- Source-adapter reconstruction preserves qualified user Fields and schema metadata
  while prepending controls. The projection planner follows ordinary qualified-index
  versus physical-name handling. The fix preserves scoped identity rather than
  making expressions unqualified as a workaround.
- The codec retains original projection expressions, aliases, child and output
  metadata; worker decoding recreates the protected node and mapper. Two required
  controls distinguish zero user columns from an absent projection.
- Session fixtures now install the production analyzer, logical optimizer and
  physical optimizer lists, plus the existing extension planner. Independent async
  calls, nested-call refusal and physical constant reasoning are tested through
  that actual path rather than a reduced default-optimizer configuration.

No new must-fix structural design issue was found in this frozen candidate. The
small event scheduler with public DataFusion evaluators remains simpler than
copying whole operators or introducing marker rejoining machinery. The plan now
explicitly states mapper call-site behavior, helper limitations, bounded scheduling
versus retained-byte accounting and the separate logical source-erasure boundary.
Those earlier precision findings are therefore resolved as design/evidence limits.

Performance qualification remains material. Mixed-marker fragmentation and helper
chunk/result retention do not disappear because the operator passes functional
checks. The initial shared-host mixed-marker gaps remain known limitations; the
final performance repeat after the empty guard is pending. No general performance,
resource-envelope, production-readiness, package-integration or distributed-recovery
claim follows from this source verdict. The full SDP/Extensions objective remains
incomplete.

The saved request, updated projection plan and applicable governance were read.
This pass ran only read/hash/Git verification and appended this assigned report.
No build, test, benchmark, source edit, cleanup or remote action was performed.
The integration owner's pending qualification must supply its own completed
immutable verdict before the candidate is represented as gated.

## Nullable marker payload construction decision

Reviewed 2026-11-06T02:46:38.453188+00:00 before the
proposed marker-construction repair. The Test Case role reported an Arrow 59.2
new_null_array panic for a nullable RunEndEncoded Int16 output with 32,768 adjacent
markers, even when the original input type is ordinary Utf8. This pass inspected
the dependency's run-end constructor and Sail's complete existing placeholder
traversal; it did not execute the counterexample.

Using Sail's existing fallible placeholder_array for all marker payload fields is
semantically sound. A nullable field admits non-null values, and flow-event marker
payload values are unspecified and must never reach user expressions. The output
field type, nullability, nested metadata, marker bytes and retraction column remain
the actual contract. This avoids a second top-level policy selected only by
nullability and reuses the checked run-end capacity handling already present in
Sail. Returning a named capacity error is preferable to panicking; it must remain
a disclosed marker-batch capacity boundary rather than a claim of unlimited runs.

A top-level substitution alone does not eliminate the demonstrated failure family.
The existing placeholder traversal still invokes Arrow new_null_array for nullable
Struct children, FixedSizeList children and Union children. Their child lengths
can reach the same unrepresentable Int16 run-end boundary. Prefer recursively using
the same fallible placeholder traversal for those children too, preserving the
one-traversal design. Add nested Struct/FixedSizeList/Union boundary controls as
well as the direct case. Lists and maps also have nullable-child forks, though
their ordinary empty placeholder children have zero length.

The cost is schema-dependent. Primitive placeholders generally avoid a validity
bitmap; empty variable lists/maps retain empty children. Nullable dictionaries
previously allow null keys and zero values, while a non-null placeholder dictionary
creates one representative value. A wide FixedSizeList or nested value can therefore
allocate more. Removing nullable-child branches simplifies ownership and type
construction but does not establish allocation neutrality across Arrow types.
Retain that limitation and measure actual applicable marker/schema cells.

An owned fallible nullable constructor could preserve the previous null encodings,
but adds another recursive construction mechanism. Splitting markers by output
capacity would preserve more batch schedules, but needs a type-aware split policy
and explicit ordering/resource tests. Neither is justified solely to repair this
constructor panic before the simpler existing traversal is evaluated. A narrow
Int16 check around Arrow would miss nested representations and duplicate dependency
limitations as special cases.

Recommendation: reuse the existing fallible placeholder traversal consistently,
repair its nullable-child escapes and qualify direct/nested capacity boundaries.
Do not describe it as a general memory/overflow proof for arbitrary schemas and
lengths: caller resource admission remains required. This is a pre-code design
assessment; a new frozen source pin and executed controls are still required.
No source edits, builds or tests were performed by this reviewer.

## Revised nullable construction decision after a valid-schema counterexample

Reviewed 2026-11-06T03:00:55.796569+00:00 before the
proposed owned nullable constructor. This supersedes the earlier recommendation
to use non-null placeholders universally. The earlier allocation-cost qualification
was insufficient: the newly identified schema has a valid all-null encoding but
no constructible non-null representative value at the requested shape.

For a nullable Dictionary<Int8, FixedSizeList<nullable RunEndEncoded<Int16>, 32768>>,
positive-length null keys can refer to zero dictionary values. The empty dictionary
value array then requires zero fixed-list children and zero run ends. Creating one
non-null dictionary value instead requires a fixed-list child length of 32,768,
which Int16 run ends cannot represent. Rejecting this schema under universal
non-null construction is a valid-schema regression, not merely a memory tradeoff.
Marker splitting cannot repair it: even a single marker requires the impossible
representative value under that policy.

Inspected the complete resolved Arrow 59.2.0 ArrayData::new_null implementation.
Its dictionary branch deliberately uses empty value data. Its zero-length helper
recurses through the same null constructor. Those semantics are distinct from the
existing non-null placeholder traversal and are necessary to preserve this valid
nullable case. Nullable parent structs and fixed lists also have genuine parent/
child validity semantics, not just a different top-level bitmap.

Recommendation: carry the pinned, attributed Arrow null-construction function as
a small owned fallible utility, preserving its null encodings. Adapt recursive
null/empty calls consistently and replace capacity conversions, size arithmetic,
invalid-layout unwraps and run-end panics with named Result errors before relevant
allocations. Preserve exact nested Fields and metadata. Keep the existing non-null
placeholder traversal for fields that require it; use the nullable constructor
where nulls are admissible, including appropriate marker children and empty output
construction. The two constructors have distinct semantic contracts, so owning
both is justified rather than an accumulation of representation exceptions.

Simpler alternatives do not satisfy the full boundary:

- Universal non-null placeholders reject the valid dictionary schema above.
- Splitting marker runs does not solve a one-value nested-shape impossibility.
- A run-end-only guard misses nested nullable recursion and other fallible layout
  arithmetic. A complete preflight walker duplicates the constructor's type shape
  knowledge while retaining a dependency that panics.
- Catching panics around the dependency neither defines a fallible construction
  contract nor establishes allocation/ownership behavior.
- Changing the flow-event representation to remove payload columns would require
  an unrelated transport/operator protocol redesign.

Retain the original pinned function and a comparison diff limited to ownership of
that constructor, public imports/formatting, fallibility and required checked
operations. Test the wide nullable dictionary's positive length and zero dictionary
values, direct/nested run-end capacity boundaries, both field nullabilities and
empty outputs. Check that marker construction invokes no user expressions.

Result-based capacity errors are not an out-of-memory guarantee. Buffer allocation
and schema/length budgets remain caller responsibilities, and this repair must not
claim production resource qualification without that work. This source-derived
design assessment ran no builds/tests and changed no product source. The new
counterexample and eventual implementation still require executed controls and
a new frozen cumulative pin before readiness.

## Revised frozen source closure: owned nullable construction

Reviewed 2026-11-06T03:18:08.026068+00:00. Independently
verified all 54 cumulative file hashes, all 26 increment paths, exact cumulative
changed paths, unchanged parent `06dd7e237eb5a343dcc6a6145e775f495e6c30de` and staged tree
`0fd5f5e69cf79ce8afed06474219ef81730a84de`. Incremental SHA-256:
`97566bc3fcdb028e8fa524c5ade7b0e765bee5c323acfba35e2eac889a1c29b3`. Cumulative SHA-256 against upstream
`b52144955b629314a000b1fe49eeea97fa3d0c5c`:
`b888f019db493c1865e9fcbe43a061b85df9cc7d7db0af264039bc5634d38fb6`. No unstaged tracked source changes were present.
The temporary performance probe is untracked and outside that product tree.

Read the complete owned null constructor, retained upstream comparison, non-null
traversal changes, new type/capacity tests, encoder counterexample and revised
projection paths. Rechecked their fit with the complete previously reviewed
projection/planner/codec and retained foundation/native-scalar source. The new
first-principles marker-placeholder note clearly supersedes the rejected universal
non-null proposal and is independently understandable at 292 words.

The revised source resolves the valid-nullable-schema design finding. Nullable
dictionaries retain null keys and zero values; the wide nested value need not be
materialized. Nullable parent structs/fixed lists and nested child construction
retain Arrow's null encodings. The existing non-null traversal keeps its nullable
child choices but routes them through the owned fallible helper. Its fixed-size
child product is checked, and an empty dictionary no longer materializes an unused
value. These preserve the distinction that the rejected universal traversal lost.

The owned routine is a focused dependency-ownership change. Verified its final
source hash against the comparison receipt, original extraction and initial
verbatim-copy evidence, adapted method hash and comparison-patch hash. The comparison
retains the original type-layout decisions and limits changes to public imports,
fallibility/recursive propagation, checked arithmetic and capacity conversions,
and checked Arrow builders. Pin and Apache attribution are visible in source.
No dependency fork or new runtime service is introduced.

Projection now uses the same fallible placeholder construction for marker payloads
and empty results. Empty inputs still bypass all user evaluation. Event encoding
also uses the fallible nullable constructor for payload fields; the fixed Binary
marker-column data path is retained, avoiding an unrelated hot-path change.
The source and tests cover nullable run-end capacity errors, nested forms, preserved
field metadata and the valid zero-value dictionary encoding. The new controls
address the failure family rather than hiding it with one Int16-specific guard.

No unresolved must-fix structural design issue remains in this revised candidate.
The two constructors have distinct contracts: one constructs null representations,
the other provides required non-null placeholders. Owning both is justified by the
valid-schema counterexample. A preflight layout walker would duplicate recursive
shape knowledge while leaving construction in a panic-oriented dependency.

The source does not promise recoverable allocation exhaustion or a general resource
envelope. Allocation budgets, recursion and retained state remain caller concerns.
The helper's checks reject representational/size failures; they are not input-data
validation jobs or arbitrary native-producer correctness checks. Mixed-marker
fragmentation remains a performance limitation pending the repeated measurement.
The final whole-workspace gate is also pending and must issue its own immutable
verdict. Earlier functional results are not silently relabeled as that verdict.

The integration owner reports 334 affected tests passing, including reproduced
panics and the valid-nullable-schema counterexample. This review inspected source
and retained evidence; it executed no build, test or benchmark. Only this assigned
report was appended. Saved request and governance compliance remains confirmed,
and no cleanup, product edits or remote actions were performed.

## Final Python lint-only pin confirmation

Confirmed 2026-11-06T03:22:23.890952+00:00: staged tree
`b67d1a9416d22241ab0359e2ef96dcdf3c678757`, all 54 cumulative file hashes, unchanged parent
`06dd7e237eb5a343dcc6a6145e775f495e6c30de`, increment SHA-256
`0a556ee174bbd47da7148e8ae8f999707482b8078b6fcabed553882fa015bea3` and cumulative SHA-256 against
`b52144955b629314a000b1fe49eeea97fa3d0c5c`:
`c34dcc56ba6d8f7260e7d6eb0997a7dd016fd07de6e79d5a2424da574d6cf1bf`. No unstaged tracked source changes were present.

Independently diffed the tree against reviewed `0fd5f5e6`: only the Python projection
test file changed. Three simple SQL selections now use table/select/limit APIs;
the result and error assertions remain unchanged. Product runtime source and
the Arrow ownership comparison therefore remain identical to the reviewed tree.
This delta introduces no design finding and does not alter the prior qualification
boundaries. The lead reports the final optimized diagnostic completed with the
known mixed-marker limitation; the whole gate remains pending. No build/test or
benchmark was run by this reviewer. Only this report was appended.

## Observability integration decision before code

Reviewed 2026-11-06T03:34:29.010729+00:00. The previously
pinned source verdict is superseded pending this concrete integration repair and
a new source pin. Inspected Sail's telemetry dispatcher, ProjectionMetricEmitter,
metric test helper and resolved DataFusion 55.2 BaselineMetrics/projection source.

The existing telemetry dispatcher recognizes ordinary ProjectionExec only. The new
StreamProjectionExec exposes projector expression metrics but therefore loses their
projection-specific export route. It also lacks the ordinary baseline output and
compute instrumentation. This is a real observability regression when replacing
the ordinary operator, even if result rows are correct. Preserving visibility is
part of human-maintainable integration rather than an optional unrelated feature.

Recommend explicit typed dispatch for StreamProjectionExec alongside ProjectionExec,
reusing the existing ProjectionMetricEmitter and DefaultMetricEmitter chain. A
normal/build manifest reachability inspection found no reverse route from physical
plan to telemetry through the currently declared local dependencies; Research's
complete graph check and Cargo qualification must establish the final acyclic edge.
Adding telemetry's dependency on the instrumented physical-plan crate is narrower
than inventing a plugin registry, name-string routing or globally matching
expression-shaped metrics on unrelated operators. The operator can continue using
DataFusion metrics without depending on Sail telemetry, preserving the useful
instrumentation/export direction.

Use per-partition BaselineMetrics in the existing stream. Its record_poll method
already records output rows, batches, bytes and completion/error; do not double
count those outputs manually. Counts concern encoded outputs, including marker
rows and emitted empty batches. Output bytes follow DataFusion's reported batch
size convention, which can count shared buffers multiple times; they do not
establish unique or retained memory. Expression evaluation can continue using
Projector.with_metrics with the existing expression labels and indices.

Do not hold an elapsed_compute timer across an await. Explicit synchronous
projection, marker/empty construction and final-assembly timer scopes preserve
that rule. Such scopes omit synchronous argument evaluation/concat work performed
inside the asynchronous helper; document the boundary instead of claiming full
CPU accounting. A small per-poll timer around that helper future can include its
active work while excluding suspension if fuller accounting is wanted, without
a scheduling service. In either case elapsed active work is not wall-clock
request latency or a measure of cancelled external side effects.

Verify positive data plus markers through the existing telemetry exporter so the
new typed dispatch is exercised. Empty-only inputs deliberately invoke no user
expressions and cannot prove expression metrics are populated. Check output
counts and absence of wait time in compute using controlled futures rather than
a wall-clock race. The correction must not alter marker/error ordering, future
ownership or callback/schema behavior. Requalify the full candidate after the
new instrumentation, since metrics and polling costs are part of the cumulative
change. No generic metrics framework or other streaming operator repair is needed
to close this specific regression.

This is a pre-code assessment of the proposed correction, not a completed source
review or execution verdict. No builds, tests, benchmarks or product source edits
were performed by this reviewer. Only this assigned report was appended.

## Final observability source closure and cumulative pin

Reviewed 2026-11-06T03:52:17.443021+00:00. Independently
verified staged tree `5a8f4f67535644e0cb8e4eb52389cfb4395bc3d9`, parent
`06dd7e237eb5a343dcc6a6145e775f495e6c30de`, all 58 cumulative source hashes, all 31 increment
paths and the exact upstream changed-path list. No unstaged tracked source changes
were present. Increment SHA-256:
`e0ed57aa267daafbc6c4517a2712c4b1e9cbc050bf544bc62e4f7a1e9e4200f5`. Cumulative SHA-256 against upstream
`b52144955b629314a000b1fe49eeea97fa3d0c5c`:
`450642c939973266f80b2e7bcb52fe60dad7bc0f69fac5d733b9e18f34c77023`.

Read the complete revised operator, metrics tests, typed exporter changes, crate
edges, shared lockfile delta and Rustdoc link correction. Read the self-contained
metrics note and Research's Cargo-metadata graph assessment. Rechecked the full
cumulative architectural fit with the earlier event, filter, failure and native
scalar source. No previous contract is relaxed by the instrumentation.

The observability finding is closed in source. One BaselineMetrics is owned by
the executing stream state. It is not cloned per run, so dropping a completed
run cannot publish a terminal timestamp while later input remains. Each emitted
RecordBatch uses RecordOutput exactly once, preserving the built-in output row,
batch and reported-size conventions. State destruction handles EOF, execution
error and early stream drop. The lifecycle test distinguishes those paths and
asserts terminal timestamps remain unset after intermediate outputs.

Boundary scanning starts its compute timer after awaiting input. Synchronous
projection, placeholder construction and final assembly have explicit timer
scopes. Each asynchronous helper poll is wrapped in a timer that is dropped on
returning Pending, so argument evaluation/kernel polling/concatenation work is
counted without charging suspension time. No outer timer spans that await, and
no new scheduling task or detached future is introduced. The helper's future
and per-call code remain owned by the same stream lifetime.

Telemetry now recognizes StreamProjectionExec by concrete type and reuses the
existing ProjectionMetricEmitter/DefaultMetricEmitter chain. The added dependency
is from the exporter crate to the instrumented operator crate; the operator
still uses DataFusion metrics rather than depending on Sail telemetry. Research's
resolved local graph inspection found this edge acyclic. No registry framework,
string-based node classification or broad metric-pattern rerouting was added.
The lockfile records the workspace edge without external version movement.

The positive mixed-event exporter test exercises both baseline and expression
metric names. The internal test asserts exact encoded output rows/batches/bytes
and partition labels using the built-in aggregation API. Its counts are not
relaxed. The retained dispatch-disabled control fails specifically because the
expected expression metric is missing. The retained lifecycle test addresses
early completion rather than asserting timing thresholds. Inspected the completed
metrics-tests-v2 log: 347 affected tests passed, zero skipped. This is inspected
execution evidence, not a test run by this reviewer.

No unresolved must-fix structural design finding remains in this frozen candidate.
The relevant notes precede the implementation and explain both the preservation
requirement and the selected mechanism. The earlier concern about omitted helper
active work is resolved by per-poll timing. Output size remains DataFusion's
reported size, which can count shared buffers repeatedly; it does not prove a
unique-memory envelope. Active elapsed computation is not end-to-end latency.

The full immutable gate and final performance comparison remain separate pending
qualification. Instrumentation adds per-poll/segment measurement cost and the
known mixed-marker fragmentation remains material. This source verdict does not
claim general performance neutrality, production resource admission, distributed
recovery or completion of the full SDP/Extensions goal.

Saved request, updated plans and governing instruction compliance remains
confirmed. Only read/hash/Git inspection and this report append were performed;
no source edit, build, test, benchmark, cleanup or remote action was performed.

## Frozen synchronous-scope refactor review

Reviewed 2026-11-06T04:02:03.831574+00:00. Verified staged
tree `8b03aee0e5a6909b8b3f7aef085a525de1914b14`, parent `06dd7e237eb5a343dcc6a6145e775f495e6c30de`, all 58
cumulative file hashes, all 31 increment paths and exact cumulative changed paths.
Increment SHA-256 `5fd32ec3258c10719cd2e1951846365d69a85199cfb19d8ef1cdfdba0f7f8d08`. Cumulative SHA-256
against `b52144955b629314a000b1fe49eeea97fa3d0c5c`:
`4dd11e5232f1f1a326cf362c225854b0117f1154330260f323986203b778945d`. No unstaged tracked source changes were
present. Independently confirmed only projection.rs differs from reviewed 5a8f4f67.

Read the first-principles cost note and the complete source delta. The refactor
implements the smaller shared-timer design rather than adding another stream
scheduler. next_input awaits only input acquisition, preserving the pending batch
and its offset; offset resets only when a fresh child batch is requested. The
synchronous next_run then extracts a contiguous slice while advancing the same
pending/offset state. The no-marker branch still avoids scanning or slicing.

One timer begins after acquisition and covers boundary extraction plus synchronous
projection or placeholder construction. Empty input still takes placeholders,
without user expression invocation. The timer is explicitly dropped before both
asynchronous work and output accounting. Synchronous projection errors are stored
as Result until that drop, then propagated. A boundary-extraction error drops the
guard before the enclosing state is destroyed. Input waits and upstream polling
remain outside this node's compute scope.

Only positive non-marker data with mapped asynchronous expressions enters
project_async_data and clones configuration. The retained helper future is still
polled under per-poll timers that end before Pending. Argument/return-field mapping,
metadata, helper semantics and cancellation ownership are unchanged. The stream
retains one BaselineMetrics and records each successful output exactly once after
timing. EOF/error/drop still destroy that state; no per-run baseline clone or
premature completion mechanism was introduced.

Marker-before-error ordering, output-by-run scheduling and release of consumed
input retain their prior structure. There is no evaluation across a marker and
no added buffering/coalescing policy. The typed exporter and owned Arrow nullable
constructor are unchanged, as verified by the cumulative hashes.

No new structural design issue was found in this frozen source. This is a plausible
removal of unnecessary work, not evidence that the previous measured slowdown has
been explained or repaired. New functional, metrics/lifecycle and same-cell paired
performance receipts remain required. Mixed-marker fragmentation is a separate
known limit. No runtime, performance-neutrality or final readiness claim is made
from this source review.

Saved request and governance compliance remains confirmed. This pass performed
read/hash/Git inspection and appended this assigned report only. No source edit,
build, test, benchmark, cleanup or remote action was performed.

## Frozen direct-poll specialization review

Reviewed 2026-11-06T04:07:44.732146+00:00. Independently
verified tree `bb8699fdfbc4ca88fa6c0e816e189af80e560efd`, parent `06dd7e237eb5a343dcc6a6145e775f495e6c30de`, all
58 cumulative file hashes, all 31 increment paths and exact cumulative changed
paths. Increment SHA-256 `9414d2b00491eedfd76e52e212459f92735963e46a6eb0d3c9f79b444e4693a2`. Cumulative
SHA-256 against `b52144955b629314a000b1fe49eeea97fa3d0c5c`:
`7f2cf1d64419f8968e311f04b4b132bed8ee05e5e94be995dcf083b10dd9f8aa`. No unstaged tracked source changes were
present. Only projection.rs and its metrics/lifecycle test file differ from the
previously reviewed observability tree 5a8f4f67.

Read the complete final 403-line operator, independent new channel/wake test and
updated first-principles cost note. The note explains that timer consolidation
alone left meaningful no-marker cost; it therefore supplies a concrete reason
for the direct synchronous branch rather than presuming another scheduler is
necessary. The branch is narrowly selected when there are no mapped async calls.
Both paths share input acquisition, marker/data extraction, data evaluator and
stream-owned baseline. There is no duplicated planner, codec or nullable helper.

The direct path performs one upstream poll or resumes its pending slice, then
returns one projected run. It does not skip empty batches or loop through
immediately ready inputs, so it introduces no unbounded per-poll traversal of
multiple batches. Pending input preserves the state and registered waker. EOF
and upstream/projection errors take and drop the state before returning; subsequent
polls return None. Buffered input and metrics ownership are therefore not retained
until another downstream poll after an already terminal result.

A fresh input resets offset; pending slices retain their advanced offset. The
synchronous timer covers extraction and projection only after child polling.
RecordOutput occurs once after that scope. Marker placeholders and empty data
still bypass user evaluation. The asynchronous path retains per-helper-poll
timing, owned futures and marker-before-later-data scheduling. A synchronous
projection error drops its timer before terminal state destruction. Metadata,
conservative properties, worker reconstruction and nullable-schema semantics are
unchanged, as confirmed by cumulative hashes.

The independently written channel test exercises actual Pending, synchronous
wake notification, data output, upstream failure, buffered unread-payload release
and fused terminal polls. It asserts the baseline remains unfinished while work
is pending and records completion only after terminal release. This targets the
new specialization's lifecycle risk rather than reproducing a particular polling
implementation or racing the clock. Its execution remains pending in this review.

No unresolved structural design finding was found in this frozen v7 candidate.
The added specialization is proportionate to the measured no-marker concern and
keeps the shared contracts visible for maintainers. Prior direct-path exploratory
measurements belong to their exact candidate, not this new pin. Functional and
same-cell performance receipts for v7 are still required; mixed-marker costs remain
material. No performance-neutrality, full immutable-gate or production-readiness
claim follows from this source-only closure.

Saved request and governing instruction compliance remains confirmed. This pass
performed read/hash/Git inspection and appended the assigned report only. No
source edits, builds, tests, benchmarks, cleanup or remote actions were performed.
