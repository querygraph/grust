# Fable continuation handoff

Snapshot written 2026-10-31T20:59:31.247215+00:00, updated by the Opus batch-lane checkpoint below. Live coordination read through **CF-0565**.
Re-read live channel/Git/process state; later entries supersede this snapshot. [Initial scope](codex-fable-handoff.md). User requested stopping at this qualified checkpoint and handing Codex’s batch lane to Opus, using this existing file only. Fable continues its independent CDC lane. After this handoff is committed, pause root goal bookkeeping and await user resume; full objective remains incomplete.

## Goal and current truth

The user goal remains: **design and build Sail Declarative Pipelines, targeting Spark 4.2.1, and pass all Spark SDP tests**. Keep that full objective active.
Batch comes first, then streaming/Iggy and CDC, in human-reviewable increments. Do not redefine success as the currently passing helper or public selection.

Substantial batch/SQL/catalog/ORC-read work and ownership foundations are committed.
The ROOT lowercase helper, Grust column kernel and pure bounded source/control,
binding, admission, lowering and typed-error components are integrated. CDC
consumers/C5/events remain offered. Public ORC writing, complete session/cluster
cleanup, durable streaming/CDC effects and full original Scala-suite acceptance
remain incomplete. Existing execution still rejects incremental/sink pipelines
before writes. Keep that guard until the effect path is qualified.

Fable's [supplement](/Users/alexy/src/grust-sdp-fable/docs/sail-declarative-pipelines/FABLE-HANDOFF-FABLE.md)
provides peer gate/environment and offers. Original vendor d07a95c2c precedes consumer167d577c6; use Git ancestry, not offer order.

## First actions after resuming

1. Read applicable AGENTS.md, this handoff and the coordination protocol below.
2. Determine which role you replace. A successor taking over Codex uses the
   coordinator worktrees; a successor replacing parallel Fable uses Fable's
   worktrees. A handoff file or old ACK does not establish that another agent
   or process stopped. Observe actual Git/process/tool state and coordinate.
3. Read the canonical log **from the last acknowledged point** and post a scoped ACK using its generated read-through reference; do not use an arbitrary tail.
4. Inspect HEAD/status and fetch each repository touched; preserve active checkouts, offered history and failed evidence.
5. ROOT lowercase is integrated atcae618d7f with common/JVM corpus proof. Fable CF-0056 authorizes move-only source-contract extraction; async API changes remain separate.
   C5/progress corrections remain separate. C0 is a user-notified design checkpoint; do not infer activation authority.
6. Continue independent work; only claim a live wait after polling its actual handle.

## Worktrees, branches and source pins

| Role | Path / branch | Inspected source snapshot |
| --- | --- | --- |
| Codex product / Opus successor | `/Users/alexy/src/sail-pipelines-proposal`, `work/spark-declarative-pipelines` | `ba0d692c671fd78b0a1ca77e497c6eb049380981` |
| Codex documents/live log | `/Users/alexy/src/grust-sdp`, `work/sail-declarative-pipelines` | base before this update: `27e2762efcf76b959772a90b37cd72034a12dee5` |
| Codex Sail detached gate | `/Users/alexy/src/sail-sdp-gate` | verify live gate HEAD; local capture/control evidence linked below |
| Codex Grust detached gate | `/Users/alexy/src/grust-sdp-review-gate` | changes with each documentation candidate |
| Parallel Fable CDC build | `/Users/alexy/src/sail-sdp-fable-cdc-build`, `work/sdp-cdc-build` | `a690e2ce96075b433edaf17faadb00088a30e9f9`; existing `/Users/alexy/src/sail-sdp-fable` history preserved |
| Parallel Fable docs | `/Users/alexy/src/grust-sdp-fable`, `work/sdp-streaming-cdc-fable` | latest consumed2075e56b (temp-view policy),d262bcbf (shared diagnostics/DROP correction),04eb37ac (multipart port); table `87f423c0` |
| Parallel Fable detached gate | `/Users/alexy/src/sail-sdp-fable-gate` | verify its actual current candidate/process |
| Fable config component | `/Users/alexy/src/sail-sdp-fable-config`, `work/sdp-flow-config-merge` | offer `164058355ce2bd52214339a4092d519abf2ea859` imported at349771bd9; own `/Users/alexy/src/sail-sdp-fable-config-target` |
| Spark reference | `/Users/alexy/src/spark-sdp-4.2.1` | `617618396087429b5627a86ce933bb0f5d6645cb` |
| Native ORC work | `/Users/alexy/src/orc-rust-sdp`, `work/sail-orc` | `41304b061d13bc5278e2308c35c9574bc9a03b17` |
| Sail-Iggy review | `/Users/alexy/src/sail-iggy-sdp-review` | `5816b9b2f3bd20cd124f24128b7e45818351bcc1` |
| Iggy source | `/Users/alexy/src/iggy` | pin `153fdf466aea94b7bcb90681ee7274f9f76ec00d`; independently active |
| Fable Iggy pin/gate | `/Users/alexy/src/iggy-fable-pin` | same Iggy pin, detached; Fable owns its processes |
| LakeCat review gate | `/Users/alexy/src/lakecat-sdp-gate` | `27e18f390c450c187a34b1c3bb2037c26d107699` |

**Do not modify `/Users/alexy/src/sail`**, the original independently active
`lakecat` checkout. Do not edit/reset/rebase another participant's worktree,
target directory or running processes. Git objects are shared across worktrees:
use `git -C <correct-repository> show <commit>:<path>` for immutable offers.
Sail/Grust object databases differ; resolve short hashes before gating.

Local Sail `main` was updated by guarded fast-forwards (no worktree held main).
From0ba425c03 through d803e13f0/ac469 to `35d4d2f2d58890567c2a7b56372b12c9a4092c57`, equality with
origin/main was verified. No worktree had main checked out. The SDP branch has
not incorporated that upstream delta; any new merge/rebase needs its own exact
combined gate. Main synchronization is not evidence that the SDP tree was rebased.

## User constraints and ownership

- Preserve Sail architecture: use its PlanResolver, RelationScope, catalogs,
  JobService, task contexts and existing actor model. Avoid broad framework rewrites.
- General catalog improvements belong in Sail; LakeCat is one supported catalog.
- Reuse/extract minimal Grust/LakeCat modules when concrete contracts fit, and
  allow reimport by those projects. Do not import entire services for one utility.
- Small logical, reviewable commits; commit necessary work. No push, PR opening,
  publication or release has been authorized. No external messaging except the
  explicitly authorized coordination file.
- Notify before a significant new design phase so the user can switch to Astra.
  Owned-effect, bounded-plan and C0 representation/staging checkpoints have been announced. Production
  durability/fencing/recovery, C0 staging and B12 tie decisions remain open.
- Product code/tests belong in Sail. Plans/reviews/evidence/handoffs belong in Grust.
  The closed `SDP-FABLE-DESIGN-REVIEW.md` is not an active scratch document.
- User restored original division at CF-0532: Codex owns batch/SQL/catalog/runtime/resource/ORC; Fable independently owns CDC implementation and necessary streaming/Iggy support.
  Recent read-only-reviewer directions are superseded. Port/reuse existing peer CDC commits onto the prepared current base; no routine per-commit approval or batch-review loop.
  Shared orchestration/session/protobuf/catalog/Delta edits require declared scope.
  Coordinate concrete overlaps; unresolved durability/fencing/recovery needs design work/user notice, not a blanket stop on unrelated CDC implementation.

## Canonical communication protocol

Read [CODEX-FABLE-COORDINATION.md](docs/sail-declarative-pipelines/CODEX-FABLE-COORDINATION.md).
The only live channel is `/Users/alexy/src/grust-sdp/codex-to-fable.md`. The persistent lock is `/Users/alexy/src/grust-sdp/codex-to-fable.lock`.
Never unlink/replace it; observed inode was 353239041. The Sail Fable worktree
links to the canonical log; the tracked Grust Fable copy is historical.

```sh
/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python \
  /Users/alexy/src/grust-sdp/scripts/sdp-coordination-append.py --since CF-0044
```

Read all stdout; use final stderr `read-through: CF-…` as Seen-Through.
Write a body file, then:

```sh
/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python \
  /Users/alexy/src/grust-sdp/scripts/sdp-coordination-append.py \
  --author Fable --body-file /tmp/fable-message.md \
  --reply-to CF-0044 --seen-through CF-0044
```

