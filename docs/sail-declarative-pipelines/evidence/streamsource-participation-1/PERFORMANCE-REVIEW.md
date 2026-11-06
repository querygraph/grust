# Streaming source participation: initial performance review

Read the complete saved request, `STREAMSOURCE-PARTICIPATION.md`, repository
`AGENTS.md`, `LAKESAIL.md`, `SHEHAB.md`, `CLARITY.md`, `WRITING-RULES.md` and
applicable source instructions. Inspected the existing rewrite, source wrapper,
source provider contract and configured planning entry points at detached source
`327572240365e2507f348ee92bc009cbfc67abe9`. This is a plan/source-baseline review;
implementation and final cumulative qualification remain pending. No source edits,
builds or measurements were performed by this reviewer.

## Architectural fit and costs to preserve

Moving event lowering to the final analyzer boundary addresses a correctness
failure that a timing improvement cannot waive. A false filter over a live source
must still carry control markers and source failures. An earlier Boolean discovery
flag alone does not retain executable source participation.

Source discovery adds a planning traversal before ordinary pruning, when more
nodes may still exist. The new pass should remain linear in the traversed plan
and expression/subquery graph where practical. Avoid repeated discovery of each
subtree during lowering or recursively revisiting exposed view plans without a
clear recursion/cycle boundary. Ordinary batch queries also pay discovery cost,
even when their original optimization/execution path is otherwise unchanged.
This cost should be measured rather than described as free.

A reference-counted opaque token per source occurrence is a small local allocation,
with reference clones during plan reconstruction. Pointer identity avoids a global
allocator counter or synchronization registry. Preserve the token through cloning
and use consistent equality/hash/ordering; it must not retain a second source
graph or be confused with a restart-stable identifier. Source objects continue
to be owned through existing plan references.

The limit-expression preparation is narrower than running a relational optimizer
before protection. Reusing analyzed types, configuration and the existing query
time avoids a second semantic evaluation context. Zero initial consumer demand
should return before child execution or polling, with baseline observability and
output schema retained. This avoids waiting for another event from an otherwise
live source without claiming durable completion.

## Source pushdown risk requiring an explicit control

Lowering scans before the optimizer can lose ordinary source column/filter
pushdown. The current wrapper stores scan projection/filter/fetch options but
has no logical inputs or expressions. The streaming projection's
`necessary_children_exprs` requests every input column. Once a `TableScan` becomes
this opaque wrapper, ordinary DataFusion scan-pruning rules cannot discover and
edit its options through the usual table-scan path.

The old late rewrite inherited options from an already optimized `TableScan`.
For an otherwise unchanged query selecting one column from a wide source, the
new boundary could therefore request and materialize every column. This is a
separate possible regression from required source participation. Avoiding unsafe
source erasure does not require abandoning safe payload pruning.

Use a projection-aware counting source with one selected fixed-width column and
one materially wide unused payload. Record the exact projection, filters and
limit passed to `StreamSource::scan`, along with materialized columns/bytes and
source execution counts. Compare the old and new paths for a positive query that
both admit correctly. Preserve zero-column literal projections too. If options
regress, restore event-safe pruning or explicitly constrain and measure the
replacement before claiming parity. This control establishes the regression
without relying on noisy wall-clock timing.

## A bounded comparison method

Keep the prior mixed-marker filter/projection costs explicitly unresolved. This
increment neither changes their batching policy nor establishes its performance.

For planning, compare old and new source pins using equivalent contexts, schemas,
inputs and query graphs. A small four-cell matrix is sufficient initially:
batch versus streaming source, each with a short plan and a modest nested
projection/filter plan. Prepare input logical plans and contexts outside timing;
time analyzer plus logical optimizer, and optionally record physical planning as
a separate phase. Warm both paths, alternate order and retain all samples and
plan displays. Explain and standard execution must share the same boundary.
For source-free cells, assert the resulting batch plan and output still follow
ordinary batch behavior. For source cells, assert scan options and event semantics
as well as data results. Do not count faster incorrect baseline source erasure
as equivalent work or conceal a new supported/refused distinction in a ratio.

