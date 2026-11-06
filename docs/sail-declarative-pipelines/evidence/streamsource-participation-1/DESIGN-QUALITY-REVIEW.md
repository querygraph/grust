# Preserve real streaming source participation

Reviewed 2026-11-06T04:38:08.515592+00:00.
Starting source `327572240365e2507f348ee92bc009cbfc67abe9`; upstream base
`b52144955b629314a000b1fe49eeea97fa3d0c5c`.
This is a first-principles design assessment before dependent code, not an
implementation or runtime verdict.

## Required contract

Data emptiness and control participation are different facts. WHERE FALSE can
eliminate every data row while the source still owes ordered checkpoint/watermark/
end markers, errors and progress. Remembering a Boolean streaming flag after
optimization cannot reconstruct the erased source, and refusing this previously
admitted filter is not the requested repair. The actual execution path must retain
and drive the source according to its selected finite/live contract.

## Recommended phase boundary

Prefer analyzing and structurally normalizing the query, then rewriting admitted
streaming operations to existing flow-aware logical nodes before source-pruning
optimization. Optimize the protected event plan afterward. Keep ordinary batch
planning on its established route. This extends existing Sail components rather
than introducing a second execution graph solely to repair a disappearing scan.

The current resolver executes logical commands, calls SessionState::optimize and
only then detects streaming. DataFusion's optimize combines analysis and optimization.
Its EliminateFilter/EliminateLimit/PropagateEmptyRelation family can therefore remove
a stream before Sail wraps it. The existing StreamingRewriter already provides
StreamSourceWrapper, StreamFilter, StreamProjection, StreamLimit and collector nodes.
Those nodes express the semantic boundary that should precede data pruning.

Use an explicit analyzed-plan phase and its public optimizer rather than casually
calling the combined analyze-and-optimize routine twice. Audit the minimal structural
normalizations required by the rewriter. It currently expects subquery/distinct
normalization and literal limits; moving it earlier without those prerequisites
would replace the source-erasure bug with rejected or misbound valid queries.
The normalization phase must not be full optimization under another name. The
resolved expression simplifier mainly rewrites expressions; pruning passes remain
a separate risk. Existing unsupported streaming operators are not made supported
merely by preserving their source.

## Why the alternatives cost more

Owning source-aware variants of every pruning rule would preserve more early data
optimization, but the affected behavior is distributed across filter elimination,
zero-limit elimination, empty propagation, unions and pushdowns. Guarding just one
rule misses the same erasure through another path. A growing family of patched
optimizer rules is a larger maintenance burden than establishing the correct
semantic phase boundary. If a specific post-rewrite rule proves unsafe, isolate its
counterexample and evaluate narrow ownership then.

A source-participation graph independent of the pruned data graph is a reasonable
future checkpoint architecture, but not the smallest repair here. It needs stable
source identity, shared scan ownership, fan-out, demand routing and control/data
alignment. Reopening or polling the source twice is not equivalent. Existing event
nodes can keep the original source in the actual execution graph now, while later
checkpoint work gives it stable distributed control identity.

## Discovery and command caveats

Early discovery must inspect expression subqueries as well as ordinary plan inputs.
Verified DataFusion logical-plan TreeNode::apply_children visits inputs only, while
apply_subqueries is a separate API for Exists/InSubquery/SetComparison/ScalarSubquery.
The current plan.exists-based detector alone is therefore insufficient before
normalization. An unsupported streamed subquery needs an explicit capability
boundary; it must not be silently classified as an ordinary batch plan and erased.

SessionContext::execute_logical_plan also has command-specific optimization, including
PREPARE's stored input. Preserve command execution exactly once, with its existing
catalog/session effects. Do not assume a new resolver phase automatically protects
sources already optimized inside command handling. State and test the selected
entry-point boundary before claiming coverage of commands, prepared statements or
all programmatic planning callers.

Event-aware extension nodes are not a blanket proof against every generic optimizer
rule. Check the production rule sequence on the rewritten graph and preserve actual
source identities/counts. StreamSourceWrapper equality/hash currently omit the source
object itself, so distinct same-schema sources need a nonmerging control before
claiming source-identity preservation under any sharing transformations.