Use actual references, not an assumed last ID. Labels include ACK, OFFER/DONE,
REVIEW, QUESTION/ANSWER, DECISION, INTEGRATED and BLOCKED. An offer is not integration;
a posted review is not received until readback. Append corrections; never rewrite
another entry. Lock only for append or snapshot prepare/advance, not builds/waits.
Do not share work via Git stash (worktrees share a stash stack). Use owned commits,
patches and detached controls. Preserve offered commits rather than rewriting them.

## What Codex implemented and validated

[REVIEW.md](docs/sail-declarative-pipelines/REVIEW.md) is the chronological index of
batch, SQL, catalogs, file sources, ORC and runtime units. Its early header describes
an older source; read later entries and exact evidence/source pins. The initial
batch stack adds scoped relation resolution, typed Connect responses, a small
vendored Grust topology kernel, graph definitions/analysis/selection, catalog
publication and execution through JobService, then SparkSession/Connect wiring.
Subsequent commits cover SQL registration, namespaces/configuration, declared
schemas, catalog operations/errors, nested materialization and extensive ORC reads.
Do not replay the initial stack onto the current branch; it is already present.

Recent implementation units relevant to the current work:

| Sail commit | Implemented boundary / evidence |
| --- | --- |
| `76dd36983f` | TaskResourceScope owns admitted supervisors and shared drainage; Drop requests cancellation only. [Packet](docs/sail-declarative-pipelines/evidence/task-resource-scope/README.md) |
| `779cb136d9` | ScopedTaskContext preserves IDs, all function registries, runtime and configuration while adding a fresh resource scope. [Packet](docs/sail-declarative-pipelines/evidence/scoped-task-context/README.md) |
| `e02e4f712f` | Distributed task-monitor scope drainage before terminal reports. Driver/worker shutdown remains separate. [Packet](docs/sail-declarative-pipelines/evidence/task-monitor-resources/README.md) |
| `71f24a87a2` | ORC primitive semantic schema preflight; public writer remains unsupported. [Packet](docs/sail-declarative-pipelines/evidence/orc-write-schema/README.md) |
| `5fc71b3792` | Synchronous noncanceling seal; cancellation notifications outside the scope mutex. [Packet](docs/sail-declarative-pipelines/evidence/scope-notification/README.md) |
| `f3d32b8959` | ManagedRecordBatchStream owns retained/unpolled streams, disposal and registered cleanup without eager input forwarding. [Packet](docs/sail-declarative-pipelines/evidence/managed-stream/README.md) |
| `30f943ef91` | StreamPreparation, resources_drained qualification and nonblocking completion observation. [Packet](docs/sail-declarative-pipelines/evidence/stream-preparation/README.md) |
| `ec8e74d57d` | Local runner admission/preparation, fallible stop, retained uncertainty; checkpoint cleanup skipped after stop failure. [Packet](docs/sail-declarative-pipelines/evidence/local-runner-ownership/README.md) |
| `cba833ae08` | Closed checkpoint descriptors survive failed/canceled storage cleanup; insert/seal share one lock; explicit retry. [Packet](docs/sail-declarative-pipelines/evidence/checkpoint-registry-recovery/README.md) |
| `36525a06f8` | Characterization: held multipart completion republishes a deleted object after caller cancellation/join. No production behavior change. [Packet](docs/sail-declarative-pipelines/evidence/checkpoint-effect-baseline/README.md) |
| `34eb270d00` | Preserve commit + cleanup typed errors as Collection/Context, retaining nonretryable unknown-commit classification. [Packet](docs/sail-declarative-pipelines/evidence/checkpoint-typed-errors/README.md) |
| `590fc2f9d3` | TaskResourceScope.run shares typed completed results with retained supervisor ownership; owned_put.put joins a PUT through lost callers. 107 library + 4 optimized CPU-load tests pass; no dependency change or production routing activation. [Packet](docs/sail-declarative-pipelines/evidence/owned-put/README.md) |
| `4cb9aec14` | Whole multipart supervisor in sail-object-store, no new dependency or routing. 33 library + 16 optimized CPU-load tests pass; notification control fails unchanged regression. [Packet](docs/sail-declarative-pipelines/evidence/owned-multipart/README.md) |
| `beebb83d0` | Execution adapter registers the lifetime with existing TaskResourceScope, retaining typed completion uncertainty. 197 library +5 optimized tests pass; removing the marker fails unchanged classification regression. [Packet](docs/sail-declarative-pipelines/evidence/execution-owned-multipart/README.md) |
| `9d83baa8b` | Explicit mutation-supervisor interruption retains typed JoinError + nonretryable uncertainty for owned PUT/multipart. 111 common +198 execution library tests and111+6 optimized tests pass; unchanged publication/runtime-loss control fails before fix. [Packet](docs/sail-declarative-pipelines/evidence/owned-mutation-runtime-loss/README.md) |
| `a2cee8f00` | Native Drop stops aborting after complete admission. 38 library/optimized tests +300 public/67 upstream pass; real-published error control fails before fix. [Packet](docs/sail-declarative-pipelines/evidence/uncertain-runtime-drop/README.md) |
| `070caa80b` | Mutation observers classify interruption before drain, preserving typed observer/join errors. 112+198 library and112+6 optimized tests pass; both unchanged publication controls fail before fix. [Packet](docs/sail-declarative-pipelines/evidence/interrupted-mutation-observers/README.md) |

Latest accepted source/public runtime is **ba0d692c671fd78b0a1ca77e497c6eb049380981**:125Plan+228Connect native/fmt/strictClippy,300selected+67upstream PASS;12diagnostic vectors byte-identical to46742817. [Read-mode API/design evidence](docs/sail-declarative-pipelines/evidence/scoped-read-mode/README.md) includes72Spark framework/read-mode observations. Materialized virtual streaming-schema projection is designed but NOT activated. Full original Spark SDP acceptance remains unproved.
300 selected public +67 upstream Python executions; inspect the [numeric divisor packet](docs/sail-declarative-pipelines/evidence/numeric-divisor-guard/README.md)
for historical arithmetic qualification and basic-metadata-refresh packet below for test-source/inherited runtime proof. These selections are not original Scala acceptance.

## Current root: `5cc046a0c` (supersedes the status lines below)

Root `5cc046a0c` on `work/spark-declarative-pipelines`, not pushed. Batch is complete against the audit in `docs/sail-declarative-pipelines/evidence/batch-gaps`: 435 entries, 384 ported, 37 partial, 14 internal, 0 missing, pipelines 1245 passed with 4 strict expected failures, a Hive metastore profile (69 passed) and a second-catalog profile (13 passed) in the gate, the same in local-cluster mode, whole tree 0 regressed and 0 failed against upstream `0ba425c03` with `run-full.py`, 12 JVM fixture errors on both sides. Compare with that base, not only the last root. No original Scala suite ran against Sail.

Landing: `merge/gate-run.sh` then `merge/land.sh`, or `merge/gate-merge.sh` then a fast-forward. Check that the frozen harness printed PASS: a changed frozen source stops it. Never run `cargo fmt --all`, which rewrites `vendor/`.

Open: streaming stateful operators (sliding windows, watermarked deduplication, stream-stream joins), exactly-once for plain file tables, Iceberg append sources, rate limits. Non-checkpoint writers and cluster workers are not covered by the session effect owner, and fallible actor results need the common actor framework.

User decisions, 2026-11-02, all keeping current behavior:
- `catalog.shared_memory` stays off by default (opt-in; the CLI tests run with it in the gate).
- Cluster release of a session with checkpoints keeps failing and keeps the files when the driver cannot confirm the writers stopped; the server exits 1.
- ORC timestamps keep Sail's stored type; the write failure about one second before the epoch is a documented difference from Spark, which returns a wrong value there.
- Spark's internal Scala suites are excluded from the goal; the 300 + 67 frozen ports stand in for them.
- Docker- and S3-backed Hive tests are waived (Docker Desktop down); the Derby Hive profile runs in every gate.
- The 4 strict expected failures (deliberate Sail designs) and the 37 wire-invisible partial audit entries are accepted as finished scope.

Worker shutdown (found at `2e73a0b87`): a stuck worker sits in its gRPC server's graceful stop (`ServerMonitor::stop` awaiting the server handle), which waits for open connections to finish. The stop is now bounded at 5 seconds and then aborted; in 120 start/stop rounds the bound fired 4 times on the old binary and once on the new one, and the driver's 30-second limit never fired. Which connection stays open was not identified.

Gate launch: a gate started from a shell with SIGINT blocked passes the block to every Sail server it starts, and `run-hive-metastore.sh` then waits forever in its SIGINT teardown (seen in the CF-0605 merge gate, 2026-11-02; Sail exits on SIGINT when started normally). Launch gates with SIGINT unblocked.

