# C5 and streaming-progress source review

This is a source comparison and proposed regression schedule, not an observed
Spark/Sail runtime counterexample or a combined integration gate. The exact
reviewed source objects and byte hashes are in provenance.json.

## C5 global phase boundary remains open

At Sail550bb198a, analyze calls graph.validate before source resolution. That
validation still performs raw-plan streamingness checks. Inside the per-output
resolution loop, analyze calls validate_multiple_flows immediately after only that
output's flows resolve. In pinned Spark4.2.1 DataflowGraph.validationFailure,
validateSuccessfulFlowAnalysis precedes global multiquery and streamingness checks.

An earlier resolvable CDC multiflow destination can therefore fail before a later
unrelated missing-source flow has been analyzed. Request both declaration orders
of that competing-error graph against the reference, plus a streamingness error
combined with an independent missing source. A per-output correction cannot be
accepted as complete global phase parity. Schema inference needed for downstream
resolution requires its own phase-specific fixture; this review does not assume
all inference can simply move to the end. C5 remains pending correction.

## Progress must bind incarnation across runs

At Sailc9a0132cf, Progress maps partition ID to cursor alone. RunFrontier captures
incarnation separately. next_intent compares start==captured_end before validating
an incarnation, and then declares no remaining range. Source-derived schedule:
an old run reaches pos:2; its partition is recreated with a new incarnation and
two replacement rows; a new frontier again ends at pos:2. Reusing the old Progress
can report caught-up without a scan that would detect recreation. Bind progress
to source/partition incarnation or require an enforced validated binding before
consumption. A check only when scanning an old recorded Range does not cover this
new-frontier shortcut. No production streaming runner is wired by this component.

Similarly max_rows_per_partition=0 or an adapter returning a nonadvancing end
currently lets next_intent return None while start differs from frontier. Reject
invalid zero limits and distinguish stalled planning from actual caught-up state.
These requests preserve opaque-cursor equality; they do not add generic offset
ordering or arithmetic. Request across-run recreation and nonprogress regressions.

## Unit4 design handoff

Fable has the concrete next scope in coordination CF-0039: draft bounded-plan
admission in Grust before shared runtime edits. Use explicit recorded-scan relation
bindings through PlanResolver/RelationScope, preserve the operation context and
existing JobService preparation ownership, and return bounded logical plans
without target effects. Explain local graph versus external streaming references,
context/resource preservation, and async Iggy network work behind the currently
synchronous source API. Keep the incremental/sink execution guard until the
execution/effect barrier qualifies activation. C5's separately approved correction
scope remains available. Units2/3/5/6 are offered and require independent review.
