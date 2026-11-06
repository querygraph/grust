# Decisions for recoverable streaming pipelines on Sail

Review whether the proposed streaming pipelines, change capture and native Extensions fit Sail's continuous execution model, and select the boundaries of the first implementation milestone. The initial delivery should prove one replayable Delta source feeding one fenced append target through process restart. Keyed change capture follows that recovery contract. Extensions remain separately packaged; Comet's Arrow-only scalar interface is an optional additional boundary.

Sail already transports data, retractions and ordered control markers. A retraction cancels an earlier row. `StreamSource` describes a scan, while an executing task owns the running source. Existing job runners, driver/task actors, physical-plan codecs and format/catalog commit paths are the integration points. The proposal extends those components; it does not introduce a bounded microbatch engine or a local-mode driver.

Recovery needs more than saved source positions. Before publishing table effects, persist the exact prepared boundary and its intended effects. If publication succeeds but its reply is lost, reconcile that same effect identity after restart. Every admitted target must reject obsolete owners at acceptance. These are required guarantees; the mechanisms below remain choices.

## Execution ownership and expression isolation

A planner object cannot control the source instance reconstructed on a worker. Checkpoint requests, cancellation and acknowledgements must reach the task that actually owns it, and late responses from replaced tasks must not advance progress.

**Recommend routing source controls through the existing local job runner or distributed driver/task actors.** A separate coordinator can span independent jobs, but adds another lifecycle and authority boundary. Select it only if that cross-job requirement belongs in the first delivery. Real worker replacement and cancellation tests must establish the chosen route.

Control markers also pass through operators that normally evaluate row expressions. Evaluating a user cast or arithmetic expression on an internal placeholder can fail a query that has valid data. Two reasonable mechanisms are dedicated flow-aware filter/projection operators, or changes to existing operators so they evaluate only data rows.

The local flow-aware implementation provides a concrete reference, including worker reconstruction, but mixed marker/data inputs can fragment output into costly small batches. **Choose the operator boundary before extending that architecture.** Require data-only evaluation, preserved event order and measured batching costs from either option; component correctness alone does not settle the performance choice.

## First source, target and failure model

The Delta descriptor and sorted-replay repairs provide reusable source foundations. Complete manifest capture, a replay-qualified reader, durable preparation and restart integration remain unbuilt. A manifest must preserve file membership and interpretation; it does not itself retain missing data files.

For the target, ordinary version ordering and transaction tags are insufficient. An obsolete writer can reload the newest table and still submit a fresh write. Ownership must participate in the same serialized acceptance decision as the effect.

**Start with one Delta source and one explicitly admitted Delta append target; select its authority mechanism before code.** Reasonable options are:

- Use a catalog's existing acceptance boundary, extended to check ownership and effect identity. This best reuses a managed catalog when it can express the contract; generic catalog serialization is not proof that it can.
- Put ownership and append acceptance in the same Delta log. An exact-next-version create can serialize takeover and append without a second acceptance history. This needs an explicit required writer feature, enforcement or refusal on every permitted mutation path, and interoperability review.
- Ratify exact staged effects through a separate durable authority, then publish them. This can serve multiple adapters, but requires recovery of accepted-yet-unpublished effects and a qualified authority restart/restore model.

For a local-filesystem first target, process crashes with the OS and filesystem surviving are a narrower initial qualification than power loss or multi-host failover. Current create-only local publication does not establish power-loss durability. Select that failure model explicitly, or require the broader durability work in the first milestone. A protected commit endpoint is an alternative when storage access must enforce the authority boundary; its deployment and availability costs must be included.

No selected target may expose an unfenced durable-write fallback. Creation, takeover, retries and cleanup must respect accepted or uncertain effects. Managed Delta and Iceberg remain required adapters for the full design, each admitted only after its own enforcement is demonstrated.

## Native package boundary

Existing native packages use DataFusion's foreign-function interface. Comet offers a smaller Arrow-only scalar interface with a separately pinned binary contract. Replacing the existing package route would broaden migration and compatibility work; supporting both requires explicit export selection and two well-defined admission paths.

**Recommend preserving the existing route and selecting the C scalar route per export.** Decide whether that additional boundary belongs in Sail's host. Before package admission, verify host/worker identity, allocation ownership, cancellation and result lifetime. Standalone SDK probes do not establish package integration or compatibility with other Comet versions. A relation interface is a separate decision.

## Review outcome and supporting sequence

Record the chosen source-control and operator boundaries, first target authority and failure model, and native package boundary. Size the first delivery around one source, one target and append recovery; resolve these choices before further dependent implementation. Strict typed configuration, optional Dhall authoring, deterministic change semantics and fencing remain full-design requirements. Spark compatibility cannot justify weaker engineering guarantees.

The primary proposal sequence is [overall scope and readiness](HUMAN-REVIEW.md), [streaming](STREAMING-ON-STREAMSOURCE.md), [change capture](CHANGE-CAPTURE-ON-STREAMSOURCE.md), then [Extensions](EXTENSIONS-STREAMSOURCE-INTEGRATION.md). Each develops a distinct part of the design. The [delivery plan](REDESIGN-PLAN.md), decision notes and evidence are optional references for specific questions. Local reference implementations establish only their recorded component claims; they do not establish integrated recovery or architectural agreement.