For execution, the wide-source positive query and a normal batch control can
compare exact rows, requested/materialized bytes and polling counts before
timing. A false-filter controlled stream should instead prove all marker kinds,
failure propagation and bounded source completion: its old result is a known
semantic negative control, not a valid throughput baseline. `LIMIT 0` needs exact
zero child-execution/poll counters, not a timing race. Two occurrences of the
same provider must retain independent participation.

Use the existing complete baseline/typed metrics for both sides. Retain code and
lock hashes, compiler/profile, host load, commands, every cell and failures.
Shared-host timing supports diagnostic ratios only. No new broad benchmark
framework or production throughput/resource envelope follows from this plan.

## Mandatory compiler preparation and immutable-expression sharing

The current WIP uses a mandatory Sail compiler phase after analysis rather than
an optional analyzer/optimizer registration. It passes the actual session optimizer
configuration and applies three public preparation rules before event lowering:
Sail expression simplification, filter pushdown and projection optimization.
The implementation owner reports wide-source Exact/Inexact pushdown controls
passed, including disabled optional passes. Those are reported results rather
than execution by this reviewer; final cumulative review remains pending.

Another existing optimization needs an explicit control: common-subexpression
elimination. The previous late rewrite inherited this work sharing from the full
logical optimizer. DataFusion 55.2's rule handles ordinary projections and filters
but its extension-node case only recurses into inputs/subqueries. It does not
rewrite the extension's own expressions. Early `StreamProjectionNode` lowering
can therefore hide repeated immutable work, including expensive native functions,
from this optimization. Source inspection found no physical CSE rule that would
generally restore it afterward.

Prepared `review-logs/performance/participation_cse_probe_v1.rs` outside product
source for the implementation owner to run. The ignored integration test uses
one bounded encoded source, four data rows and three aliases of the same immutable
identity function. It compares the old `state.optimize` followed by streaming
rewrite with the new compiler entry point on the same current source tree.
Both must return the exact expected rows. Counters independently record function
invocations and data-row evaluations; the final assertion rejects increased work.
It prints both logical and physical plans. The counter measures implementation
work without a wall-clock or shared-host noise claim. It has not been compiled
or executed by this reviewer, so no runtime regression is yet asserted.

Inspected the pinned public `CommonSubexprEliminate` implementation. Its only
production `EmptyRelation` match is a no-op recursive branch. For admitted
projection/filter nodes, common-expression extraction inserts an intermediate
projection over the original input and preserves its fields. Recovery projections
restore schemas. This is different from input-erasing aggregate/projection
pruning. The preparation graph guard must still exclude unsupported relational
shapes before any rule runs; the rule's own recursion and subquery handling must
not be replaced with an incompatible traversal.

If the counterexample reproduces, adding the public CSE rule as a fourth audited
preparation rule is a plausible narrow correction. Put extraction after rules
that can duplicate or merge expressions, and test their interaction across the
bounded preparation iterations so CSE does not merely get undone before lowering.
Retain conditional-expression, nonimmutable-function and two-source-occurrence
controls. Work sharing must not evaluate conditionally unreachable expressions or
share computations across distinct source identities. Final qualification still
needs actual results on the cumulative implementation, with the previous mixed-
marker performance limitation preserved. No source edits or builds were performed
by this reviewer.

## Executed CSE counterexample and prepared planning probe

Read the implementation owner's `cse-before-v2.json` and complete failure log.
Both paths returned the expected four rows in all three output columns. The old
late-rewrite path invoked the counted immutable function once for four data rows;
the new three-rule preparation path invoked it three times for twelve data-row
evaluations. The work-preservation assertion failed. This is an observed threefold
increase in repeated function work, independent of timing, and requires correction
before readiness. It is not merely a plan-shape concern.

The first probe did not compile because the fixture returned a concrete
`Arc<DataSourceExec>` where the async trait required `Arc<dyn ExecutionPlan>`.
V2 only adds the explicit `Ok(...?)` coercion. The original compile log, both
probe versions and the semantic failure remain separate artifacts; no assertion
was weakened. Execution was performed by the implementation owner, not this
reviewer.

