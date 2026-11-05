# CDC control store and fenced commit authority

> **Reference scope.** This specifies the bounded reference implementation, not the required storage
> or service layout for new StreamSource pipelines. Exact-byte acceptance and
> recovery reasoning remain useful. Bounded-only admission, Spark checkpoint paths,
> a fixed two-table representation and unfenced compatibility mode are superseded.
> New durable writes require enforced fencing; reuse an existing catalog authority
> where possible and select atomic version-state publication or fenced sidecar
> recovery by target capability. See [Fenced commits](FENCED-TABLE-COMMITS.md) and
> [Change-capture semantics](CHANGE-CAPTURE-SEMANTICS.md).

Status: selected architecture for implementation and cross-boundary review, 2026-10-31. Requested by the user from Fable's CONTROL-STORE-ASTRA-BRIEF. This document specifies the control store; it does not claim a working durable runner, backend qualification, or production activation.

## Decision

Use **one transactional control/catalog authority**, initially backed by a durable Turso SQL store and exposed through a service to Sail coordinators/workers. This is option B from the brief strengthened so that the fence check, Delta catalog ratification and effect receipt share one database transaction. A lease in one system followed by a Delta commit in another is insufficient.

Keep the Sail interfaces provider-neutral. LakeCat is the first intended catalog adapter, with an optional standalone Sail authority adapter using the same small storage kernel; neither requires importing the complete LakeCat/Grust services into Sail. LakeCat currently provides reusable CAS/idempotency machinery, not the new Delta/control transaction. Implement that capability before claiming it.

The first deployment has one authoritative service/database, durable disk, multiple remote Sail clients and no database file shared across hosts. HA/replication is a separate adapter qualification: a copied local database or eventually consistent replica is not another authority. A local JSON record remains a compatibility/test mode explicitly labeled single-writer and unfenced, never an automatic fallback from a failed durable service.

The brief reports these prior user decisions; retain them: AutoCDC-only bounded graphs are the streaming admission envelope, checkpoint directories mirror Spark beneath the warehouse, and Iggy integration lives in the sail-iggy fork lineage.

| Candidate | Decision and reason |
| --- | --- |
| Separate Delta control table | Reject as the authority. Its conditional MERGE does not atomically guard a commit to either data table. Commit-info tags and application transaction IDs do not repair that gap. |
| Catalog/SQL authority with ratification | Select. The same transaction can conflict on target ownership, publish a catalog-ratified Delta head and insert its durable receipt. |
| Advisory lock plus local file | Retain only the honest local/test boundary; it cannot exclude another host or provide durable shared-target recovery. |

## Existing seams and missing work

Sail source pin 7f7a14eb39f54ab8991063df2ca58bbf66fa5c54 already has DeltaCommitExec staging, catalog ratification and later backfill, plus CatalogProvider.commit_lakehouse_table/get_delta_ratified_commits and CommitAuthority::DeltaRatifiedCommit. MERGE planners reach DeltaCommitExec. Preserve this path rather than building a second CDC writer.

The coordinator explicitly lists outstanding read-bound, consistency and state-unknown reconciliation work. Bootstrap and protocol/metadata-only branches can still use direct CommitBuilder publication. None of these paths is yet an SDP fence. Every enrolled-table mutation, including bootstrap, no-op, auxiliary creation/drop and reset truncation, must pass the new authority; the data-only staged branch is insufficient.

MergeIntoOptions has no application transaction identity today. Add a typed optional write context through the common lake-source boundary, planner/worker codec and physical commit operators. Ordinary unenrolled batch writes keep their existing behavior. An enrolled target rejects an absent context; a caller cannot remove the fence by selecting another SQL operation.

Reuse LakeCat pin 27e18f390c450c187a34b1c3bb2037c26d107699 transaction/CAS and immutable idempotency-receipt patterns, and Grust pin e90e80be314f55e24d8f2e54ddb76753f25b46c3 guarded expectations plus receipt-in-transaction. Extract only a narrow transaction/ledger module if dependencies would otherwise pull catalog graphs, DataFusion or server frameworks into the control model. Existing Iceberg metadata records are not Delta ratification records; add a typed Delta adapter, not a JSON reinterpretation of Iceberg commits.

## Identities and durable records

