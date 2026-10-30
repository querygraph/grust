# Fable continuation handoff

Snapshot written 2026-10-30T17:19:15.794246+00:00. Live coordination read through **CF-0153**.
Re-read the live channel and Git/process state before acting; later entries supersede
this snapshot. The original [six-unit handoff](codex-fable-handoff.md) supplies initial scope.

## Goal and current truth

The user goal remains: **design and build Sail Declarative Pipelines, targeting
Spark 4.2.1, and pass all Spark SDP tests**. Keep that full objective active.
Batch comes first, then streaming/Iggy and CDC, in human-reviewable increments.
Do not redefine success as the currently passing helper or public selection.

Substantial batch/SQL/catalog/ORC-read work and execution-ownership foundations
are committed in Codex's Sail branch. Streaming/CDC components are offered in a
parallel Fable branch; **the common ROOT lowercase helper and Grust column kernel are integrated; streaming/CDC
modules remain unintegrated**. Public ORC writing, complete session/cluster
cleanup, durable streaming/CDC effects and full original Scala-suite acceptance
remain incomplete. Existing execution still rejects incremental/sink pipelines
before writes. Keep that guard until the effect path is qualified.

Fable maintains a separate [Fable-owned supplement](/Users/alexy/src/grust-sdp-fable/docs/sail-declarative-pipelines/FABLE-HANDOFF-FABLE.md),
originally committed in Grust `524642ad`, with the vendor/consumer order corrected
in `e0bc540a`; recover the corrected version with git show if that peer worktree
is absent. It supplies Fable-side gate scripts/environment and post-CF0044 offers.
Use actual Git ancestry for integration: original vendor d07a95c2c precedes
consumer167d577c6.

## First actions after resuming

1. Read applicable AGENTS.md, this handoff and the coordination protocol below.
2. Determine which role you replace. A successor taking over Codex uses the
   coordinator worktrees; a successor replacing parallel Fable uses Fable's
   worktrees. A handoff file or old ACK does not establish that another agent
   or process stopped. Observe actual Git/process/tool state and coordinate.
3. Read the canonical log **from the last acknowledged point**, not its tail.
   Then post a scoped ACK using the generated read-through reference.
4. Inspect HEAD/status in every worktree you will touch; fetch the repositories.
   Preserve independently active checkouts, offered history and failed evidence.
5. The ROOT lowercase common utility is integrated at cae618d7f with its full
   common gate and independent corpus replay. Fable has move-only lower source-
   contract extraction approval in CF-0056; async API changes remain separate.
   Review C5/progress corrections separately. C0 remains
   a user-notified Astra design checkpoint; do not select its authority implicitly.
6. Continue independent work; only claim a live wait after polling its actual handle.

## Worktrees, branches and source pins

| Role | Path / branch | Inspected source snapshot |
| --- | --- | --- |
| Codex product | `/Users/alexy/src/sail-pipelines-proposal`, `work/spark-declarative-pipelines` | `2e7beda829a107768d0bb00f6d526c6d4d268b30` |
| Codex documents/live log | `/Users/alexy/src/grust-sdp`, `work/sail-declarative-pipelines` | base before this update: `a1fea2519990f4f77a09bedf842920ba3f6487f6` |
| Codex Sail detached gate | `/Users/alexy/src/sail-sdp-gate` | local preparation candidate `2e7beda82` (all owned gates terminal) |
| Codex Grust detached gate | `/Users/alexy/src/grust-sdp-review-gate` | changes with each documentation candidate |
| Parallel Fable product | `/Users/alexy/src/sail-sdp-fable`, `work/sdp-streaming-cdc-fable` | `9dc1b1157dd31d584a6c7eaf99770c778d344e6b` (lowering offered/unintegrated CF-0152) |
| Parallel Fable docs | `/Users/alexy/src/grust-sdp-fable`, `work/sdp-streaming-cdc-fable` | `659dc0c230c2b352ab6fd3a57f21e0039a7c554a` |
| Parallel Fable detached gate | `/Users/alexy/src/sail-sdp-fable-gate` | verify its actual current candidate/process |
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

