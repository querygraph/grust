# Projection regression review before implementation

**Verdict: proceed with a dedicated data-only projection boundary, preserving
the existing synchronous and asynchronous planning contracts. No implementation
verdict is issued yet.** The risks below are source-derived requirements and
negative-control targets, not failures observed in a new candidate.

## Source and scope

Inspected clean tracked source at
`/Users/alexy/src/sail/tmp/streamsource-projection-20261105-06dd7e237`, HEAD
`06dd7e237eb5a343dcc6a6145e775f495e6c30de`, upstream base
`b52144955b629314a000b1fe49eeea97fa3d0c5c`. Source references below are relative
to that worktree unless an absolute dependency path is given. Read the existing
data-only expression design and the current saved request. No builds, tests,
benchmarks or source changes were performed.

## Planning and optimization contracts to preserve

1. **The streaming rewrite currently delegates projection semantics to the ordinary
   planner.** `crates/sail-plan/src/lib.rs:45–57` optimizes the logical plan before
   streaming rewriting. `streaming/rewriter.rs:69–79` then prepends the marker and
   retraction expressions to an ordinary logical projection. Replacing that node
   changes which physical-planning branch runs. DataFusion 55.2.0's
   `datafusion/src/physical_planner.rs:2990–3128` derives physical names of column
   expressions using the qualified logical index and physical input field, applies
   output metadata, extracts asynchronous functions and rewrites their result
   columns. Preserve each behavior rather than treating projector evaluation as
   the entire old projection contract.

2. **Encoded indices and fields must remain coherent through both phases.** Sail's
   filter planner at `crates/sail-session/src/planner.rs:471–484` binds expressions
   to the encoded logical input. A new projection must not remove the first two
   columns and evaluate expressions still bound to those indices. Preserve aliases,
   qualifiers, nested fields and schema metadata. DataFusion's public
   `ProjectionExprs::make_projector_with_schema_metadata` derives names/types/
   nullability from expressions and copies metadata separately; supplying a schema
   does not override every field property.

3. **Physical optimizers still run.** Sail installs projection pushdown twice and
   other default/custom rules in `crates/sail-physical-optimizer/src/lib.rs:59–98`.
   Streaming projection properties must describe encoded rows, including marker
   placeholders. A constant user expression is not necessarily constant across
   those rows. Use conservative properties until proved, while preserving physical
   partition count, pipeline behavior and per-partition event order. Check the
   optimized plan for ordinary computed projections or asynchronous evaluators
   introduced beneath the protected boundary.

4. **Some current optimizations recognize only ProjectionExec.** Examples include
   `mixed_numeric.rs:27–54`, `correlation_cast.rs:42–54` and lambda protection in
   `projection_pushdown.rs:55–87`. The new node will not automatically participate.
   These are not grounds to reproduce ordinary projection pushdown across markers.
   Preserve ordinary batch plans and inspect/measure applicable streaming plans
   before claiming performance neutrality. Lambda-bound columns and source metadata
   expressions need controls so context-sensitive expression handling is not lost.

## Asynchronous behavior cannot be silently dropped

Sail calls `prepare_async_functions` at `crates/sail-session/src/planner.rs:114`.
The function in `crates/sail-plan/src/function/mod.rs:55–255` preserves supported
calls while explicitly rejecting async-inside-async nesting. The replacement must
continue exposing its expressions to this traversal. It must not accidentally
admit nested calls or make previously working projection calls synchronous.

DataFusion's `AsyncMapper` is a public reuse point: it appends result-column
indices after the input columns and remaps occurrences in final expressions.
Retain deterministic expression/name ordering, the configuration context and the
same original input fields when evaluating multiple async expressions. Do not
evaluate mapped result-column references against the pre-append schema.

Ordinary `AsyncFuncExec` coalesces input batches before invocation. Putting it
below a flow-aware projection over encoded batches would still evaluate markers
and could accumulate across them. Evaluate only a contiguous data run and settle
its result before forwarding the following marker. Cancellation must drop the
pending invocation and retained input; it must not detach computation and continue
publishing later markers.