A name or checkpoint path is never a sink identity. Enrollment resolves aliases to one physical target-group key: authority-domain UUID plus canonical storage/log identity and an opaque enrollment ID. Store the immutable Delta table UUID and auxiliary UUID as mandatory, separately checked sink incarnations. The physical-group guard persists across an authorized table replacement; old incarnations/receipts remain tombstoned rather than being mistaken for the replacement. Bind the auxiliary table's identity as part of that target group. A unique registry prevents the same physical target being enrolled through another catalog alias, pipeline or control root. Unknown alias equivalence fails enrollment. Persist and verify the control-authority binding with the catalog-managed table identity/protocol metadata on every open: putting a domain UUID in a key alone does not exclude a second authority. Cross-domain migration must revoke/reconcile the old publisher. Alias access must reuse the enrolled auxiliary identity; if it cannot address that identity, reject rather than create a second auxiliary state table.

Use separate monotone numbers for ownership epoch, checkpoint/reset generation, flow batch sequence, catalog table version and source positions. None substitutes for another. A fence token contains authority incarnation, target key, reset generation, owner epoch and owner ID. Ownership changes do not change a batch's stable effect identity.

| Record | Required content |
| --- | --- |
| Authority | Domain/incarnation, schema/protocol version, backend durability profile and catalog binding. |
| Target guard | Target/auxiliary identities, revision, epoch, owner, server-time lease deadline, generation, active intent or reset, enrollment/write policy. |
| Flow checkpoint | Stable pipeline/flow identity, definition/config digest, generation, continuing batch ID, committed per-source progress and checkpoint directory index. |
| Run frontier | Immutable source descriptors/incarnations and captured end vector for this AvailableNow run; a resumed incomplete run does not recapture its end. |
| Batch intent | Stable ID, original range/start/end vector, frontier ID, source/static snapshot identities, lowering/config/schema digests and original read preconditions. |
| Prepared manifest | Immutable archived input/winners, object versions/checksums, schema, decoder/validator versions and validation receipt. |
| Effect preparation | Intent ID, auxiliary/target/reset step, exact sink identity, expected read/head version, immutable staged-action digest, data manifest and request digest. |
| Effect receipt | Stable effect ID, original intent/prepared digest, Data or Noop, ratified version or checked no-op head, action digest and authority commit ID. |
| Batch completion | References to every required effect receipt, resulting progress/batch sequence and ack work; atomically linked to checkpoint advancement. |
| Operation/ack ledger | Request ID plus digest/result, source consumer generation/incarnation, ack request history and Confirmed/Unknown state. |

Canonical request encoding is versioned and domain-separated. Preserve exact identifier/cursor bytes; sort map keys, preserve meaningful vector order, encode wide integers/bytes explicitly, and avoid floating-point JSON ambiguity. Do not rely on HashMap iteration or arbitrary Arrow IPC reserialization for identity. Prepared receipts bind the original immutable artifact manifest; validation must run against the sealed artifact that replay will consume. Audit/adapt the existing prepared-input receipt before reuse: logically equal Arrow batches need not have equal physical encodings.

## Atomic operations and their linearization points

The adapter supplies a durable database transaction with conditional updates and unique keys. No network/object-store I/O occurs inside a transaction body that the backend may retry.

1. **Enroll** binds physical target and auxiliary identities to this authority. First durable activation uses new managed targets, or an explicitly quiesced migration with credentials and in-flight old writes fenced. Do not transparently upgrade arbitrary unmanaged Delta tables.
2. **Acquire/renew** CAS the target guard. Takeover increments the epoch; it preserves an unfinished intent. Expiry permits takeover but is not proof that old network requests stopped. Only authority time decides lease eligibility. Clock jumps may affect availability or cause earlier takeover; the serialized epoch/ratification check, not client clock assumptions, supplies safety. Acquisition of a target with unfinished work returns recovery-only access to that intent, not permission to start another flow.
3. **Seal intent** requires current ownership and an empty target slot, or returns the exact prior intent for a matching request. Persist its original range/frontier/config before any sink effect. A different digest for the same identity is a hard mismatch.
4. **Prepare effect** records immutable staging/read preconditions. Preparing a target effect requires the matching auxiliary receipt and binds its recorded version/head; ratification rechecks that predecessor. Workers may write immutable data/staged objects using Sail's owned effect machinery; they cannot independently ratify a table head.
5. **Ratify effect** is the critical transaction. Verify current owner/epoch/generation/lease, active intent, required predecessor/step, prepared/validation digest, sink incarnation and original expected head. Mutate the target guard row, conditionally advance the catalog-ratified Delta head, and insert the effect receipt atomically. Conflicting ownership and commits must write the same guard row: snapshot-isolation reads alone permit write skew.
6. **Ratify no-op** checks the same guard and exact sink head, then records an explicit no-op receipt in that transaction. Zero output rows or absence of a Delta log entry is not a receipt.
7. **Complete batch** requires all matching auxiliary/target receipts, atomically advances flow progress/batch sequence and clears the target slot, and queues ack work. No range moves forward after only one effect.
8. **Lookup** returns Confirmed, AbsentWithinCoverage, Unknown or Mismatch. Transport errors, missing retained history or an expired recovery window cannot become permission to rerun arbitrary work.