## Opus batch-lane checkpoint (supersedes the next-work item below)

Opus now holds the batch lane in the coordinator worktrees; the CDC lane is an Opus session in the Fable role. The channel helper accepts only the labels Codex and Fable, so those remain role labels. Per the user, each lane does real work and syncs only on a shared reusable design.

Accepted source is **7a32efd2a62e3668a64e21e87c3f9dc0938e1912** (parent ba0d692c6): materialized virtual streaming-input projection in pipelines/schema_stream.rs. Evidence: [streaming-input-schema](docs/sail-declarative-pipelines/evidence/streaming-input-schema/README.md). 125 Plan + 237 Connect/fmt/strict Clippy, 300 selected + 67 upstream, 58 new public tests on Spark 4.2.1 and Sail; 40 of 58 fail on the ba0d binary.

**Correction:** field metadata is dropped on STREAM reads at every depth. The "preserve metadata" instruction below and in evidence/scoped-read-mode is wrong and was disproved by a real Spark run. Error-based probes cannot observe a second flow call, because the failing expression stops the first call; use a declared consumer.

Also accepted: **15272ec0a17070b3a9694992cc4a94ba98f572ce** (parent 7a32efd2a), analyzed view streamingness and both view read-mode errors; [evidence](docs/sail-declarative-pipelines/evidence/view-read-modes/README.md). 125+237 native, 300+67, 92 of 92 new public on Sail; 19 of 34 fail on the 7a32 binary. Its known limits are listed there.

Also accepted: **dea8e10fb4c6ff4c258cd747e2a4b14b2c960daa** (parent 15272ec0a), the server-side definition guard; [evidence](docs/sail-declarative-pipelines/evidence/query-function-guard/README.md). 125+245 native, 300+67, 61 on Spark and Sail, 535 of 535 in the pipelines directory; 32 of 61 fail on the 15272 binary. **The frozen harness now lives in evidence/query-function-guard/harness**, because two test fixtures migrated; the earlier copy no longer matches the tree. Query functions cannot pass a DDL string schema, which is an analysis RPC.

Also accepted: **2eae921c51f63de1baa5400be6a8d12b514782f3**, a fast-forward of dea8e10fb with the peer's CDC chain (CF-0570, CF-0572); [evidence](docs/sail-declarative-pipelines/evidence/cdc-root-integration/README.md). This is the current root. The union is qualified; CDC itself is not accepted, and no public path reaches it because no production code registers BoundedSources. Delta Python outcomes are unchanged from dea8e10fb, with 12 failed and 12 errors pre-existing; the delta-spark interoperability tests do not run on this host. An external test server needs SAIL_EXECUTION__DEFAULT_PARALLELISM=4 and SAIL_RUNTIME__STACK_SIZE=16777216, or Delta plan snapshots fail.

**Current root: d4c7a45ebe4c0a910cb0936e372e5381d1335849.** On top of 2eae921c5 this adds, each with a packet under evidence/: orc-writer (public ORC writing), streaming-tables (append flows, file-table sources, checkpoints in storage), flow-progress (lifecycle events, retries, upstream skips), python-pipeline-suite, sinks-watermarks (path sinks, tumbling windows with a watermark), spark-suite-ports, iggy-root-integration, remaining-suite-ports (file streams, memory and console sinks, read options). Fenced reset from the CDC lane is merged. The frozen harness is evidence/spark-suite-ports/harness. An external test server also needs JAVA_HOME at JDK 17; JVM-mode ports need SPARK_REMOTE='local[2]', since is_jvm_spark() is false for sc:// remotes. Gate: 15 crates in remaining-suite-ports/gates/native-all.sh, including sail-session.

Two landing faults happened and are recorded: 31ac33f65 landed with a failing Clippy gate and d521ca587 with one failing test. Land only through sinks-watermarks/gates/land.sh or its later form, which checks native, frozen and pipelines runs on the exact commit.

Public pipelines tests are 825 passed, 0 failed, 13 strict expected failures. Those 14 name their reasons in the tests. No original Scala suite was executed against Sail; the ports go through the public client, so the inventory counts are unchanged. Outstanding: Delta and Iggy append sources, stateful operators beyond tumbling windows, ORC timestamp, decimal and nested writes, native encoder memory accounting, at-least-once recovery for plain file tables, distributed runs, session and manager shutdown.

Follow-ups: named_struct reports literal fields nullable while struct() does not; SHOW CREATE TABLE is unimplemented in Sail's parser.

## Opus stopping checkpoint and next implementation (read-mode API accepted, CF-0563)

User usage is below2%. Every action since that instruction is recorded in this checkpoint/evidence. No new design phase or CDC integration was started; the active goal remains incomplete.