One public-helper edge needs an explicit control: DataFusion 55.2.0's
`datafusion-physical-expr/src/async_scalar_function.rs:136–199` collects no chunks
for an empty batch when an ideal batch size is present, then calls `concat` on
the empty result list. Directly invoking this helper on a zero-row data run can
introduce failure where the ordinary coalescing path discarded empties. Specify
and test empty-data behavior. The helper also expands scalar async returns to one
element per chunk; its existence is not proof of arbitrary scalar-return support.
Distinguish existing supported behavior from a new capability before changing it.

## Worker reconstruction is part of correctness

`crates/sail-execution/src/proto/codec.rs:1453–1463,2983–2994` explicitly encodes
and reconstructs the streaming filter. A new projection likewise needs a distinct
case preserving the protected node, child, expressions, aliases and output field/
schema metadata. Async expression identities and result-column mapping must
reconstruct consistently. Existing async function codec controls at
`codec.rs:6357–6383` preserve the Jev async wrapper and distinguish a Python
function with the same name; do not replace those identity rules with name-only
lookup.

The optional scan-projection helper at `codec.rs:5674–5699` interprets an empty
expression list as `None`. A zero-user-column streaming projection is a real
projection and must not turn into identity projection during serialization.
Use an explicit wire representation or preserve the two required control
expressions so absence and zero user columns remain distinct.

## Required discriminating controls

| Boundary | Negative control and preserved behavior |
| --- | --- |
| Marker isolation | Strict cast and counting sync/async functions fail on marker placeholders in the old path; marker-only input invokes neither, and genuine invalid data still fails |
| Ordered failure | A marker before bad or pending data is observable before that data's failure; a marker after pending data cannot overtake it; include adjacent markers and all marker kinds |
| Schema and cardinality | Qualified/reordered/repeated columns, aliases, literals, zero user columns, metadata-bearing nested fields, sliced arrays and positive zero-column row counts |
| Retractions | Mixed flags remain aligned with their transformed data rows; no duplicate expression invocation merely to preserve flags |
| Async scheduling | Multiple supported async calls, sync expressions surrounding async results, ideal batch sizes smaller/larger than a run, empty data, delayed completion, cancellation and existing nested-call refusal |
| Optimization | Actual rewrite and physical optimization, including constant projection followed by contradictory filtering, lambda-bearing expressions and source renaming; no marker-unsafe evaluator reappears |
| Reconstruction | Child replacement and codec round trip execute the protected node with the same sync/async result, metadata and ordered markers; zero user columns stay zero |
| Baseline preservation | Ordinary batch projection/async queries retain their existing plans/results; no-marker path avoids unnecessary fragmentation and releases consumed input before another downstream poll |

Use component fixtures to construct markers and deterministic pending/error
interleavings. Also exercise the actual planner and fresh public server, because
operator-only fixtures cannot establish optimizer or worker reconstruction.
Compare exact outputs before cost measurements. Existing filter, fidelity,
terminal-error and standalone native-adapter tests remain cumulative obligations.
No projection result establishes graph-wide barrier alignment, volatile-retraction
correctness, durable replay or native package integration.

## Instructions and review boundary

Read the exact saved request and source `.github/copilot-instructions.md`,
`dev.instructions.md`, `rust-review.instructions.md` and
`python-review.instructions.md`. The full repository AGENTS.md, LAKESAIL.md,
SHEHAB.md, WRITING-RULES.md and current CLARITY.md were read in the continuing
review; no compaction has occurred since those readings. This is the independent
Regression role, with implementation and verification owned by the lead. Only
this assigned evidence file was written. Final cumulative source review remains
required after implementation and integration.

## Implemented increment review before final freeze

**Source assessment: no concrete runtime regression identified in the inspected
projection implementation. One optimizer-configuration coverage gap must be
resolved before claiming the planner fixtures qualify Sail's actual optimizer
pipeline. Final frozen-tree review and execution qualification remain pending.**

Reviewed the current 19-file product increment against `06dd7e237`, including
the new logical/physical node, planner, rewriter, codec and tests. Source was still
being completed during inspection, so this is not an immutable-candidate verdict.
The temporary ignored cost probe is outside this product review. Independently
confirmed that base `06dd7e237eb5a343dcc6a6145e775f495e6c30de` has no tree diff
from previously reviewed Comet tree `455101575ecbfbec6f843464ce178e0d09046f51`.
The cumulative upstream diff therefore retains those earlier foundation and
Comet changes, with this increment isolated above them.

