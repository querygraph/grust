# Scope review of the event-fidelity and expression-isolation increments

## Verdict and reviewed versions

**No scope or standalone-clarity blocker in these two design documents.** They
provide concrete choices before their dependent implementation, fit the existing
Sail event model and do not imply maintainer agreement. This verdict covers the
designs, not a completed or qualified implementation.

| Document | Committed version | SHA-256 of reviewed contents |
| --- | --- | --- |
| `STREAMSOURCE-EVENT-FIDELITY.md` | `4e2c40e7` | `429547ed5de1e746a136aaa44f1c4f6adc6f933631481a28b2a7ca7b52c45992` |
| `STREAMSOURCE-DATA-ONLY-EXPRESSIONS.md` | `207e715e` | `f63fe0715985d9b063cd2ff3fad75052d552d992035dbbfba6c3edcbdcc77c8a` |

Both current files matched those committed contents when checked. They contain
822 and 1,528 whitespace-separated words respectively, below the design-document
limit. Each was read end to end without relying on the companion for its basic
argument.

Source inspection used upstream
`b52144955b629314a000b1fe49eeea97fa3d0c5c` in
`/Users/alexy/src/sail/tmp/streamsource-build-20261105-b52144955`.
Baseline file contents were read through `git show` where implementation edits
were present. Dependency inspection used the locally available DataFusion 55.2.0
sources, matching the lockfile. No tests or builds were run by this reviewer.

## Existing contracts and proposed scope

The fidelity note repairs specific constructor defects: decoding positive-length
data with no payload columns, preserving schema metadata and constructing exact
decimal and run-end types. The baseline decoder reconstructs its payload batch
without an explicit row count; the schema helpers rebuild metadata-free schemas;
decimal placeholders discard requested precision and scale; run-end construction
uses default field attributes and unchecked length casts. The rate generator
likewise constructs its projected batch from columns alone. Repairing that
constructor if reached by the public regression belongs to the same row-count
contract, rather than introducing another source feature.

The note preserves the two control columns, existing schema nullability and
empty-data elision. Its alternatives explain why nullable payloads or separate
control transport would change more than this repair requires. Exact types,
metadata and positive row counts are observable acceptance criteria. Invalid
precision and run-end capacity are narrow constructor failures, not a mandate
to redesign all array validation.

The expression note addresses a separate defect. The baseline rewriter prepends
control columns to ordinary projections and builds the marker disjunction for
filters. `StreamFilterExec` then evaluates the complete encoded batch. The
session planner and codec bind the filter expression to that encoded schema,
supporting the note's decision to retain those column offsets.

Contiguous data runs preserve the original marker order without an interval
buffer or a separate scheduling subsystem. Forwarding markers outside expression
evaluation is a clear replacement for relying on Boolean evaluation order.
The public DataFusion projector explicitly preserves row counts for empty
projections. Its ordinary projection planner also extracts asynchronous
expressions, so preserving that path is a necessary regression boundary rather
than an unrelated feature expansion.

Planner, optimizer and codec work is justified by the introduced operator: a
safe local evaluator is insufficient if optimization or worker reconstruction
replaces it with an ordinary expression operator. Conservative properties need
the proposed plan inspection and measurements; they are not presented as free.

## Order and remaining decision boundaries

Fidelity and filter isolation are independently useful repairs. Projection
marker reconstruction depends on exact placeholder encoding, which explains
that dependency without imposing a serialized approval itinerary. Filter-only
delivery must be described as filter isolation; it does not complete the broader
projection claim.

The current notes adequately cover their selected local repairs. The following
changes require a concrete contract before dependent code; they are boundaries
already identified by the designs, not prerequisites for finishing these repairs:

- **Control names or malformed events:** decide collision handling, admission
  and error behavior before reserving more user names, changing wire fields or
  accepting a new malformed-input policy. Preserve the existing boundary here.
- **Asynchronous projection deviations:** if the public APIs cannot preserve
  supported evaluation, cancellation and marker ordering, describe the exact
  narrowly owned helper or alternative and its costs before introducing it.
  A synchronous-only fallback must not silently remove working queries.
- **Volatile retractions:** decide whether to restrict functions or retain
  previous transformed values before claiming that reevaluating a retracted row
  cancels its earlier output. Preserving flags alone makes no such guarantee.
