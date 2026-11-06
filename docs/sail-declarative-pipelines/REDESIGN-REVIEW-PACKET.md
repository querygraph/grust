# Review agenda for streaming pipelines, change capture and Extensions

Sail can transport continuous data and control events, but those events alone do
not make table updates recoverable. The proposed design adds replay, durable
preparation and enforced writer ownership, then builds deterministic change capture
and native extension integration on that foundation.

The [overall review](HUMAN-REVIEW.md) explains scope, architectural fit and current
readiness. Read the streaming proposal first, then change capture and Extensions.
This agenda identifies the choices to discuss; it does not restate their contracts.

## Decisions for the first delivery

| Choice | Why it needs an answer | Recommendation and evidence needed |
| --- | --- | --- |
| Running-source control | A source described during planning is reconstructed in an executing task. A planner-held object cannot command that instance. | Route controls through the job runner and existing driver/task actors. A separate coordinator is justified only if recovery must span jobs. Test replacement, cancellation and stale responses through real execution. |
| Expression isolation | User expressions must never evaluate internal marker placeholders. Both dedicated flow-aware operators and changes to existing operators can enforce this. | Review the local flow-aware operator design against changing existing operators. Preserve data-only evaluation, worker reconstruction and marker-before-error ordering; resolve its mixed-marker cost. |
| First source and target authority | Recovery needs retained input and an authority that can reject an obsolete owner at commit acceptance. Format transaction tags alone supply neither. | Start with a Delta log source and an authority-protected filesystem Delta target. Qualify retention, authority durability and storage permissions that prevent bypass before admitting this path. |
| Native package boundary | Existing packages use DataFusion’s foreign-function interface; Comet offers a smaller Arrow-only scalar interface with a separately pinned binary contract. | Retain the existing route and select the C route explicitly per export. Verify the host port, worker identity and result lifetime before admitting packages through it. |

These are mechanism and delivery choices. Deterministic change semantics, fencing for
every admitted durable target and strict configuration are requirements. Starting with
one target does not require all format adapters in the first delivery or allow an
unfenced fallback.

## Supporting material by question

The [delivery plan](REDESIGN-PLAN.md) explains why append recovery precedes change
capture and sizes its implementation slices. The [streaming](DECISION-NOTES-STREAMING.md)
and [extension](DECISION-NOTES-EXTENSIONS.md) notes provide focused alternatives when a
particular choice needs closer review. The architecture and results documents support
specific claims; none is an additional prerequisite for reading the proposals.

The requested outcome is agreement on these boundaries and the first milestone,
with unresolved choices recorded before dependent implementation. Local reference
code demonstrates particular behaviors, not adoption of the architecture.
