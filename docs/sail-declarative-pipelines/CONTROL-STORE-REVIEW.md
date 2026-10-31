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
2. **Sink incarnation needs a seam the pin does not have.** The design keys
   fencing on the immutable Delta table UUID (the `Metadata` action `id`)
   and the auxiliary table's UUID. `LakehouseExecutionContext` and
   `TableKind::Table` carry location and format but no table id; the id is
   available from the Delta log at commit time and must be threaded into the
   write context in unit 3. Not a contradiction; an explicit seam to add.
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