- **Completion and multi-input control:** distinguish ordinary query termination
  from durable success before changing limit, cancellation or end-of-data
  behavior. Define participants and alignment before extending markers through
  exchanges or multiple inputs.
- **Durable execution:** select actual replay, commit-authority and storage
  contracts before their implementation. These encoding and expression repairs
  do not settle source identity, prepared-effect recovery or target fencing.

Required fencing and strict optional typed configuration remain part of the
broader task. Deferring them from these local increments does not weaken the
guarantees of an admitted durable path or claim that a durable path now exists.

## Reader clarity, evidence and follow-up

Both documents explain the user-visible failure, current Sail component,
recommended mechanism, alternatives and discriminating tests inline. They avoid
agent-session history, internal approval records and assumed prior conversation.
The source comparison with Spark is explicitly source inspection, and component
probes are not promoted to integrated execution evidence.

The cumulative implementation patch still requires independent scope review
after integration. In particular, check that source changes stay within these
contracts, preserve ordinary batch behavior and do not quietly broaden admission,
remove asynchronous behavior or introduce unsupported durability claims. A
design verdict is not a substitute for that review or the lead's validation.

Confirmed compliance with instruction-reading requirements: read the complete
saved current and preceding engineering requests, root `AGENTS.md`, `LAKESAIL.md`,
`SHEHAB.md`, `CLARITY.md` and `WRITING-RULES.md`. Only this assigned evidence file
was written. No design document, source file, index, commit or remote state was
modified by this reviewer.

## Final prospective cumulative patch review

**No scope blocker found in the 17-file cumulative implementation patch.**
This supersedes the earlier statement that cumulative scope review was pending
for this exact candidate. It is not a test, performance or integration-gate verdict.

- Source baseline: `b52144955b629314a000b1fe49eeea97fa3d0c5c`.
- Worktree: `/Users/alexy/src/sail/tmp/streamsource-build-20261105-b52144955`.
- Patch: `review-logs/cumulative-three-increments.patch` in that worktree.
- SHA-256: `d7fc1fab085e3aa5b22605dd350c488cdbd9365f0114d9c50864127dcd5a6c55`.
- Status reviewed: prospective candidate before its immutable commit; no final
  commit hash was supplied for this review.

Read the entire cumulative patch, including all added tests, and rechecked the
patch hash afterward. `git apply --reverse --check` against the frozen working
contents succeeded. No patch was applied and no source file was changed.

The governing request and the fidelity and expression notes reviewed above remain
applicable. Also read `STREAMING-FAILURE-PROPAGATION.md` at `2192b091`, including
its atomic terminal-state refinement after the initial note at `b8af1d2e`.
That note is a short, standalone explanation of the existing failure, chosen
behavior, alternative retry boundary and exclusions. It does not imply human
approval or introduce an approval procedure.

### Adversarial scope findings

The event-fidelity implementation matches the selected constructor repair.
It preserves the event representation, explicitly retains row counts and schema
metadata, supplies decimal precision and scale, and constructs checked run-end
buffers with their original field definitions. The rate generator change reaches
the same zero-column contract. It does not add replay, checkpointing or a new
source capability. The broader Arrow matrix is relevant verification of a shared
helper; it is not an unrelated expansion of runtime functionality.

The filter change replaces whole-batch evaluation with a lazy traversal of data
and marker runs. It retains encoded column offsets, filters payload and retraction
flags together and forwards markers without calling the predicate. It keeps the
existing single-kernel path for data-only batches, including empty batches. Only
the current input and unfinished traversal are retained; no interval store,
coordinator or dependency fork is introduced. A data error cannot consume a later
marker from that same batch before the earlier output is yielded.

This is the **physical filter portion** of the expression design. The rewriter's
redundant `predicate OR marker_present` remains unchanged and is tested against
the corrected operator. Streaming projection, its logical and physical planning,
codec reconstruction and asynchronous evaluation are not implemented. Keeping
the existing filter wire shape is within the explicitly independent filter
increment; reporting the whole expression-isolation design as complete would
overstate the patch.

