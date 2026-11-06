# Scope review: marker-isolated streaming projection

## Initial design and work-in-progress verdict

No scope blocker was found in the projection design and inspected integration
seams. The full request selects projection isolation as the next increment while
retaining the complete Declarative Pipelines, existing Extensions and Comet route
objective. The plan supplies its own problem, existing behavior, example failure,
alternatives, recommendation, tradeoffs and evidence requirements. It does not
require authoring history or a separate discussion to understand the decision.

The reviewed `STREAMSOURCE-PROJECTION.md` draft has SHA-256
`c9dc845b856d2a6587ff089975f95ea1903c14a73118010ae2f466b2ea4ec2a4` and 968 words.
The inspected worktree is
`/Users/alexy/src/sail/tmp/streamsource-projection-20261105-06dd7e237`, starting at
`06dd7e237eb5a343dcc6a6145e775f495e6c30de`, upstream base
`b52144955b629314a000b1fe49eeea97fa3d0c5c`. It is still mutable WIP; this is not a
final cumulative source or gate verdict.

## Scope fit

A new logical projection node, physical execution node, streaming rewrite,
extension-planner branch and physical-plan codec are connected changes required
to enforce one contract through real planning and worker reconstruction. They do
not create an unrelated execution framework. The physical node keeps event
scheduling in Sail and reuses DataFusion's public projection/asynchronous evaluators.
Conservative partitioning and equivalence declarations belong to this work because
ordinary computed-column properties can be false on marker placeholders.

Per-run asynchronous evaluation is in scope: leaving an ordinary asynchronous
coalescer around the projection could evaluate across a marker and defeat the
promised boundary. The plan explicitly preserves supported behavior, documents
nested-call and helper limitations, refuses a zero ideal batch size and distinguishes
local future drop from cancellation of external side effects. It does not claim
new replay semantics for volatile functions or retractions.

The increment does not implement source controls, checkpoint alignment, durable
preparation, target fencing, typed configuration, native package admission or
worker package loading. These remain explicit requirements elsewhere in the full
goal. Projection isolation enables later native expressions without pretending
that a Comet component result already establishes package or recovery integration.
HUMAN-REVIEW retains the full goal and marks projection qualification as pending.

Ordinary batch projection follows its existing planner path. The proposed change
therefore has a meaningful admission boundary and requires actual batch controls,
streaming public queries, optimizer checks and codec reconstruction rather than
only physical-operator tests. Those requirements are present in the plan.

## Scope finding sent to the owner

The WIP rewriter also removes the filter predicate's redundant
`OR marker_present` expression. The prior flow-aware filter already bypasses
markers, so this cleanup is not necessary to implement projection. Retain it for
this focused increment, or explicitly justify its inclusion and qualify real
filter behavior. This is a small scope-tightening recommendation, not an identified
correctness defect.

The observed lock changes reorder an existing workspace record, simplify a
libloading dependency qualifier and add the test-only async-trait edge. No dependency
version advancement was present in that inspected diff. Final review should confirm
that no broader dependency change enters the cumulative candidate.

## Evidence and compliance

Read the complete saved request, projection plan and current HUMAN-REVIEW.
Repository AGENTS, LAKESAIL, SHEHAB, CLARITY and WRITING-RULES remain the governing
requirements read in this review chain; source development and Rust-review
instructions were refreshed for this increment. No source edits, builds, tests,
performance measurements, cleanup or remote actions were performed. Only this
report was written. A final frozen cumulative review remains required.

## Small scope-delta review before the final pin

Confirmed the unrelated filter predicate cleanup was removed: the streaming
rewriter retains the baseline `OR marker_present` construction. Confirmed the
lockfile diff is now only the `async-trait` entry corresponding to the physical
plan crate's test dependency. The earlier scope-tightening finding is resolved.

The `sail-plan` crate root now reexports the existing `is_streaming_plan` and
`rewrite_streaming_plan` functions. This is a reasonable additive API seam for
programmatic logical-plan callers and cross-crate integration tests. It exposes
the same implementation used by normal planning, while the streaming module
remains private. It adds no duplicate rewrite, new scheduling mechanism, automatic
second rewrite or different execution policy. The existing rewrite documentation
states its optimized-plan and executed-command preconditions. Tests should respect
those preconditions just as the normal planning path does.

