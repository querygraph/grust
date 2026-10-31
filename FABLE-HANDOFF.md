# Fable continuation handoff

Snapshot written 2026-10-31T16:37:28.838746+00:00. Live coordination read through **CF-0519**.
Re-read live channel/Git/process state; later entries supersede this snapshot. [Initial scope](codex-fable-handoff.md).

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
| Codex product | `/Users/alexy/src/sail-pipelines-proposal`, `work/spark-declarative-pipelines` | `4fca6f3d4982e2639061094ededdd12a50f8ad1c` |
| Codex documents/live log | `/Users/alexy/src/grust-sdp`, `work/sail-declarative-pipelines` | base before this update: `d649eb485c2fb4b68c399ed1506db7a181854090` |
| Codex Sail detached gate | `/Users/alexy/src/sail-sdp-gate` | verify live gate HEAD; local capture/control evidence linked below |
| Codex Grust detached gate | `/Users/alexy/src/grust-sdp-review-gate` | changes with each documentation candidate |
| Parallel Fable product | `/Users/alexy/src/sail-sdp-fable`, `work/sdp-streaming-cdc-fable` | `d88467e419a6fe2546e8bd18d4705e4909d02b28` (inline guard; pure pieces imported separately) |
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
- Codex owns runtime/resource scopes, local/distributed cleanup, session/effect
  ownership and ORC. Fable owns offered pipeline CDC/streaming modules and tests.
  Shared orchestration/session/protobuf/catalog/Delta edits require declared scope.
  C5's analysis/graph correction is approved; unit4 shared runtime edits are not.

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

Latest native/public-qualified source/runtime is **4fca6f3d4982e2639061094ededdd12a50f8ad1c** (254 selected analyzer+Connect tests,300 selected+67 upstream,15 Flow-policy cases per engine). Common source unchanged from c864/279 historical gate; no common rerun claimed. Original Spark reference remains142 executions/595 names.
300 selected public +67 upstream Python executions; inspect the [numeric divisor packet](docs/sail-declarative-pipelines/evidence/numeric-divisor-guard/README.md)
for historical arithmetic qualification and basic-metadata-refresh packet below for test-source/inherited runtime proof. These selections are not original Scala acceptance.

## Current implementation and immediate next work (CF-0519)

Sail HEAD **4fca6f3d4982e2639061094ededdd12a50f8ad1c** is clean. [Flow INSERT policy](docs/sail-declarative-pipelines/evidence/flow-insert-policy/README.md) follows partition→columns→overwrite→by-name, after raw Flow-name validation and before target resolution; shared INTO IFNE remains raw parser error.254native(52analyzer+202Connect)/fmt/strictClippy,fresh300+67,paired15 and12 registration vectors pass; message/precedence controls each fail unchanged0/1 with production-only diffs/test blob proof. Three BDD SQL inputs unchanged: exact per-input expected messages replace incorrect combined message; harness preserves297IDs and explicitly maps three same-query IDs, changing only feature source hash. Public15 includes complete wrapper metadata for these same three cases. Prior [shared INSERT validation](docs/sail-declarative-pipelines/evidence/insert-mode-validation/README.md)cbee/252native/300+67/paired15/three controls retains initialb48 golden failure and official one-output correction among32 unchanged inputs/Spark exceptions. Prior18604 table-as-select and c864 raw Flow units remain qualified in own packets. Existing525/580 partial coverage and canonical486sites116reviewed87partial399unmapped unchanged; original reference142/595names43nonempty/56bindings,no JVM-on-Sail promotion. [Registration design](docs/sail-declarative-pipelines/REGISTRATION-ERROR-FIDELITY-DESIGN.md) reuses source/wrapper/ownership machinery. Fable CF-0514 accepts producer order/strings/BDD migration; residuals pinned: overwrite IFNE without PARTITION must be a grammar error, and WITH-led/non-INSERT Flow bodies must fail parsing before the current prefixed fallback. [Syntax design checkpoint](docs/sail-declarative-pipelines/SQL-SYNTAX-DIAGNOSTICS-DESIGN.md) announced to user for Astra. New16 Spark vectors pin raw syntax error/hint empty/first IF or invalid body token and valid INSERT-query WITH; two ordinary statements submitted through registration are not execution evidence. Both directory forms/REPLACE WHERE get Unsupported-flow wrapper; REPLACE USING gets overwrite rejection, correcting Fable CF-0517 drop-criteria inference. Next generic macro variant parser hook keeps default/AST layout, then dedicated INSERT/Flow grammar plus owned token/span/reason/context diagnostic retention before Display. Public parity required before integration; no parser source change yet. Reject end-of-body filters/regex/string reconstruction. Broader hints/query contexts/mixed-error ordering remain open. Current public runner `/tmp/sail-sdp-flow-policy-public-harness/run.py`, archived in the policy packet, uses300cases with all source hashes including23 BDD/helper bindings. Expanded scope5 unmapped constraints105/querytext227/collation253/lifecycle2 and owned-root batch work remain. No public Table/Sink/streaming/CDC activation/E′/F–K authority or new effect path. Fable design review invited in CF-0518, read-only; no source assignment. All owned jobs/listeners terminal at snapshot; revalidate. Full goal remains incomplete.
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

[Read](docs/sail-declarative-pipelines/evidence/resolver-read-session/README.md),
[writer/schema](docs/sail-declarative-pipelines/evidence/resolver-writer-session/README.md) and
[lake metadata/properties](docs/sail-declarative-pipelines/evidence/lake-metadata-session-callbacks/README.md)
preserve their exact historical gates and bypass failures. The existing
[preparation](docs/sail-declarative-pipelines/evidence/local-bound-preparation/README.md),
[ScopedSession](docs/sail-declarative-pipelines/evidence/scoped-session/README.md) and
[helper](docs/sail-declarative-pipelines/evidence/resolver-query-session/README.md) seams remain opt-in.

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
reported inCF-0206; queue delay/self-matching pgrep failure disclosed. No root integration. E′/F–K not
authorized yet; two CDC phase calls/four assertions remain reintegration obligations.
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

Keep this handoff current; successors post role/read-through/file scope. Completion requires evidence for the full original goal.