Console source, formatting and write failures now return through the execution
stream instead of being printed or ignored. The query runner stops on its first
observed error and publishes stopped status with the retained cause as one watch
value, after releasing input. The small state enum replaces two notifications;
it does not establish another lifecycle service. The error wrapper supplies the
existing streaming exception class needed by the public wait contract.

Individual waits retain failures across manager reset. Manager waits check
retained failures before and after waiting, so a known failure is not hidden by a
successful waiter's completion. These changes implement the new failure note's
explicit choices. The patch does not implement dynamic membership for an already
pending manager wait, deterministic selection among simultaneous failures, task
panic supervision or a new cancellation policy. Error-versus-explicit-stop races
must not be described as a stronger guarantee than the preserved stop contract.

The added tests exercise the selected boundaries, including exact Arrow types,
mixed markers, single predicate evaluation, retained input lifetime, console
failures, first-cause retention and atomic terminal publication. The public
failure test is explicitly Sail-specific rather than a claimed executed Spark
comparison. Existing assertions are not weakened or replaced with expected
failures in this patch.

### Limits that must remain in the handoff

No durable source-to-table or change-capture path, target fencing, prepared-effect
recovery, checkpoint alignment or stateful operator is implemented here. Normal
input exhaustion still does not establish durable completion. Required future
fencing remains required; these local repairs neither implement nor waive it.

This reviewer performed source and patch inspection only. The lead's ongoing
crate tests, public tests, strict Clippy checks, controls and performance probes
were not treated as completed evidence. No build or execution result is asserted
by this verdict. The immutable candidate must preserve these reviewed contents;
subsequent changes require review of the affected scope.

The saved request and governing instructions were read for this task, and the
current request was reread before the cumulative review. Only this assigned
evidence file was appended; no design, source, index, commit or remote mutation
was performed.

## Final delta review of the 19-file candidate

**No new scope blocker in the 19-file candidate.** The earlier cumulative scope
findings and exclusions carry forward, with the changes below reviewed in their
full surrounding implementation context.

- Baseline: `b52144955b629314a000b1fe49eeea97fa3d0c5c`.
- Patch: `review-logs/cumulative-four-design-notes.patch` in the same source worktree.
- SHA-256: `6782613a31c5278296421622c5a5fcea918603506a70de62c0f77671fa0f3376`.
- Status: source frozen for prospective candidate checks; no immutable candidate
  commit was supplied for this review.

Verified the hashes of both the previously reviewed patch and this replacement.
Read their complete difference and confirmed the replacement contains 19 files.
The changes since the prior review are the direct-poll filter path, the service
exception response builder and its Rust tests, and the expanded Python tests.
The rest of the reviewed cumulative implementation is unchanged.
`git apply --reverse --check` succeeded against the working source contents.

The direct-poll path avoids creating the per-batch iterator and cloning its
predicate and marker buffers when there are no marker rows. Mixed batches still
use the same lazy traversal, preserve order and apply the predicate only to data.
This changes how the existing stream is polled, without adding a queue, scheduling
service, new supported operator or new marker contract. It is a targeted response
to the reported overhead rather than justification for broader optimization work.

Read the complete `STREAMING-ERROR-PROTOCOL.md` at its preceding design commit
`70c6a7c6`. Its scope is necessary to make the retained error usable by the existing
client: prepend the exception class in the message field and keep a recorded
error condition distinct from that class. The service helper implements that
choice without changing execution or inventing structured conditions. It leaves
absent conditions and stack traces absent. The note explains the failure,
representation, source contract and limits without review-history language or
an implied maintainer decision.

The Rust tests exercise the response builder and protobuf round-trip. The nine
new Python cases exercise actual PySpark protobuf and exception decoding with a
mocked command response; they are client-contract tests, not nine live server
executions. The retained live failed-query test now requires its full retained
cause, so an indexing failure or a lost colon-delimited prefix cannot satisfy it.
The old-wire counterexample reported by the lead is separate execution evidence;
this reviewer did not rerun it.

This remains a local functional candidate. The direct-poll change does not
establish acceptable performance under frequent marker/data alternation. The
reported significant fragmentation cost remains an explicit qualification issue
requiring optimization and measurement before upstream readiness. This scope
verdict neither dismisses that cost nor approves an upstream offer.