- **Prior accepted source (O2):**7cf0254bca8dfc9534e30dd1bcdde4f8cae03551 (parent26500918b), the logical unresolved-flow aggregation/event/wire commit. This historical pin retains its proof below; current accepted source is c64533302173f88087485a531306f34346732b5e in the worktree table and advancement checkpoint.
- **Built:**all producer outcomes and requested inputs survive query failures; independent flows continue; failed producers classify direct/downstream failures; successful producers of failed destinations are excluded; Grust checks the failed-flow graph. Downstream failure events precede direct events and the sorted unquoted-name summary. Completed materialized outputs release cached working providers. Typed reports hold diagnostics, not plans/providers. Command reanalysis keeps raw errors; configuration conflicts retain their phase.
- **Wire:**UnresolvedPipelineException retains its AnalysisException hierarchy through a three-line error.rs class-hierarchy arm; condition/SQLSTATE/parameters remain absent. Other touched source: analysis.rs, analysis/failure.rs, config/resolve.rs, reanalysis.rs, pipelines/mod.rs, native tests. Public test_resolution_failures.py covers12 combinations; one old BDD now asserts missing-column text in its event and summary in the terminal exception.
- **Final proof:**217Connect native/fmt/strictClippy,300 selected public+67upstream, paired Spark4.2.1/Sail13 (primary12+BDD1), all PASS. Primary12 unchanged tests fail12/12 on old265 binary. Provider release/no scans, underlying structured causes and exact wire hierarchy are checked natively. No full-SDP conformance claim or inventory promotion.
- **Durable packet:**[unresolved-flow-reporting](docs/sail-declarative-pipelines/evidence/unresolved-flow-reporting/README.md), verify.py PASSED. It contains native candidates/receipts/logs01–05, initial reference assertion failure and corrected reference runs, old-binary control, initial299/300 public failure, predecessor300+67 run, final public05, paired13, probe.py, updated frozen harness and hash manifests. The initial native Clippy test-only clone lint and old terminal-only BDD failure are retained.
- **Final exact handles:**native05 session20858 TERMINAL0; public05 session26915 TERMINAL0 with300+67; Sail13 session92290 TERMINAL0 with13/no remaining listeners. Do not restart them. Public receipt /tmp/sail-sdp-unresolved-flows-public-05/receipt.json; candidate/selected paths /tmp/sail-sdp-unresolved-flows-05-candidate.json; native receipt /tmp/sail-sdp-unresolved-flows-05-gate.json. Durable packet copies are authoritative if /tmp disappears.
- **Prior schema API foundation (historical):**7f7a14eb39f54ab8991063df2ca58bbf66fa5c54 accepted at that checkpoint, parentc645; detached gate same. VirtualTableSchema owns name/declaration/incoming Arrow schemas only; load bypasses incoming merge when declared, validate enforces compatibility, existing infer delegates to validate. Three native contracts cover declared bypass, no fallback for untyped inference failures, nullability and Spark JSON metadata preservation. Initial gate35141 failed220/1 on an authored plain-comment-key assumption (Sail uses SPARK_METADATA_JSON_KEY); corrected metadata assertion, no production metadata change. Revised64962 PASSED221/fmt/strictClippy;64476 PASSED300+67;65431 completed12-vector replay, all fields unchanged fromc645 and all12 Spark divergences retained. All jobs terminal/no listeners. Evidence/virtual-schema-api verifier PASSED before conditional source advance; initial failure and final receipts preserved. Candidate/receipt labels virtual-schema-api-02. Source scope only schema.rs + schema_virtual_tests.rs; no GraphScope/command reanalysis/CDC effects changed. CF0554 announces result. API proof/handoff docs acceptedf21b98c6c6495b0ce7454bb6dc806f1302c33521. User-requested CDC control-store design now completed as a specification and offered to Fable inCF0556; no control runtime code written.
- **Reproduction:**use packet harness/run.py with explicit full --commit and fresh --output against clean detached Sail gate;300-case selection IDs unchanged. diagnostic-migration.json binds the two changed Python/feature hashes. Add feature tests: packet probe.py with SDP_TEST_PATH=python/pysail/tests/spark/pipelines/test_resolution_failures.py, SDP_TEST_NODES JSON containing that file and python/pysail/tests/spark/pipelines/test_features.py::test_analysis_fails_before_any_output_is_published; call sail FRESH_DIR EXACT_PUBLIC_RECEIPT. Uses50095; Spark uses15002/JDK17. Never stop arbitrary listeners or overwrite old logs.
- **CDC CONTROL STORE — DESIGN DELIVERED:**[CDC-CONTROL-STORE-DESIGN.md](docs/sail-declarative-pipelines/CDC-CONTROL-STORE-DESIGN.md), SHA2560c2f997090d765015f50b4303ab1a5a3d9399be6cc9d173cef0cb75e8baa2317, fulfills the new user request from Fable brief. Source audit/provenance pins13 files in evidence/cdc-control-store-design; verifier confirms sources/artifact only, not real backend durability/fencing/recovery. Selected optionB strengthened to one SQL control/catalog authority with atomic target guard+Delta-ratified head+effect receipt; first Turso authority service, provider-neutral Sail interfaces and LakeCat/standalone adapter, minimal reusable ledger extraction. Existing LakeCat Delta fence is NOT implemented; existing Sail catalog-managed read/reconciliation/bootstrap/protocol-only publication gaps must be closed. No separate control-CAS/txn-ID/tag fencing fiction. Target-group guard persists across incarnations; all sink UUIDs, alias/domain binding and auxiliary identity checked. Two MERGEs are separate recoverable receipts, with a target-wide slot and sealed prepared input; no two-table atomic-read claim. Design includes concrete SQL keys/transaction, Initialization intents, data/no-op receipts, takeover/lease, unknown outcomes, fenced reset/checkpoint generations, protected source frontiers, ack lifecycle/retention/restore, stateless bounded SCD1 admission, worked failure trace and6 gated units. User brief decisions retained: AutoCDC-only bounded graph gate, warehouse checkpoint layout, Iggy fork lineage. V1 one durable authority service; HA/other catalogs/stateful execution need qualification. CDC-ACTIVATION remains unwired; local JSON runner honestly unfenced. No real control-store/backend/fencing/crash tests run this design turn.
- **Fable offer CF0548:**ten component commits on265, ordered23aa26eff(A2),abfac64c2(A3),9fa5609c3(public33pass/7strict-xfail),6bc37f2c2(A4a),5189c8392(A4b),8a3a8a063(A4c),b38ecbbfb(O2 marker reasons),d34441e10(A5 components),f6be32bc7(full-refresh compositions),b302e1c28(A5b selective refresh). Branch work/sdp-cdc-build in /Users/alexy/src/sail-sdp-fable-cdc-build. Peer-gated; not integrated beyond A1. Read full CF0548 and peer CDC-UNITS.md before porting; do not reactivate the routine review loop.
- **Fable update CF0549:**A6 bounded Iggy adapter planned as new crates/sail-iggy-bounded, SDK153fdf466, AutoCommit disabled and fail-closed retention/offset/incarnation checks; no existing crate source changes proposed, only workspace/dependency/lock changes. New9ef96af61 metadata NOT NULL and51959c5be18Delta merge cases were gating when offered, not yet qualified/integrated by Codex. No reply requested unless objecting. CF0551 supersedes this: new rebased chunk2 tip4fc62deed gating;13 commits include03e837133(A3),4164528c5(tests),e7134a6f0(A4a),57bf2fc6f(A4b),8ef776afc(A4c),d0fdddaae/4fc62deed(markers),0eae68af9(A5),9d9aac8bb(full refresh),95cb03eb2(A5b),fd3bffafd(NOT NULL),c8551e369(18 Delta merge cases),A2 earlier in chain. Peer reports all Spark SCD1 suites ported/accounted except activation-runner cases; not independently integrated/qualified here. D1: pinned Iggy SDK QUIC quinn dependency conflicts with Sail Iceberg→reqwest0.12.28; SDK cannot disable it. Proposed adapter scaffold removed/uncommitted, needs dependency decision or sail-iggy fork lineage. Fable reports CDC code idle pending activation/dependency decisions; do not infer its gate jobs terminal.
- **Seven original AutoCDC assertions:**CF0551 reports an actual O2 rerun on7cf: five of seven original assertions PASS with assertions unchanged and strict markers removed; two remain strict-xfail in both registration orders because an unread output raises eager UNABLE_TO_INFER_PIPELINE_TABLE_SCHEMA before the unresolved-flow summary. This confirms the remaining eager-schema batch gap; no full-SDP claim. CF0555 records user division: Codex/Astra owns control-store design, Fable reviews pinned sources and then implements it in gated CDC units, including shared Delta fencing plumbing after declaring scope. CF0556 posted the complete content-addressed design for that review. CF0557 now accepts the design as the build specification after pinned-source review; [Codex response](docs/sail-declarative-pipelines/CDC-CONTROL-STORE-REVIEW-RESPONSE.md) accepts all five findings. B0 materialization fixes repeated evaluation only; durable restart still needs sealed artifacts. Fable owns B0/B1 and declared shared Delta work; Turso dependency qualification precedes its adapter. LocalUnfenced is explicit, never fallback. Codex keeps independent batch/lazy-schema work; no routine review loop. CF0561 now offers B0 28515224e and B1 2d4174d0c: peer-qualified pure sail-sdp-control model22pass/1ignored, not root-integrated; sail-gate.sh does not cover that crate so peer ran separate gates. Peer says Turso0.7.2 builds (82lock additions), guard-race/SIGKILL proof with negative control at Grust6c9db581; power loss/live-process sharing/restore/fork unqualified. Completion uses sealed intent progress; reset seals slot/token and rebinds recreated auxiliary identities. Peer B2 feature-gated adapter next; B3/B4 shared catalog/Delta/context scope declared before edits. Opus should keep building batch independently, not become a standing peer reviewer.
- **Activation:**public Table/Sink/streaming/CDC effects remain disabled. CDC-ACTIVATION-DESIGN.md in Grust Fable is the Astra checkpoint: run-record authority, execution gate, checkpoint layout. No new activation approval/design choice is inferred here. Prior A1 cleanup/source units remain qualified in their packets.
- **Accepted source and exact qualification:**ba0d692c671fd78b0a1ca77e497c6eb049380981, parent46742817, product clean/Sail gate same. Five files in sail-plan: resolver/scope.rs and query/{mod.rs,read.rs,session_tests.rs,factory_session_tests.rs}. Read.is_streaming reaches named/computed RelationScope hooks; legacy scopes keep defaults and late-bound semantics; ViewScope forwards mode+creation namespace; CTE precedence preserved. Native contracts cover4mode/binding combinations, legacy scopes, CTE priority, stored namespace and zero physical execution. No GraphScope projection/config behavior, shared catalogs/Delta/control or streaming effects changed. Initial16f72bad3 failed Clippy on unused private wrapper; removed wrapper and existing factory fixture now passes false explicitly. Final native29034 passed125Plan+228Connect/fmt/strictClippy; public88128 passed300+67, CLI/server4.2.1; replay23497 completed12vectors, every diagnostic/event field identical to467. All terminal/no listeners. Evidence/scoped-read-mode verifies source/log/CLI/count pins, failed initial gate retained. Source advanced conditionally after verifier PASS. Parent final-merge467 remains qualified228native/300+67/paired18/all12freshSpark; missing SQLSTATE suffix failure and fixed gate history retained in evidence/final-schema-merge. Earlier lazy69ac5ab remains qualified223native/300+67/paired9 in evidence/lazy-virtual-scope. No original peer markers changed; full goal incomplete.
[Review units](docs/sail-declarative-pipelines/evidence/flow-config-runtime/README.md): b4d source-case seam (88+151; two 0/2 controls),349 pure maps (88+166),fa78 trace (88+170),1bc runtime. Native dynamic/parameter-relation regression fixtures fail0/2 without the no-view-settings path; pass unchanged in the integrated source. Earlier query/expression packets retain their exact historical gates. No captured public Session activation.
[General missing-column units](docs/sail-declarative-pipelines/evidence/unresolved-column-errors/README.md): abad typed PlanError→existing Connect codec (88+176);7b native diagnostics (91+176), unchanged control2 helper pass/1 native fail. Two retained initial gates failed solely on three old golden error strings; official fixture generation changed no inputs/outcomes.
[Shared schemas/file sources](docs/sail-declarative-pipelines/evidence/parquet-column-validation/README.md):52d extracts Spark-compatible validation, old column_change path reexported, actual JVM12-case oracle;005 validates captured policy and fixes inferred partition shadowing. Exact643/646 library gates; disabling checks fails0/3 unchanged tests. Retains239/1 initial data-source failure, intermediate pass and probe directory-name collision. Public read replay uses original Spark file bytes. Follow-up95 closes the two ambiguity diagnostics; full reader matching/merge policy remains open.
[Ambiguity unit](docs/sail-declarative-pipelines/evidence/ambiguous-reference-errors/README.md): shared formatter reuse; requested spelling and UTF16 order; qualifier/origin identities preserved even with identical display names; no diagnostic allocation on successful lookup. Exact647 libraries/unchanged control0 pass+1 fail/fresh300+67/public10+9 comparisons. Initial Clippy borrow and missing normal catalog fixture retained. Dynamic/reference design phase is now active, user notified before starting.
[Current design](docs/sail-declarative-pipelines/DYNAMIC-REFERENCE-BINDING-DESIGN.md): ccb normalizes non-null string literals to named reads, preserves computed/null forms and fixes Identifier sampling grammar. Same-input literal control1 pass/1 fail. Spark thirteen-case dynamic and seven-case protocol oracles show late computed lookup, used-only generic references, eager SQL parameters and frozen external Foo9 despite catalog replacement bar10. No source-snapshot/binding representation selected; do not fresh-resolve parameters or retain graph providers as a shortcut. See retained grammar/warehouse/missing-argument/verifier failures.
[Computed/helper history](docs/sail-declarative-pipelines/evidence/identifier-constant-validation/README.md): d2ada245e/dd4c9344a keep native CTE/default/view namespaces and select live-session late targets;15fd1888c adds scoped constant validation/parameter substitution/table type-only handling.
[Expression-local provenance](docs/sail-declarative-pipelines/evidence/identifier-function-provenance/README.md):25534e8ea keeps non-foldability in a private typed Volatile marker, guarded before materialization; no collector/mutable context borrow or worker codec. The20-case oracle improves11→19 behaviors with11 complete metadata sets. Collector18de98927 and failed101c2fce2 are unadvanced/preserved, with all gates/probes/controls; broader34-case validation now29 behaviors/11 metadata sets.
[Arithmetic](docs/sail-declarative-pipelines/evidence/constant-context-lowering/README.md):3ffb497d3 separates lowering's constant_context from eager require_foldable, preserving type-before-evaluation under ANSI on/off and ordinary policy. Four new cases improve2/14→6/14, metadata3/14. Remaining division transport, unbound parameters/origins, full expr.sql/state/parameters and catalog nondeterminism are explicit.
Catalog and operand evaluation design stay active. [Source/phase and decimal contract](docs/sail-declarative-pipelines/evidence/source-dependent-cast-folding/README.md): own Spark/public56 gives34 outcomes/16 with schema+planning-vs-collect; own decimal192 gives114 outcomes/101 with schema; all131 combined failures retained as general Sail conformance backlog. Original VALUES16 remains valid only for those shapes; corrected fastpath README. ANSI bad literal under nonfoldable Parquet division must fail during planning, while foldable whole/CASE/local relations can skip. No documented leniency accepted as final parity. Decimal scalar8a7, wireb481 and config226 are built; folding/type/resolver integration still required, so retained public63f5 failures are not declared fixed. Fabled527d8ed/b38215b4/6b7fe4de accepts decimal config/scalar/wire and prior component reviews and reconciles known-data-only replay with per-body/per-dtype vocabulary proof. Planner seat remains open: physical optimizer+decoder reproof can avoid wire eligibility state, but expression visitation is read-only and scan pushdown/rebuilds need proof; final QueryPlanner logical rewrite is another audited candidate. CF-0421 records IF/CASE8 closure and explicit ELSE, with four additional literal-condition schema failures retained; Fable5dace5c3 corrects CaseWhen.nullable to include its TrueLiteral special arm. The VALUES-order correction still holds: an eager pre-pass must not erase earlier local-row lazy evaluation. Nanvl remains eager in DataFusion and needs a once-only lazy left evaluation. Folding/type design remains retained; CF-0438 adds original :599 parse qualification and flags metadata-only materialization design. No source assignment. Product/gate/qualifiedCLIdb650 clean; owned commands terminal. No new mode/classifier/lowering/provider/streaming authority. Original Scala and generic CASE/type-only/PATH/parameter/origin/binding gaps remain required.
[Frozen inputs](docs/sail-declarative-pipelines/evidence/computed-identifier-binding/README.md): added files invisible, deleted listed files fail, replacements visible; no etag enforcement/owned-plan exception selected. Generic references/frozen parameter ownership/UDF/config/encoding, captured public Session, streaming/CDC and full original Scala acceptance remain required work; the entire goal stays active.
- **Next work for Opus after user resumes:**No owned build/probe remains; original /Users/alexy/src/sail untouched. Read channel fromCF0563 under persistent-flock protocol; do not overwrite peer entries/lock. Take Codex worktrees and batch lane, leave Fable worktrees/processes alone. Resume materialized virtual-input schema projection using the accepted read-mode hooks. At FlowContext.call snapshot the consuming flow’s effective semantic settings after existing base/flow/accepted-view overlay, preserving two-call reanalysis and source-case boundaries; never mutate shared session config. Project only streaming reads of provider-free VirtualTableSchema descriptors. Batch reads retain precision/bounds; final raw merge/publication and concrete command reanalysis retain their separate semantics. New hook alone does NOT implement this. Native/paired contracts must cover explicit frameworkfalse/true, batch/STREAM, nested arrays/structs/maps, declared/inferred inputs, metadata/nullability, session/flow/view precedence and second-call changes. Source-backed design is in evidence/scoped-read-mode README; no extra handoff file was created. Next separate units: analyzed view streamingness + incompatible-view override; general public analysis/execute guard inside pipeline query functions. Do not infer those from current raw read flags or from Spark-only observations. Keep public CDC/sink/streaming activation guards; Fable owns control-store model/adapter and declared Delta fencing work. Canonical inventory486sites/116reviewed/87partial/399unmapped,142originalreference executions,595names/43nonempty/56bindings unchanged. Root goal remains incomplete and user-requested pause takes effect after handoff acceptance.
[Read](docs/sail-declarative-pipelines/evidence/resolver-read-session/README.md),
[writer/schema](docs/sail-declarative-pipelines/evidence/resolver-writer-session/README.md) and
[lake metadata/properties](docs/sail-declarative-pipelines/evidence/lake-metadata-session-callbacks/README.md)
preserve their exact historical gates and bypass failures. The existing
[preparation](docs/sail-declarative-pipelines/evidence/local-bound-preparation/README.md),
[ScopedSession](docs/sail-declarative-pipelines/evidence/scoped-session/README.md) and
[helper](docs/sail-declarative-pipelines/evidence/resolver-query-session/README.md) seams remain opt-in.
- **Research evidence and resolved TIME question:**Initial1612 failed bad helper import; corrected49282 completed11direct-expression probes (schema/typeof/explain) plus44contextual .schema requests, all rejected ATTEMPT_ANALYSIS_IN_PIPELINE_QUERY_FUNCTION; no contextual schema values observed. Error-based89431 completed36dry cases;70697 completed72explicit framework cases (9expressions ×materialized/temp ×batch/STREAM ×frameworkfalse/true). Batch virtual reads preserve TIME precision/interval bounds. STREAM(materialized) exposes TIME6 in legacy mode, original precision in framework mode, and full interval families in either mode; recursion observed for arrays/structs, null/non-nullTIME3. STREAM(batchTEMPVIEW) rejects INCOMPATIBLE_BATCH_VIEW_READ. Source617618396 resolves the earlier contradiction: RowEncoder and installed javap do pass TIME precision into LocalTimeEncoder, but ExpressionEncoder.schema derives serializer expression types; legacy SerializerBuildHelper emits TimeType() while TypeOps selects precision-preserving TimeTypeOps only when spark.sql.types.framework.enabled=true. Key defaults to Utils.isTesting in source (runtimefalse, native Spark tests maytrue); qualify both profiles. Interval encoders use full-family types. No need to relax raw merge or erase precision globally. Nine immutable source snapshots, raw experiments, summary/verifier and failed import evidence are retained. User was notified before this design phase and informed when the early RowEncoder-only explanation proved incomplete; CF0562/0563 carry the final causal result and file scope. All experiment sessions terminal.
[Row factories](docs/sail-declarative-pipelines/evidence/row-factory-session/README.md)
1a80c0a95: DELETE/UPDATE/TRUNCATE/MERGE selected-Session routing,63 libraries/
8 optimized CPU-load cases; unchanged four-site bypass fails4 scoped/passes4 legacy.
[Delta metadata](docs/sail-declarative-pipelines/evidence/delta-metadata-session/README.md)
63b660ac0: path feature/catalog constraint callbacks,67 libraries/4 optimized;
independent path/catalog bypass each3pass/1 corresponding scoped failure. Completion
counts detect metadata errors otherwise skipped. Initial input-schema/read-count
fixture failures retained. [Procedure callbacks](docs/sail-declarative-pipelines/evidence/procedure-factory-session/README.md)
41759759b: catalog and predicate procedures,71 libraries/4 optimized; unchanged
factory bypass2pass/2scopedfail, metadata bypass3pass/1predicatefail. All strict
Clippy/fmt; ten load workers joined per optimized run. Probes stop before mutation/
implementation/physical planning; real SDK behavior/public activation unqualified.
[Rustdoc0af](docs/sail-declarative-pipelines/evidence/resolver-factory-coverage-doc/README.md)
changes no non-doc source from417; fmt/diff checks only. Native analyzers unchanged.