## Zero output and finite demand are different

WHERE FALSE over a live source remains live; it must not acquire a bounded empty
collector merely because no data rows can pass. A bounded source can finish after
its real source completion and leave an empty result. LIMIT 0 is an explicit
finite-demand/cancellation boundary and requires a separate lifecycle decision.

The current StreamLimitState forwards markers but closes only after a later data
batch fails its fetch decision. With fetch zero and an empty batch, the first
condition fetch >= batch.num_rows is true, so it emits the empty batch and does not
close. A false-filtered live source can therefore keep LIMIT 0 alive indefinitely
once early rewriting exposes this path. Its existing TODO also acknowledges missing
end-of-data and final-checkpoint handling. Preserving the node is not proof of
proper finite cancellation or durable completion.

Define when a zero-demand consumer constructs/opens the source, drops or cancels
it, and which terminal guarantee it reports. Do not confuse local early stop with
having observed a source end or committed a final checkpoint. Collector retraction
handling remains a separate known obligation, not a guarantee supplied by this phase
repair.

## Discriminating acceptance evidence

Require actual source scan/execute/poll counters, ordered marker identities and
source errors through constant-false and contradictory predicates. A plan name or
is_streaming flag is insufficient. Test a bounded source ending with zero data and
a live source that remains pending while still producing controls. Drive the internal
encoded path before collector marker removal, then exercise the public sink path.

Include source branches inside unions, qualified aliases, literal-limit folding,
empty finite inputs and distinct same-schema source instances. Verify the real
analyzer/logical/physical optimizer sequence and worker reconstruction. Use controlled
input and cancellation rather than wall-clock hangs. Include LIMIT 0 after a false
filter and distinguish its selected cancellation contract from zero-output live
participation. Preserve ordinary batch empty-folding as an independent control.

No runtime behavior was executed by this reviewer. Source inspection found no diff
between the pinned upstream base and fetched 5411f8433 in the selected streaming
rewriter/lib, logical/physical streaming directories and session optimizer. This is
a narrow relevant-file comparison, not qualification on the new upstream head.

## Compliance

Read the full saved request, continuing objective and human-review steering, plus
applicable repository AGENTS, LAKESAIL, SHEHAB, CLARITY, WRITING-RULES and source
instructions. No product source edits, builds, tests, cleanup or remote actions
were performed. Only this assigned report was written. Final decisions, source
implementation and immutable cumulative qualification remain pending.

## Refined phase placement: final Sail analyzer rule

Assessed 2026-11-06T04:40:06.547343+00:00 before code.
A final AnalyzerRule registered after Sail's other session analyzer rules is a
stronger minimal placement than a resolver-only orchestration fork. It establishes
the semantic boundary for ordinary SessionState optimization, Explain and
programmatic query-planner entry points. Existing name/type/input-file analysis
can finish first; lowering then protects actual sources before pruning rules run.
It should preserve already lowered graphs idempotently and audit mixed/raw
subquery cases rather than assuming every caller begins with the same plan shape.

This placement does not remove every earlier command caveat. PREPARE's command
handler invokes the optimizer directly and does not invoke analyzer rules in that
step. Coverage of that path requires a separate explicit hook or tested admission
contract. Removing every post-optimizer safeguard without covering it would leave
a bypass. The final analyzer should not be described as command-wide protection
until the relevant handlers are included.

For in-process optimizer occurrence identity, prefer a clone-preserved Arc<()>
token with pointer-based equality, hash and ordering. Arc's allocation includes
its reference counts even for a zero-sized payload, so distinct live allocations
have distinct addresses; cloning preserves the allocation. This avoids global
atomic sequence state and random UUID generation. Comparing only underlying
source Arcs would conflate multiple occurrences of one provider.

The token needs consistent pointer semantics for PartialOrd as well as Eq/Hash;
Arc<()> value comparison itself sees only unit values and would not supply that
identity. Keep it out of human display. It is local logical occurrence identity,
not a persistent source identity or a restart-stable checkpoint identifier. The
latter still belongs to the full source/recovery contract.