Each mutation has an operation ID and request digest with its result stored in the same transaction. A lost response is resolved by lookup/retry of that original request, not a new batch. Database conflict retries may reload the guard, but never silently change the intent, prepared input, sink incarnation or original snapshot precondition. A genuine replan needs an explicit new prepared attempt under the same uncommitted effect identity and a proven conflict policy; v1's exclusive target policy makes ordinary external-write rebases unnecessary.

A stale epoch cannot ratify after a takeover/reset transaction. If its ratification won first, its receipt/head update are already durable and the successor must recover them. These are the only two serial outcomes. A pre-commit control-table read, epoch in a user tag, or two separate transactions does not establish this property.

## Concrete SQL transaction boundary

Initialization is also recorded: target enrollment/materialization and ensure_auxiliary_table use a short Initialization intent in the same target-wide slot, with fenced DDL/data-or-no-op receipts but no source progress or batch-ID advancement. Resolve an unfinished initialization before accepting a batch or another flow; never call the existing unannotated bootstrap/create helper first and attach a receipt afterwards.

The first adapter adds dedicated SDP/Delta ledger tables, not Iceberg metadata JSON. Minimum keys/constraints are:

| SQL table | Keys and constraints |
| --- | --- |
| sdp_target | target_key PK; canonical_physical_key UNIQUE; authority incarnation, target/aux UUIDs, epoch, generation, owner, lease deadline, revision, state and active_intent. |
| sdp_flow | PK(target_key,generation,flow_key); definition digest, next batch sequence, progress blob/hash and frontier reference. |
| sdp_intent | intent_id PK; UNIQUE(target_key,generation,flow_key,batch_sequence); original range/frontier/config payload and digest; prepared manifest set once; never overwritten on takeover. |
| sdp_effect_prepare | PK(intent_id,step); immutable request/action/input hashes, expected sink UUID/head and stage manifest. A changed preparation requires an explicit uncommitted attempt, not an overwrite. |
| sdp_effect_receipt | PK(intent_id,step); immutable request/prepared digests, Data/Noop kind, checked head, optional ratified version and authority commit ID. |
| delta_head / delta_ratified_commit | table_uuid PK / PK(table_uuid,version); table incarnation, ratified head and immutable staged URI/action digest/effect reference. All enrolled head changes share the target guard transaction. |
| sdp_operation | request_id PK; request digest and original response, including epoch/deadline or receipt. Same ID/different digest is rejected. |
| sdp_ack | ack_id PK; completed batch receipt, full consumer/partition/incarnation/generation identity, desired opaque cursor, request history and outcome. |

Use checked signed-64-bit database counters with explicit overflow errors; source cursors are versioned opaque blobs, never SQL integers. Foreign-key deletion must not cascade away receipts/intents. Detailed payloads are versioned canonical records. The adapter migration/version itself is checked before service admission.

RatifyData executes this one transaction (parameter names denote the sealed request):

~~~sql
BEGIN CONCURRENT;
-- Authenticate/authorize, then replay a matching sdp_operation if present.
UPDATE sdp_target SET revision = revision + 1
 WHERE target_key = :target AND authority_incarnation = :authority
   AND epoch = :epoch AND generation = :generation AND owner = :owner
   AND lease_deadline > :authority_now AND active_intent = :intent
   AND state = 'Running';
-- Require exactly one row. Validate the sealed preparation/validator digests.
-- Compare sink UUID and delta_head.version with the original expected head.
-- Insert the immutable delta_ratified_commit and CAS the delta_head.
-- Insert the matching sdp_effect_receipt and original sdp_operation response.
COMMIT;
~~~

Every intervening check failure rolls back. No object-store operation occurs in this body; files/staged JSON are already durably sealed. Takeover/reset also write sdp_target, so they conflict with this transaction under the selected MVCC semantics. The backend must demonstrate these properties with races and durable restart tests; the SQL listing is a specification, not evidence that a provider already implements it.