### Planner fixture does not yet use production rule configuration

At inspection, `crates/sail-session/src/streaming_projection_tests.rs:160` built
its context with DataFusion default features and Sail's query planner only. The
production server in `session_factory/server.rs:145–155` explicitly installs Sail
analyzer, logical optimizer and physical optimizer lists. The latter includes
ContextSafeProjectionPushdown and custom input-file/numeric handling discussed
above. The current fixture assertions therefore exercise the default physical
pipeline, not the complete configured Sail pipeline. Run those scenarios with
the production rule lists, or retain a separate explicit production-configuration
control, before describing the result as full optimizer preservation. This is a
validation gap, not an observed runtime failure.

### Contracts preserved by the inspected source

The rewriter preserves the original projected logical fields and metadata while
adding the two control fields. Physical planning reproduces qualified-column
index/name lookup. The bounded-source adapter now retains logical qualifiers and
metadata; it does not change physical data layout. That narrow repair addresses
the reported old-path bounded-name failure rather than introducing a new source
execution protocol.

The physical node requires positional control-column expressions, evaluates only
contiguous data runs and reconstructs marker payloads without user evaluation.
It preserves marker bytes and retraction flags, drops exhausted owned input and
publishes conservative encoded-row properties. Its coroutine stops on error and
holds asynchronous work within the current run. The async tests use deterministic
gates and drop observations rather than timing assumptions, and inspect argument
metadata, ordering, cancellation and ideal batch sizes.

The codec serializes original unmapped expressions and output schema, rebuilding
the same protected node and async mapping. Two leading control expressions remain
present even when user output is empty, so the optional-projection helper's empty
list convention cannot silently produce identity projection. Sync reconstruction
tests execute data and markers; the async codec case checks wrapper identity and
marker-only execution, not a remote service call on worker data.

The public re-export of the existing streaming predicates/rewrite functions adds
test access without changing their implementation or ordinary batch detection.
The new dependency entry is an existing workspace async-trait dependency used
only for tests; existing resolved dependency versions are unchanged. Ordinary
batch projection remains on its original planner branch.

### Outstanding evidence limits

The lead reported 19 focused passes and three failing controls before later test
additions. These counts are not independent executions by this reviewer and do
not cover changes made afterward. At inspection the added multiple-async,
nested-async, bounded-qualifier and empty-sync tests were still being completed or
compiled. The newly added empty-sync no-invocation control preceded its runtime
branch change and is not recorded here as passing.

Cost qualification, actual configured optimizer controls, final immutable tests
and selected public tests remain necessary. No marker-heavy performance neutrality,
distributed async-service execution, native package integration or durable recovery
claim follows from this source review. No builds, tests or source edits were
performed; only this report was appended. The saved request and governance
readings above remain current, with no intervening compaction.

## Final frozen cumulative source review

**Verdict: no unresolved introduced correctness regression identified by source
inspection of this candidate. The optimizer-configuration gap is closed in the
fixture source, and the empty synchronous batch guard is now correctly placed.
Execution and performance qualification remain separate, pending evidence.**

Independently verified the frozen Git tree and recomputed both binary-diff hashes:

| Item | Verified value |
| --- | --- |
| Starting HEAD | `06dd7e237eb5a343dcc6a6145e775f495e6c30de` |
| Upstream base | `b52144955b629314a000b1fe49eeea97fa3d0c5c` |
| Candidate tree | `52cbe5f4281bf74b9d54615504ce7eb9e062f80d` |
| Increment SHA-256 | `5fa79cdd5f911e5449ffb64b0991ef7a21d3d3101e2311576cddb0f143022ecc` |
| Cumulative SHA-256 | `70390f447d0b7425a49cc8cbec2649ec1a3a11a5f2cb5d5ea7a372c11dfc6b20` |

All 52 file hashes in `review-logs/candidate-snapshot-final.json` match their
blobs in that tree. Its 19 increment paths match the actual diff. Tracked working
files have no difference from the frozen tree, and HEAD remains the stated base.
This identifies a candidate tree, not an already gated commit.

