# How the SDP work affects the Sail extensions proposal and the Sail book

Assessed 2026-11-02 by the Fable 5.1 session, read-only, against:

- the SDP root `6f862b188` on `work/spark-declarative-pipelines` (querygraph/sail);
- the extensions branch `sail-extensions` at `a20d660d9` ("publish review request version 1.0.0"), whose substance is `docs/development/extensions/design-review.md`, `abi-review.md` and `datafusion-graph-plan.md`, with the review harness and evidence bundles on Morrobay under `src/sail-extensions-gates`;
- the Sail Rust Book (`~/src/book-sources/sail-rust-book`, 19 chapters, 55,500 words, the 0.7.2 preparation edition).

The two branches fork at `a85d912d7 feat: support v3 MOR operations for Iceberg (#2655)`: 31 commits are only on the extensions side, 491 only on the SDP side.

## The short answer

- **Merging the two is a real job, not a rebase.** A dry three-way merge (`git merge-tree`) of the extensions branch onto the SDP root conflicts in 23 files. The conflicts are not scattered: they sit on exactly the host seams the extensions proposal names as its "necessary host contracts", because SDP rewrote those seams for its own needs (session lifecycle, the Connect executor, the job scheduler, the physical-plan codec, the resolver's expression path).
- **The proposal's design survives; its evidence does not.** None of the SDP changes contradict the proposal's contracts (bounded relation entry point, trusted registration, worker identity, host-funded memory, lifecycle coverage). But the lifecycle and distributed-execution evidence in `design-review.md` was produced against a session layer and a driver that no longer exist in that form, so it must be re-run after the merge, and the review harness on Morrobay re-pointed at the merged tree.
- **The book needs one new chapter and revisions to six.** Chapters 8, 10, 12, 16 and 17 describe code SDP changed materially; chapter 13 (extension architecture) must account for the new session layer; chapter 3 gains the pipeline commands. ORC, which the book does not mention, is now a first-class format.

## Where the conflicts are, and why

| Area | Files in conflict | What the extensions side did there | What SDP did there |
|---|---|---|---|
| Session manager (`sail-session`) | `session_manager/actor/{core,handler}.rs`, `session_manager/mod.rs`, `session_factory/worker.rs` | Extension loader state per session, native admission domains owned by the session manager, worker loading of packages | Rewrote the lifecycle: Creating/Running/Deleting/DeletionFailed/Deleted/Failed states, one shared cleanup record, owned concurrent shutdown, checkpoint cleanup after operations close. `handler.rs` is rewritten on both sides (ext +327/−254, SDP +283/−153). |
| Session lifecycle contract (`sail-common-datafusion`) | `session/lifecycle.rs`, `lib.rs` | Resource-governance hooks for native extensions | Operation closing before checkpoint removal; the fenced-commit and ORC sink modules |
| Spark Connect server layer | `executor.rs`, `session.rs`, `session_manager.rs`, `server.rs`, `entrypoint.rs`, `error.rs`, `proto/plan.rs`, `service/plan_analyzer.rs` | Relation-extension dispatch, interrupt and early-termination coverage for native regions, embedder-chosen session factory | Typed command events and heartbeats through the executor, reliable "session closed" to clients, pipeline command handling and the query-function guard in the analyzer, structured errors, fenced writes on `Write` |
| Driver and codec (`sail-execution`) | `driver/job_scheduler/core.rs`, `job_graph/planner.rs`, `proto/codec.rs` | Driver placement of native regions and bound-plan registry (+793/−273 in the scheduler; +1086 in the planner; +3887 in the codec for extension plans) | Stopping drivers abandon job output forwarders and mark canceled jobs; new physical nodes with codec support (owned ORC sink, fenced Delta commit, cast policies) |
| Resolver and functions | `resolver/expression/mod.rs`, `scalar/array/spark_array.rs` | Extension scalar functions; geometry field metadata through array construction | Constant contexts for `SET CATALOG`/IDENTIFIER, structured ambiguity errors, ANSI cast UDFs |
| Build | `Cargo.toml`, `Cargo.lock`, two crate manifests | New workspace members and FFI dependencies | New crates (`sail-sdp-control`, `sail-iggy-bounded`), orc-rust, Turso |

The remaining 168 files both branches touched merge cleanly.

## Effect on each host contract of the proposal

1. **Bounded relation entry point** (`proto/extension`, `resolver/query/extension.rs`, `connect_extension.rs`). Untouched by SDP. But SDP added request-local state to `PlanResolver` (`relation_scope`, `query_session`, `source_read_case_sensitive`) and a scoped-session capture; an extension handler that resolves child plans must do so through those, or a pipeline's graph-local names and streaming marks will not reach it. Small.
2. **Trusted registration and explicit compatibility** (`sail-session/src/extensions`). The loader keeps "per-session bound state separate from process-retained code". SDP's session manager now owns one cleanup record per session and a Closing/terminal manager state; the extension's per-session state must be released through that record (not on actor drop), or a session with native state can report a false clean deletion. This is the heaviest rework, in the files that conflict most.
3. **Worker identity and complete expression fields.** The codec conflict is mechanical (both sides add nodes). The worker now joins its task runner before stopping its server and the driver aborts output forwarders on stop; an extension's worker-resident state that assumed the old stop order should be re-checked, though nothing in the proposal depends on it.
4. **Host-funded native memory.** Independent of SDP, except that SDP's `TaskResourceScope` (seal, latched cancel, drain) is now the owner of a task's effects; a native quota lease that outlives a task must be a resource of that scope to be drained at stop.
5. **Lifecycle coverage** ("interrupt, early consumer termination, session deletion/expiry and graceful shutdown"). This is the evidence that no longer applies as recorded: SDP changed interrupt semantics (flows are stopped), session deletion (tombstones, sticky failures, no resurrection), shutdown (exit 1 on unconfirmed cleanup, 5 s worker-stop bound, 30 s driver bound) and the settled-failure rule. The matrix in `design-review.md` §"Evidence" must be re-run on the merged tree; the pass/fail expectations for deletion and shutdown will differ where SDP made a previously silent success an error.
6. **Deployment and ABI** (`abi-review.md`). Unaffected in substance: SDP changes no FFI boundary and no DataFusion/Arrow version. The pinned host revisions in `hosts.json` predate SDP, so the "unchanged wheel passes a new host revision" claim should simply gain one more host revision (the merged tip) in the matrix; that is a rerun of the Morrobay harness, not a redesign.

The datafusion-graph-plan (Nutmeg graph tables as relational plans, native kernels by explicit choice) is independent of SDP in design. Its gate procedure assumes the old session manager for staging state (`stage`, `drop`), which is contract 2 again.

## The Sail Rust Book

| Chapter | Status after SDP | What changes |
|---|---|---|
| 3 Spark Connect | revise | The six pipeline commands (`CreateDataflowGraph`, `DefineOutput`, `DefineFlow`, `DefineSqlGraphElements`, `StartRun`, `DropDataflowGraph`) and the event stream; typed command events and heartbeats; the closed-session response. |
| 8 Drivers, workers, tasks, streams | revise | Session lifecycle states and the cleanup record; stop ordering and the two bounds; canceled-job output; the task resource scope and the settled-failure rule; the preparation lease. |
| 10 Spec and plan resolver | revise | Request-local resolver state (relation scope, scoped query session), constant contexts for `SET CATALOG`, structured errors, the ANSI cast UDFs, the TIME type. |
| 12 Catalogs, lakehouse, file formats | revise, add ORC | Shared memory catalogs, HMS purge semantics (data-deleting `DROP DATABASE`), case-insensitive memory table names, the ORC reader and writer (absent from the book today), the fenced Delta commit path. |
| 13 Extension architecture | revise | Everything in the table above about the session layer; the extension loader's place in the new lifecycle. |
| 16 Local and streaming execution | revise | Bounded microbatches as AvailableNow, `BoundedSource`, checkpoints under the storage root, the Iggy source, AutoCDC and the control store. |
| 17 Testing Spark compatibility | revise | The frozen 300 + 67 ports, Spark-first measurement, the gates, the whole-tree comparison, the Spark oracle runs. |
| new: Declarative Pipelines | add | The pipelines module end to end; the user manual being written now is the source. |
| 1, 2, 4–7, 9, 11, 14, 15, 18, 19 | unchanged or a line | Chapter 19's roadmap should list SDP as delivered at milestone 1. |

The book mentions "declarative" once today.

## Recommendation

- Do not merge the extensions branch onto the SDP root until M1 closes; the session-manager rewrite is still receiving fixes (the CDC lane's C1 fence registry is in that layer too).
- Then merge in the extension branch's order of units, resolving the session manager first: port the extension loader's per-session state onto the cleanup record, and its native admission domains onto the manager's Open/Closing states. Expect the 23 conflicts to take a day of careful work, mostly in `session_manager/actor/handler.rs` and `executor.rs`.
- Re-run the lifecycle evidence and the Morrobay ABI harness on the merged tip, and add that tip to `hosts.json`. Keep the proposal's text; replace its evidence section.
- Revise the book's six chapters and add the pipelines chapter from the manual; the ORC material is new.

## The performance branches

Assessed the same day, read-only: `agent/sail-performance-hot-paths` (22 commits, 2026-08-08), `agent/sail-performance-alignment` (36, 2026-08-09, the LakeCat-aligned variant) and `agent/grust-performance-alignment` (31, 2026-08-09, adds the graph-extension parser work). All three fork from August upstream (`3c000fd86` or `7da486db9`), two months before the SDP base `0ba425c03`.

**What they optimized.** Six hot sites, each with a criterion bench: Iceberg metadata discovery (streamed, searched from the newest snapshot, deserialized directly), manifest parsing (a reused Avro reader), the delete index (shared descriptors, routed file matching), current-snapshot lookup, single-statement SQL parsing, and an object-store read-through cache on Foyer (fast-path hits, single-page reads, reused locations) with a consistency model documented in `docs/guide/performance/index.md`. No commit body or document records a measured number; the evidence is the benches themselves.

**How the work holds against the SDP root.**

| Hot site | What happened since the fork | SDP's own part |
|---|---|---|
| Iceberg metadata, manifests, delete index (`sail-iceberg`) | Upstream rewrote all of it: `datasource/provider.rs` is gone, `delete_apply_exec.rs` +874/−127, `manifest/mod.rs` +729, `delete_index.rs` +308, `metadata_loader.rs` +109 (v3 MOR, metadata-discovery and manifest fixes #2542/#2544/#2853). The branch's changes do not apply to this code. | None. SDP did not touch `sail-iceberg`. |
| SQL frontend parsing | Upstream removed the parser cache and upgraded Chumsky (#2786) and fixed a parser memory leak (#2789); the single-statement specialization targets a parser that no longer has that shape. | Small: the pipeline statements and keywords (+20 lines in `sail-sql-parser`, −10/+8 in the analyzer's `parser.rs`). |
| Object-store Foyer cache (`layers/cache.rs`) | Never reached upstream; the file does not exist on the root. The standalone `feat/object-store-foyer-cache` branch conflicts with the root in 9 files. | SDP reworked the object-store layers for owned stores and multipart supervision (`layers/runtime*.rs`, `owned_multipart/`), which is where the cache layer would have to re-home. |
| Physical-plan codec | Upstream and SDP both added nodes (+3853/−567 since the fork in all; SDP +337). | Mechanical conflict only. |
| Catalog provider seams (alignment branch: `provider/mod.rs`, `options.rs`, `sail-catalog-iceberg`) | The LakeCat branch's planning helpers and commit-table seam (PRs #2134/#2135/#2140); SDP added `SHOW CREATE TABLE`, the HMS purge semantics and shared-memory catalogs on the same files. | 18 conflicts for the alignment branch, 10 for hot-paths, 14 for the grust variant. |

**Verdict.** The performance work does not hold as code: its hot sites were rewritten upstream between August and October, independently of SDP, and its six benches are not on the root. SDP's contribution to that drift is minor (the parser's pipeline statements and the codec); the one place SDP matters is the object store, where the Foyer cache layer would now sit beside owned stores and the multipart supervisor. The ideas hold: streaming discovery, a reused Avro reader, delete-file routing and a read-through cache are still the right targets, but whether upstream's rewrites already captured the gains is unknown, because nothing recorded the before/after numbers.

**What it would take to know.** Port the six benches onto the root (they are self-contained criterion files), run them on the root and on the branch's own tip, and record the numbers in the repository this time. The parser and object-store benches port in an hour; the Iceberg ones need rewriting against the new types. Do this after M1 closes and after the extensions merge, since the object-store layer is involved in both.