The pure bounded stack is imported: [contract](docs/sail-declarative-pipelines/evidence/bounded-contract-root-integration/README.md),
[control](docs/sail-declarative-pipelines/evidence/bounded-control-root-integration/README.md),
[binding](docs/sail-declarative-pipelines/evidence/bounded-binding-root-integration/README.md),
[admission](docs/sail-declarative-pipelines/evidence/bounded-admission-root-integration/README.md),
[signature fixtures](docs/sail-declarative-pipelines/evidence/admission-signature-fixtures/README.md),
[lowerer](docs/sail-declarative-pipelines/evidence/bounded-lowerer-root-integration/README.md),
[typed causes](docs/sail-declarative-pipelines/evidence/bounded-lower-error-chain/README.md) and actual clocks above.
[Clock failure](docs/sail-declarative-pipelines/evidence/fable-stable-admission-review/README.md)/
[unchanged correction](docs/sail-declarative-pipelines/evidence/fable-stable-admission-correction-review/README.md),
[inline UDTF failure](docs/sail-declarative-pipelines/evidence/fable-inline-udtf-binding-review/README.md)/
[guard/replay](docs/sail-declarative-pipelines/evidence/bounded-inline-udtf-guard/README.md) and
[lowerer controls](docs/sail-declarative-pipelines/evidence/fable-local-lowering-review/README.md) remain retained.
Scope is unused in pure lowerer; snapshots declare inputs, not complete replay
identity/backend pin proof. No broker/target/checkpoint/durable CDC/public activation.
Owned dynamic Python analysis, mixed read modes/multi-leaf views remain required.

