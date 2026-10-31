# Control store for durable SDP runs: brief for the Astra design checkpoint

Prepared by Fable on 2026-10-31 so the user can switch to Astra with the
facts pinned. This is the "Next Astra design checkpoint" row of
`SDP-FABLE-DESIGN-REVIEW.md` (select the atomic ownership/progress
mechanism, prove sink fencing and reset, define the admission boundary,
specify frontiers and receipt retention) and the "Astra decisions before
production effects" section of `STREAMING-CDC-PARALLEL-HANDOFF.md`.
Decisions already taken by the user today: the execute gate opens only for
AutoCDC-only bounded graphs; checkpoints mirror Spark's layout under the
warehouse; the Iggy adapter lives in the sail-iggy fork lineage.

## What exists (all gated, chain tip `4fc62deed` on Codex `7cf0254bc`)

- A local run record per flow (`autocdc/run.rs`): captured frontier,
  progress, continuing batch id, written by rename; single writer, no
  fencing, and it says so in an `authority` field.
- Replay safety at the data level: the auxiliary and target merges are
  idempotent for a replayed batch (18 executed cases plus a run-level replay
  test), which is Spark's own retry argument.
- Bounded intents with immutable incarnations and explicit ranges, a
  lowering snapshot (descriptor digest, ranges, statics, locals, conf) per
  batch, and `DeterministicSource` for tests.
- Prepared-input identity and validation receipts (`autocdc/prepared.rs`,
  unit 5 of the old branch): a sealed digest of what was validated.
- Iggy facts from the pinned broker (`evidence/fable-iggy-harness`):
  accepted-but-unconfirmed acks under partition loss, owner generations,
  silent retention gaps, recreation under a new incarnation.

## What is missing (the checkpoint's own list)

1. One atomic authority for ownership and progress across processes.
2. Sink fencing: a stale owner's commit to the Delta target or auxiliary
   table must be refused, with takeover and reset defined.
3. Preserved original intents and receipt retention, including no-op
   receipts, so a replay after an uncertain outcome neither re-applies nor
   loses a batch.
4. Target-wide coordination for CDC: two tables (auxiliary, target), two
   MERGEs, one batch; "per-flow leases and two transaction IDs do not
   provide a two-table transaction" (handoff). Confirm unfinished work before
   admitting a different flow on the same physical target.
5. A worked recovery trace through real backend and Delta operations before
   the production control-store/run-actor path.

## Constraints found while building

- Sail's Delta write path exposes no application transaction identifier
  (`txnAppId`/`txnVersion`) in `MergeIntoOptions` or the lake-source API, so
  Delta's idempotent-write fencing is not reachable from the merge resolver
  today; adding it is a shared `sail-common-datafusion`/`sail-delta-lake`
  change (batch lane).
- The bounded-source trait is synchronous with deterministic refusals; the
  typed operational errors (`SourceError`) exist but the trait does not
  return them yet (`ASYNC-SOURCE-CONTRACT.md` §3 holds the ownership rules).
- `execution::execute` rejects every streaming output before
  materialization; the agreed arm admits AutoCDC-only bounded graphs.

## Candidate mechanisms to choose between

A. **Delta control table.** One table `_sdp_control` (pipeline, flow, epoch,
owner, lease_until, progress JSON, last receipt). Ownership and progress
advance by conditional MERGE on the expected epoch; Delta's optimistic
commit gives the atomicity. Fencing of data commits needs the epoch
carried into the Delta commit (transaction identifier or a commit-info
tag checked on conflict), which requires the shared change above.
B. **Catalog-backed lease plus Delta commit check.** Lease and epoch in the
catalog (LakeCat provider) with conditional updates; data commits carry
the epoch as above. Fewer Delta commits per batch, two systems to keep
consistent.
C. **Local file record with advisory lock**, the A5 default extended with
an epoch and an exclusive lock file. Single host only; no fencing against
a second host; honest for triggered local runs, not for production.

The two-table problem (item 4) is independent of A–C: the proposal on the
table is a batch receipt written after both merges, keyed by (flow, batch
id, intent digest), and a recovery rule that re-runs the auxiliary merge
(a no-op by its conditions) before the target merge when the receipt is
absent, which is what A5's replay test already demonstrates for the local
record.

## Questions for Astra

1. Which of A/B/C is the authority, and what is the fencing token's path
   into a Delta commit (transaction identifier, commit-info tag, or a
   conditional read of the control table inside the merge)?
2. Takeover and reset semantics: who may increment the epoch, what a stale
   owner observes, and how a full refresh (new checkpoint version) interacts
   with an in-flight lease.
3. Receipt contents and retention: per batch, which of intent digest,
   lowering snapshot, validation receipt, source offsets and effect
   outcomes are kept, and for how long.
4. The admission boundary: stateless bounded flows only (today), or the
   first stateful operator class, before the control store lands.
5. Frontier capture for lakehouse-table sources (Delta version ranges,
   table UUID as incarnation), since AutoCDC sources will not only be Iggy.
6. Whether the recovery trace (item 5) is written as a document first or as
   a failing test against `DeterministicSource` plus a Delta target.

Fable's estimate: one Astra session for the decisions; then three to five
implementation units (store adapter, epoch/lease transitions as pure code,
fenced-commit plumbing on the batch lane, receipts, the recovery trace as
tests), each gateable as the CDC units were.
