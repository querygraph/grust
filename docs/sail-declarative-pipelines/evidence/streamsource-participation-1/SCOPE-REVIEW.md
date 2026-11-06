# Scope review: preserve executable stream participation

## Before-code verdict

No scope blocker was found in the proposed participation increment. Read the
complete saved request and the current first-principles plan. The reviewed
`STREAMSOURCE-PARTICIPATION.md` has SHA-256
`5c22b1c99d3c1cdbaf0fb8e0ed5c3faf96b65ec682ce458e413fcdb9301754b5` and 954 words.
Source inspection began at detached parent
`327572240365e2507f348ee92bc009cbfc67abe9` in
`/Users/alexy/src/sail/tmp/streamsource-participation-20261105-327572240`.
Tracked source was clean at the initial inspection. This is a design/baseline
scope review, not a verdict on implemented cumulative code.

## Why the proposed boundary fits

The plan explains the failure without requiring previous work history: a batch
optimizer can replace a false-filtered stream with an empty relation, eliminating
markers and source errors as well as data. Retaining only a streaming Boolean
would not retain an executable participant. Lowering into Sail's existing
flow-event nodes before ordinary pruning is directly related to completing the
StreamSource foundation rather than inventing another pipeline runtime.

The proposed final analyzer rule fits the existing session analyzer registration.
Placing it after type/function and input-file metadata resolution avoids turning
it into a replacement analyzer. Narrow expression simplification for limit/offset
bounds is necessary preparation for existing stream limits; running the whole
optimizer first would undo the source-preservation objective. The plan explicitly
prohibits a new independent query timestamp and requires batch planning to retain
its current path.

Opaque clone-preserved identity per logical source occurrence belongs to this
boundary because protected source wrappers become visible to optimization. Comparing
only schemas/options can otherwise conflate different participants. The plan
correctly limits that token to one in-process compiled graph. It supplies no
restart identity, fencing epoch or durable checkpoint guarantee.

Initial zero demand is a coherent companion repair. An executable graph can retain
its source in planning while a LIMIT0 consumer intentionally never opens it.
The plan distinguishes that cancellation from source completion or a final durable
checkpoint, and requires execution/poll counters rather than a timing claim.
It does not redefine a live zero-output computation as successfully finished.

## Boundaries to enforce during implementation

Actual currently supported scalar-subquery, alias/view and command paths need
baseline/candidate tests. Moving the rewrite earlier must preserve bounded-subquery
preparation and execute commands only once. Broad refusals replacing working
queries would violate the selected preservation contract. Named refusals are
appropriate for genuinely unadmitted streaming operators; their coverage must
come from observed plans rather than an assumed query class.

The prepared-statement audit must inspect actual Sail entrances and support.
A DataFusion optimizer bypass is not by itself a reason to add a new SQL PREPARE
feature merely to complete a coverage list. Record unsupported syntax or opaque
provider boundaries accurately, while testing any supported programmatic entrance
that reaches the same source-participation promise.

EXPLAIN, standard execution and programmatic planning must share the analyzer rule.
Repeated analysis must not create duplicate wrappers or polls. These are direct
integration obligations, not optional follow-up scope. Existing ordinary batch
controls remain required to substantiate the stated unchanged path.

## Full goal and compliance

The increment does not implement source controls, distributed alignment, durable
preparation, change capture, mandatory target fencing, typed configuration/Dhall or
package/worker extension integration. Those full-goal obligations remain explicit
in the request and human-review compendium. The plan includes alternatives,
tradeoffs, discriminating tests and limitations within one self-contained argument,
without agent/session history. No integrated recovery, SDK, production-performance
or executed Spark-parity claim is made.

Read the full saved request and governing AGENTS, LAKESAIL, SHEHAB, CLARITY and
WRITING-RULES. No source edits, builds, tests, cleanup, external messages or remote
changes were performed. Only this report was written. Final cumulative code,
regression and qualification review remains required after implementation.

## Final frozen v2 cumulative source review

Verified all 77 source hashes and 24 increment paths in
`review-logs/candidate-snapshot-final.json`, the unchanged parent
`327572240365e2507f348ee92bc009cbfc67abe9`, working/index equality and exact
index equality with tree `9f6047eba2df8bdc83fe69be300a021131829add`.
Independently recomputed:

- Increment SHA-256:
  `017f008512f88e7a7b7b0e7b52aefb7246d7b12ce5f01a1a2fbd9d044661f37a`.