[C5 manifest review](docs/sail-declarative-pipelines/evidence/fable-c5-integration-manifest-review/README.md):
original7cf claim narrowed by716 after checking114 root-changed files; application
is not buildability. CF-0202 authorizes only A–D preparation, separate peer worktree
/Users/alexy/src/sail-sdp-fable-c5, branch work/sdp-c5-events-integration on immutable09,
own target, offers A bb50a54d3/B7de7712f1/Cbad45044d/D0744b4c99. Exact peer detached gates
reported inCF-0206; queue delay/self-matching pgrep failure disclosed. No root integration of these offers. Prior E′/F–K staging limits are historical; CF-0532 authorizes independent CDC implementation.
Two CDC phase calls/four assertions remain reintegration obligations; qualified effect activation remains required.
No Status-rendering policy selected. Original peer history remains untouched.

**Capture primitives implemented; provider/caller Astra checkpoint active**. [Design](docs/sail-declarative-pipelines/CAPTURE-EXECUTION-TRANSFER-DESIGN.md)
retains worker transport, Delta lineage, primary/cleanup and provider limits.
[Shared contract](docs/sail-declarative-pipelines/evidence/captured-preparation-contract/README.md) 16c43aa29:136+223 libraries/one optimized case; explicit unsupported cancellation.
[Local capture](docs/sail-declarative-pipelines/evidence/local-captured-execution/README.md) 7505e2ced:136+228 libraries/optimized6+9 overlapping cases, all load workers joined.
a74c3f429 documents recapture cancel/complete registry replacement; failed attempts,
held-I/O registry lifetime and authority control retained in the packets.
[Boundary](docs/sail-declarative-pipelines/evidence/capture-execution-boundary/README.md) e42e1be96 pins legacy7/child→9/parent.
[Analyzer](docs/sail-declarative-pipelines/evidence/scoped-native-analyzer/README.md) ece5b6aed is optimizer-free; optimizer control1pass/1fail retained.
[Typed resolver](docs/sail-declarative-pipelines/evidence/resolver-native-analyzer/README.md) 17b8ac254:136+78 libraries/strict Clippy/fmt, authority control2pass/5fail.
Last setter wins, child mode preserved, two native command sites routed. CF-0221
review consumed; CF-0223 withdraws unreachable view-mode fixture request.
No captured public/cluster/provider activation or C5/Status scope expansion.

[Batch design](docs/sail-declarative-pipelines/BATCH-PROVIDER-MIGRATION-DESIGN.md) and [source audit](docs/sail-declarative-pipelines/evidence/batch-provider-migration/README.md)
retain Spark's table-only stop/view/config fusion target and historical cache hazard.
[Historical artifacts](docs/sail-declarative-pipelines/evidence/batch-analysis-artifacts/README.md)954 retains139 libraries/1+3 control and137+2→139 same-binary env proof; [native helpers](docs/sail-declarative-pipelines/evidence/view-publication-metadata/README.md)5717 retains222 libraries/initial unused-import failure.
[Publication artifact](docs/sail-declarative-pipelines/evidence/analysis-time-view-publication/README.md):
31dfb2cc9 native view/options225 libraries; f4a6a541f prepared catalog stages227;
f0ac099e6 schemas/publications only229. Full working plans drop before return,
mock provider leases release, Tail sees working data; source-unavailable publication
preserves SQL/types/nullability/comments/namespace. Re-resolution control5pass/1fail.
Arrow metadata remains; qualifiers/dependencies are not replay identity. Invalid definitions already failed analysis; do not overstate error timing.
[Command inputs](docs/sail-declarative-pipelines/evidence/command-input-reanalysis/README.md):
f72120882 resolves each command independently, traverses graph views, stops tables,
uses view flow namespace/config and consumer config for table reads. Each map drops;
no eager post-write read. Mock leases and unrelated-closure checks qualify that scope.
163b2fb52 removes dead required/with_dependencies selection state. Two unchanged-test
controls each2pass/1fail. Fable0ceb51c8/fea89cc0 reviews consumed through CF-0248.
The selected [native configuration design](docs/sail-declarative-pipelines/NATIVE-INPUT-BINDING-DESIGN.md) now has runtime activation: ordered trace, private first-pass config, success-only union/conditional native second call, accepted per-command settings. No opaque binding node. Identical13 public condition/success-row outcomes now all match after7b native diagnostics;12 ordinary SQL probes match full condition/state/parameters, and five missing-column first-line messages match Spark. Broader binding and full duplicate-flow provenance parity remain unqualified. Fable CF-0286 identified the format gap; shared listing checks now cover supplied/inferred duplicate names and partition schemas. Parquet metadata7/9 and six partition outcomes are qualified at005;95 closes ambiguity to9/9 plus10 ordinary probes with full metadata/rows. Configured dynamic/WithRelations/plan-ID inputs and CTE equivalence remain unfinished; no-settings graphs preserve native query support. Root owns wiring/activation; no E′/F–K authority. Notify the user before a new substantial binding/lifecycle design phase. Captured preparation/admission, provider/SDK I/O, shutdown, ORC writes, CDC/C0 and full Scala acceptance remain.
Mock plan-map leases do not qualify SDK/session/factory caches. C5 E′ must preserve schemas/publications, one-resolution publication and per-command execution; never restore required/with_dependencies.

## Acceptance accounting and major remaining work

The canonical [inventory](docs/sail-declarative-pipelines/spark-4.2.1-inventory.json)
currently has **486 reconciled declaration sites**, **116 assertion-reviewed**,
**87 partial-behavioral-port**, **399 unmapped**. These are not expanded runtime
counts; none is a full Sail conformance verdict.24 additional declarations are reconciled.
[CROSSWALK.md](docs/sail-declarative-pipelines/CROSSWALK.md) supplies assertion
context; its reviewed-suite table is reconciled to the canonical JSON at87 partial.
New Fable component crosswalks do not automatically change the canonical inventory.

