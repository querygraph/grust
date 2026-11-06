# Fenced commits for streaming tables

A restarted pipeline must prevent an older writer from changing its tables
after a successor takes ownership. A lease determines when takeover is allowed;
a fence rejects obsolete write authority at the point a commit is accepted.
Every admitted durable target needs that protection, including managed Delta
and Iceberg. Missing fencing is implementation work, not a reason to weaken
the guarantee to an externally managed single writer.

## Why ordered commits are insufficient

Suppose writer A holds ownership number 7 and pauses. Writer B takes ownership
number 8 and commits. A resumes, reloads the latest table version and submits
a write based on that version. A normal compare-and-swap can accept it: the
metadata version is current, but the writer's authority is obsolete.

Checking a lease before submitting the write has the same gap if takeover
occurs between that check and acceptance. The authority accepting the effect
must check ownership and reserve or commit the effect in the same serialized
operation. Retries must repeat that check without replacing the request's
meaning. Correct table-version ordering is useful, but it is not this fence.

## Build on existing commit boundaries

Sail already routes table writes through format-specific commit operators and
catalog interfaces. Those are the enforcement points. Adding a separate check
in the pipeline scheduler would leave other write paths and paused workers
able to bypass it.

A bounded change-capture implementation provides reusable reference code for
filesystem-managed Delta: stage exact log bytes, record their approval in a durable
commit service, then publish by creating the log entry only if absent. The service retains the
staged path and digest so a successor can finish an accepted publication.
Its table property and server registry reject unfenced cooperating Sail writers.
This is not yet a universal or distributed StreamSource commit capability.

| Target path | Existing primitive | Required addition |
| --- | --- | --- |
| Filesystem-managed Delta | Staged log entry and create-only publication; reference authority can ratify an exact effect | Generalize ownership to admitted append and change-capture writes, creation, reset and worker execution; establish who may publish log entries |
| Catalog-managed Delta | Catalog ratifies versions and controls table commits | Bind owner generation and effect identity to catalog acceptance or an enforced commit service |
| Iceberg through a catalog | Snapshot requirements and conditional metadata publication | Enforce the same owner generation and effect identity at that publication boundary |

The current bounded writer routes managed Delta and Iceberg to a plain path.
That choice must be removed. The existing fenced Delta operator also refuses
new or catalog-managed tables, so its interface cannot simply be attached to
every target. Each adapter must provide the required contract.

## One explicit commit capability

Represent fenced commit support as a capability with verified semantics,
rather than infer it from a format name or the presence of catalog transactions.
Extend the existing lakehouse execution context and commit requests where
possible. Each accepted effect must bind:

- The authority domain and immutable table identity, not just its path or name.
- The target generation and current owner number.
- A stable operation identifier, checkpoint or refresh identity, and effect identifier.
- The expected table head or equivalent precondition.
- A digest identifying the prepared rows, configuration and exact effect being accepted.

The accepting authority checks ownership, target identity, preconditions and
request identity together. Repeating the same accepted request returns its
recorded result. Reusing its identifier for different content is an error.
A rejected stale writer cannot become current merely by refreshing metadata.

Keep accepted, definitely rejected, retryable conflict and unknown-outcome
responses distinct. A timeout after submission does not prove failure. Resolve
it by the same operation identity; do not issue a new write or delete its
staged files while acceptance is uncertain.

A control database may authorize publication before the storage write occurs.
In that design, authorization is the durable acceptance point and must reserve
the exact next effect. After takeover, either writer may finish publishing
those already accepted bytes. That is completion of an earlier decision, not
permission for the old owner to authorize new work. The successor must resolve
such effects before advancing conflicting table state.

## Cover every visible mutation

The fence must cover append, merge, delete, overwrite, schema changes, full
refresh and table recreation, including maintenance that changes reachable
state. A no-op still needs an identity-bound outcome when recovery depends
on whether that step completed. Two-table change capture needs protection for
both tables; a single-transaction layout needs it at that transaction's boundary.

Creation requires an atomic reservation of the absent target identity and
initial generation. A table with no log head must not create an unfenced
bootstrap exception. Enrollment and ownership metadata must become authoritative
before ordinary writers can modify the new target. A recreated table has a
new identity even when it reuses the same location.

Refresh must reconcile accepted effects before switching generations. Unaccepted
work may be explicitly superseded; accepted publication cannot simply be abandoned. Cleanup must respect accepted-but-unpublished effects and every
snapshot or artifact still referenced by recovery. Losing a lease does not
make pending data disposable.

Carry the operation identity and authority reference through the physical-plan
codec to the running task. A serialized token alone is insufficient: the worker
needs an authenticated route to the accepting authority. Authority failure
must stop acceptance, not fall back to an unfenced write. Process-local
registries are useful caches, not the durable source of ownership.

## Prevent bypass by other writers

A custom table property checked by Sail does not make other engines enforce
that property. The deployment must put every permitted writer behind the
same commit authority or a protocol requirement those writers must respect.
Direct storage credentials that allow bypass publication are incompatible
with a universal fence claim.

For catalog-managed Delta, the
[Delta protocol](https://github.com/delta-io/delta/blob/master/PROTOCOL.md#catalog-managed-tables)
already requires writers to use the catalog's commit protocol. That is a useful
place to enforce ownership, but ordinary catalog ratification does not imply
that it checks Sail's owner number. A new mandatory writer feature is another
possible protocol change; it needs an interoperability and deployment design,
not an invented property that existing writers silently ignore.

Iceberg's [commit model](https://iceberg.apache.org/spec/#table-metadata)
uses atomic metadata replacement, with the atomic mechanism supplied by the
catalog implementation. The catalog adapter or enforced commit service must
supply ownership enforcement. If the available service cannot do so, build
that capability before admitting the target for durable streaming.

Prefer an existing catalog enforcement point. Add a Sail-owned commit service
only where the backend cannot express the contract and access controls can
make that service authoritative. Document its availability and operational
cost. Neither a preflight lease check nor an optimistic retry loop is an
acceptable substitute.

## Durability and takeover

Ownership state must survive process failure and be shared by all potential
owners. A database file qualified only for one authority process does not
establish multi-host takeover, backup restoration or power-loss durability.
Choose and qualify those deployment properties explicitly.

Restoring or cloning an old authority must not recreate valid ownership over
a newer table. Bind the authority incarnation and target generation to the
storage acceptance contract. A durable shared authority needs one coherent
history; copied local state is not a second independent authority.

Do not conflate fencing with atomic visibility across several tables. Fencing
prevents obsolete owners from authorizing new effects. A multi-table protocol
must still define partial visibility and recovery, or use a genuinely atomic
target transaction when the target supports one.

## Required implementation and tests

Generalize the existing commit seam and implement filesystem Delta,
catalog-managed Delta and Iceberg adapters against the same behavioral contract.
Remove the plain durable-write fallback. Extend target creation, refresh and
worker-to-authority transport together with the adapters that use them.
Targets remain unadmitted until their enforcement tests pass; this is an
implementation dependency, not a permanent single-writer workaround.

For each admitted path, pause an owner after its last check, allow takeover,
then resume it before acceptance. Also resume after acceptance but before
publication to verify that only the exact accepted effect can finish. Repeat
with a lost response, changed content under the same identifier, table
recreation, refresh and source retry. Exercise every write entry point and a
second permitted client that does not hold the current token.

The reusable Delta path contains tests for stale owners, unfenced writes,
replayed requests and recovery after ratification. Those tests do not qualify
managed catalogs, Iceberg, external writers or distributed authority transport.
The design requires new evidence at those actual commit boundaries before
claiming coverage.