The cumulative review covers all 52 paths against upstream, carrying forward the
earlier foundation and Comet source reviews only where their contents remain
identical. Rechecked the empty tree diff between the starting HEAD and previously
reviewed Comet tree `455101575ecbfbec6f843464ce178e0d09046f51`. This increment
does not alter native admission/nullability, filter evaluation, encoding,
query-failure publication or console locking. Re-read the new projection nodes
and all integration changes, with the prior complete test inspection retained.
The lockfile delta adds the existing async-trait dependency to the physical-plan
test crate without changing resolved package versions.

### Closure of earlier review points

`crates/sail-session/src/streaming_projection_tests.rs:160` now installs Sail's
analyzer and logical optimizer lists plus `get_physical_optimizers` with explicit
default `PhysicalOptimizerOptions`. This addresses the concrete missing-rule
configuration finding. Production `session_factory/server.rs:145` additionally
constructs its own runtime, configuration and registrations, so this fixture is
not a complete replacement for public-server verification. Its newly configured
execution results were pending at this review; initial DataFusion-default passes
must retain their original description.

`crates/sail-physical-plan/src/streaming/projection.rs:245` returns the exact
empty output schema before entering either synchronous or asynchronous
evaluation. The no-invocation assertion in `projection_tests.rs:368` directly
tests the previously uncovered synchronous case. The lead reports that removing
this placement produced one invocation against the expected zero; that is
reported control evidence, not an execution performed by this reviewer.

The bounded adapter preserves original qualifiers and field/schema metadata at
`crates/sail-logical-plan/src/streaming/source_adapter.rs:23`, including child
replacement. Its unit control checks those properties. The public strict-cast
test in `python/pysail/tests/_dev/spark/streaming/test_projection.py:35` supplies
the complementary bounded branch inside a streaming union. Ordinary batch
planning remains on its existing path, with a public batch control retained.

### Limits and remaining verification

No build or test was executed by this reviewer. The lead's final gate, configured
optimizer controls, repeated cost measurements and fresh public-server checks
were still pending. In particular, the earlier source-detection/constant-folding
boundary remains a separately disclosed limitation; the physical optimizer
control does not establish pre-rewrite logical source preservation. Performance
neutrality, distributed async data-service calls, native package integration,
graph-wide barriers and durable replay are not established here. The existing
marker-heavy performance qualification remains unchanged by this source verdict.

After compaction, re-read the exact saved request, its preceding build requests,
AGENTS.md, LAKESAIL.md, SHEHAB.md, CLARITY.md, WRITING-RULES.md and the source
development/Rust/Python instructions. Confirmed compliance with the read-only
source boundary and preserved artifacts. Only this assigned evidence report was
appended.

## Revised frozen review: fallible nullable construction

**Verdict: no unresolved introduced correctness regression found in the revised
candidate. The nullable-layout repair preserves valid empty dictionary values
and converts the inspected run-end and size-overflow panics into errors. Final
workspace, public-server and performance qualification remain pending.**

This section supersedes the candidate pin above, without replacing its retained
observations. Independently verified:

| Item | Verified value |
| --- | --- |
| Candidate tree | `0fd5f5e69cf79ce8afed06474219ef81730a84de` |
| Starting HEAD | `06dd7e237eb5a343dcc6a6145e775f495e6c30de` |
| Upstream base | `b52144955b629314a000b1fe49eeea97fa3d0c5c` |
| Increment SHA-256 | `97566bc3fcdb028e8fa524c5ade7b0e765bee5c323acfba35e2eac889a1c29b3` |
| Cumulative SHA-256 | `b888f019db493c1865e9fcbe43a061b85df9cc7d7db0af264039bc5634d38fb6` |

All 54 recorded blob hashes and all 26 increment paths match. Tracked source
matches the frozen tree. The full cumulative review carries forward unchanged
content from the previous pin and independently examines all ten changed paths
between those candidates. Comet, filter, failure publication, planner, rewriter
and codec source remain unchanged by this delta. The temporary untracked
performance diagnostic is outside the candidate and this source verdict.