67 upstream Python executions represent 63 unique IDs (an inherited remote-mode
case repeats five times). The frozen 300-case public selection is regression
coverage, not full original Spark SDP acceptance and not coverage of every new
Fable module. Run added tests and actual combined-tree gates as well.

Unfinished: original suite/assertion acceptance, remaining batch events/catalog
cases, public ORC writing, memory/accounting and writer ownership, truthful session
Deleted/RPC acknowledgement, retained failed-deletion ownership, operation/legacy
and distributed effect joins, manager/transport shutdown, durable streaming control,
Iggy integration, CDC preparation/effects/recovery and MERGE. Do not hide these
behind a fail-closed guard or an unsupported result and call the goal achieved.

## Fable offers and integration state

The [historical offer ledger](docs/sail-declarative-pipelines/FABLE-OFFER-HISTORY.md)
preserves every previous C1–C6, CDC/prepared, event and source-contract offer/pin.
Current integration is listed above; do not replay earlier offered history wholesale.
C5/events/CDC definitions/validation/dedup/prepared-input consumers remain pending.
The original vendor-only Cargo.lock edge must not precede its consumer declaration.
Keep peer history intact and independently gate each actual root union.

## Independent reviews and open requests

- [Original CDC review](docs/sail-declarative-pipelines/evidence/fable-cdc-unit1-review/definition-review.md): phase ordering, identifiers, global precedence, lookup policy, intermediate lock edge, wire/schema evidence. Fable accepted all findings.
- [JVM/Rust lookup oracles](docs/sail-declarative-pipelines/evidence/fable-column-oracles/README.md): Scala small-map/CHAMP behavior and JDK-vs-Rust Unicode differences; helper scope only.
- [C1 oracle](docs/sail-declarative-pipelines/evidence/fable-c1-parser-oracle/README.md): 9,338 exact-parser/JVM comparisons; error metadata/handler precedence not covered by that probe.
- [C2 failures](docs/sail-declarative-pipelines/evidence/fable-c2-context-review/README.md), [C4 review](docs/sail-declarative-pipelines/evidence/fable-c4-independent-review/README.md), [corrected C2+C4](docs/sail-declarative-pipelines/evidence/fable-c2-corrected-review/README.md): immutable failed and successful evidence, not contradictory verdicts on one source.
- [C5/progress review](docs/sail-declarative-pipelines/evidence/fable-c5-progress-source-review/README.md): source-derived competing-error and across-run recreation schedules. Review769914891's actual fixes and rerun the counterexamples; do not equate an offered gate with integration.
- [Prepared/unit4 review](docs/sail-declarative-pipelines/evidence/fable-prepared-input-review/README.md): current highest-priority new findings; full message bodies are CF-0043/0044.

Earlier prepared findings are retained, with the corrected-source review in
[evidence/fable-prepared-component-review](docs/sail-declarative-pipelines/evidence/fable-prepared-component-review/README.md),
committed in Grust `70b74065e51fd4efad977c36616a9ec571ff3c7c`.
Exact prepared/lookup/lowercase source71e4a94d9 passed 64 equal-schema/metadata
reconstructions, 0/1/2-row case/literal-dot key binding, nine independent manifest
mutations, wrong expected identity rejection, unknown-case rejection and serde
round-trip. The probe supplied record-shaped intent/error adapters; it did not
execute actual source, original-row validation, dedup or the pipeline runtime.

**Open C0 representation decision:** equal Arrow59.2 batches with ids[1,2] and
nullable payload[10,null] but hidden null-slot values111 versus222 produce different
content digests; verify rejects the equal batch as ContentMismatch. This is a
physical IPC fingerprint after row ordering, not representation-independent logical
canonicalization. Fable accepts the finding in CF-0054 and drafta0e5644b §9.
Choose/version either a supported canonical logical encoding with null/nested/
dictionary/slice/offset proofs, or stored sealed-byte authority where reconstruction
only cross-checks. The user has been notified this needs Astra. **No choice has been
selected.** Do not patch only the Int64 example, weaken mismatch rejection or silently
change B12 tie policy.

Unit4 answers already sent: context/overlay must cover planning I/O and execution
under one existing preparation/resource owner; lowering returns LogicalPlan and
evidence, with no effects; codec comes before distributed admission. Draft changes
requested: preserve read mode before the resolver discards it; local streaming
reads must bind ranges rather than GraphScope's EmptyRelation; valid empty intents
retain obligations; bounded current-range joins do not implement cross-batch joins;
volatile inputs must not reevaluate between validation/dedup; actual evaluation
snapshot must include semantic config/source identity (current struct lacks flow
sql_conf); seal is noncanceling, cancel also latches cancellation; public dry run
must not become a frontier-consuming run; async Iggy needs retained ownership.
No unit4 shared-runtime edits are approved yet. C5 correction scope is approved.

Latest peer state: Fable CF-0054 proposes a small lower-layer bounded-source
contract extraction in drafta0e5644b §6. Connect/Plan/Execution/Session already depend
on DataSource, so a DataSource adapter cannot import Connect's private trait without
a cycle. Proposed destination: common-datafusion/src/streaming/bounded.rs; protocol-
neutral Cursor/Incarnation/PartitionId/Partition/SourceDescriptor/Range/ScanError and
BoundedSource only. Connect keeps intents/progress/deterministic tests and Spark
error conversion; Iggy SDK stays in its later adapter. Existing streaming::source::
StreamSource emits flow-event plans and has no bounded frontier/range contract;
leave it intact.

**CF-0056 scope approval:** Fable may implement the move-only extraction, preserving
current method shapes and leaving existing StreamSource unchanged. No new dependency,
SDK, feature activation or unit4 runtime changes. Async conversion is a separate
proposal: the current error model cannot represent transport/auth/provider uncertainty
and describe is infallible. Require preserved typed provider causes and nonblocking
calls. Review the exact offered source and detached combined gate before integration.

**Completed common unit:** Sail `cae618d7ff4661cb126333ad109f275b32bcad4b` imports
root_lowercase.rs, tables and oracle from immutable71e4a94d9, adds its module declaration,
and splits tests into root_lowercase_tests.rs. Production/table/oracle bytes match the
offer; malformed/missing explicitly supplied corpora now fail. All24 common library
tests, fmt, strict Clippy and a separate68,588-case replay pass; negative controls
exit101 as expected. [Evidence](docs/sail-declarative-pipelines/evidence/root-lowercase-integration/README.md).
No dependency/lock change or CDC caller. The full offered stack is still unintegrated.
The minimal Grust column kernel is now integrated in Sail
`02d39b5fead46b694725c97de1b2341793100ca2`: exact four-file Grust727baa3e match,
all16 library tests/fmt/strict Clippy pass, and only its own lock stanza is new.
No Connect dependency yet; consumer manifest/lock edge must land together.
[Evidence](docs/sail-declarative-pipelines/evidence/grust-columns-integration/README.md).
C5 review/decisions are in CF-0058,0064,0066,0074,0082,0089,0095,0099. Current
truth: the retained wrapper/callback carrier, typed root-pair merge error and revised
loop are offered; none integrated. The two source corrections to Codex's earlier
reading are retained in the channel: same-named-flow inference can run before final
inference even without declaration; table installation waits for all producers, so
declared-schema readers do not bypass failed-producer availability. Fable's b61da2c98
implements the reviewed loop and fixes the private SMALLINT/CHAR/VARCHAR formatter
against raw64-case JVM parameters, public toDDL unchanged. Keep that formatter
correction reviewable during integration rather than silently accepting the original
renderer-normalised evidence. Phase6 and phase4 follow-ups address later source
findings; latest7962984be has133 Rust/277 Python +1 strict xfail for missing flow-failure
events. Full original-suite phase parity still needs independent combined review.
Async source error-only types f93efc3c9 are offered, no signatures changed. Async
conversion awaits ownership review; PositionStore/C0 remain deferred. A timed-out
read may have executed, SDK future drop does not prove clean drain, and read-back
is not durability. Current proposals/evidence live in the Fable docs worktree; read
the live channel and exact immutable offers before integration or scope decisions.

## Runtime and ORC work Codex must continue