The selected shape should also define literal-limit preparation before lowering
and zero-demand cancellation, preserving the distinction from a live false
filter. Actual source counters/control output and ordinary batch controls remain
the acceptance boundary. These design recommendations do not establish working
code; the lead owns the plan, discriminating experiments and dependent changes.
No source edits, builds or tests were performed by this reviewer.


## Preserve scan pushdown before the event boundary

Assessed 2026-11-06T04:49:59.923593+00:00 before dependent code. Reread the saved full request and
AGENTS, LAKESAIL, SHEHAB, CLARITY and WRITING-RULES after context compaction.
Read the complete current STREAMSOURCE-PARTICIPATION.md. No source edits,
builds or runtime tests were performed.

Early lowering alone loses an existing optimization opportunity. The opaque
source wrapper has no logical child to which ordinary projection optimization
can propagate required columns. Stream projection also conservatively retains
its input columns. A wide source can therefore materialize columns that the
ordinary scan projection would have avoided. Source retention must not excuse
that introduced cost.

Recommend a deliberately bounded preparation phase using DataFusion 55.2's public
PushDownFilter and OptimizeProjections rules before lowering, after establishing
that every source-bearing relational path has an admitted implementation.
This preserves existing filter/projection policy without owning another column
liveness engine. The preparation phase must use only the stated rules, not the
session's full optimizer, and state their order, traversal and repetition behavior.
PushDownFilter declares top-down traversal; OptimizeProjections owns its own
recursive traversal and also visits uncorrelated expression subqueries. Calling
only a rule's rewrite on the root does not necessarily run the advertised pass.

Inspected production implementations, not only searches for EmptyRelation.
PushDownFilter can merge filters, distribute a filter over union inputs, rewrite
aliases/projections and push eligible expressions into scan filters. These paths
retain the input scans. It keeps predicates containing scalar subqueries and
volatile expressions outside provider pushdown. Exact pushdown removes the
residual predicate; Inexact retains it. Its simplify_predicates helper reduces
redundant comparisons and does not itself replace the scan. OptimizeProjections
rewrites required columns on scans, merges/removes projection nodes, reconstructs
other admitted inputs and preserves union branches. Its input-discarding empty
global-Aggregate branch is outside the currently admitted source-bearing graph.
The audit is pinned to dependency version 55.2 and must be revisited if these rules
or admitted source-bearing node classes change.

Admission and discovery must precede this preparation, including expression
subqueries. Do not confuse an ordinary bounded scalar-subquery Aggregate with
an unsupported Aggregate consuming the stream. Rejection of the former would
regress previously working queries. Likewise, pruning unused expressions must
not erase an undiscovered streamed subquery before the participation check.
Existing successful public query cases must retain results and schemas; existing
unsupported-streaming failures must stay distinct from queries that only happened
to succeed because batch pruning hid their unsupported operation.

The alternative of extending event-aware projection pruning remains coherent,
but requires defining how parent column requirements change an opaque source
leaf, remap source indices and preserve encoded control columns. Reimplementing
those policies now duplicates the dependency's existing required-column logic.
Dependency ownership remains available if a concrete unsafe public-rule behavior
appears; no behavior change to those dependency rules is currently required by
the selected narrow phase. A separate source participation graph still introduces
shared polling and control routing without solving scan pruning by itself.

Require source scan-argument observations as well as source counts: a narrow
projection over a wide schema, zero payload columns with nonzero row counts,
qualified aliases, union branches and repeated preparation. Exercise Unsupported,
Exact and Inexact source filter capabilities. The Exact case is especially
important because no residual filter remains; the source must apply predicates
to data while preserving control markers and errors. A retained node or correct
scan argument does not alone prove that event contract. Use the actual configured
post-lowering optimizer and codec in these controls. Verify source participation
for literal false and contradictory predicates, and measure the wide-source case
against the unchanged baseline before readiness. None of these runtime or
performance properties is claimed from this source-only assessment.


## First logical rule: stronger context, conditional semantic boundary

