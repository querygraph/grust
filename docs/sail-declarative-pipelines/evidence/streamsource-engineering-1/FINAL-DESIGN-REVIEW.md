# Final Design Quality review

## Candidate and verdict

Documentation baseline: `f23da50ccdf4ac1258fa1c6803aeb54df042a03e`.

Reviewed candidate: `cumulative-documents.patch`, SHA256
`2a619d67564fa3090733def44d5cf97c5ac4437ca0d8accc6abcf258a250a05c`.
All 22 document hashes match `candidate-files.json`.

**No blocking Design Quality findings.** The candidate is a coherent technical
proposal grounded in Sail's actual extension points. It implements the requested
change in design direction without claiming that the replacement runtime exists.
This verdict covers the frozen documentation candidate, not production readiness,
an implemented target adapter, or agreement on the remaining backend choices.

## Review coverage

Reviewed the cumulative changes within the Design Quality specialty and read
the active proposals, founder brief, implementation plan, architecture, decision
notes, semantics, fencing, configuration, runtime comparison, prototype specifications
and results. The eight legacy documents were reviewed for their new reference-scope
notices; their unchanged historical bodies are not recertified as current guidance.
The governance change was checked against the latest engineering directive.

Source reasoning builds on `STREAMSOURCE-FOUNDATION.md` and the source pins
recorded there. Executed component evidence remains separately attributed to
`TEST-EVIDENCE.md`. This final pass ran document identity and word-count checks,
not engine, storage, broker or distributed tests.

## Architectural assessment

- The design repairs the event path before promising durable sinks. Expression
  isolation, exact Arrow encoding, actual exchange alignment, truthful completion
  and resource accounting are execution responsibilities. A coordinator beside
  the engine would not repair them, and the proposal no longer implies otherwise.
- Existing job runners, task attempts, catalogs and format commit interfaces
  remain the integration points. Local execution does not acquire a driver.
  A broader coordinator or new commit service needs an actual ownership or
  enforcement requirement; neither is introduced as a prerequisite.
- Source descriptor identity, incarnations, pinned checkpoint participants and
  explicit partition discovery close the gap between an offset and replayable
  input. Event identity may be derived for replacement events, avoiding an
  unnecessary requirement for an independent broker identifier.
- Complete per-key order and one comparison for both actions replace undefined
  ties and checkpoint-dependent outcomes. Evaluate-once normalization preserves
  original-row validation. The default verification scope is honestly limited
  to prepared input and current durable state; exhaustive historical conflict
  detection is not smuggled in as an unbounded default index.
- Storage follows the required atomicity and public table contract. Atomic
  publication of rows and key-state metadata is explicitly proposed capability
  work. Fenced sidecar recovery remains a concrete alternative. A physical state
  table exposed through a view is not treated as a transparent substitution.
- Fencing is mandatory at acceptance for every admitted durable target, including
  creation, maintenance, refresh and worker paths. Exact effects accepted before
  takeover remain recoverable. Missing managed Delta and Iceberg enforcement is
  implementation work, with no external-single-writer escape clause.
- Resource budgets cover transport, prepared output and state together. Existing
  pools, temporary files and object-store interfaces are reused without asserting
  that bounded channels or checkpoint frequency alone provide bounded memory.
- Strict typed configuration is shared by YAML, JSON and APIs. Optional Dhall
  compiles outside the runtime into the same model. This avoids a second execution
  configuration authority while retaining connector and semantic admission checks.

## Reader and scope assessment

The founder brief explains user value, existing Sail capability, concrete gaps,
the partial-commit failure and three consequential choices without requiring
companion reading. The plan explains dependency reasons and permits independent
configuration, source-control and fencing work. Active documents distinguish
required correctness from selectable mechanisms and delivery scope.

Every active document is under 2,000 whitespace-delimited words. Decision notes
retain S1 through S13, total 1,967 words, with the longest standalone body at
157 words. Historical files exceeding the ceiling are explicitly scoped as
reference records rather than current proposals. Test observations, source
inferences and proposed behavior remain distinguishable.

## Remaining design and validation limits

The first source/target pair, enforcement authority and interoperable key-state
representation still need selection. The documents correctly do not claim that
all three target adapters, multi-host authority durability, external-writer
enforcement or bounded distributed execution have been established. Acceptance
requires the actual local and cluster plans, target commit boundaries, failure
schedules and external table operations. The new semantic model is evidence for
the ordering argument, not a replacement-engine execution result.

The saved full request and governing `AGENTS.md`, `LAKESAIL.md`, `SHEHAB.md`,
`CLARITY.md` and `WRITING-RULES.md` were read and reread after context compaction.
The latest request controls over earlier compatibility defaults. No source
worktree was edited, and no commit, cleanup or external action was performed
for this review.

## Final-candidate addendum

Re-reviewed the delta from the preserved initial candidate to
`cumulative-documents.patch`, SHA256
`8dd7bac1e54a6b463f74f91c37b9cb604e15872b4c30772b5fba6089ee7e57b9`.
Verified the patch hash and all 22 current document hashes. Only
`CHANGE-CAPTURE-SEMANTICS.md`, `CHANGE-CAPTURE-ON-STREAMSOURCE.md` and
`REDESIGN-PLAN.md` differ from the candidate reviewed above.

**Final verdict: no blocking Design Quality findings.** The clarification closes
an important implementation ambiguity without adding another subsystem. Original
normalized events must be checked against the pinned durable state before
reduction hides them. Durable version 8 with payload A must conflict with input
8:B even when 9:C wins the interval. Validation binds that state snapshot to
the commit precondition. If state changes, reconciliation or revalidation uses
the same immutable normalized input rather than reevaluating the source plan.

This preserves the declared current-version verification scope and the distinction
from exhaustive historical checking. The plan now names the decisive losing-event
case and its resource obligation. The changes remain consistent with fixed
prepared effects, exact retries and fenced acceptance. They specify required
implementation and tests; this addendum supplies no new runtime execution result.
The prior scope, instruction-compliance statement and residual limits still apply.
