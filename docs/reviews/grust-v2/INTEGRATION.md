# Wave 2/3 stack integration and review

Integrated into `main` via [PR #47](https://github.com/querygraph/grust/pull/47).
Branch: `work/grust-v2-integrated`.

Exact integrated source: `7d1f3f6f122ea3fe6c6becbe937637ff8fe11ff9`.
The merge retains main and the original stack as parents, so all seven
original PR heads remain ancestors. PRs #40–46 are closed as superseded,
not represented as individually merged into their old stacked bases.

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
are retained. The corrected merge source passed the full exact-source gate below.

## Observed exact-source verdict

> PASSED integrated Wave 2/3 source 7d1f3f6f122ea3fe6c6becbe937637ff8fe11ff9 on main base f568c534378676e48b37f7c9ac868a44e40d22b7: production parser, both draft workspaces and native semantics/SNB oracle; HEAD unchanged and clean

The exact tested merge was promoted to main by a non-forced fast-forward with
an expected-base lease. No different merge commit was substituted. Later
report-only commits do not extend the source verdict; historical imported
receipts still cover only their own original commits.

| Gate                                                          | Outcome                                      |
| ------------------------------------------------------------- | -------------------------------------------- |
| Current parser formatting and Clippy                          | Passed                                       |
| Current parser unit/integration tests                         | 904 passed; 2 ignored, not counted as passes |
| Current parser benchmark smoke checks                         | 12 passed; no performance measurement        |
| Wave 2 Clippy/format and release tests                        | 35 all-features + 31 default passed          |
| Wave 2 programmatic example                                   | Compiled and ran                             |
| Wave 3 Rust format/Clippy; default/all-features/release tests | 40 tests in each configuration passed        |
| Python Ruff lint/format and strict mypy                       | Passed                                       |
| Native relational / iterative / frontend results              | 92 / 22 / 40 passed                          |
| Native new semantics results                                  | 104 passed; 8 expected arithmetic errors     |
| SNB cells, including warmups                                  | 130 passed                                   |
| Unsupported-contract diagnostics                              | 18 refused before execution                  |
| Runtime controls                                              | 19 passed                                    |

[Exact source receipt](integration-evidence/native/source-gate.json),
[full gate log](integration-evidence/native/native-gate.log),
[PR status](integration-evidence/pull-requests.json) and
[review/comment observations](integration-evidence/review-observations.json)
are preserved. There were no review comments on the seven original PRs at
inspection. Owned servers closed without session-shutdown errors and were
terminated with SIGTERM; binary hashes were unchanged.

## Shared-host cost observations

This repeats the prior five-query SNB v1 development track against current
main's parser. Two configured workers, a fair 256-MiB Sail-managed pool,
fresh execution scope per cell, warmup for each variant then ABBA twice.
Four measured cells per variant form each median. Query planning, scans,
program materializations/traversals, final collection and cleanup are included;
input preparation and compilation are excluded. There is no OS RSS cap.

Ratio is optimized median / resolved median. Every binding and control is
shown, including ratios above one. The small development dataset and shared
host do not establish large-graph throughput or universal performance.

| Query | Binding | Optimized / resolved |
| ----- | ------- | -------------------: |

| IS1 | 8796093022220 | 0.871 |
| IS1 | -1 | 0.870 |
| IS3 | 8796093022220 | 0.976 |
| IS3 | -1 | 1.006 |
| IS4 | 343597383680 | 0.983 |
| IS4 | 206158430246 | 0.977 |
| IS4 | -1 | 1.013 |
| IS5 | 343597383680 | 0.979 |
| IS5 | 206158430246 | 0.972 |
| IS5 | -1 | 0.984 |
| IS6 | 343597383680 | 0.990 |
| IS6 | 206158430246 | 0.986 |
| IS6 | -1 | 0.971 |

[All normalized cells and exact answers](integration-evidence/native/snb/receipt.json),
[ratios/ranges](integration-evidence/native/snb/ratios.json),
[queries, parameters, types, SQL/programs, estimates and rewrite traces](integration-evidence/native/snb/queries.json),
and [schema/table request](integration-evidence/native/snb-request.json)
are published. Absolute execution/compile times are omitted from public JSON;
verbose explain strings are replaced by hashes. Full raw evidence remains at
the external output location in the source receipt. Unknown iterative cost,
including IS6, remains unknown rather than zero.

[New semantics answers](integration-evidence/native/semantics/receipt.json),
[refusals](integration-evidence/native/refusals.json), and the imported
[development failure index](wave-3/evidence/cypher-semantics/development-failures/index.json)
keep successful answers, expected errors, refusals and failures distinct.
[Cleanup receipt](integration-evidence/cleanup.json) records removal of the
three owned targets and the two detached checkouts. Native Sail and full raw
evidence remain available.

## What follows

The integrated code remains an unpublished read-query draft. Production engine
migration, complex SNB queries, larger-dataset qualification and a working
Cosmolang/browser/Nutmeg slice are further work. This integration does not
claim those deliverables. The [earlier consolidated Sem report](https://github.com/querygraph/grust/blob/36eaf1edcfd80e1d968256522c3b46d6b6df5e5c/docs/reviews/second-string-extension-2026-10-06/SEM-STATUS.md)
is an immutable historical edition; this report updates the Wave 2/3 PR states
and source qualification.