Assessed 2026-11-06T04:51:12.857208+00:00, still before code. A first logical PrepareStreaming rule
has a material advantage over a final analyzer rule: OptimizerConfig supplies
the actual query execution timestamp, options and alias generator. The public
expression simplifier consumes that timestamp. Inventing another timestamp in
analysis would change stable time-dependent bounds or pushed predicates. The
configured logical rule also reaches DataFusion PREPARE's direct optimizer call.
With ApplyOrder::None it can discover, prepare and lower the whole graph before
ordinary pruning. These facts supersede the earlier preference for analyzer
placement if the semantic bypasses below are closed.

Sail's existing SimplifyExpressions wrapper first delegates to DataFusion's
expression pass and then applies exact numeric comparison coercion. Inspected
the production wrapper and DataFusion optimize_internal: expression mapping and
Aggregate-shape repair retain the admitted streaming relational input. Reusing
that owned wrapper before PushDownFilter and OptimizeProjections preserves Sail's
numeric semantics and actual optimizer query context. This does not authorize
the other full-optimizer pruning passes before lowering.

Two concrete configuration caveats prevent unconditional endorsement of the
logical-rule boundary. DataFusion optimize clones/restores a plan and skips a
rule's error when optimizer.skip_failed_rules is true. A PrepareStreaming named
refusal could therefore be discarded and the raw stream erased by a later
ordinary rule. The outer optimization loop does not execute at all when
optimizer.max_passes is zero, bypassing PrepareStreaming entirely. Inspected
55.2 defaults are false and three respectively; defaults do not prove a contract
for configurable sessions. Before code, select an explicit non-skippable semantic
preparation mechanism or an enforced, observable configuration boundary. Test
both counterexamples. A rule that merely returns an error for those options is
itself skippable under the first option.

No runtime counterexample was executed by this reviewer. These findings follow
from the pinned optimizer's actual error restoration and loop control, and were
sent to the lead promptly. The placement decision remains open pending their
resolution; no readiness verdict is issued.


## Converged boundary: mandatory Sail compilation phase

Assessed 2026-11-06T04:54:18.337527+00:00 before dependent implementation. Prefer a shared mandatory
compiler phase after configured analysis and before configured optimization over
both optional-rule placement and a timestamp-compensating analyzer. This resolves
the concrete preceding caveats without a SessionState fork or global query state.
SessionState implements OptimizerConfig with its real query timestamp, alias
generator, options and function registry. The phase can reuse that exact context.

Inspected actual entrants. resolve_and_execute_plan currently executes logical
commands, obtains the DataFrame's state, calls combined state.optimize, then lowers
streams. Explain's collect_plan_with already calls configured analysis and logical
optimization separately and records their outputs. Both can share preparation at
the analyzed-plan boundary. Keep analysis exactly once, preserve Explain's analyzed
snapshot before preparation and retain physical observer behavior. Bare DataFusion
SessionState entry points have not provided Sail StreamSource compilation: their
ordinary provider scan explicitly refuses an unlowered source. An explicit public
Sail compiler/preparation helper is therefore an architectural boundary, not a
claim that arbitrary stock DataFusion APIs now gain streaming semantics.

The three preparation passes must themselves run mandatorily. Calling a nested
Optimizer::optimize with unchanged options would restore the max_passes=0 and
skip_failed_rules bypasses the new phase is meant to avoid. Prefer public
bottom-up/top-down rule traversal plus the projection rule's owned recursion,
using the unchanged actual OptimizerConfig. Avoid growing a general alternate
optimizer framework for three known passes. Bound and document their ordering
and repetition, and retain literal-limit checks after simplification.

Update previously manual state.optimize-then-rewrite component fixtures to the
same public Sail phase. Require unchanged-batch controls and streamed participation
with max_passes zero and skip_failed_rules true. The optional ordinary optimizer
may do no work or skip a failed optimization, but neither option may bypass source
admission/lowering. Preserve working bounded expression-subquery preparation and
inspect resolver paths that eagerly execute a subquery before the final compiler.
Sail's unsupported PREPARE resolver remains an explicit admission boundary; do not
claim the stock DataFusion command path is protected by this helper or implement a
new command feature merely to broaden that claim.