For Noop, omit the Delta head advance but check the exact sink UUID/head and insert the receipt while holding the same guard mutation. CompleteBatch separately checks both effect receipts and the old progress hash, sets progress only to the original intent's validated end vector, increments the sequence, clears active_intent and inserts ack work in one transaction. It cannot accept a caller-supplied arbitrary cursor. A duplicate completed operation returns its original result, not a fresh lease or a new effect.

## Delta publication and access policy

Carry a typed SDP write context, with the fence token, stable effect ID, intent/prepared digest, sink identity and original read versions, to the physical commit. Signed permits authenticate a request but do not replace checking current authority state.

The authority ratifies only immutable staged bytes and referenced durable files whose identities/checksums are sealed. A stage PUT with an unknown result must be resolved/verified before ratification. Unique staging names and create/version preconditions prevent overwrite. Missing files after confirmation are an integrity/restore failure, never grounds to reapply a confirmed batch.

After SQL ratification, backfill the already-committed version into the conventional Delta log. A crash/lost backfill response is repairable from the ratified action bytes. Backfill does not perform another data effect and must verify existing content rather than treating every AlreadyExists as a match. Catalog-aware readers use ratified heads/replay; finish the existing coordinator/read-bound TODOs before admission.

Fence permits are bound to the authenticated attempt/principal and checked against current authorization. Recovery does not hand an old private input archive to a newly authorized target writer automatically; require recovery access or leave the target blocked for an authorized repair/reset.

All enrolled writers, resets, DDL and maintenance use this authority. Deny ordinary unannotated mutations while enrolled, including writes through aliases. Restrict canonical-log publication credentials to the coordinator; stage/data permissions go to workers. Old/uncoordinated writers that can independently publish log files invalidate the fence guarantee. Compatible protocol profiles and storage permissions are admission requirements, not inferred from a catalog name.

Advertise a separate FencedSdpCommit capability only when control guard, ratified head and receipt truly share this transaction. Existing DeltaRatifiedCommit or a remote catalog commit API does not imply it. An external catalog cannot be combined with an unrelated local SQL lease by calling both APIs in sequence. Unsupported catalogs reject durable admission; ordinary batch behavior is unchanged.

Delta transaction application IDs/versions may be added as secondary deduplication/audit evidence. Their identity stays stable across ownership takeover and includes flow/checkpoint/effect scope. They are not the fencing token; current Sail checkpoint retention can discard transaction markers. Commit-info tags alone are audit data.

## The two-table CDC protocol

There is one target-wide slot across flows and pipelines. Execute:

~~~mermaid
stateDiagram-v2
    [*] --> IntentSealed
    IntentSealed --> Prepared
    Prepared --> AuxConfirmed
    AuxConfirmed --> TargetConfirmed
    TargetConfirmed --> ProgressCommitted
    ProgressCommitted --> AckPending
    AckPending --> AckConfirmed
~~~

Auxiliary and target commits each have a separate authoritative receipt. Their heads are not claimed to be a two-table atomic snapshot. Auxiliary state is internal; ordinary readers may see the old target while the auxiliary step has advanced. Another CDC flow or ordinary mutation cannot interleave until the unfinished batch is recovered/completed or explicitly retired by a fenced reset.

Materialize the complete nondeterministic/tied winner subplan once before the first effect, or reject it if sealing cannot make it replay-stable. Validate that sealed artifact, not a separately reevaluated source plan. Seal nondeterministic/tied winner selection before the first effect, and consume the same prepared artifact in both steps and every retry. A handler's idempotent MERGE conditions do not authorize recomputing a different winner. After the auxiliary receipt exists, prepare/read the target step against the recorded auxiliary version and fixed prepared rows.

If only the auxiliary effect is confirmed, takeover resumes that exact intent and finishes the target step. It does not hand the physical target to a different flow. If a target response was lost, lookup its receipt; do not replay both merges based solely on an absent final batch marker. The earlier Spark-style local replay tests remain valuable but do not prove cross-process fencing.

## Worked recovery trace

Start with generation4, ownerA/epoch12, flow batch41, target version90 and auxiliary version55.