Read [LOCAL-STREAM-OWNERSHIP-DESIGN](docs/sail-declarative-pipelines/LOCAL-STREAM-OWNERSHIP-DESIGN.md),
[SESSION-CLEANUP-LIFECYCLE-DESIGN](docs/sail-declarative-pipelines/SESSION-CLEANUP-LIFECYCLE-DESIGN.md)
and [owned-effect checkpoint](docs/sail-declarative-pipelines/evidence/checkpoint-effect-adapter-design/README.md).
TaskResourceScope.seal closes admission without cancellation; cancel closes and
latches cancellation. Local stop qualifies its owned stream/registered resources,
not every legacy/operator/provider effect. RuntimeAwareObjectStore's spawned PUT,
creation/complete and Drop abort are not a full session barrier.

Selected next boundaries: operation-scoped ownership (not a mutable owner on a
cached global store); one multipart lifetime supervisor owns creation/parts/
complete/abort; cleanup remains possible inside that admitted lifetime after job
sealing. Retain runtime affinity and synchronous part order. Exact owner hook API,
provider qualification and runtime-wrapper instrumentation remain unresolved.
An outer store forwarder alone misses nested detached work. ParquetSink resolves
its store again through runtime_env, so wrapping only an earlier local store
variable misses writes. A private RuntimeEnvBuilder.from_runtime_env registry
overlay is the routing direction; preserve underlying resources/cache contents,
not identity of the newly built CacheManager container.

The typed-error prerequisite is done at34eb270d00. The owned PUT component is
committed at590fc2f9d3: run retains a completed result future in the existing scope,
shares the original typed error with observer/drain, and invokes no provider for
sealed or unpolled calls. It is not routed into existing pipeline writes yet.
The multipart component is now implemented at4cb9aec14: prepare an unstarted
supervisor, register its entire run before creation, then await a command handle.
It retains raw creation/part/complete/abort futures, bounded FIFO part admission,
concurrent uploads, shared typed errors and exactly one disposition. Notifications
happen outside the admission lock and capacity is released before result wakeup.
Failed complete remains uncertain without blind abort. Native wrapper Drop policy
is corrected below; checkpoint routing remains unchanged. The TaskResourceScope adapter is done below. Read the
[concrete design](docs/sail-declarative-pipelines/OWNED-MULTIPART-SUPERVISOR-DESIGN.md).
33 library/16 optimized tests pass, all ten load workers joined. Initial fixture
compile failure, failed notification control, canceled wrong-checkout run and
superseded passing candidates are retained in its evidence packet.
The execution adapter is implemented atbeebb83d0 in sail-execution::owned_multipart:
register the entire supervisor before creation on the existing scope/runtime; preserve
Complete causes alongside CommitStateUnknownError in a DataFusion Collection.
197 execution library tests/fmt/strict Clippy and5 optimized adapter tests under ten
joined load workers pass. Shared-store sibling isolation and actual scope cancellation/
drainage are tested. Removing only the marker fails the unchanged classification test.
No dependency or checkpoint/session change. Runtime-loss classification is now fixed
at9d83baa8b: spawn_mutation/run_mutation retain the real JoinError and nonretryable
uncertainty. Generic resources, cooperative settlement and normally returned errors
are unchanged. Actual PUT and multipart publication-before-runtime-loss regressions
pass; the unchanged multipart control fails on old production. 111+198 library and
111+6 optimized CPU-load tests pass, ten workers joined per run. This covers the
supervisor-runtime boundary, not every nested I/O/provider-returned-error path.
The provider/runtime phase produced a smaller seam from Fable's CF-0088 review:
Native RuntimeAwareMultipartUpload records complete admission before its I/O hop and
suppresses later Drop abort, while explicit informed abort/unpolled cleanup remain.
No descriptor/context marker was added. Known nested wraps on distinct runtimes and
pre-I/O observer loss are tested.070caa80b additionally makes direct interrupted
mutation observers nonretryable before drain, retaining RecvError and real JoinError;
generic resource observers stay generic. Full raw disposal/recovery remains open.
[Current design](docs/sail-declarative-pipelines/PROVIDER-RUNTIME-OWNERSHIP-DESIGN.md)
records why descriptor/context alternatives were not selected for this defect.
Next: qualify remaining nested child/returned-PUT-error paths, then isolated
registry/context routing and actual checkpoint integration; truthful session/manager
shutdown and distributed qualification remain. Keep prefix deletion contingent on
confirmed settlement. An error report alone is not retained raw recovery identity.

Session architecture keeps policy in sail-session: retained cleanup ownership,
Creating/Running/Deleting/DeletionFailed/Deleted/Failed, no resurrection, manager
Open→Closing while required lifecycle/lookup messages are serviced, cancellation
requests before dependent joins, transport drain concurrent with shutdown, always
join actors and retain sibling failures. Exact cleanup driver, operation seam,
legacy effects and fallible distributed actor outcomes remain implementation work.

ORC admission/schema/compression/options/native foundations exist. Public writer,
upload ownership, native memory bounds and remaining semantic types remain open.
Read [ORC writer design](docs/sail-declarative-pipelines/ORC-WRITER-DESIGN.md).
Do not resurrect withdrawn graph/flow ORC override candidate42c65ecf64: reference
probes disproved its blanket source-read configuration assumption. Its evidence
is retained under flow-orc-config-withdrawal. Resolve read/analyzer/write settings
at their actual phases.

## Iggy and durable streaming boundaries

Fable's Grust8b0bd605 packet records actual pinned single-node TCP broker probes:
retention can resume silently at a later offset; partition recreation changes
incarnation while reusing ID/offsets; the SDK can accept and later replay a store request issued while reconnecting. Only acknowledge after SDP's own durable progress; do not infer confirmed commit from SDK acceptance. Compare the first returned position with the requested start and bind incarnation on every range. The packet's OperationUncertain scenario was not induced; preserve that limit. The broker build used Rust1.99.1/hwloc2.15, separate from Sail's Rust1.98.1.

The accepted CDC control-store design specifies durable frontier/intent/progress, CAS/fencing, commit/offset recovery and sealed winners; implementation and real-backend qualification remain open. Do not activate them by accepting pure components. General catalog behavior stays in Sail; LakeCat supplies a catalog/provider path, not an excuse to move Sail's generic semantics into LakeCat.

## Gates, reproducibility and durable tools

Use `/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python` (Python3.12). Generic Homebrew Python3.15 has broken Expat linkage on this host and fails XML checks. For Rust embedding explicitly set PYO3_PYTHON to that interpreter, VIRTUAL_ENV to the .venv and PYTHONPATH to its lib/python3.12/site-packages. Without importable PySpark, get_pyspark_version falls back to3.5 and ORC defaults can appear Snappy instead of4.2 Zstd. Fable's controlled run explained the two old ORC failures; retain the failed full-library run rather than relabeling it.

Rust gates use1.98.1, nightly fmt, --locked and strict Clippy; CARGO_INCREMENTAL=0. The gatehelper supplies PYO3_PYTHON/PYTHONPATH/VIRTUAL_ENV for Python3.12+PySpark4.2.1; the build-interpreter variable alone does not configure embedded module paths.
Check disk before long builds. Every verdict names one immutable detached commit,
with its own target directory; verify HEAD/status before and after. For concurrency,
run optimized tests under CPU load and stop/join every owned worker. Use channels/
held futures for ordering. Source/model/helper probes do not qualify runtime joins.
Do not kill unrelated processes to free a port or cancel another agent's build.

Durable [coordinator helper snapshots](docs/sail-declarative-pipelines/handoff-tools/README.md)
replace reliance on /tmp scripts: make-candidate.py, library-gates.py,
advance-candidate.py, doc-commit.py and evidence-gate.py. They hard-code coordinator
worktrees and /tmp receipt paths. Read them first; parallel Fable must not use them
to advance Codex's branch. In particular advance-candidate does **not** enforce gate
success: inspect exact receipts/source/binary pins and advance only in a conditional
successful chain. Keep dependencies, edits, gates and advancement sequential.

The reusable [frozen public runner](docs/sail-declarative-pipelines/evidence/analysis-order/harness/README.md)
is archived with run.py, manifest and input selections. Supply --commit and a
fresh --output directory. Its 300 selected cases/67 upstream executions need added
feature-specific tests for Fable integration. Historical evidence harnesses often
expect fresh absolute output paths; do not rerun them in place or overwrite logs.

For documentation, prepare an exact candidate, run the detached documentation
gate plus the packet's source/hash/count verifier, then conditionally advance.
Take the canonical log's persistent flock around snapshot prepare and advance;
release it during gates. If Fable appended meanwhile, refresh/regate the snapshot,
never discard its entry. Preserve initial compile failures, canceled invalidated
builds and unchanged-source controls. No new broad tests are needed merely to
check a Markdown edit; the relevant document/source checks suffice.

Keep this handoff current; successors post role/read-through/file scope. Completion requires evidence for the full original goal.