This supersedes unconditional analyzer or first-optimizer-rule placement advice.
It recommends a technically stronger and smaller boundary based on actual product
entrances and query-context evidence. Actual execution coverage and maintainability
remain subject to the implementation, discriminating controls and cumulative gate.
No product source edits, builds or tests were performed by this reviewer.


## Frozen candidate v1: exact source design review

Reviewed 2026-11-06T05:48:22.433716+00:00. Reread the saved request, current first-principles plan
and applicable governance. Source worktree is
`/Users/alexy/src/sail/tmp/streamsource-participation-20261105-327572240`.
Independently verified parent HEAD `327572240365e2507f348ee92bc009cbfc67abe9`,
index tree `0eee4fd9d9e34a28f3cea54eb6a2e80843c64bae`, all 77 cumulative file
SHA-256 values, all 24 increment paths and the complete cumulative path set.
Regenerated staged binary diffs match the retained patches exactly:

- Increment SHA-256 `6ef125ea78c0b7ad8e86e61d4c14330d0f783ed2b6cd4a6b155c03d3a775f231`.
- Cumulative SHA-256 `4672c5700077d505a417a6613d9002cbab56f8dc1ccb654ba65379b67d818c83`
  against `b52144955b629314a000b1fe49eeea97fa3d0c5c`.

The mandatory shared compiler implementation follows the converged boundary.
Configured analysis occurs once, preparation uses the actual SessionState optimizer
context, and configured ordinary optimization follows the protected flow graph.
The public helper and both Sail execution/explain paths use it. Preparation applies
known rule traversals directly and is independent of optional optimizer iteration
and error-skipping settings. It discovers expression-subquery sources before
simplification, gates preparation on admitted shapes, then produces named refusals
for unsupported source-bearing operations. Known extensions share one classifier
between eligibility and rewriting. The six before-compilation eager/command guards
retain bounded behavior and prevent source evaluation before the mandatory phase.
Bare DataFusion entry points remain explicitly outside this compiler contract.

The added common-expression rule is justified by actual retained counterevidence,
not speculative optimization. The initial probe evaluated 12 rows versus the old
path's four, despite equal results. The retained repaired probe observes four rows
and one call on both paths. Inspected pinned DataFusion production CSE paths retain
source inputs and introduce projection sharing rather than replacing participation.
Focused controls distinguish immutable sharing, volatile calls, conditional partial
evaluation and separate union occurrences. Source pushdown controls inspect actual
requested projection/filter arguments, materialized bytes, Exact/Inexact residual
semantics and every marker kind. Empty payload projections preserve positive row
counts without materializing unused values.

Occurrence equality/hash/order use the same clone-preserved pointer token. The
underlying provider can have two distinct read occurrences. No address enters normal
logical explain formatting, and the contract explicitly disclaims durable identity.
The collector preserves payload qualifiers and metadata, satisfying ordinary
optimizer schema expectations after early lowering. LIMIT zero returns a fused
empty encoded stream before child execution or polling. It reports demand
cancellation rather than source exhaustion or checkpoint completion. Later finite
limit checkpoint lifecycle remains a separate explicit obligation.

Reviewed the cumulative integration with the existing Arrow marker construction,
flow-aware filter/projection, telemetry/codec/public admission and Comet adapter.
The increment does not modify their previously reviewed source contracts. Comet
still uses explicit unsafe trusted immutable admission, process-retained native
code and exact argument/planned output checks; source preservation does not imply
native deployment, durability or resource admission. Existing mixed-marker
projection cost remains an open limitation.

Independently checked dependency ownership evidence: the retained 77-line original
method occurs verbatim in the pinned local DataFusion source, and the initial Sail
copy matches it byte for byte. The retained Sail method equals current source;
regenerating its comparison reproduces the saved diff. Changes are public-accessor
adaptation and mandatory preparation in both branches, plus imports, license,
credit and formatting. This is smaller and more maintainable than a SessionState
fork or a family of source-aware owned pruning rules.

