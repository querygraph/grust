# Source participation regression review

## WIP assessment and scope

No concrete introduced correctness regression identified in the inspected compiler,
source-occurrence and zero-demand changes. This is a review of work in progress,
not a frozen-candidate verdict. A pre-compilation entrance coverage gap remains
to be settled, and final cumulative source and execution reviews remain required.

Inspected `/Users/alexy/src/sail/tmp/streamsource-participation-20261105-327572240`
at starting HEAD `327572240365e2507f348ee92bc009cbfc67abe9`, against upstream
`b52144955b629314a000b1fe49eeea97fa3d0c5c`. Independently confirmed the starting
tree has no difference from previously reviewed projection tree
`bb8699fdfbc4ca88fa6c0e816e189af80e560efd`. Reviewed the cumulative path inventory
and the current delta, including the untracked compiler and preparation modules.
Prior foundation, projection and Comet reviews apply only to their unchanged
contents. Source and test writers were still active during inspection.

Read the full saved request, predecessor constraints, AGENTS.md, LAKESAIL.md,
SHEHAB.md, CLARITY.md, WRITING-RULES.md and source development/Rust/Python review
instructions. No builds, tests, source changes, cleanup or remote actions were
performed. Only this assigned evidence file was written. Full SDP, recovery,
mandatory fencing and both Extension routes remain active obligations.

## Compiler boundary preserves the intended ordering

`crates/sail-plan/src/optimizer.rs:35` follows the pinned DataFusion 55.2.0
SessionState orchestration: configured analysis runs once, followed by mandatory
streaming preparation and then configured optional optimization. The ordinary
batch branch returns through the same analyzer/optimizer APIs. Independently
verified the retained upstream source hash, exact method extraction and initial
copy in `review-logs/compiler-ownership/initial-copy.json`. Final comparison
against the frozen owned routine remains an evidence requirement.

`streaming/preparation.rs:12` receives the actual optimizer context, preserving
query timestamp and configuration. The three audited rules execute directly
with their declared traversals. Neither optional `max_passes=0` nor
`skip_failed_rules=true` can bypass this phase. The bounded three-round loop
limits preparation work without enabling unrelated optional rules.

The main-input shape check matters: inspected DataFusion OptimizeProjections
can replace a global aggregate with no required aggregate expressions by a
one-row empty relation. Unsupported main-input shapes therefore skip preparation
and reach the streaming rewriter's refusal. Bounded expression subqueries remain
outside that admission check, preserving their existing scalar-aggregate path.
Stream-bearing expression subqueries are inspected before simplification and
receive a named refusal. Recompiling an already lowered graph detects no remaining
raw source scan and avoids lowering the wrappers again.

Both the production execution path at `sail-plan/src/lib.rs:49` and explain's
collection path at `sail-plan/src/explain.rs:303` invoke the same preparation
function. Final tests must establish equivalent success/refusal behavior through
both entrances, including optimizer settings and analyzer invocation counts.

## Pre-compilation entrances remain an explicit coverage gap

Three existing Sail resolver paths collect a DataFusion dataframe before the new
main compilation helper can run:

| Source location | Work performed before the boundary |
| --- | --- |
| `crates/sail-plan/src/resolver/query/time_travel.rs:233` | Evaluate a scalar used by time travel |
| `crates/sail-plan/src/resolver/query/pivoting.rs:227` | Infer distinct pivot values |
| `crates/sail-plan/src/resolver/query/stat.rs:386` | Collect distinct crosstab values |

Time-travel validation checks columns, correlation and volatility, but the
inspected code has no streaming-source check. These are existing mechanisms,
not an established regression caused by the patch. They nevertheless precede
the promised mandatory boundary. Before claiming all Sail entrances are protected,
prove stream-bearing inputs are refused or prepared there, or retain a precise
documented limitation with a control. Preserve valid bounded eager evaluation.
This concern was sent to the implementation owner; no experiment was run here.

DataFusion's own PREPARE path at `execution/context/mod.rs:727` optimizes before
storing its input, and EXECUTE substitutes parameters later. Inspection found no
Prepare/Execute command in Sail's current spec/resolver surface. Treat this as
the documented bare-DataFusion boundary, rather than adding unrelated SQL command
support. Do not infer coverage from the newly exported Sail helper alone.

## Identity, schemas and cancellation

The source wrapper's new `Arc<()>` occurrence token compares and hashes allocation
identity consistently. A clone keeps its token, while separate construction gets
a separate token even for the same provider and scan options. Normal explain
display exposes no pointer. This is in-process optimizer identity, not durable
source identity. Final tests should cover equality, hash/ordering consistency,
rebuilding and two actual scans through a self-union.

