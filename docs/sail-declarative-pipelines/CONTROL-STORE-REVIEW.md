# Review of `CDC-CONTROL-STORE-DESIGN.md` (Codex, CF-0556)

Reviewed by Fable on 2026-10-31 against the design's pinned sources
(SHA-256 `0c2f9970…ba2317`, source audit of thirteen files), as CF-0555
agreed: verify, improve, then build.

## Source claims checked

| Claim                                                                                                                                               | Pinned source                                                                                                                                       | Result |
| --------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Sail stages a Delta commit, ratifies it through the catalog, then backfills the log                                                                 | `commit_exec.rs:1038–1075` at `7f7a14eb`: staged commit → `commit_catalog_managed_table` → `publish_staged_commit`, publication failure only warned | Holds  |
| `CatalogProvider::commit_lakehouse_table` / `get_delta_ratified_commits`, `CommitAuthority::DeltaRatifiedCommit` exist                              | `sail-catalog/src/provider/mod.rs:148–165`, `lakehouse.rs:65–77`                                                                                    | Holds  |
| MERGE planners reach `DeltaCommitExec`                                                                                                              | `op_merge.rs:354`                                                                                                                                   | Holds  |
| Bootstrap and metadata-only branches still publish with a direct `CommitBuilder`                                                                    | `commit_exec.rs:965, :1004, :1081` beside the ratified path at `:1038`                                                                              | Holds  |
| Coordinator lists outstanding reconciliation work                                                                                                   | `coordinator.rs:32` TODO                                                                                                                            | Holds  |
| Checkpoint retention can discard transaction markers                                                                                                | `checkpoint/mod.rs:69–81` `transaction_expiration_timestamp`, `:113–149` `txns` map                                                                 | Holds  |
| LakeCat's Turso store gives MVCC `BEGIN CONCURRENT` transactions with a bounded retry loop and idempotency records, not a Delta/control transaction | `lakecat-store/src/turso_store/mod.rs:37–158, :219–233` at `27e18f39`                                                                               | Holds  |
| Grust's guarded commit stores the receipt in the transaction and recovers it by idempotency key                                                     | `grust-turso/src/guarded_commit.rs:28–81` at `e90e80be`                                                                                             | Holds  |
| `MergeIntoOptions` has no write context                                                                                                             | `datasource.rs:315–330`                                                                                                                             | Holds  |

The atomicity argument (guard row mutated in the same transaction as the
ratified head and the receipt; takeover and reset also mutate the guard row,
so a stale ratification and a takeover have exactly two serial outcomes) is
correct for one MVCC database with write-write conflict detection on the row,
which is what the pinned Turso store runs. Lease time from the authority
only, expiry as permission rather than proof, and lookup outcomes that never
authorise a rerun are consistent with `ASYNC-SOURCE-CONTRACT.md` §3.

## Findings

1. **A contradiction in my own write component, which the design is right
   about.** `autocdc/write.rs` publishes the reconciled microbatch as a
   temporary view over a lazy `LogicalPlan`; the auxiliary merge and the
   target merge each execute that plan again. The deduplication keeps one
   of several tied rows by `max_by`, and nothing pins the same winner across
   the two executions, so the two merges can consume different winners.
   The design's rule, "seal nondeterministic/tied winner selection before
   the first effect and consume the same prepared artifact in both steps
   and every retry", is the fix: materialize the reconciled rows once and
   publish the materialized batch. Built first (below), independent of the
   store.
2. **Sink incarnation: half the seam exists.** `CatalogTableIdentity.table_id`
   (`lakehouse.rs:8`) and the coordinator's `table_id` carry the
   catalog-managed table identity to the commit path; the Delta log's
   `Metadata` id and the auxiliary table's identity are not threaded into
   `MergeIntoOptions`, which has no write context. Unit 3 adds the typed
   context and checks both; not a contradiction.
3. **Turso in Sail is an unqualified dependency.** The design's first
   adapter needs the Turso/libsql client in the Sail workspace, where no
   SQLite-family dependency exists today. After the Iggy SDK conflict
   (finding D1) this must be resolved by a `cargo check` of the dependency
   before unit 2 is scheduled; if it conflicts, the adapter lives beside
   LakeCat and Sail talks to the authority as a service, which the design
   already allows ("exposed through a service").
4. **Improvement, build order.** Unit 1 (pure model) and the executable
   recovery-trace target need no shared change and no backend; they are the
   CDC lane's next units. Units 3 and 4 touch `sail-common-datafusion`,
   `sail-catalog` and `sail-delta-lake`, the batch lane's files; their scope
   is declared before any edit. Unit 2 waits on finding 3.
5. **Improvement, local record.** A5's record stays as the labelled
   unfenced test mode the design permits; the design's "never an automatic
   fallback" becomes a constructor-level distinction (`Authority::LocalUnfenced`
   only reachable from tests and an explicit option), not a runtime fallback
   path.