Inspected affected-tests-v4.log: 217 passed with one skipped. The retained unchanged
identity/zero-demand implementation control fails both new tests, and restoration
passes both. These are inspected receipts from the lead, not tests rerun by this
reviewer. Public Python qualification, planning cost and the immutable full gate
remain pending; the earlier native-fixture setup errors are not semantic passes.

Two nonblocking precision findings were sent. The current idempotence fixture
reruns preparation, while the plan claims repeated complete compilation; add a
full-helper control or narrow the claim. Also OptimizeProjections marks a TableScan
transformed even when projection is unchanged, so the change-flag early stop normally
cannot avoid all three preparation rounds. CSE can consequently be extracted again
after projection merging in successive rounds. Measure this planning cost; compare
actual plan equality or run CSE once after earlier rounds only if evidence warrants
that change. This is not a demonstrated result or source-participation defect.

Design verdict for this exact source: no demonstrated source-level architectural
blocker. The implementation preserves actual source execution rather than merely
remembering classification or refusing admitted false filters. Readiness remains
unproven until public behavior, planning/performance and immutable cumulative gates
provide their own receipts. This verdict applies only to the named tree and does
not complete SDP, deterministic CDC, mandatory fencing, typed configuration/Dhall,
distributed recovery or Extensions integration. No source edits, builds or runtime
tests were performed by this reviewer; only this assigned report was appended.


## Frozen candidate v3: final pin confirmation

Reviewed 2026-11-06T06:04:19.691652+00:00. Reread saved REQUEST.txt, literal latest continuation
request `continue`, LAKESAIL, SHEHAB, CLARITY and WRITING-RULES. Applicable
repository instructions and source boundaries remain those recorded above.

Independently verified the complete current staged candidate:

- Parent HEAD `327572240365e2507f348ee92bc009cbfc67abe9`.
- Tree `c1e9563dec7527ed11c2e2bf5476816229317a93`.
- Increment SHA-256 `cddf405cb8205cfce54b14f97190b135bcd8b843f79724a8ffc90eb0b756694c`.
- Cumulative SHA-256 `28c0c0b0400fc61662667d08d878ff629ca4a3b303c4637f6c3c5cbf3437c066`
  against `b52144955b629314a000b1fe49eeea97fa3d0c5c`.
- All 77 cumulative file SHA-256 values and exact path coverage match the snapshot;
  all 24 increment paths match. Independently regenerated binary patches and the
  retained final-v3 patches have the same hashes above.

Read the complete v1-to-v3 delta. The only product source change moves Ordering
into the ordinary import block. Three fixture files replace expect/expect_err with
fallible fixture errors and add full compiler re-entry. Every prior assertion,
marker expectation, scan/execution/poll count and result check remains. New fixture
helpers centralize mutex poison errors rather than duplicating unchecked unwraps.
The complete compilation control reruns configured analysis, preparation and
optimization, compares the full logical graph exactly, then physically plans the
recompiled result. This closes the earlier preparation-only idempotence coverage
finding at source level. The lead reports the two marker/failure controls pass;
this reviewer did not independently execute them.

Inspected the retained public-v3 pytest output and matching receipt: 38 passed,
exit zero, server version probe 4.2.1, full streaming directory plus rate tests.
Earlier setup failures remain separately described and are not relabelled semantic
passes. The fixture-only delta does not change the runtime exercised by this
public binary. The immutable full gate is still pending. Planning-v1's old batch
depth-12 wrong output remains a diagnostic requiring the direct/old/new comparison;
no cause, correctness exemption or performance conclusion is inferred here.
The previously observed three-round preparation behavior and mixed-marker cost
remain subject to their own measurements.

Read the newly published FABLE-REDESIGN-REVIEW.md. Its human-review concerns remain
material: a repository full of individually self-contained documents can still
exceed the reader's time. Keep one founder-facing entry with the concrete source
pruning example, existing Sail fit, chosen compiler boundary, real alternatives
and open questions; make supporting detail optional. A concise commit body should
state the defect and behavior, name the preceding design, identify discriminating
controls and state the durability/distributed exclusions. Do not make that body
an evidence index. Maintainer agreement before upstream architecture adoption is
distinct from the explicitly authorized local reference implementation. No upstream
PR, source push or maintainer contact is authorized by this review.