The collector restores the qualified payload fields and schema metadata directly
after validating the encoded schema. This avoids losing qualifications when the
collector moves into the logical optimizer's input. Its child-replacement method
rebuilds that schema. Marker columns remain excluded from public output.

`StreamLimitExec::execute` checks zero fetch before child execution or polling.
It returns an empty stream with the encoded schema. This implements zero consumer
demand, not source exhaustion or a final durable checkpoint. Positive-fetch
behavior remains unchanged and retains its previously documented completion
limitations. Counter-based tests must verify zero child execution as well as zero
polls, including an input whose execution itself would fail.

## Compatibility and verification obligations

The retained baseline summary contains 32 observations for 26 distinct case
names. It distinguishes executed row matches, errors and explain-only outcomes.
Preserve the actually admitted limit arithmetic, aliases, temporary views,
self/bounded unions, scalar projection/predicate, bounded scalar aggregate and
ordinary batch cases. A false predicate that erased an unsupported source-bearing
aggregate/join/window is evidence of the existing bug, not a supported behavior
to retain. Explain-only outcomes must not become execution passes in the report.

Inspected Spark 4.2.1 commit `617618396087429b5627a86ce933bb0f5d6645cb`,
`Optimizer.scala:2043`: PruneFilters gates false/null elimination on streaming
children. This is narrow source evidence for the participation distinction;
no JVM parity was executed. Separately inspected fetched upstream
`5411f84330e8172acb22dd477044f42c07fcc2e5` and its 14-file CASE/IF/common-type
change inventory. It is outside the current parent and has not been rebased into
this candidate; do not attribute its coercion repairs to this increment.

Final controls should exercise all marker kinds and later source errors under
false/NULL predicates, unsupported shapes hidden by constants, exposed views,+nested expression subqueries, repeated compilation, zero demand, and same-source
occurrences. Check actual requested projections, exact/inexact pushed filters and
materialized bytes, not just retained wrapper names. Run configured production
rules and worker reconstruction, with ordinary batch controls and the existing
public scalar-subquery corpus. No runtime, performance, package or recovery
readiness claim follows from this WIP source inspection.

## Frozen candidate v1 review

**Source verdict: no unresolved introduced correctness regression identified.
The eager-execution coverage finding above is closed for the identified Sail
entrances. Public/native, full-gate and planning-cost qualification remain pending.**

Independently regenerated both binary diffs, checked all 77 recorded file hashes,
verified the 24 increment paths and confirmed tracked source equals this tree:

| Item | Verified value |
| --- | --- |
| Candidate tree | `0eee4fd9d9e34a28f3cea54eb6a2e80843c64bae` |
| Starting HEAD | `327572240365e2507f348ee92bc009cbfc67abe9` |
| Upstream base | `b52144955b629314a000b1fe49eeea97fa3d0c5c` |
| Increment SHA-256 | `6ef125ea78c0b7ad8e86e61d4c14330d0f783ed2b6cd4a6b155c03d3a775f231` |
| Cumulative SHA-256 | `4672c5700077d505a417a6613d9002cbab56f8dc1ccb654ba65379b67d818c83` |

Reviewed all increment source and tests in full cumulative context, carrying
forward prior reviews only for identical base contents. The lockfile change adds
the existing async-trait dependency for logical-plan tests without changing
resolved versions. The new upstream CASE/IF work remains outside this candidate.
Independently checked the final owned-compiler comparison hashes and method
extract; its changes remain the public-accessor adaptation and mandatory
preparation between analysis and optimization, with license/imports/attribution.

### Earlier boundary finding resolved

`streaming/preparation.rs:12` now supplies a shared named refusal before eager
evaluation. Time-travel scalars, inferred pivot values, crosstab values and tail
counting invoke it before collecting. `sail-plan/src/lib.rs` also guards raw
CreateMemoryTable and Prepare before delegating their side effects to DataFusion.
The boundary tests enter all six paths, assert no stream scan, and retain bounded
positive controls. The time-travel fixture additionally confirms that the terminal
table is not opened on refusal. This closes the specific source gap rather than
claiming control over bare DataFusion APIs.

Source discovery now recognizes lowered wrappers too. Preparation checks hidden
expression subqueries before its already-lowered early return, so lowered sources
cannot evade that refusal. Generic subquery traversal covers scalar, EXISTS, IN
and quantified comparison forms; controls include both ANY and ALL. A shared
extension classifier prevents preparation from invoking unknown extension
projection hooks before the rewriter refuses the shape. The positive hook control
establishes that its zero-hook streaming assertion reaches a meaningful boundary.