| Event | Durable operation and recovery result |
| --- | --- |
| Capture | Store frontierF and seal intentI for the original source range; archive/validate prepared artifactP. |
| Auxiliary | Stage immutable actionsSA. RatifyAux checks epoch12, I/P and aux55, then atomically records aux56 plus receiptRA. |
| Crash after auxiliary response loss | A has no usable response. No progress/ack changed. |
| Takeover | B acquires epoch13 in the guard transaction, preserving I/P. A's delayed ratification with epoch12 is refused. If A had won before takeover, RA would already be present. |
| Resolve | B looks up RA by stable effect identity/digest and obtains Confirmed. B loads P; it does not repoll/reselect source rows or increment batch41. |
| Target | Stage ST against target90 and recorded aux56. RatifyTarget under epoch13 records target91 and RT; lose its response. |
| Second recovery | Lookup RT returns its exact digest/version. No second target effect is attempted. If it was a no-op, the checked-head no-op receipt serves the same purpose. |
| Complete | One transaction checks RA/RT, advances progress to I.end and next batch42, clears the target slot and queues the source ack. |
| Ack response lost | Persist ack Unknown; the committed progress and RA/RT remain authoritative. Restart cannot rerun I's data effects. Resolve or retry only the generation-scoped ack. |
| Later unrelated table work | Original receipts remain independently queryable; latest snapshot metadata need not contain them. |
| Receipt absent after retention/restore loss | Return Unknown/RecoveryEvidenceUnavailable and stop. No data replay and no additional ack is authorized. |

The implementation entry gate is this trace executed with the real SQL adapter and Sail Delta commit operators, including failpoints immediately before/after SQL COMMIT and backfill. The table is a specification, not a report of tests already run.

## Reset and checkpoint generations

Authorized BeginReset CASes the target guard, increments generation/epoch, reserves the next checkpoint index and marks Resetting. Old owners immediately lose ratification authority. Filesystem directory enumeration is not the allocator.

First preflight identity, permissions, source reset origin, retained replay coverage and pinned/archive input. Do not truncate a target and then discover that a requested historical source range is unavailable. A newly numbered checkpoint is not permission to silently start at the broker's current oldest position.

Resolve the old intent's authoritative effect prefix. Retain it and its receipts as completed or superseded-by-reset; do not advance its source progress or ack an unfinished range. Missing/unknown evidence blocks destructive reset.

Run fenced target truncate/replacement and auxiliary drop/recreation as distinct reset effects, recording old/new table UUIDs. Existing materialize::tables commands must carry this context; the current unannotated full-refresh path cannot be reused as a durability shortcut. FinalizeReset only after both effects are confirmed, enabling the new generation and its source reset policy. A crash mid-reset resumes the reset; no other flow is admitted.

Mirror the agreed warehouse/_checkpoints/destination/flow/n layout as a projection of the ledger. Use unambiguous escaped components and identity markers; names containing dots/slashes must not alias. Local JSON files are exports, not authority. reset.allowed=false retains Spark's ordinary-refresh downgrade and does not allocate a reset.

Never import an old unfenced JSON record as a fenced checkpoint automatically. Require an offline, quiesced reconciliation tool with positive effect evidence, or a new protected full refresh.

## Frontiers, acknowledgments and retention

Admit stateless bounded plans and SCD1 only, using the existing binding/admission/lowering machinery. No cross-batch joins, aggregates, watermarks or SCD2 are silently admitted. The completed AutoCDC-only graph gate decision does not waive provider/durability capabilities.

For Iggy, retain consumer/stream/topic/partition identity, incarnation and ownership context plus exact opaque cursor ranges. AutoCommit stays disabled. Establish retention protection before the first effect/ack, or archive the complete required captured range. At offset zero, do not invent a last-consumed predecessor to create a barrier. Retention gaps, incarnation changes and lost request history have distinct errors.

Acks follow confirmed effects and atomic progress. Use generation-scoped consumer identities or a broker-enforced fencing context so an old in-flight ack cannot mutate replacement progress. Ack uncertainty never changes a confirmed data outcome into uncommitted. Old consumer cleanup needs quiescence/request resolution; do not blindly delete retention barriers.

For Delta sources, capture table UUID/storage identity and a committed readable end version with explicit initial-snapshot/CDF/append-only semantics. Freeze per-batch version ranges and static-side versions. Ordinary file additions are not a substitute for row changes: reject updates/deletes without the required change-feed mode. Vacuum/time-travel retention must be pinned or input archived. Table recreation is a new incarnation, not a continuation at the same path.

V1 retains all operation/effect receipts and identity/digest tombstones without automatic GC. Pending intents, staged actions, prepared input and required source/static snapshots remain pinned until resolved. Completed payload GC is a later explicit protocol requiring progress, ack/recovery state, no in-flight work and the supported restore horizon. An expired archive/coverage marker causes a typed stop on old-checkpoint restoration, not fresh execution.

