# Wave 2/3 stack integration and review

Integration branch: `work/grust-v2-integrated`.

## Inputs and scope

The reviewed PRs are #40 (Wave 2), #41 (Wave 3 interfaces), #42 (executable
resolution/costed joins), #43 (finite paths/providers), #44 (iterative Sail),
#45 (Cypher frontend) and #46 (semantics/SNB). Their source heads form a
linear ancestry chain ending at `36eaf1edcfd80e1d968256522c3b46d6b6df5e5c`.

Integration starts at current main `f568c534378676e48b37f7c9ac868a44e40d22b7`.
It imports the final Wave 2/3 draft paths from that stack, including their
historical source receipts. The earlier research-report base is linked by
immutable URL. This keeps the integration scoped to the seven PRs.
Production library source, root workspace manifests and lockfile match the main base;
all draft crates remain `publish=false`. The one root-crate change corrects a legacy benchmark fixture, described below. No released API migration occurs.

## Review findings

1. **Reproducibility fix required:** the Wave 3 standalone lockfile named local
   grust-core/grust-procedures/grust-cypher 0.23.0, but current main has 0.24.0.
   `cargo check --locked` refused to build. The draft lockfile now records the
   three current path-package versions; no registry dependency or root lockfile
   was updated. The initial failed check is retained.
2. **Parser compatibility requires a new verdict:** main includes typed write
   AST changes after the stack diverged. Compilation against the current parser
   passes; the detached gate additionally runs its own tests and the native
   source-text qualification. A previous branch verdict is not substituted.
3. **Architecture boundaries reviewed:** frontend emits unresolved IR; catalog,
   function/provider binding and backend storage remain separate. The join
   optimizer preserves optional, non-immutable, correlation/materialization and
   graph-program boundaries. Unknown estimates remain unknown. Plain SQL
   emission refuses programs needing materialization/traversal steps.
4. **Execution boundary reviewed:** ordered steps own scratch views/files;
   stable outer-row tokens preserve duplicate correlations; paths hydrate by
   typed identity and ordinal. Cancellation/resource refusals do not expose
   partial success. The adapter writes fresh unsorted Parquet and does not
   validate valid graph data by distributed jobs.
5. **Qualification limits retained:** local shared-filesystem execution,
   managed-memory pools rather than process RSS, explicit language refusals,
   five SNB development queries rather than a full audited workload, and an
   unpublished draft rather than production query-engine replacement.
6. **Existing main benchmark fixture fixed:** the combined candidate gate
   failed in `cypher_read_planning/two_segment_filter_and_spark_sql`; an
   independent clean main checkout reproduces it. The query repeated KNOWS
   on both hops, which the legacy planner deliberately refuses because its
   SQL joins cannot guarantee TRAIL uniqueness for overlapping type sets.
   The fixture now uses KNOWS/FOLLOWS, retaining two-hop planning and Spark
   SQL generation and the unchanged `pushable query` assertion. No production
   planner rule is relaxed. Both failed logs are preserved.
7. **Document integration fix:** links to the consolidated Sem report now name
   its immutable published edition, which predates this integration. New
   integration evidence will have its own exact-source identity.

## Gate

Run `bash docs/reviews/grust-v2/gate-integrated.sh` in a clean detached
checkout with owned external `CARGO_TARGET_DIR` and `GATE_OUTPUT`,
`CARGO_INCREMENTAL=0`, `GATE_PYTHON`, `SAIL_BINARY` and `GATE_SNB_CHECKOUT`.
It verifies production library paths equal the pinned main base (with the
explicit benchmark-fixture exception), runs current parser
Clippy/tests, Wave 2 formatting/Clippy/release tests/example and the full Wave 3
Rust/Python/native semantics and paired SNB gate. A final verdict requires
unchanged HEAD and a clean checkout.

The first candidate `42400a2f81b66c6a6db0818ca03380c31cf579fe` failed in the
legacy benchmark and has no passing integration verdict.
[Candidate failure](integration-evidence/failed-candidate-42400a2f.log) and
[independent main baseline failure](integration-evidence/main-baseline-benchmark.log)
are retained. The corrected candidate still needs the full exact-source gate.

Exact source verdict and integrated evidence are pending. Historical receipts
inside the imported drafts continue to cover only their original source commits.