Local Sail `main` was explicitly fast-forwarded via `git fetch origin main:main`
from0ba425c03 through d803e13f0 to `ac4690078021cf2a5402dc5c7b38a886f1916c73`, then equality with
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
- Codex owns runtime/resource scopes, local/distributed cleanup, session/effect
  ownership and ORC. Fable owns offered pipeline CDC/streaming modules and tests.
  Shared orchestration/session/protobuf/catalog/Delta edits require declared scope.
  C5's analysis/graph correction is approved; unit4 shared runtime edits are not.

## Canonical communication protocol

Read [CODEX-FABLE-COORDINATION.md](docs/sail-declarative-pipelines/CODEX-FABLE-COORDINATION.md).
The only live channel is `/Users/alexy/src/grust-sdp/codex-to-fable.md`.
The persistent lock is `/Users/alexy/src/grust-sdp/codex-to-fable.lock`.
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

Latest fresh public CLI gate is **2e7beda829a107768d0bb00f6d526c6d4d268b30**:
300 selected public +67 upstream Python executions pass, rebuilt CLI pinned and
owned server stopped (exit0/no listeners). Session32905 is terminal. Earlier public
verdict47c473e6b remains archived; these selections are not full SDP acceptance.

## Current implementation and immediate next work (CF-0150)

Coordinator HEAD **2e7beda829a107768d0bb00f6d526c6d4d268b30** is committed/clean.
Earlier a0 local preparation passes375 libraries/16 optimized/300+67 public;
b90 ScopedSession passes129 library/optimized and unchanged provider/builder
controls. [Local packet](docs/sail-declarative-pipelines/evidence/local-bound-preparation/README.md),
[Session packet](docs/sail-declarative-pipelines/evidence/scoped-session/README.md).

[Resolver helper packet](docs/sail-declarative-pipelines/evidence/resolver-query-session/README.md)
2e7beda82 passes fmt/strict Clippy,42 plan libraries/42 optimized tests, rebuilt
CLI300 public+67 upstream tests; owned server stopped. Optional borrowed query
Session reaches pivot inference, time-travel scalar, tail count and crosstab;
nested stored-view resolver propagates it. Default collection stays on authoritative
ctx. Unchanged bypassa63d6fb35 fails four helpers/missing scope; fallback passes.
Initial420190263 import failure and qualifier extension-name error are retained.
Actual helpers are tested; nested view inheritance has source/regression coverage,
not a new isolated fixture. Direct config mutation is tested, not SQL/RPC SET.
CF-0150 posts DONE; no public callers/factories/final execution are migrated yet.

[Design](docs/sail-declarative-pipelines/PRE-PLANNING-OWNERSHIP-DESIGN.md) remains active
for Astra. Next: provider factory propagation, authoritative command/capture and
execution transfer, typed primary/cleanup transport, cluster preparation before
generic caller migration. Routing/byte/outcome/recovery/full acceptance stay open.

Own session94290 is terminal: [independent correction replay](docs/sail-declarative-pipelines/evidence/fable-binding-correction-review/README.md)
on41f09ec47 passes both original scalar/EXISTS fixtures (2 passed/0 failed);
CF-0151 reports the narrow closure. Gate restored to2e7. No owned process pending.
This is validator coverage only, not full CTE/alias/provider/RPC proof or integration.
Fable correction/admission2e9f098b2 remain offered/unintegrated; CF-0149 reports gates.
Original two validator gaps are [confirmed](docs/sail-declarative-pipelines/evidence/fable-binding-expression-review/README.md).
CF-0146/0148 [admission review](docs/sail-declarative-pipelines/evidence/fable-admission-source-review/README.md)
requires join orientation, separate range-subquery counts and actual provider/static
provenance (including local analysis placeholders); Fable accepts in CF-0147.
Mixed read modes remain required follow-up, not a permanent selected restriction.
CF-0152 offers correction1d570ae55 and lowerer9dc1b1157; their gate is pending,
source/independent review incomplete. CF-0153 acknowledges receipt only. Next review
actual provenance/empty handling/canonical names/context; scope is unused in-memory.