No scope blocker was found in that seam. It helps qualify real logical-to-physical
integration rather than testing a parallel imitation, and is directly related to
the projection node and worker reconstruction work. This additive public surface
should remain visible in the final change description so reviewers can assess it.
No builds, source edits or gate claims were made here. The source remains WIP;
this review will wait for the final frozen cumulative pin before a final verdict.

## Final frozen cumulative scope verdict

Verified all 54 source file hashes listed in
`review-logs/candidate-snapshot-final.json`, working/index equality, the unchanged
parent `06dd7e237eb5a343dcc6a6145e775f495e6c30de`, and exact index equality with tree
`b67d1a9416d22241ab0359e2ef96dcdf3c678757`. Independently recomputed:

- Projection increment SHA-256:
  `0a556ee174bbd47da7148e8ae8f999707482b8078b6fcabed553882fa015bea3`.
- Full cumulative source patch against upstream
  `b52144955b629314a000b1fe49eeea97fa3d0c5c`, SHA-256:
  `c34dcc56ba6d8f7260e7d6eb0997a7dd016fd07de6e79d5a2424da574d6cf1bf`.

No scope blocker was found. The final increment has 26 paths covering projection
execution, logical rewrite/planning/worker reconstruction, qualified bounded-source
schema preservation, required placeholder support and their tests. Earlier foundation
and Comet scalar files remain part of the explicitly pinned cumulative source;
this increment does not silently replace or discard those capabilities.

The final null-constructor addition is a justified dependency of the projection
contract. Read both the current projection plan and the standalone marker-placeholder
plan. Their concrete counterexamples explain why ordinary Arrow null construction
can panic on direct/nested run-end capacity and why substituting nonnull placeholders
would refuse a valid nullable dictionary. The implementation carries a narrowly
attributed Arrow routine with its Apache license, checked capacities, fallible
recursion and checked builder. The pinned original extract and comparison are
retained under `review-logs/null-ownership/`. It adds no vendored dependency crate
or general schema-validation subsystem.

Routing generic nullable payload construction through the same helper is coherent
scope: projection markers, empty outputs and encoded event payloads need the same
fallible schema-preserving operation. The nonnull placeholder corrections for
fixed-size multiplication and empty dictionaries support that operation. The fixed
Binary data-marker path is unchanged. The helper does not claim recoverable
allocation failure or provide task memory admission.

The public tests now use DataFrame table/select/limit operations for query construction
while retaining exact sorted-row/multiset assertions, explicit invalid-data failure
and ordinary batch controls. Those interface changes do not weaken the intended
observable behavior. The earlier filter cleanup remains reverted; lockfile scope
is still only the test dependency edge. The existing rewrite-function reexport
remains an appropriate additive integration seam.

The plans and current compendium retain the complete SDP, existing Extensions,
Comet route and performance objective. Source controls, alignment, fencing, typed
configuration and integrated recovery remain required subsequent work; they are not
claimed as qualified by this projection component.

The lead reports 334 affected tests passed. This reviewer performed source and
artifact inspection only; full immutable qualification remains pending. The verdict
above is a final source-scope review of the exact candidate, not a completed test,
performance or production-readiness verdict. Only this report was appended. No
source edits, builds, cleanup or remote actions were performed.

## Final cumulative review including observability repair

Verified the revised frozen tree
`5a8f4f67535644e0cb8e4eb52389cfb4395bc3d9` against its snapshot: all 58 listed
file hashes, 31 increment paths, unchanged parent
`06dd7e237eb5a343dcc6a6145e775f495e6c30de`, working/index equality and exact
index/tree equality. Recomputed both complete patch hashes:

- Increment SHA-256:
  `e0ed57aa267daafbc6c4517a2712c4b1e9cbc050bf544bc62e4f7a1e9e4200f5`.
- Cumulative against upstream `b52144955b629314a000b1fe49eeea97fa3d0c5c`, SHA-256:
  `450642c939973266f80b2e7bcb52fe60dad7bc0f69fac5d733b9e18f34c77023`.

No scope blocker was found in the revised cumulative source. Read the standalone
`STREAMSOURCE-PROJECTION-METRICS.md` plan and inspected the stream metrics ownership,
compute timers, typed exporter routing, tests and dependency changes. Preserving
existing projection observability is a regression repair within this projection
increment, not an unrelated monitoring subsystem. A replacement node should not
appear less expensive merely because it drops baseline or expression metrics.