All previous capability limits remain: physical filter isolation only, with the
existing rewriter disjunction retained; no projection or asynchronous isolation,
new codec path, durable change capture, fencing or distributed checkpoint
alignment. The manager wait snapshot, task-panic handling and explicit-stop race
semantics remain unchanged. No full parity or durable-completion claim follows
from the added client serialization fix.

The current saved request was reread. Governing instructions previously read for
this uncompacted task remain in force. No source edit, build, test run, commit or
remote action was performed by this reviewer; only this evidence was appended.

## Final cost-fix delta review

**No new scope blocker after the console and active-query cost fixes.** The final
19-file cumulative candidate remains within the four preceding design notes.

- Final cumulative patch: `review-logs/cumulative-final.patch`.
- Final SHA-256: `bda65fdba075378f3088a2b00681fdf63f57b9d9a66722ec78c8e1f688220163`.
- Reviewed three-file delta: `review-logs/failure-reporting-cost-fix.patch`.
- Delta SHA-256: `73baa58870461a4b5143a97d24145a5dc86d896e51338a5e42da7075499587f1`.
- Baseline and source worktree remain as recorded above. This verdict is bound
  to patch contents; the final immutable gate pin has not been supplied here.

Verified both hashes, read the complete delta and its difference from the
previously reviewed cumulative patch, and confirmed there are no other changes.
The final cumulative patch reverse-application check succeeded against the source
contents. The earlier cumulative findings carry forward.

Console formatting and rendering now finish before stdout is locked. Formatting
errors still return before output, and header and body write failures still
propagate. The write helper accepts completed text and preserves the output
framing. Its tests now use that narrower interface; the separate execution-path
test for formatting failure remains. Moving formatting out of the shared output
lock changes cost and contention without changing the selected failure contract.

Active-query listing takes one watched-state borrow, excludes stopped queries
before allocating a status, and constructs retained statuses from that same
borrow. This avoids formatting a discarded status while preserving atomic
state-based visibility. It adds no lifecycle state, query-retention rule or
manager-wait behavior. Both fixes fit the existing notes and do not require a new
product or architecture decision.

The lead reports completed checks for the preceding candidate and resolution of
the two measured cost regressions. This reviewer has not independently executed
those checks or measurements. Their receipts and the final immutable gate remain
separate from this source-inspection verdict. Significant dense-marker filtering
cost remains an explicit limit before upstream readiness.

Projection and asynchronous isolation, durable recovery and change capture,
target fencing and typed configuration remain unbuilt in this candidate. The
absence of those additions is stated scope, not permission to claim their
guarantees. No source edit, build, test run or remote action was performed during
this review; only this evidence file was appended.

## Immutable candidate pin and filter-batching note

Confirmed the reviewed source contents at immutable commit
`2c9fa84994d317aade0d1c69faa9a378c780127d`, tree
`5d67cdc81cdd9ba7eb18a74eda17d84b9e5d30c7`. The binary diff from
`b52144955b629314a000b1fe49eeea97fa3d0c5c` contains 19 files and hashes to
`bda65fdba075378f3088a2b00681fdf63f57b9d9a66722ec78c8e1f688220163`, exactly
matching the final cumulative patch reviewed above. Worktree `HEAD` matched that
candidate and tracked source was clean. The scope verdict therefore applies to
this commit, subject to the previously recorded limitations.

The full immutable workspace gate remains in progress. This pin check does not
claim that the gate passed, and no build or tests were run by this reviewer.

Read the complete `STREAMSOURCE-FILTER-BATCHING.md`, reviewed SHA-256
`a637afe558a9be57409f350f0f338bacbc08cecd70b2d089a9dcb8980e633bbc`, containing
293 whitespace-separated words. No scope blocker: the note explains the existing
encoded batches, correctness constraint, observed fragmentation, reasonable
alternatives and the experiment needed before selecting another batching policy.
It does not claim production throughput or qualify durable/distributed behavior.
A byte-bounded combiner remains a choice to test, not an already justified
subsystem or an implicit implementation approval.

One nonblocking clarity suggestion was sent to the owner: distinguish the code
change from the compiler build profile in the phrases “after optimization” and
“unoptimized results.” “After the direct-poll change” and an explicit build-profile
description avoid suggesting that the dense-marker cost was already measured in
an optimized build. No source or design file was changed by this reviewer.