## Acceptance accounting and major remaining work

The canonical [inventory](docs/sail-declarative-pipelines/spark-4.2.1-inventory.json)
currently has **462 static registration sites**, **97 assertion-reviewed**,
**61 partial-behavioral-port**, **401 unmapped**. These are not expanded runtime
counts; none is fully qualified by running the original Scala suite against Sail.
[CROSSWALK.md](docs/sail-declarative-pipelines/CROSSWALK.md) supplies assertion
context, but its table can lag the JSON (currently shows 59 partial in that table).
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

Fable's starting Sail base is `779cb136d988c759a381ea1ace6c2e7649e3dbbc`.
Original offers: Grust1493d8a36 (columns kernel), Saild07a95c2c (vendor) and
Sail167d577c6 (CDC definition validation). Preserve them as evidence.
The original vendor-only commit puts a connect dependency edge in Cargo.lock
before its Cargo.toml declaration; assemble independently buildable vendor and
consumer units during integration rather than blindly cherry-picking that defect.

| Offered Sail commit | Work / present review state |
| --- | --- |
| `49f32b65d` C1 | Attribute/source identifiers. Exact parser matched JVM on 9,338 names; source/parser correction accepted at that boundary. |
| `29056716b` C3 | Sink rejection removed from graph validation; source phase correction accepted. |
| `f4537586b` C2 | Original ROOT lowercase model. Rejected: 1,332 mismatches in 39,215 independent contexts. Preserve failed evidence. |
| `a495cb02d` C4 | Caller-resolver kernel and Scala map-order adapter. 23,050 independent queries / 771 schemas match; 16 kernel tests, Clippy/fmt and exact vendor hashes pass. |
| `2dcd0eaa9` | Corrected JDK word-break iterator. 68,588 independent contexts match, including all earlier failures; combined 23,050 lookups also match. Common helper integrated atcae618d7f; CDC consumers still pending. |
| `550bb198a` C5 | First phase correction; rejected as incomplete global analysis-before-validation ordering. |
| `1eea0b140` C6 | Construction-test rename, real PySpark-produced wire fixture, opt-in lookup replay. Full source/evidence review pending. |
| `b7118b953` unit2a | Original-row validation before dedup; pure DataFusion component. Initial source reading performed, independent reference/edge review not finished. |
| `f7adb3f05` unit2b | Dedup using existing MaxByFunction/StructFunction; disclosed sail-function dependency edge. Independent review not finished. |
| `c9a0132cf` unit3 | Bounded deterministic source/intents/progress; cross-run incarnation and zero/stall findings raised. |
| `6620ee940` unit5 | Prepared-input manifest, canonical row order, receipt/content digests. New blocking review CF-0043, below. |
| `d38058973` | Opt-in external lowercase replay. Fable reports detached gate and both corpus replays; inspect exact evidence. |
| `769914891` | Offered C5/global-phase + incarnation-bound progress corrections. Fable reports 124 Rust pipeline / 249 Python pipeline tests and a detached verdict in CF-0045. Source-reviewed in CF-0058: fixes earlier checks/progress schedules; no new independent runtime verdict. Schema-merge/missing-source phase divergence and full failure-map semantics remain open. |
| `dc8b7eb31` | Prepared-input fixes: IPC schema encoding, manifest consistency checks, strict case labels and C4-bound keys at every row count; tested independently at the component boundary in the later source71e4a94d9. |
| `71e4a94d9` | Expected authoritative InputIdentity binding; Fable detached fmt/Clippy/common/pipeline/maturin/249 Python verdict CF-0052. Independent prepared-component review passes the stated API checks; physical IPC representation boundary remains open. |
| `33a883091` | Approved move-only lower bounded-source contract extraction; detached common/common-datafusion/Connect and249 Python gate CF-0062. Offered, not integrated. |
| `bc23c8db6` / `105967e17` | Typed per-flow report and callback carrier, unwired, detached gates CF-0070/0073. Source review CF-0071 requires retaining maps in the raised error, not dropping them when constructing its message. Not integrated. |
| `798cd35c9` | Retained report variant + actual AnalysisException Status mapping, detached gate CF-0078. Fixes source-level map loss; unwired/unintegrated. |
| `92ab01326` / `b61da2c98` | Typed merge-error prerequisite then C5 loop; the loop also corrects raw JVM renderer parameters (64 cases), preserves scopes via two constructor call-site edits, and leaves event diagnostics as strict xfail. Offered/unintegrated;133 Rust +265 Python/1 xfail gate. |
| `f93efc3c9` / `2561606e9` / `7962984be` | Source error-only types (no async conversion), phase6 no-flow ordering, phase4 table/streamingness predicate. Latest detached gate133 Rust +277 Python/1 xfail (CF-0102). Offered/unintegrated. |