One partition-owned BaselineMetrics lives with the stream, and each output is
recorded once. Encoded marker rows are included as physical output. Compute timers
cover active work without remaining live across input waiting or asynchronous
suspension. The plan distinguishes reported output bytes from uniquely retained
memory and makes no resource-admission claim.

The typed dispatcher extends the existing projection exporter rather than adding
a registry or changing all nodes based on metric names. The telemetry-to-physical-plan
workspace edge is directly required for that type check. Inspected the ordinary
workspace path-dependency graph and found no reverse physical-plan-to-telemetry
path. The lockfile adds that edge and the existing test-only async-trait edge;
no external version advances enter this repair. The qualified Rustdoc links in
the flow-event schema are local documentation corrections associated with the
required gate, with no runtime contract change.

The lifecycle tests assert terminal metric publication only at EOF, failure or
stream destruction. Metric-count tests retain exact rows, batches, bytes and
partition labels; exporter coverage requests the expression metric explicitly.
The lead reports two pre-repair metric controls failed and an isolated dispatcher
control missed the expression metric, followed by 347 affected tests passing.
Those are attributed execution reports, not runs by this reviewer. Earlier timing
results are superseded until equivalent-instrumentation comparisons complete.

The complete SDP, existing Extensions, Comet and performance objective remains
active. These observability changes neither expand into source controls, fencing
or configuration nor claim integrated recovery readiness. Full immutable gate
qualification remains pending. This is an exact-candidate scope verdict only.
Only this report was appended; no source edits, builds, cleanup or remote actions
were performed.

## Final v7 synchronous-cost correction and exact pin

Verified the new frozen tree
`bb8699fdfbc4ca88fa6c0e816e189af80e560efd`, unchanged parent
`06dd7e237eb5a343dcc6a6145e775f495e6c30de`, all 58 listed file hashes, all 31
increment paths, index/tree equality and working/index equality. Independently
recomputed complete source patches:

- Increment SHA-256:
  `9414d2b00491eedfd76e52e212459f92735963e46a6eb0d3c9f79b444e4693a2`.
- Cumulative against upstream `b52144955b629314a000b1fe49eeea97fa3d0c5c`, SHA-256:
  `7f2cf1d64419f8968e311f04b4b132bed8ee05e5e94be995dcf083b10dd9f8aa`.

Only projection execution and its metrics/lifecycle tests differ from the previously
reviewed `5a8f4f67` tree. Read `STREAMSOURCE-PROJECTION-COST.md` and inspected both
execution branches, shared stream helpers and the new controlled input-channel test.
No scope blocker was found. Removing measured synchronous-path overhead belongs
to qualifying the new operator; it does not create another scheduler or change
the overall pipeline architecture.

The direct synchronous poll path shares input acquisition, contiguous-run extraction,
projection and stream-owned baseline metrics with asynchronous execution. It retains
state on Pending and releases it on input or expression failure and EOF. The async
branch preserves per-poll compute timing around actual asynchronous work. Marker
ordering, output accounting and the previously reviewed fallible payload constructors
remain part of the same projection contract.

The independent channel test exercises registered wakeup, returned data, upstream
failure, buffered-input release, terminal timestamp and fused subsequent polls.
That is appropriate verification of the new scheduling seam rather than unrelated
concurrency coverage. The source maintains observability instead of reducing work
by deleting instrumentation.

The lead reports 53 focused tests and an optimized eight-cell three-way comparison
passed. The stored performance result identifies the reviewed tree and records
source stability and exact ordered outputs. This reviewer did not run the tests
or measurement. The reported no-marker median ratios, 1.0303 and 0.9580 versus
ordinary projection, remain shared-host diagnostics. Mixed-marker cost remains
explicitly unresolved, so this source-scope verdict supplies no production
performance or integrated recovery claim.

This pin supersedes earlier source-scope pins for the current candidate while
retaining their review history. The full SDP, existing Extensions, Comet, fencing,
configuration and performance objective remains active. Full immutable qualification
is pending. Only this report was appended; no source edits, builds, cleanup or
remote actions were performed.