- Full cumulative source against upstream
  `b52144955b629314a000b1fe49eeea97fa3d0c5c`, SHA-256:
  `317d792059a1d9bb1e405f9b835f9df88854738b1ec7b0c46630154c5de0ef3d`.

No scope blocker was found. Reviewed the complete increment's production changes
and tests against the preceding source, and the cumulative source paths/pins
including the existing foundation, scalar adapter and projection work. No unrelated
connector, durable target, CDC, configuration or package-loading subsystem enters
this increment. The lockfile adds only the logical-plan test dependency edge.

The final design deliberately differs from the initial analyzer-rule proposal.
The current plan describes the actual mandatory Sail compiler phase between
analysis and optional optimization, preserving the query's real optimizer context.
The attributed owned compilation routine preserves established explain/error
orchestration. Standard execution and explain call the same preparation phase;
programmatic callers receive an explicit complete Sail compilation helper rather
than a promise that bare DataFusion APIs provide Sail-specific participation.
This mechanism change is explained in the existing first-principles plan rather
than hidden behind the initial review verdict.

The audited preparation subset is necessary to avoid introducing scan-width,
filter-pushdown and repeated-immutable-work regressions when lowering earlier.
It consists of existing expression simplification, filter pushdown, projection
optimization and common-expression sharing, with bounded rounds and an admitted
main-input-shape check. It does not call the full optional optimizer before
protection. Unsupported source-bearing shapes skip that subset and reach named
refusals. The dedicated tests distinguish immutable sharing, volatile calls and
conditional evaluation rather than granting blanket CSE permission.

Source-occurrence tokens remain in-process, clone-preserved identities, not durable
source IDs. Collector qualifiers/metadata preserve existing name binding. Initial
LIMIT0 bypasses child execution explicitly as consumer cancellation. Actual views,
expression subqueries and eager command/resolver entrances have dedicated tests;
raw stream-bearing memory-table and Prepare inputs are refused before eager work,
while bounded controls retain execution. No new SQL PREPARE feature was added.
The public tests preserve exact multisets, cardinalities, failures and expected
unsupported outcomes rather than declaring all unsupported queries compatible.

The lead reports 38 selected public tests passed against a fresh server/native
PySpark 4.2.1 setup, 217 affected tests passed with one skip, and two negative
preparation controls failed before restoration and passed afterward. This reviewer
performed inspection only. Full immutable qualification remains pending. The
planning comparison's retained v1 batch-alias fixture has a wrong-output finding
under diagnosis; it is unresolved measurement evidence, not a completed performance
qualification or proof that the new preparation is neutral.

## Human review and continued scope

Read `FABLE-REDESIGN-REVIEW.md`. Its actionable reviewability feedback supports a
concrete code commit body stating the defect, selected boundary, control evidence,
remaining limits and the existing design-note path. Keep the founder entry short
and preserve the specifically requested HUMAN-REVIEW compendium. Prefer those
improvements over adding another reader-facing document or asking a human to read
specialist evidence to discover the basic change.

The user-authorized local reference work can continue. Review recommendations do
not authorize source publication or maintainer contact, and do not cancel the full
SDP, Extensions, Comet, performance, fencing and typed-configuration objective.
Those requirements remain active and are not redefined around this preparation
increment. Maintainer agreement and upstream readiness remain distinct from local
reference qualification.

Reread the complete saved request and governing AGENTS, LAKESAIL, SHEHAB, CLARITY
and WRITING-RULES. Only this report was appended. No source edits, builds, runtime
or performance tests, cleanup, remote changes or maintainer messages were performed.

## Frozen v3 test-only lint correction

Verified the updated final snapshot's 77 file hashes and 24 increment paths,
unchanged parent `327572240365e2507f348ee92bc009cbfc67abe9`, working/index equality
and exact index equality with tree `c1e9563dec7527ed11c2e2bf5476816229317a93`.
Independently recomputed:

- Increment SHA-256:
  `cddf405cb8205cfce54b14f97190b135bcd8b843f79724a8ffc90eb0b756694c`.
- Cumulative source against upstream `b52144955b629314a000b1fe49eeea97fa3d0c5c`,
  SHA-256: `28c0c0b0400fc61662667d08d878ff629ca4a3b303c4637f6c3c5cbf3437c066`.

