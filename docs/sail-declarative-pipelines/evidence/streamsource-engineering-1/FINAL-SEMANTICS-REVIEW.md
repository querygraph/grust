# Final semantic review of the cumulative document candidate

## Candidate and verdict

Role: Spark Compatibility and Correctness specialist. Reviewed the complete
3,834-line `cumulative-documents.patch` against documentation baseline
`f23da50ccdf4ac1258fa1c6803aeb54df042a03e`.

Patch SHA-256:
`2a619d67564fa3090733def44d5cf97c5ac4437ca0d8accc6abcf258a250a05c`.

All 22 working documents matched `candidate-files.json` during this review.
That initial verdict covers the original frozen candidate only. One clarification
required correction before document readiness; no other semantic blocker was found.
The final candidate and resolution are recorded in the addendum below.
This is not implementation, runtime qualification or submission approval.

## Finding: preserve original/current-version conflict evidence through reduction

**Medium in the original candidate; resolved in the addendum below.**
`CHANGE-CAPTURE-SEMANTICS.md:85`,
`CHANGE-CAPTURE-ON-STREAMSOURCE.md:70`,
`STREAMING-ARCHITECTURE.md:102` and
`REDESIGN-REVIEW-PACKET.md:54` promise conflict checks within the prepared interval
and against the current durable version. The surrounding execution description
reduces the interval to its maximum before target effects, without making the
current-version check's placement and state precondition explicit.

Counterexample: durable state is `8:A`; incoming events are `8:B` and `9:C`.
There is no same-version pair within the interval. Reducing first keeps only
`9:C`, so comparing that winner with durable `8:A` misses the conflicting `8:B`.
Valid-input convergence is unaffected, but this loses a conflict inside the
promised default detection scope.

Retain the stated scope. Compare original normalized versions with the pinned
durable validation snapshot before reduction discards their evidence. Bind that
snapshot to the commit precondition and define revalidation after a relevant
state change. This need not reevaluate source expressions or require a separate
source execution: batch lookups, retained normalized values and bounded spill
can supply the required evidence. Add the counterexample to acceptance tests.
This is a consequence of the proposed contract, not an observed engine defect.

## Verified semantic alignment

- Source/application complete order and one action-independent comparison replace
  undefined Spark ties and asymmetric upsert/delete equality. Convergence claims
  are limited to valid full-row replacement events and final state.
- Native event IDs are optional when source incarnation, canonical key and
  complete order uniquely identify a replacement event. Arbitrary transformations
  do not inherit identity automatically.
- Default checks explicitly exclude exhaustive validation of superseded history.
  Historical fingerprints have a separate horizon and retention budget.
- Original-row validation and evaluate-once normalization remain required. The
  bounded runtime's repeated lazy execution is labeled a source-path risk, not
  a reproduced runtime failure.
- Live and deleted keys retain ordering state. Atomic row/state publication is
  a proposed target capability; fenced sidecars retain partial-effect recovery.
  A table-to-view substitution is an explicit product migration.
- Refresh requires authoritative reconstruction, not universal physical origin.
  Key/order/schema changes cannot silently reinterpret old state or pending work.
- Watermark and bounded-completion contracts no longer inherit Spark batch
  scheduling. Source evidence, component executions and unbuilt guarantees remain
  distinguished. Legacy documents clearly identify superseded requirements.

## Evidence, limitations and instruction compliance

Used the pinned source investigation in `SEMANTICS-AUDIT.md` and earlier
`../redesign-discussion-1/SPARK-SEMANTICS.md`. Additional source spot-check:
Spark `617618396087429b5627a86ce933bb0f5d6645cb`,
`MicroBatchExecution.scala:773–774,807–808` restores the combined watermark into
a fresh tracker; `WatermarkTracker.scala:89–103` initializes per-operator values
unset. This supports the runtime-review statement about combined-only recovery.

No Spark, Sail, broker or storage suite ran for this final review. The earlier
Python logic model remains algebra evidence, not implementation validation.
Other specialists own the new Rust probes, configuration execution and backend
fencing qualification; their reported results were not relabeled as my executions.

Confirmed the full saved engineering prompt and referenced earlier requests,
`AGENTS.md`, `LAKESAIL.md`, `SHEHAB.md`, `CLARITY.md`, `WRITING-RULES.md` and
`ASTRA-REDESIGN-1.md` were read and reread after compaction. The latest engineering
directive governs over earlier Spark-conformance defaults. The cumulative patch's
governance changes were reviewed. Only this review artifact was added during the
final review; no shared design or production source was edited.

## Addendum: amended candidate verified

Final cumulative patch SHA-256:
`8dd7bac1e54a6b463f74f91c37b9cb604e15872b4c30772b5fba6089ee7e57b9`.
The documentation baseline remains
`f23da50ccdf4ac1258fa1c6803aeb54df042a03e`.

Compared the amended patch with preserved `candidate-0-documents.patch`.
Only `CHANGE-CAPTURE-SEMANTICS.md`, `CHANGE-CAPTURE-ON-STREAMSOURCE.md` and
`REDESIGN-PLAN.md` changed. Verified all 22 final file hashes against the updated
`candidate-files.json`; there were no mismatches.

The amendment explicitly compares original normalized versions with a pinned
durable-state snapshot before reduction discards evidence. It includes durable
`8:A` versus incoming `8:B, 9:C`, binds the validation snapshot to the commit
precondition, and requires safe reconciliation or revalidation of the same
immutable normalized input if relevant state changes. The plan adds this
acceptance case and retains the requirement to budget checking without
reevaluating input. This closes the finding without weakening default conflict
detection or implying exhaustive historical verification.

**Final verdict: no unresolved semantic document-readiness findings for the final
patch above.** The unchanged 19 documents retain the preceding full-review
coverage. This scoped addendum does not qualify an implementation or authorize
submission. No additional engine or storage tests ran; the existing evidence
limits and instruction-compliance statement remain applicable.