The audited public CSE rule is an appropriate fourth preparation rule, ordered
after projection optimization so its shared intermediate projection survives
event lowering. Its projection/filter transformation retains the original input;
the pinned production `EmptyRelation` match is no-op recursion. Keep the admitted
main-graph shape guard and the actual query optimizer configuration. Independently
added immutable/volatile/conditional tests must qualify function-work sharing and
preservation of conditional evaluation. The original three-rule failure should
remain the negative control rather than being relabeled as an unsupported query.

Prepared `review-logs/performance/participation_planning_probe_v1.rs`, outside
product source and not built or executed. It reuses the corrected bounded-source
fixture and configured Sail session from the CSE probe. Four cells combine batch
versus declared streaming input with zero versus twelve nested projection/filter
layers. All queries are positive and meaningful under both compilation paths;
none relies on incorrect false-filter source erasure.

The owner should pin and retain the source tree, full diff, lock and probe hashes
before execution, then verify unchanged source afterward. Within the same process
and source tree, the probe compares the old full logical optimizer followed by
late event rewriting with the new mandatory compiler entry point. It isolates the
planning-entry change, not every difference between historical branches. Both
schemas and exact collected data are checked outside timing. Physical planning
and execution are also outside timing; they preserve their existing metrics.
The timed region includes analysis, logical optimization and event lowering.

Each cell has warmups followed by seven alternating-order pairs. Each sample
compiles the same prepared logical plan 32 times, retaining totals and the
iteration count. Inputs and session construction stay outside timing. Complete
logical/physical plan displays are retained. If a fixture or semantic mismatch
fails, no timing result qualifies that cell. All cells and ratios, including
slowdowns, must remain visible. Profile and shared-host limits still apply; this
probe does not establish throughput, mixed-marker performance, bounded-resource
admission or end-to-end recovery. No source edits or builds were performed here.

## Frozen v2 cumulative source inspection

Independently verified all 77 cumulative file hashes and the 24-path increment
in the v2 snapshot, staged tree `9f6047eba2df8bdc83fe69be300a021131829add`,
increment SHA-256 `017f008512f88e7a7b7b0e7b52aefb7246d7b12ce5f01a1a2fbd9d044661f37a`,
and cumulative SHA-256 `317d792059a1d9bb1e405f9b835f9df88854738b1ec7b0c46630154c5de0ef3d`.
Reviewed the mandatory compiler, selected preparation rules, source discovery and
rewriting, source-occurrence identity, zero-demand limit, explain integration,
eager-input guards and supporting optimization/pushdown controls. Previously
qualified foundation, Comet and projection behavior remains in the cumulative
source; this increment does not repair their mixed-marker cost limits.

No additional must-fix allocation or synchronization finding was identified in
this inspected implementation. Compilation still uses the existing analyzed
schema, session optimizer configuration, query properties and alias generator.
Batch plans bypass mandatory rule preparation after source discovery. The streaming
preparation loop is bounded to three rounds of four rules and exits when none
changes the plan. CSE runs last. This adds bounded planning work, not a new
execution scheduler or per-row data-path work. The small source-occurrence
allocation is per compiled logical occurrence, with no global registry.

The source-aware preparation restores column/filter pushdown before scans become
opaque. Controlled tests inspect Exact/Inexact residual behavior, requested source
projection and actual materialized bytes, including an empty payload projection.
Thus the wide-source concern has a discriminating structural control, rather
than relying solely on identical final output. The implementation owner reports
these and the restored CSE counter passed; execution was not performed here.
The CSE bypass controls failed twice and restored controls passed twice, according
to the owner's retained evidence. Final immutable qualification remains pending.

The zero-demand limit returns before child execution, preserving the existing
encoded schema. This avoids an otherwise unnecessary open/poll and retains the
distinction between cancellation of demand and durable completion. Occurrence
identity preserves separate reads without cloning source payloads. Eager metadata
and scalar commands explicitly refuse declared streaming inputs rather than
starting an unbounded batch collection. Opaque undeclared providers remain outside
the discovery contract.

## Planning v1 failure and discriminating follow-up