The store's backups and Delta/input retention must share a declared recovery horizon. Forbid unsafe vacuum, lifecycle deletion and retention-property changes on enrolled evidence. A restored/forked control database cannot serve with reused authority identity/epochs: reconcile the authoritative heads/ledger and rotate authority incarnation/credentials before reopening admission.

## APIs, integration and reviewable build units

Pure model operations: enroll, acquire, renew, seal/resume intent, prepare effect, ratify data/no-op, lookup, complete batch, begin/finalize reset and record/resolve ack. Distinguish Conflict, Fenced, IdentityMismatch, PreparedMismatch, SourceUnavailable, StateUnknown, EvidenceUnavailable and UnsupportedCapability. Cancellation is neither rollback nor proof that an external commit failed.

Use Sail's existing actors/JobService/TaskResourceScope and native commit operators. No control transaction spans job execution or network I/O. Source capture/scan and authority RPC need an async, ownership-aware operational boundary: retain typed SourceError causes, deterministic ScanError refusals and separate position effects from ASYNC-SOURCE-CONTRACT. Do not block inside the current synchronous bounded-source trait or map network errors to deterministic refusals. SDK deadlines bound observation, not queued work; use TaskResourceScope ownership and qualify client-worker shutdown. Cancellation records the request and preserves unfinished intent/effect evidence; it cannot clear the target slot merely because a local future stopped. Durable progress is not reconstructed from actor mailbox state. Proposed small modules are a pure control model, backend-neutral store/capability traits and an optional Turso adapter; extract only the guarded transaction/receipt kernel reusable by LakeCat/Grust.

Implementation units, each with its own human-reviewable source commit and exact gate:

1. Pure identities/state transitions, canonical request digests and lookup outcomes; deterministic crash/interleaving model tests.
2. SQL schema/adapter, immutable intents/receipts and guard-row conflict tests using real backend transactions, durable restart and unknown COMMIT outcomes.
3. Generic Sail catalog/write-context/worker-codec plumbing plus LakeCat/standalone adapter capability; reject missing fences on every enrolled mutation, including bootstrap and no-op.
4. Delta staged ratification/read replay/backfill and receipt lookup, closing existing coordinator gaps; stale-owner races through actual MERGE and reset operators.
5. Sealed input/validation archive, two-step CDC orchestration, atomic progress and generation-scoped ack/reset integration; execute the worked recovery trace.
6. Admission/activation vertical slice for one deterministic bounded source, then qualified Delta source frontiers and the Iggy fork adapter. Add providers only after their own uncertainty/retention tests.

Required fault matrix: takeover before/after each effect ratification; a stale commit racing acquire/reset; lost SQL/Delta/backfill responses; duplicate request with changed digest; no-op followed by later writes; competing flows/catalog aliases/control roots; target/aux recreation; failure between reset effects; source loss before first ack; delayed old-generation ack; expired receipts/archive; database restore/fork; worker codec dropping context; schema/bootstrap/unannotated DDL bypass. Inspect both physical tables, ratified heads, progress and acknowledgments.

Write the recovery trace as this document now, and create its executable conformance target alongside the first pure-model unit. Run it explicitly during subsequent adapter/commit units and preserve its unsupported/failing status until a real Turso authority and real Delta target satisfy the assertions. It is not a passing acceptance check before the fenced path exists. Do not substitute existing local idempotent-replay tests for this gate.

## Readiness and limits

This design answers the authority, fence, takeover/reset, receipt retention, admission, source frontier and recovery-trace questions in Fable's brief. New capabilities and deployment qualification remain implementation work. The initial deployment is one durable authority service; HA, additional catalogs and stateful streaming are separate qualifications. Existing ordinary batch/catalog behavior and honest local tests remain available. No claim of two-table atomicity, universal catalog support or completed Spark SDP conformance is made.

## Source provenance

The [pinned source audit](evidence/cdc-control-store-design/source-audit.json) records thirteen exact source files and content hashes across Sail, LakeCat, Grust and Fable's gated runner. The [request brief](evidence/cdc-control-store-design/CONTROL-STORE-ASTRA-BRIEF.md) and [async ownership contract](evidence/cdc-control-store-design/ASYNC-SOURCE-CONTRACT.md) are preserved alongside it. The audit verifies the cited seams and limitations; it does not constitute a backend or crash-test result.