### Optimization and participation contracts

The fourth preparation rule restores common-expression elimination before
projection becomes opaque to ordinary batch optimization. It uses the same
DataFusion rule, actual query context and bounded direct traversal as the other
three preparation rules. Inspected the retained counterexample: early lowering
initially increased one immutable call over four rows to three calls over twelve
rows. The restored probe records one call/four rows for both paths. The candidate
controls compare exact output, source scan count and markers, preserve three
volatile calls, and reject evaluation outside a conditional's selected domain.
This supports that specific work-sharing repair, not a general cost-neutrality
claim for every expression.

The marker tests execute through configured Sail analysis and logical/physical
optimization, including disabled optional passes and skipped optional failures.
They inspect all four marker kinds in order, later source failure, exact/inexact
pushdown residuals, requested columns and materialized bytes. Empty projections
retain positive row counts without materializing unused payload. Separate provider
occurrences execute twice. The occurrence identity and zero-demand tests retain
their failing parent controls and passing restored runs; counters establish that
zero demand neither executes nor polls the child.

The corrected raw-view control explicitly constructs and asserts a raw ViewTable
scan. Its complementary high-level scan demonstrates successful automatic view
exposure and preserved markers. The original auto-inlined fixture failure remains
retained as a fixture applicability error, not a product regression or a weakened
assertion. Ordinary batch and bounded eager behavior remain positive controls.

### Evidence and limits

Inspected `affected-tests-v4.log`: 217 affected tests passed, with one skipped.
The identity/limit control logs show two parent failures followed by two restored
passes. These are lead-produced execution records, not tests run by this reviewer.
The preliminary public run failed setup because `pysail._native` was unavailable;
its 38 setup errors establish no public query pass or query-semantic failure.

Final native/public verification, the immutable whole gate and planning/execution
cost measurement are still required. Keep the prior material mixed-marker
performance qualification open. This source verdict does not establish durable
source identity, checkpoints, distributed recovery, fencing or Extension package
integration. No builds or source edits were performed. Saved request and governance
readings remain current without intervening compaction; only this report was
appended.

## Frozen candidate v3 review

**Source verdict: no additional introduced correctness defect identified in
the final delta. Qualification remains open for the full gate and measured
planning cost. The retained same-alias wrong-result case is not a pass.**

Independently regenerated the complete binary diffs, verified all 77 recorded
file hashes against both Git objects and working files, and checked the full
77-path cumulative inventory and 24-path increment inventory. Tracked working
files equal the frozen tree. HEAD remains the starting commit; this is a tree
review, not a claim that the candidate has been committed or gated.

| Item | Verified value |
| --- | --- |
| Candidate tree | `c1e9563dec7527ed11c2e2bf5476816229317a93` |
| Starting HEAD | `327572240365e2507f348ee92bc009cbfc67abe9` |
| Upstream base | `b52144955b629314a000b1fe49eeea97fa3d0c5c` |
| Increment SHA-256 | `cddf405cb8205cfce54b14f97190b135bcd8b843f79724a8ffc90eb0b756694c` |
| Cumulative SHA-256 | `28c0c0b0400fc61662667d08d878ff629ca4a3b303c4637f6c3c5cbf3437c066` |

Reviewed the complete v1-to-v3 delta in cumulative context. The sole production
change moves the `Ordering` import. Three fixture files replace panicking
`expect` calls with propagated test errors. Missing expected errors, poisoned
locks, wrong array types, invalid timestamps and unordered identities still fail
their tests. Expected rows, marker order, schemas, scan counts, materialized
bytes and refusal messages are unchanged. The existing eager-boundary finding
remains closed within the stated Sail compiler API.

`sail-session/src/streaming_participation_tests.rs:279` now tests complete
compiler re-entry as well as preparation-only re-entry. It compares the
recompiled plan and executes that plan, covering analysis and optional
optimization on already-lowered nodes. This strengthens the fixture without
changing runtime behavior. Re-read the owned compiler, preparation and source
identity implementations; their contracts match the earlier source review.
The other cumulative foundation, projection and standalone Comet contents are
byte-identical to the previously reviewed candidate and retain its limitations.

Inspected lead-produced execution evidence: public v3 reports 38 passed and a
4.2.1 server version; preparation-bypass controls report two failures followed
by two restored passes. The 217 affected passes and one skip remain the earlier
pre-lint-cleanup run, not a newly executed v3 full gate. The preliminary 38
native-module setup errors remain historical failures and are not erased.