The owned constructor in `crates/sail-common-datafusion/src/array/null.rs`
retains Arrow's nullable layouts and empty unselected children. Its changes add
checked arithmetic, representable run-end/dense-union lengths, allocation-layout
checks, recursive error propagation and checked Arrow construction. Independently
verified the retained upstream extract against the local Arrow 59.2.0 source,
the initial exact copy, the owned method extract and all comparison artifact
hashes in `review-logs/null-ownership/comparison-v1.json`. Read the full comparison
patch; no unrelated layout change was identified.

Nullable children in `array/placeholder.rs` now use that fallible constructor.
Fixed-size list multiplication is checked before constructing children, and an
empty dictionary no longer constructs an unused representative value. The
encoder applies the helper to nullable marker payloads; its existing Binary
control-column construction for data rows is unchanged. Projection uses the same
placeholder path for empty batches and marker runs, preserving the input control
arrays without evaluating expressions.

The tests retain positive and negative boundaries. The four run-end projection
controls explicitly verify delivery of one batch containing all requested rows
before invoking the projection. This is material: the first control log contains
"oversized run-end output was accepted" because the memory source split the
fixture. The corrected `nullable-marker-control-v2.log` records four Arrow
run-overflow panics plus the fixed-size multiplication panic with the repair
removed. These are distinct observations, not five equivalent confirmations of
the original fixtures.

The rejected all-non-null replacement has its own retained counterexample:
`nonnull-marker-counterexample.log` records refusal of a valid nullable dictionary
whose unselected value type contains a wide fixed-size list of Int16 runs. The
final constructor leaves dictionary values empty. Both utility and marker-encoder
tests inspect this case; it is not dismissed as an invalid schema. Tests also
cover zero-length nested dictionaries, nullable children and run-end limits.

Inspected `owned-null-tests.log`, which records 334 affected tests passed with
zero skipped, including the configured Sail optimizer fixtures. This is retained
execution evidence produced by the lead, not an independent run by this reviewer
or a complete immutable gate. The public test delta removes diagnostics and
compares ordinary batch rows without asserting unspecified ordering; expected
values and failure checks remain intact.

No new must-fix source finding remains. Allocation exhaustion is outside the
constructor's recovery promise, and valid Arrow types remain its precondition.
No final performance-neutrality, complete public-server, distributed async,
package integration or durable-recovery claim follows. No builds or source edits
were performed. The previously recorded request/governance readings remain
current without intervening compaction; only this report was appended.

## Final pin confirmation after Python lint repair

**The source verdict remains unchanged: no unresolved introduced correctness
finding identified.** Independently recomputed both Git binary-diff hashes and
verified all 54 recorded file hashes and 26 increment paths for:

| Item | Verified value |
| --- | --- |
| Final candidate tree | `b67d1a9416d22241ab0359e2ef96dcdf3c678757` |
| Increment against `06dd7e237eb5a343dcc6a6145e775f495e6c30de` | `0a556ee174bbd47da7148e8ae8f999707482b8078b6fcabed553882fa015bea3` |
| Cumulative against `b52144955b629314a000b1fe49eeea97fa3d0c5c` | `c34dcc56ba6d8f7260e7d6eb0997a7dd016fd07de6e79d5a2424da574d6cf1bf` |

Tracked source matches this tree. Compared its complete diff against reviewed
tree `0fd5f5e69cf79ce8afed06474219ef81730a84de`: only three lines in
`python/pysail/tests/_dev/spark/streaming/test_projection.py` change. Each replaces
`SELECT value ... LIMIT n` with `table(...).select("value").limit(n)`. Limits,
selected fields and all exact assertions remain intact. All runtime source is
identical, independently confirming `review-logs/performance/source-equivalence-v3.json`.

Read the retained Python lint/format log and public receipt: lint and formatting
pass, the helper CLI reports server version 4.2.1, and all four public tests pass.
These are lead-produced execution records, not tests run by this reviewer or a
completed full gate. Repeated performance qualification applies to identical
runtime source and retains the material mixed-marker gap; this review does not
waive it. The full gate remains pending. No builds or source edits were performed;
the saved request and governance remain current without intervening compaction.

## Final source review after metrics repair