Read `planning-v1.json` and the failing log. The run stopped during validation of
the old batch depth-twelve case: the intended result was 13–16 but observed output
was 2–5. The unchanged assertion correctly rejected the comparison. Retain this
failed run and its partial samples; it does not supply a valid four-cell timing
verdict or a passing depth-twelve cell. At this point the failure is unassigned
between fixture construction and pre-existing optimization behavior.

Source inspection alone does not establish that reusing an alias caused the
problem. In particular, DataFusion's `columnize_expr` handles aggregate/window
output expressions rather than generally rewriting projection aliases. A plausible
alias explanation therefore needs an executed direct-plan control.

Prepared two separately versioned follow-ups without running either. The
`participation_planning_same_alias_diagnostic_v1.rs` retains original alias reuse.
The `participation_planning_probe_v2.rs` gives every layer a distinct name from
`v0` through `v12`. Both print raw and old/new compiled plans before validation,
execute the analyzed graph before optional optimization as an additional oracle,
then print direct/old/new outputs before comparing each with the original
depth-dependent expected values. No expected-value assertion is weakened.

If the direct graph already returns 2–5, fixture construction is wrong. If it
returns 13–16 and the old optimized graph returns 2–5, the old optimizer path has
a demonstrated semantic defect for that graph. Unique aliases may provide a valid
separate measurement fixture while preserving the original failure; they must
not erase or relabel it. Timing qualification waits for executed controls and
an unchanged final source snapshot. The owner is also correcting a test-only
Clippy refusal; the final pin must include that correction. No source edits,
builds or execution were performed by this reviewer.

## Final v3 source and completed planning comparison

Independently verified all 77 cumulative file hashes and 24 increment paths,
staged tree `c1e9563dec7527ed11c2e2bf5476816229317a93`, increment SHA-256
`cddf405cb8205cfce54b14f97190b135bcd8b843f79724a8ffc90eb0b756694c`, and cumulative
SHA-256 `28c0c0b0400fc61662667d08d878ff629ca4a3b303c4637f6c3c5cbf3437c066`.
Direct comparison with reviewed v2 changes only three test-fixture files for lint
corrections. Production compiler and execution code is unchanged, so the v2
allocation, source-work and synchronization review applies to this final pin.

Read `planning-v3.log`, `planning-v3.json` and `planning-summary-v3.json`. The
actual test name is `compare_participation_planning_v2`. Its source hash matches
the separately versioned unique-alias probe, all source receipt hashes match the
final files, and the run reports unchanged source. Direct analyzed, old late and
new mandatory plans matched the independent expected output in all four cells
before timing. The unoptimized build finished and the test passed. Independently
recomputed the four medians and ranges from all 28 recorded paired samples.

| Input | Projection/filter depth | Median new/old planning ratio | Pair range |
| --- | ---: | ---: | ---: |
| Batch | 0 | 1.0074 | 0.9814–1.0292 |
| Batch | 12 | 1.0034 | 0.9942–1.0077 |
| Streaming | 0 | 1.6603 | 1.5728–1.7709 |
| Streaming | 12 | 0.9416 | 0.9259–0.9675 |

Each sample contains 32 logical compilations with prepared input/session objects.
Physical planning and output validation remain outside timing. This same-process,
same-source comparison measures analysis, logical optimization and event lowering
through the two compiler entry paths; it is not an entire historical-branch
comparison. Both paths retain their existing execution observability.

The host is a shared ten-logical-CPU macOS machine, with one-minute load average
6.05 before and 6.76 afterward. CPU isolation and steal measurement were
unavailable. The profile was unoptimized. These are diagnostic planning ratios,
not production throughput, startup latency or a general improvement claim.

Batch controls stayed close to one in these fixtures. The short streaming cell
shows a consistent, meaningful planning overhead around 66 percent. That cost
must be disclosed rather than dismissed as noise. It pays for source discovery
and mandatory source-preserving preparation at compilation; this benchmark does
not show an additional per-batch execution cost. Long-running queries need not
recompile per input batch, but repeated compilation or short-lived queries can
make this startup work relevant. The nested streaming cell being below one does
not cancel the short-cell regression or establish a broad optimization gain.