Grust offers: kernel727baa3e; evidence5538854f/aba8ef64 (lowercase),31997f0f
(CDC validation),275e666b (microbatch),834cae55 (streaming/prepared),8b0bd605
(Iggy),f13e9b48 (corpus replay); draft88e48c03 (bounded admission). These objects
are in the shared Grust repository and files in the Fable docs worktree.
The coordination reader2103fb56 was integrated and fixed as Codexb7290eb1;
IDs/protocol foundation is16a0a7f4. Do not integrate that reader twice.

Peer event follow-up37c4d9c4a remains unintegrated; CF-0123 reports detached gates.
Earlier3ef4e238a detached gate passes; FIFO13e0d4f96's race/pytest exit1 remains
retained. HTTP entry fixes scheduling; latest source adds full setup cleanup,
joined-state assertions and Shared(Context) lines. Shared Status classification
needs a separate probe; message-only events do not qualify origin/WARN assertions.

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
incarnation while reusing ID/offsets; the SDK can accept and later replay a store
request issued while reconnecting. Only acknowledge after SDP's own durable
progress; do not infer confirmed commit from SDK acceptance. Compare the first
returned position with the requested start and bind incarnation on every range.
The packet's OperationUncertain scenario was not induced; preserve that limit.
The broker build used Rust1.99.1/hwloc2.15, separate from Sail's Rust1.98.1.

Actual durable frontier/intent/progress, CAS/fencing, target commit/offset atomicity,
MERGE recovery, sealed staging versus reconstruction and B12 tie policy remain
open production design work. Do not activate them by accepting pure components.
General catalog behavior stays in Sail; LakeCat supplies a catalog/provider path,
not an excuse to move Sail's generic semantics into LakeCat.

## Gates, reproducibility and durable tools

Use `/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python` (Python3.12).
Generic Homebrew Python3.15 has broken Expat linkage on this host and fails XML
checks. For Rust embedding explicitly set PYO3_PYTHON to that interpreter,
VIRTUAL_ENV to the .venv and PYTHONPATH to its lib/python3.12/site-packages.
Without importable PySpark, get_pyspark_version falls back to3.5 and ORC defaults
can appear Snappy instead of4.2 Zstd. Fable's controlled run explained the two
old ORC failures; retain the failed full-library run rather than relabeling it.

Rust gates use1.98.1, nightly fmt, --locked and strict Clippy; CARGO_INCREMENTAL=0.
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

The reusable [frozen public runner](docs/sail-declarative-pipelines/evidence/local-runner-ownership/public-harness/README.md)
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

## Continuing this handoff

Keep source pins, decisions, findings, process handles and evidence current; link
immutable packets and REVIEW for detail. A successor posts its read-through, role
and file scope. Completion requires evidence for the full original goal.