**No unresolved introduced correctness finding identified in the revised
candidate.** The earlier projection omitted baseline accounting and exporter
dispatch; this repair supplies both. It changes runtime work, so earlier
performance results alone cannot qualify this new pin.

Independently verified the frozen tree, both binary diffs, all 58 recorded file
hashes and all 31 increment paths:

| Item | Verified value |
| --- | --- |
| Candidate tree | `5a8f4f67535644e0cb8e4eb52389cfb4395bc3d9` |
| Starting HEAD | `06dd7e237eb5a343dcc6a6145e775f495e6c30de` |
| Upstream base | `b52144955b629314a000b1fe49eeea97fa3d0c5c` |
| Increment SHA-256 | `e0ed57aa267daafbc6c4517a2712c4b1e9cbc050bf544bc62e4f7a1e9e4200f5` |
| Cumulative SHA-256 | `450642c939973266f80b2e7bcb52fe60dad7bc0f69fac5d733b9e18f34c77023` |

Tracked source matches this tree. Reviewed all seven paths changed from
`b67d1a9416d22241ab0359e2ef96dcdf3c678757` in full cumulative context, retaining
the prior reviews for unchanged content. The two schema changes repair Rustdoc
links only. The new telemetry dependency adds no resolved package version and
has no reverse path through the inspected workspace path-dependency graph.

`crates/sail-physical-plan/src/streaming/projection.rs` creates exactly one
`BaselineMetrics` for each execution stream and stores it in the state moved
between runs. No per-run clone can prematurely publish its end timestamp.
`RecordOutput` runs once after successful construction of each emitted batch;
there is no second `record_poll` accounting path. Inspected DataFusion 55.2.0's
`Projector::with_metrics`, `BaselineMetrics` drop behavior and `RecordOutput`
implementation to confirm that projector expression timers do not duplicate
baseline output accounting. Counters describe encoded rows and therefore include
markers, with bytes calculated by the existing DataFusion helper.

Input polling precedes the boundary-scan timer. Synchronous projection and
placeholder construction have scoped timers. Asynchronous helper polling has a
timer inside each poll closure, which drops before suspension; active argument
evaluation, kernel polling and concatenation are included without charging the
await interval. Later array conversion and projection are timed separately.
The `try_unfold` state owns the baseline through output delivery and drops it on
EOF, error or cancellation. The lifecycle test explicitly checks that the first
output and an unpolled EOF do not set an early terminal timestamp.

`crates/sail-telemetry/src/execution/metrics/mod.rs` now selects the existing
projection emitter by the concrete streaming node type. Its exporter control
executes mixed data and markers. Reviewed `metrics-control.log`, which records
missing baseline counters and export before the repair, and the separate
`controls/metrics-dispatch.log`, which fails with dispatch alone removed.
`metrics-tests.log` retains the intermediate custom-counter lookup failure;
the revised test selects built-in OutputBatches and OutputBytes variants without
changing the expected three batches, four encoded rows or exact byte sum.
`metrics-tests-v2.log` records 347 affected tests passed with zero skipped,
including EOF/error/drop lifecycle coverage. These are inspected lead-produced
logs, not independent executions by this reviewer.

The full gate and performance repeat remain pending. In particular, per-output
memory accounting and timing add work whose cost must be measured; the material
mixed-marker gap is still an open qualification and is not waived by passing
correctness tests. Earlier public passes describe their earlier runtime pin until
the final candidate is exercised. No builds or source edits were performed. The
saved request and governance readings remain current without intervening
compaction; only this assigned report was appended.

## Revised source pin for synchronous cost repair

**No introduced correctness regression identified by source inspection. The cost
effect and this candidate's execution qualification remain pending.**

Independently recomputed the increment and cumulative binary diffs, verified all
58 recorded file hashes and 31 increment paths, and confirmed tracked source
matches the frozen tree:

| Item | Verified value |
| --- | --- |
| Candidate tree | `8b03aee0e5a6909b8b3f7aef085a525de1914b14` |
| Starting HEAD | `06dd7e237eb5a343dcc6a6145e775f495e6c30de` |
| Upstream base | `b52144955b629314a000b1fe49eeea97fa3d0c5c` |
| Increment SHA-256 | `5fd32ec3258c10719cd2e1951846365d69a85199cfb19d8ef1cdfdba0f7f8d08` |
| Cumulative SHA-256 | `4dd11e5232f1f1a326cf362c225854b0117f1154330260f323986203b778945d` |