The full v2-to-v3 tree diff contains only three test files. Inspected every changed
hunk: expect/expect_err calls become explicit Option/Result failures; fixture mutex
access returns a contextual error on poisoning; timestamp construction now returns
a Result. Success values, named-error assertions, source scan counts, marker
sequences, cardinalities, comparison ordering and zero-evaluation checks remain
required. This is a narrow test-lint correction, not assertion weakening or another
runtime feature. No production source changed from the previous reviewed pin.

No scope blocker was found. The final source-scope verdict applies to this exact
v3 candidate, with the full objective and qualification boundaries unchanged.
Read the newly saved literal continuation request, which says continue. The full
saved request and governing requirements remain applicable as refreshed above.

The same-alias direct planning probe returned old values 13–16 and candidate
values 2–5. It is not a valid equivalent-output performance cell and cannot support
a neutral-cost or slowdown claim. The lead's unique-alias measurement is still
running; it is not counted as completed evidence here. Full immutable gates remain
pending. No builds, source edits or measurements were performed by this reviewer;
only this report was appended.

## Frozen v4 narrow lint exceptions and final pin

Verified all 77 snapshot file hashes, 24 increment paths, unchanged parent
`327572240365e2507f348ee92bc009cbfc67abe9`, working/index equality and exact
index equality with tree `1501e3dcaf84158319a99fd4c3122c2dcb84bfc1`.
Independently recomputed:

- Increment SHA-256:
  `2bc3f0275441454387ed32baa8764642bf4f35edef299f63dc796b65ed4aea6d`.
- Cumulative against upstream `b52144955b629314a000b1fe49eeea97fa3d0c5c`, SHA-256:
  `e4f922d5c38697aa487fe256d9b1885227bbe506e600500a30be9e9e9b978b1a`.

Inspected the complete v3-to-v4 delta. It touches only the raw-command imports in
`sail-plan` and the existing raw-command boundary fixture. Two import-scoped
Clippy expectations permit inspecting or constructing DataFusion's raw command
variants, with comments explaining the eager-streaming guard purpose. One
statement-scoped expectation permits the bounded raw-command control to read the
DataFusion memory catalog it just created. Other imports remain outside those
exceptions. No expression, execution path or assertion changed. These are narrow
boundary exceptions rather than a crate-wide relaxation or new command feature.

No scope blocker was found; this source-scope verdict applies to the exact v4
candidate. The lead reports strict affected Clippy passed. No builds or lint
commands were executed by this reviewer. Full immutable qualification is next and
remains pending.

The measured shallow streaming compilation cost of about 1.66 times the comparator
is a material local-reference limitation. It must remain visible in the handoff;
this scope verdict does not certify performance readiness. Clarifying the preceding
probe note: DIRECT returned 13–16 while both OLD and NEW returned 2–5, in both batch
and stream cells. That is an open shared optimizer discrepancy, not evidence of a
new-versus-old participation regression or a valid equivalent-output timing cell.
Keep that evidence separate from the valid unique-alias comparison and do not widen
this unit into an unrelated optimizer fix without its own discriminating evidence.

The saved literal continuation remains continue. The full saved request and governing
requirements remain applicable as read above. Full SDP/Extensions/fencing/configuration
scope remains active, source remains local, and no maintainer-contact or publication
authorization is inferred. Only this report was appended; no source edits, builds,
measurements or cleanup were performed.

## Frozen v5 attribution-format correction

Verified all 77 snapshot hashes, 24 increment paths, unchanged parent
`327572240365e2507f348ee92bc009cbfc67abe9`, working/index equality and exact
index equality with tree `f71f8c5c97b08baa0c7f0f914ea7a2e24d150622`.
Recomputed increment SHA-256
`15fd96913eecd7d1d1e64fd1083d12bc34630a13c93802541d2cd14bb73941c7`
and full cumulative SHA-256 against upstream b52144955
`0b71c28974776dedaf643028bf12cc7959a0856b751db223b883393818e3d59a`.

The complete v4-to-v5 diff changes one documentation-comment line in optimizer.rs:
the CREDIT tag is wrapped in inline code. Executable code and test assertions are
unchanged. No scope blocker was found; the previous source-scope verdict applies
to this exact final pin. The lead reports strict Rustdoc now passed and the earlier
failed precommit receipt remains retained with no commit made by that failed run.
This reviewer did not execute Rustdoc or builds.

All preceding qualification limits remain: full immutable gate pending, material
shallow streaming compilation cost, unresolved shared same-alias optimizer behavior,
local-reference status and the incomplete full SDP/Extensions/fencing/configuration
objective. Only this report was appended; no source edits, builds, cleanup or remote
actions were performed.
