# Parallel streaming and CDC implementation handoff

Fable can begin independent implementation on a separate worktree/branch while
the batch/ORC and general execution-resource work continues. This handoff scopes
parallel work; it does not approve unresolved durability mechanisms or claim any
streaming/CDC runtime already works.

## Starting points and ownership

Use Spark4.2.1 source pin `617618396087429b5627a86ce933bb0f5d6645cb`.
The current Sail SDP branch is `work/spark-declarative-pipelines`, with the
resource-context adapter committed at `779cb136d988c759a381ea1ace6c2e7649e3dbbc`.
Fetch and inspect current state before branching; this pin is a starting snapshot,
not permission to replace independently advanced worktrees.

The existing [Fable review and responses](SDP-FABLE-DESIGN-REVIEW.md) contain the
streaming/Iggy and CDC constraints. Preserve that document; new implementation
notes belong in dedicated handoffs/evidence rather than more appended responses.
Read [the writer ownership proposal](ORC-WRITER-OWNERSHIP.md) before depending on
execution cancellation or resource lifetime behavior.

Primary-agent ownership: ORC source/writer, common-datafusion resource scopes and
TaskContext adapters, task monitors, local/distributed JobRunner integration and
shared execution cleanup. Fable ownership: new pipeline streaming/CDC modules,
independent source adapters/test fixtures and faithful Spark assertion ports.
Coordinate edits to existing pipeline graph/execution/materialization modules,
configuration/session state, physical protobuf/codecs, catalog publication and
Delta commit paths before changing them. Prefer new modules with small integration
patches. No wholesale streaming rewriter replacement or new catalog-specific
execution path.

## First reviewable commits

1. **CDC argument and definition validation.** Port the exact Spark API/ChangeArgs
   assertions, including names, keys, sequence expressions, mutually exclusive
   arguments and supported SCD type. Scope is SCD1 plus faithful SCD2 rejection.
   Preserve error class/parameters/failure stage. Keep validation independent of
   the eventual durable store and MERGE runtime.
2. **CDC input validation tests and implementation.** Validate original input rows
   before deduplication; retain duplicate null-key counts and null-sequence error
   precedence. Reuse Sail's existing max_by implementation. Keep declared key
   drift distinct from sequence-type evolution; do not synthesize key-drift errors
   for every sequence-only change.
3. **Deterministic bounded streaming test source.** Add a source adapter with an
   immutable source incarnation and opaque cursors/range planning. Generic core
   code must not do numeric offset arithmetic or order Iceberg snapshot IDs.
   Use it to port Spark assertions without requiring an Iggy broker to explain
   generic execution failures. The source must reproduce a captured range exactly.
4. **Streaming plan admission and bounded-plan lowering.** Reuse Sail's resolver,
   JobService and commit operators. Classify the initial stateless subset explicitly.
   Keep unsupported stateful cases visible in coverage. AvailableNow aggregates
   and stream-stream joins still require durable cross-batch state; ordinary batch
   support for an operator does not establish its streaming semantics.
5. **Prepared CDC input contract/tests.** Add source-driven tests and a narrow
   representation that binds original input/evaluation identity, successful
   validation and reconciled rows. An empty reconciled result must still retain
   validation/completion obligations. Do not implement target effects until the
   replay/preparation mechanism below is selected.
6. **Iggy adapter capability/fault harness.** Review pinned sail-iggy
   `5816b9b2f3bd20cd124f24128b7e45818351bcc1` and Iggy
   `153fdf466aea94b7bcb90681ee7274f9f76ec00d` through their exact Git objects.
   Establish committed readable frontiers, retention before the first ack,
   partition incarnation/ownership, gaps and request uncertainty with pinned broker
   tests. Iggy remains a required integration. Avoid importing its client/runtime
   into a pure control model.

These are incremental foundations for the full target, not a reduced definition
of SDP support. A source adapter or validation library can be useful before its
production orchestration is activated. Each commit must say what is wired and
what remains unexecuted.

## Astra decisions before production effects

The durable streaming runner needs one atomic authority for ownership and progress,
actual sink fencing/takeover/reset, preserved original intents, receipt retention
and no-op receipts. Freeze a worked recovery trace through actual backend and
Delta operations before building the production control-store/run-actor path.
Cancellation is not proof that an external commit did not happen.

CDC needs target-wide coordination across pipelines/control roots, replay-stable
prepared input, validation evidence and separate auxiliary/target effect receipts.
A second MERGE must not use a newly selected tied/nondeterministic winner. Confirm
unfinished work before admitting a different flow on the same physical target.
Per-flow leases and two transaction IDs do not provide a two-table transaction.

Stateful operator identity/state schema/watermarks/output modes and table-source
frontiers retain their own design checkpoints. Implement them against the original
Spark assertions as the contracts settle.

Iggy acknowledgments follow confirmed effects and durable progress. Persist the
complete consumer/stream/topic/partition position and ownership context. Ack
uncertainty after a committed batch must not replay its data effects. Retention
and request-history expiry are distinct from missing input. Reuse the mirror's
poll/commit/verify/acknowledge protocol and scenarios, with these corrected
contracts; do not port scalar acknowledgments or version-as-offset comparisons.

## Integration and evidence

Keep small human-reviewable local commits and use detached candidate gates with
an isolated target directory. Read applicable AGENTS guidance and fetch every
repository touched. Plans/reviews/evidence live in Grust; product implementation
and regression tests live in Sail. General catalog behavior belongs in Sail,
with LakeCat as one supported provider. Extract/reimport Grust/LakeCat primitives
only where their concrete contracts and dependency footprint fit.

Compare exact candidate commits when integrating. Two branches passing separately
is not a verdict on their combined state. Rebase/cherry-pick small units and run
checks on the resulting combined commit. Keep original failed attempts and source
references; never remove an upstream assertion merely to improve the pass count.
Track partial ports separately from actual original Scala-suite execution. The
current inventory has462 registrations and61 partial ports; new evidence must
justify every status/count change without double-counting parameter expansions.

No push, release, external message or PR opening is authorized by this handoff.