Verdict: the design is sound against its sources and is the build
specification; the one defect found is on my side (finding 1) and is fixed
first.

## Build plan under this review

- B0 (now): materialize the reconciled microbatch once in `write.rs`; the
  merges and every retry read the same rows. Test: a tied batch produces the
  same winner in both effects.
- B1: `crates/sail-sdp-control`, dependency-free pure model: identities,
  fence token, state transitions (enroll, acquire/renew, seal/resume intent,
  prepare, ratify data/no-op, lookup, complete batch, begin/finalize reset,
  record/resolve ack), canonical request digests, typed outcomes; model tests
  for the fault matrix's interleavings; the recovery trace as an executable
  target against an in-memory store that is explicitly not an authority.
- B2: store trait and the Turso adapter, after finding 3 is answered.
- B3/B4: write context, Delta identity and fenced ratification on the shared
  path, declared first.
- B5/B6: sealed input archive, two-step orchestration over the model, then
  the admission slice.

## Build log

- B0 done: `write.rs` seals the reconciled rows once (MemTable scan published
  as the view); structural test plus a tied-events case; 316 pipelines tests
  pass. Commit on the CDC branch after `4fc62deed`.
- B0 gated: `28515224e` passed every gate step at 2026-10-31T20:42:28Z.
- B1 done: `crates/sail-sdp-control` at `2d4174d0c`, gated with no regression
  at 2026-10-31T20:45:19Z. The gate script does not cover the new crate, so its
  fmt, strict clippy and 22 tests ran separately; one test is ignored until the
  adapter exists.
- Writing B1 against the design corrected five first-draft errors of mine:
  completion took a caller-supplied cursor; a crash mid-reset could not resume;
  reset handed out no token and did not rebind recreated identities; the
  prepared digest was recorded outside the fence; a finished intent could be
  sealed back into the slot. A retry under a new request id could also replace
  a receipt.
- The first B1 tests passed but left eight of seventeen mutated guards
  undetected. One guard was dead and was removed. Direct tests now fail for
  all sixteen remaining mutations.
- Finding 3 resolved: Turso 0.7.2 builds in the Sail workspace, and the probe
  in `evidence/turso-control-probe/` shows the guard-row property under race
  and process kill, with a negative control. Power loss, shared-file access
  and restore remain unqualified. The adapter can live in the workspace.
- B2 done: `947f5e113`. `control.rs` holds the operations over a small store
  seam, so the in-process store and the Turso adapter share one code path. All
  scenarios run on both, 58 tests. Tests inject a takeover between an
  operation's guard read and its commit, because the race test alone left the
  guard-row writes unpinned. Every mutated guard now fails a test, and the
  racing tests passed 10 of 10 release runs with all 10 cores saturated.
- B2 also closed gaps found against the design: initialization intents, unique
  physical keys, the auxiliary recheck at ratification, escaped key components,
  and lease time read only from the authority's clock.
- Known B2 limits: `delta_ratified_commit` is not recorded yet and arrives with
  the staged commit in B4. Incarnation rotation for a restored database is not
  implemented. Enrolling a table that already has Delta versions needs an
  initial head, also B4.
- B3/B4 done: `2a2cb8454`. An optional fence travels from the MERGE spec through
  `MergeIntoOptions`, the Delta planner and the worker codec to
  `DeltaCommitExec`. A fenced commit stages, ratifies, and publishes only a new
  ratification. A retry that replays a receipt keeps its own staged entry
  unpublished, because publishing it would append a second log version. An
  unfenced write to an enrolled table and a fenced write with no authority are
  both refused at the commit node, so choosing another operation does not remove
  the fence.
- B5 done: `bf4fb115c`. `run_durable_flow` seals, archives, merges with stable
  request identities, and completes. Tests crash at each stage of a batch and
  check both tables, heads and checkpoint, and the worked recovery trace runs on
  real Delta tables with the Turso authority reopened from disk.
- Design points B3 to B5 settled by building:
  - An unratified preparation is replaced by a new attempt, in the ratification
    transaction. Keeping it would strand recovery, since a rerun stages a new
    file name.
  - Enrolled tables need in-commit timestamps. Ratified staging takes its
    timestamp from the commit, and the auxiliary table inherits the property.
  - A Delta table has no log, and so no identity, until its first commit. An
    empty unfenced merge before enrollment writes version 0.
- Known limits after B5:
  - The auxiliary table and that first commit are still created unfenced, before
    enrollment. The design's Initialization intent exists in the model and is
    not yet used by the run.
  - Fenced commits refuse catalog-managed tables. V1 covers filesystem-managed
    Delta tables, and the merge is the only fenced operation.
  - Reset is modelled and tested in `sail-sdp-control`, but `materialize::tables`
    does not yet run it through the authority.
  - The fence is checked only in the session process; a worker without the
    extension refuses, so fenced commits run in local mode.
  - B6 (admission in `execution::execute`) and the Iggy adapter remain.