The deterministic execution controls provide stronger evidence for ongoing work:
the restored CSE path again evaluates four data rows once, and source projection,
Exact/Inexact filters and materialized-byte assertions protect existing pushdown.
Keeping this implementation as a local reference is reasonable with its bounded
mandatory preparation cost recorded. No speculative extra optimizer framework or
weaker participation policy is justified merely to reduce the short-cell ratio.
Any startup tuning should first measure an optimized profile and isolate duplicate
planning work while preserving these guarantees.

## Same-alias defect and invalid-run boundaries

The executed same-alias diagnostic resolves the earlier uncertainty: the direct
analyzed graph returns 13–16, while both old and new optimized paths return 2–5.
The raw graph therefore expresses the intended computation. This is a shared
optimized-path semantic failure, not an incorrect expected-value assertion.
The exact responsible rule is still unassigned. Its raw, logical and physical
plans and unchanged-source failure remain separate artifacts; this query supplies
no valid throughput comparison. Unique aliases form a separate valid fixture
and do not erase the original defect.

The retained `planning-v2` artifact did not execute its intended new fixture:
preserved modification time caused Cargo to reuse the preceding test binary.
It is invalid evidence for that comparison. The subsequent fresh write and
verified actual test name establish the successful `planning-v3` run above.
The final all-outcomes same-alias diagnostic is separately being collected; no
additional cause or passing result is inferred here.

No new unresolved execution-work regression was identified after CSE restoration.
The short-stream planning cost, shared same-alias optimizer defect and prior
mixed-marker gaps remain explicit limitations. They prevent a broad performance
or complete-system readiness claim. The final full immutable gate is pending.
Saved request and governing-file compliance remains confirmed. This reviewer
performed no source edits, builds, tests or timing runs.

## Final v4 pin confirmation

Independently verified all 77 final file hashes, 24 increment paths, staged tree
`1501e3dcaf84158319a99fd4c3122c2dcb84bfc1`, increment SHA-256
`2bc3f0275441454387ed32baa8764642bf4f35edef299f63dc796b65ed4aea6d`, and cumulative
SHA-256 `e4f922d5c38697aa487fe256d9b1885227bbe506e600500a30be9e9e9b978b1a`.
Direct comparison with v3 changes only scoped lint declarations, import grouping
and explanatory comments in `sail-plan/lib.rs` and the boundary fixture. Runtime
code and assertions are unchanged. The final source verdict and measured v3
planning ratios therefore remain applicable through this source-equivalence
boundary; this is not a new timing run.

Read the completed all-outcomes same-alias diagnostic v2 log. Both batch and
streaming depth-twelve graphs return 13–16 before optional optimization and
2–5 under both old and new optimized paths. The diagnostic records all outcomes
before its final failure. This strengthens the shared optimized-path defect
observation without identifying its responsible rule. Those queries remain
excluded from timing qualification; the valid unique-alias four-cell comparison
does not erase them.

No further performance source finding arises from the lint-only delta. Strict
affected Clippy success is reported by the implementation owner; the full
immutable gate remains pending. The short-stream compilation overhead and prior
mixed-marker performance limits remain disclosed. Saved request and governing-file
compliance remains confirmed. No builds, source edits or execution were performed
by this reviewer.

## Final v5 documentation-only pin confirmation

Independently verified all 77 final file hashes and 24 increment paths, staged
tree `f71f8c5c97b08baa0c7f0f914ea7a2e24d150622`, increment SHA-256
`15fd96913eecd7d1d1e64fd1083d12bc34630a13c93802541d2cd14bb73941c7`, and cumulative
SHA-256 `0b71c28974776dedaf643028bf12cc7959a0856b751db223b883393818e3d59a`.
Direct comparison with v4 changes only the Rustdoc formatting of the CREDIT
label in `optimizer.rs`. The executable method and all runtime behavior remain
unchanged. The v3 measured ratios remain attributed to that measured source;
the v4/v5 source-equivalence checks extend their applicability without implying
new measurement or a broader performance claim.

The prior gate stopped on Rustdoc before committing, and its failed record is
retained by the implementation owner. Strict Rustdoc is now reported passing;
the renewed full gate is not inferred complete here. All earlier startup-cost,
shared-host, same-alias-defect and mixed-marker limitations remain in force.
No source edits, builds or execution were performed by this reviewer.