Final design verdict for the named v3 tree: no new architectural blocker and the
v1 source assessment carries forward. This is source-design review with inspected
receipts, not an immutable integration-gate verdict or completion of the full SDP
and Extensions goal. No source edits, builds, tests, cleanup or remote actions were
performed. Only this assigned report was appended.


## Frozen candidate v4: scoped lint declarations and exact pin

Reviewed 2026-11-06T06:14:29.536043+00:00. Reconfirmed the saved continuing request and governance.
Independently verified parent `327572240365e2507f348ee92bc009cbfc67abe9`, tree
`1501e3dcaf84158319a99fd4c3122c2dcb84bfc1`, all 77 cumulative file hashes and
exact cumulative path coverage, and all 24 increment paths. Regenerated binary
diffs and retained final-v4 patches match:

- Increment SHA-256 `2bc3f0275441454387ed32baa8764642bf4f35edef299f63dc796b65ed4aea6d`.
- Cumulative SHA-256 `e4f922d5c38697aa487fe256d9b1885227bbe506e600500a30be9e9e9b978b1a`
  against `b52144955b629314a000b1fe49eeea97fa3d0c5c`.

Read the entire v3-to-v4 delta. Two import-scoped expected lint declarations admit
the exact raw DataFusion command types needed to guard the pre-compilation eager
execution boundary and exercise it. One statement-scoped declaration permits a
test to read DataFusion's own memory-table catalog after the raw bounded command.
These are justified protocol-boundary inspection/control uses, with adjacent
comments, rather than new use of DataFusion commands for Sail product behavior.
They do not change runtime logic, schemas, assertions or admission. The previous
source verdict and full-compiler idempotence closure carry forward.

Inspected unique-alias planning summary: shallow/deep batch median new/old ratios
1.0074 and 1.0034; shallow/deep streaming 1.6603 and 0.9416. Each admitted cell
matched direct, old and new output/schema before timing. These are debug-profile
shared-host planning ratios, not production throughput evidence. The repeatable
shallow-streaming startup increase is material and remains an explicit local
reference limitation, not a negligible difference or production acceptance.
The same-alias depth-12 comparison still produces expected 13 through 16 directly
and 2 through 5 on both old and new paths. Retain that failure separately without
assigning cause or treating identical wrong results as qualification.

Design verdict for this exact tree: no additional architectural blocker from the
scoped lint delta. Local reference review may retain and disclose its measured
startup cost; production/upstream readiness and full cumulative qualification
remain unproven until their own performance decisions and immutable gate pass.
No source edits, builds or runtime tests were performed. Only this assigned review
was appended; all earlier controls and limitations remain visible above.


## Frozen candidate v5: Rustdoc-only pin confirmation

Reviewed 2026-11-06T06:20:59.972456+00:00; saved request and governance are unchanged. Independently
verified parent `327572240365e2507f348ee92bc009cbfc67abe9`, tree
`f71f8c5c97b08baa0c7f0f914ea7a2e24d150622`, all 77 cumulative file hashes,
exact cumulative path coverage and all 24 increment paths. Regenerated staged
binary patches match retained final-v5 patches:

- Increment SHA-256 `15fd96913eecd7d1d1e64fd1083d12bc34630a13c93802541d2cd14bb73941c7`.
- Cumulative SHA-256 `0b71c28974776dedaf643028bf12cc7959a0856b751db223b883393818e3d59a`
  against `b52144955b629314a000b1fe49eeea97fa3d0c5c`.

The entire v4-to-v5 delta adds inline-code quoting around the CREDIT label in
optimizer.rs so Rustdoc does not resolve it as an intra-document link. Executable
source tokens and tests are unchanged. The pinned attribution URL remains intact.
No new architectural finding; previous source-design assessment carries forward.
The lead reports strict Rustdoc now passes, while the earlier failed gate is
retained and no commit was made. This is not an immutable full-gate verdict.
All material planning-cost, same-alias, mixed-marker and recovery limits above
remain open. No source edits, builds or tests were performed by this reviewer;
only this assigned report was appended.