The newer same-alias diagnostic executes direct analyzed, old late-rewrite and
new mandatory-compiler paths. At depth 12, direct execution returns 13 through
16, while both old and new return 2 through 5 for batch and streaming. This
narrows the failure to behavior shared by the compared optimization paths; it
does not identify the faulty rule, prove an upstream-only cause, or establish
correctness for that query. Preserve the failed fixture and investigate it
separately from timing. Unique-alias planning v3 cells match all three paths;
they do not replace the failed same-alias cells.

The recorded shared-host debug planning medians are new/old 1.0074 and 1.0034
for batch depths 0 and 12, and 1.6603 and 0.9416 for streaming depths 0 and 12.
These measure analysis, logical optimization and event lowering, excluding
physical planning and execution. The shallow streaming increase requires an
explicit performance disposition; neither the deeper result nor the small
batch differences dismisses it. Prior mixed-marker execution cost remains
separately unqualified. No production throughput, recovery, fencing or package
integration conclusion follows.

After compaction, reread the saved request, literal continuation request,
AGENTS, LAKESAIL, SHEHAB, CLARITY, WRITING-RULES and applicable source
instructions. No builds, tests or source mutations were performed by this
reviewer. Only this report was appended.

## Frozen candidate v4 confirmation

**Source verdict unchanged: no additional correctness defect identified in
the declaration-only delta. This is a local reference review, with the full
gate and previously recorded performance qualifications still open.**

Independently verified all 77 hashes against tree objects and working files,
the complete cumulative inventory, all 24 increment paths and both regenerated
binary diffs. Tracked working files equal the candidate tree.

| Item | Verified value |
| --- | --- |
| Candidate tree | `1501e3dcaf84158319a99fd4c3122c2dcb84bfc1` |
| Starting HEAD | `327572240365e2507f348ee92bc009cbfc67abe9` |
| Upstream base | `b52144955b629314a000b1fe49eeea97fa3d0c5c` |
| Increment SHA-256 | `2bc3f0275441454387ed32baa8764642bf4f35edef299f63dc796b65ed4aea6d` |
| Cumulative SHA-256 | `e4f922d5c38697aa487fe256d9b1885227bbe506e600500a30be9e9e9b978b1a` |

The complete v3-to-v4 diff contains only scoped lint expectations and explanatory
comments in `sail-plan/src/lib.rs` and the eager-boundary fixture. They permit
the raw DataFusion command types needed to inspect bypass attempts and the raw
catalog read needed for the bounded positive control. No runtime expression,
test assertion or expected outcome changes. Earlier cumulative source reviews
therefore continue to apply to identical executable logic.

Inspected the successful affected Clippy log separately from its retained failed
predecessors. This is not a full-gate result. The same-alias wrong results,
planning ratios and mixed-marker execution qualification remain exactly as
recorded above. No production-readiness claim follows from this confirmation.
Reread the request, continuation and governing instructions for this review;
performed no builds, tests or source changes. Only this report was appended.

## Frozen candidate v5 confirmation

Verified all 77 file hashes against both Git objects and working files, the
24 increment paths, the complete cumulative inventory and regenerated binary
diffs. Tracked files equal this tree; HEAD remains the starting commit.

| Item | Verified value |
| --- | --- |
| Candidate tree | `f71f8c5c97b08baa0c7f0f914ea7a2e24d150622` |
| Starting HEAD | `327572240365e2507f348ee92bc009cbfc67abe9` |
| Upstream base | `b52144955b629314a000b1fe49eeea97fa3d0c5c` |
| Increment SHA-256 | `15fd96913eecd7d1d1e64fd1083d12bc34630a13c93802541d2cd14bb73941c7` |
| Cumulative SHA-256 | `0b71c28974776dedaf643028bf12cc7959a0856b751db223b883393818e3d59a` |

The entire v4-to-v5 delta wraps the attribution label in inline code at
`sail-plan/src/optimizer.rs:33`. Independently compared the executable method
bytes: unchanged. No new correctness finding; previous cumulative source
verdicts and limitations apply without modification.

Inspected the retained precommit receipt: v4 passed its fixture and format
steps, then stopped with Rustdoc exit 101 before a source commit. The subsequent
Rustdoc log records successful completion. Neither record establishes a complete
v5 gate. Same-alias wrong results, shallow streaming planning cost and prior
mixed-marker qualification remain open as recorded above. This is an exact-pin
local source confirmation, not production readiness. Request and governance
readings remain current without intervening compaction. No builds, tests or
source changes were performed; only this report was appended.