Only `crates/sail-physical-plan/src/streaming/projection.rs` differs from reviewed
tree `5a8f4f67535644e0cb8e4eb52389cfb4395bc3d9`. Reviewed that complete diff and
the resulting execution code in cumulative context; all other prior reviewed
contents remain identical. Read the first-principles cost note. Its hypotheses
remain measurement questions rather than asserted causes or demonstrated gains.

The extraction preserves the same pending batch and offset transitions.
`next_input` consumes pending input before polling upstream and resets the offset
only when fetching a new batch. `next_run` performs the unchanged contiguous
marker/data scan synchronously. One timer starts after input arrives and covers
scanning plus synchronous projection or placeholder construction. On the async
branch it is explicitly dropped before awaiting the helper; the helper retains
per-poll timing. Async configuration is cloned only for positive-length data runs
that contain async expressions. Empty batches and markers still bypass user
evaluation.

There is still one baseline owner, one successful-output accounting call and one
stream lifecycle. Errors during extraction or projection unwind the timer and
owned state; successful runs preserve the same output ordering and retained-input
boundary. EOF, error and cancellation continue to drop the single baseline. No
additional polling, run coalescing, output batching or expression semantics was
introduced by the refactor.

No new must-fix source issue was found. The previously recorded 347 affected
passes belong to the earlier implementation and are not a pass claim for this
candidate. Builds, final gate, public verification and repeated performance are
pending; the material mixed-marker gap remains open. No builds or source edits
were performed. Request and governance readings remain current without
intervening compaction; only this report was appended.

## Final v7 review: direct synchronous polling

**No introduced correctness regression identified by source inspection. Final
execution and performance results remain pending.** Independently verified:

| Item | Verified value |
| --- | --- |
| Candidate tree | `bb8699fdfbc4ca88fa6c0e816e189af80e560efd` |
| Starting HEAD | `06dd7e237eb5a343dcc6a6145e775f495e6c30de` |
| Upstream base | `b52144955b629314a000b1fe49eeea97fa3d0c5c` |
| Increment SHA-256 | `9414d2b00491eedfd76e52e212459f92735963e46a6eb0d3c9f79b444e4693a2` |
| Cumulative SHA-256 | `7f2cf1d64419f8968e311f04b4b132bed8ee05e5e94be995dcf083b10dd9f8aa` |

All 58 file hashes and 31 increment paths match, as does tracked source. Compared
the full cumulative content using prior review for identical blobs: only
`streaming/projection.rs` and `streaming/projection_metrics_tests.rs` differ from
the reviewed instrumented tree `5a8f4f67535644e0cb8e4eb52389cfb4395bc3d9`.
Read both changed files and the revised first-principles cost note.

The synchronous branch holds one optional shared stream state. A pending input
poll leaves that state intact and passes the caller's waker directly upstream.
Successful projection emits one accounted batch. Upstream error, extraction or
projection error, and EOF remove the state immediately; subsequent polls return
`None`. Dropping the closure also drops its state. Thus terminal input and buffered
payload are released without requiring another poll, while the baseline remains
owned until that terminal event. No second metric owner or competing output
counter was introduced.

Input acquisition, contiguous-run extraction, placeholder construction and the
projector remain shared with the async path. The synchronous compute timer starts
after input delivery; async active-poll timers and suspension exclusion remain
intact. Marker ordering, retraction controls and empty-batch expression isolation
are unchanged.

The added channel fixture directly checks pending registration and wakeup, one
data result, upstream error, release of unread buffered payload, producer closure,
terminal timestamp and repeated terminal polls. Existing projection-error and
EOF/drop tests remain. These assertions inspect observable lifecycle behavior
without sleeps or duration thresholds; their final execution was pending at this
review, so no pass count is attributed to v7 here.

The reported v6 no-marker ratios are earlier-candidate performance evidence, not
a final v7 result. The mixed-marker gap, final benchmark, final tests and whole
gate remain open. No builds or source edits were performed. Request and governance
readings remain current without intervening compaction; only this report was
appended.
