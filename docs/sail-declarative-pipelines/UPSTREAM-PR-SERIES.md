# The upstream series: Sail Declarative Pipelines, native extensions and performance as pull requests

This is the plan for offering the `work/spark-declarative-pipelines` branch to
Sail's maintainers as a series of self-contained pull requests. The design they
implement is recorded in [SAIL-SDP-DESIGN-DECISIONS.md](SAIL-SDP-DESIGN-DECISIONS.md)
(the record); each PR cites the sections of the record it implements, and the
record's §0 is the cover letter for the whole series.

- **Reviewed:** the C-track split, by the CDC lane (CF-0722, 2026-11-04); its corrections are in place: G14, the `iggy` feature unit before C3, C6a/b/c reordered, tests travel with their PRs.
- **Opened:** D1, the design record, as draft [lakehq/sail#2930](https://github.com/lakehq/sail/pull/2930) (2026-11-03, from `alexy/sail` branch `docs/sdp-design-record`, page `docs/development/pipelines/index.md`).
- **Status:** plan, 2026-11-03, with the owner's eight decisions recorded in
  place (examples repository, `orc-rust` release first, Grust kernels as
  crates, the general track first, the record as a Sail docs PR, Iggy behind a
  feature, the discussion post by the owner in week 1, both lanes after A9).
  Nothing has been opened upstream.
- **Source:** root `d65857340` (427 commits over upstream `0ba425c03`,
  1,179 files, 274k lines added, 2.5k removed). Upstream `main` is at
  `62251e0a2`, 22 commits past the base.
- **Target:** `lakehq/sail` `main`, one PR at a time within a track, tracks
  in parallel where the dependency graph allows.

## 1. Principles

1. **Each PR stands alone.** It builds with `--locked`, passes `cargo fmt`,
   strict Clippy and its own tests on upstream `main` with only the PRs it
   lists as prerequisites applied. No PR leaves `main` in a state where a
   feature is half-wired; test-only scaffolding carries a labelled
   `expect(dead_code)` that the wiring PR removes (record §17).
2. **Upstream's shape.** Titles follow upstream's conventional commits
   (`feat:`, `fix:`, `perf:`, `chore:`, `docs:`). Upstream's merged PRs are
   mostly under 1,000 lines with occasional 3,000-line feature PRs and the
   rare mechanical chore; the series aims for that distribution. A PR above
   3,000 lines is split unless the split would break principle 1, and then
   the description says why.
3. **General improvements first.** Changes that make Sail better without
   pipelines (errors, casts, TIME, catalog behavior, session lifecycle,
   ORC, performance) go first, each justified by its own tests and by a Spark
   measurement where it claims parity. The pipelines module then lands on a
   `main` that already has what it needs.
4. **Evidence travels with the PR.** Each description names the record
   section, the Spark 4.2.1 measurement it matches, the deliberate
   differences it introduces, and the gate it passed on the branch. Test
   counts are stated; elapsed times are not.
5. **Rebase hazards are named.** Since the base, upstream moved
   `python/pysail` (945 files, the "organize development tests" chore),
   `sail-logical-optimizer`, `sail-function`, `sail-physical-optimizer` and
   `sail-plan`. The PRs that touch those are rebased first and their
   descriptions say what moved.
6. **Nothing is proposed that we would not maintain.** Vendored third-party
   code, publishing contracts, book sources and benchmark corpora stay on
   the branch (record §0, "What is not proposed").

## 2. What the branch contains, by crate

Lines added over the base, for sizing; the tracks below cut across crates.

| Area | Lines | Content |
| --- | ---: | --- |
| `sail-spark-connect` | 37.7k | `pipelines/` module: core 7.9k, AutoCDC 17.2k, streaming 5.1k, config 1.5k, SQL 0.9k, materialize 0.8k; server, proto and session changes 2.1k |
| `python/pysail` | 17.3k | 75 pipeline test files, Delta/catalog/Iceberg/execution suites, testing steps, Unity container helper |
| `sail-data-source` | 15.8k | ORC reader and writer 11.5k with fixtures, listing changes 2.3k, options |
| `sail-execution` | 9.0k | extension-plan codec 2.5k, local job runner 1.6k, task runner and stop bounds, driver placement |
| `sail-plan` | 7.7k | resolver: query scope 2.5k, expressions 1.2k, constants 0.8k, identifiers 0.6k, commands 0.5k, TIME tests |
| `sail-common-datafusion` | 7.1k | structured errors, session lifecycle contract, scoped sessions, managed streams, `BoundedSource`, fenced commits, connect and driver extension traits |
| `sail-session` | 5.9k | session manager actor rewrite 2.5k, extension loader and graph utilities 2.7k |
| `sail-common` | 5.7k | ROOT-lowercase tables (CDC name folding), TIME spec, subquery spec tests |
| `sail-sdp-control` | 4.2k | new: pure control model for durable pipeline runs |
| `sail-function` | 2.9k | ANSI string-to-decimal and string casts, zero-divisor guards, math |
| `sail-iggy-bounded` | 2.9k | new: Apache Iggy as a `BoundedSource` |
| `sail-object-store` | 2.8k | owned multipart supervisor 1.1k, Foyer cache layer 1.5k, bench |
| `sail-sql-analyzer` | 2.7k | pipeline SQL entry point, validators, temporary-view qualifiers, parser diagnostics |
| `sail-delta-lake` | 1.4k | fenced commits, enrolled tables, source reads |
| `sail-iceberg` | 0.9k | discovery, snapshot search, delete index; benches 0.7k |
| `sail-sql-parser` | 0.9k | pipeline statements, diagnostics hook, gold data |
| `sail-catalog`, `-hms`, `-memory` | 0.7k | shared memory catalog, HMS purge and listing, cache clearing |
| `sail-cache` | 0.4k | cache invalidation keyed for REFRESH and TRUNCATE |
| `sail-native-resource-ffi` | 0.2k | new: the memory-lease C ABI |
| `vendor/` | 25.7k | `orc-rust` 0.9.0 with three fixes (77 files); `grust-topology`, `grust-columns` (10 files) |
| `examples/` | 34.5k | `extensions/` (Sedona, Nutmeg, Pecan, tests, harness); `declarative-pipelines/` demo |
| `docs/development/extensions` | 69k | design review, ABI review, plans, evidence checksums and bundles, benchmark audits (JSON) |
| `docs/books`, `FIRSTPAIR.md` | 15k | manual and report sources; not proposed |
| `scripts/` | 1.1k | `spark-pipelines-tests/` (Hive, second-catalog, CLI profiles) |

## 3. The tracks

Six tracks. Within a track the order is the dependency order; across tracks,
G (general) and P (performance) can open at once, S (SDP core) after G1–G6,
C (streaming and CDC) after S, X (extensions) after G5 and G6, D (docs) with
each track's last PR.

### Track G: general Sail improvements (no pipelines dependency)

| # | Title | Scope | Size | Needs | Evidence |
| --- | --- | --- | ---: | --- | --- |
| G1 | `fix: carry structured Spark errors through serde and RemoteError` | `sail-common-datafusion/src/error/` (`StructuredSparkError`, `CommonErrorCause`), the resolver's ambiguity and column errors, Connect rendering of `SQLSTATE: x` | ~600 | – | record §6; the column/ambiguity cases measured on Spark; rebase against upstream's `sail-plan` moves |
| G2 | `fix: ANSI and legacy string casts and zero-divisor arithmetic as typed UDFs` | `sail-function/src/scalar/{spark_string_to_decimal,spark_ansi_string_cast,math}`, codec field 41, `allowNegativeScaleOfDecimal` validation | ~2,000 | G1 | record §6 "Arithmetic", "Casts"; the error-row-order tests; upstream moved `sail-function` (+2.5k), rebase first |
| G3 | `feat: TIME type with precision metadata` | `sail-common/src/spec/time.rs`, resolver TIME casts and schema merge, `time_tests` | ~900 | – | record §10 (TIME-SEMANTICS.md) |
| G4 | `feat: SET CATALOG as an expression with request-local constant contexts` | `SetCurrentCatalogExpression`, `resolve_catalog_name`, `resolver/constant/`, `resolver/identifier/`, IDENTIFIER normalization | ~1,600 | G1 | record §3 "SET CATALOG", "Three catalog constant policies", "IDENTIFIER and parameters" |
| G5 | `fix: temporary-view qualifiers, REFRESH and TRUNCATE cache invalidation, Hive and Unity drop behavior` | `sail-sql-analyzer` temporary_view, `sail-cache`, `sail-catalog{,-hms}`, `file:/` paths, `external.table.purge`, listing fallback, Unity non-PURGE fallback | ~900 | – | record §3 "Temporary views", §5 "Caches", "Hive", "Unity"; each measured on Spark or the metastore |
| G6 | `feat: shared in-memory catalog across sessions (opt-in)` | `sail-catalog-memory`, `catalog.shared_memory` option, CLI test | ~200 | – | record §1 decision 1 |
| G7 | `refactor: session lifecycle states, cleanup record and tombstones` | `sail-session/src/session_manager/actor/` (Creating/Running/Deleting/DeletionFailed/Deleted/Failed), `cleanup.rs`, `shutdown.rs`, `lifecycle_tests.rs`, `[INVALID_HANDLE.SESSION_CLOSED]` | ~2,800 | – | record §7 "Session lifecycle"; SESSION-CLEANUP-LIFECYCLE-DESIGN.md; the largest G PR, kept whole because the states and the record are one change |
| G8 | `fix: operation-owned effects, multipart supervisor and task resource scopes` | `sail-object-store/src/owned_multipart/`, `TaskResourceScope`, managed streams, local stop ordering, settled failures at shutdown | ~2,200 | G7 | record §7 "Local stop", "Ownership", "Settled failures"; PROVIDER-RUNTIME-OWNERSHIP-DESIGN.md |
| G9 | `fix: bound driver and worker stop in cluster mode; canceled jobs end with an error` | `sail-execution` driver 30 s limit, worker 5 s graceful stop, canceled-job output, unconfirmed-cleanup failure | ~700 | G7, G8 | record §8; the cluster-mode pipeline tests |
| G10 | `feat: preparation lease and scoped query sessions` | PRE-PLANNING-OWNERSHIP-DESIGN.md: move-only runner-bound lease, `with_scoped_query_session`, late TaskContext capture | ~700 | G7 | record §7 "Preparation lease", "TaskContext capture" |
| G11 | `fix: structured parser diagnostics with UTF-16 positions` | `sail-sql-parser` TreeParser hook, `sail-sql-analyzer/src/error/parser`, gold data | ~600 | – | record §3 "Parser diagnostics"; SQL-SYNTAX-DIAGNOSTICS-DESIGN.md |
| G12 | `feat: ORC read and write` | `sail-data-source/src/formats/orc/` and fixtures, options, listing changes, ORC sink in `sail-common-datafusion` | ~12,000 as two PRs: reader (G12a), writer and sink (G12b) | **a released `orc-rust` with the three fixes** (see §4) | record §9; ORC-SOURCE-DESIGN.md, ORC-WRITER-DESIGN.md; the ORC suites and the timestamp difference stated |
| G13 | `fix: Delta fenced commits and enrolled tables` | `sail-delta-lake` fenced commit path, ALTER refusal on enrolled tables, relative locations, `action_digest` | ~1,200 | G8 | record §12; the Delta suite baseline (841 passed) unchanged |
| G14 | `feat: ROOT-locale lowercase tables (JDK 17)` | `sail-common/src/utils/root_lowercase*` with the oracle JSON; used by the pipelines graph, analysis and append paths and by `schema_validation.rs`, so it precedes S3 and C2 (CDC review, CF-0722) | ~1,400 | – | the oracle tests |

### Track P: performance (independent of SDP)

| # | Title | Scope | Size | Needs | Evidence |
| --- | --- | --- | ---: | --- | --- |
| P1 | `chore: criterion benches for Iceberg metadata, delete index, parsing and object-store reads` | `sail-iceberg/benches/`, `sail-sql-analyzer/benches/`, `sail-object-store/benches/` | ~1,000 | – | record §16; `docs/development/benches.md` baseline tables (both tips) |
| P2 | `perf: specialize single-statement SQL parsing` | `sail-sql-analyzer/src/parser` | ~150 | P1 | the parsing bench, before and after |
| P3 | `perf: streamed Iceberg metadata discovery with newest-first snapshot search` | `sail-iceberg/src/{spec,table,datasource}` | ~300 | P1 | the discovery and snapshot benches; manifest-reader reuse not re-applied, with the number |
| P4 | `perf: shared delete-index descriptors and delete routing` | `sail-iceberg/src/physical_plan`, delete index | ~200 | P1, P3 | the delete-index bench; Iceberg MOR tests |
| P5 | `feat: opt-in Foyer read-through cache layer for object stores` | `sail-object-store/src/layers/cache.rs`, `registry.rs` `maybe_wrap_from_env`, root deps `foyer-common`, `foyer-memory` | ~1,600 | P1 | the read bench; the performance guide page (D4) |

### Track S: the pipelines module, batch

| # | Title | Scope | Size | Needs | Evidence |
| --- | --- | --- | ---: | --- | --- |
| S1 | `feat: parse pipeline SQL into definitions without executing DDL` | `sail-sql-parser` pipeline statements, `sail-sql-analyzer/src/pipeline/` (entry point, validators: INSERT clause order, CTAS/RTAS, `USE SCHEMA`/`USE CATALOG`, REPLACE forms), source slices from lexer spans | ~1,800 | G4, G11 | record §3; SQL-SOURCE-DESIGN.md, REGISTRATION-ERROR-FIDELITY-DESIGN.md; every error measured on Spark |
| S2 | `feat: Spark Connect pipeline commands and graph registration` | `pipelines/` module skeleton: `CreateDataflowGraph`, `DefineDataset`, `DefineFlow`, `DefineSqlGraphElements`, `DropDataflowGraph`; graph IDs, atomic SQL files, the graph lock with async preparation; proto changes; the `pyspark.pipelines` protocol tests | ~3,000 | S1, G7, G10 | record §3 "Declarative registration", "Atomic files", "Preparation and the graph lock"; the registration suites |
| S3 | `feat: pipeline analysis and validation in Spark's order` | `analysis.rs`, `reanalysis`, `topology.rs` (with `grust-topology` and `grust-columns` as crates.io dependencies, see §4), schema merge, `UnresolvedPipeline`, flow failure events, lazy virtual schemas, configuration fusion | ~3,000 | S2, G14 | record §4; FLOW-CONFIGURATION-DESIGN.md, BATCH-PROVIDER-MIGRATION-DESIGN.md; ViewSuite and SqlPipelineSuite ports |
| S4 | `feat: materialize pipeline outputs through catalog providers` | `materialize/`, metadata-only materialization, the execute guard, refresh and reset semantics, partition columns last | ~1,200 | S3, G5, G6 | record §5; METADATA-TABLE-MATERIALIZATION-DESIGN.md; MaterializeTablesSuite port |
| S5 | `feat: run pipelines: scheduler, events and the local job runner` | `execution.rs`, `StartRun`, dry run, the typed event stream, `sail-execution/src/job_runner/local`, interrupt and release semantics; the run dispatch on an admitted AutoCDC graph becomes a function that returns "not admitted" behind a labelled `expect(dead_code)`, which C6a removes (CDC review, CF-0722) | ~2,800 | S4, G8, G9 | record §4 "Analyze before writing", §7 "Deliberate difference"; the end-to-end CLI tests, cluster-mode runs |
| S6 | `feat: query functions, dynamic references and SQL parameters in pipelines` | `query_function_guard`, DYNAMIC-REFERENCE-BINDING-DESIGN.md, `DefineFlow.once` rejection | ~700 | S5 | record §3 "Query functions", "IDENTIFIER and parameters" |
| S7 | `test: the frozen Spark pipeline suite ports and the pipelines harness` | `python/pysail/tests/spark/pipelines/` (the 300 selected and 67 upstream ports, the 1,284-test suite), `scripts/spark-pipelines-tests/`, `pysail/testing/spark/steps/pipelines.py`, the Hive 4.0.1 and second-catalog profiles | ~10,000, as 2–3 PRs by suite | S2–S6 (each earlier S PR carries its own tests; this PR carries the ports) | record §17; rebase onto upstream's reorganized `python/pysail` layout first |

### Track C: streaming and AutoCDC

| # | Title | Scope | Size | Needs | Evidence |
| --- | --- | --- | ---: | --- | --- |
| C1 | `feat: BoundedSource, a protocol-neutral bounded streaming source` | `sail-common-datafusion/src/streaming/bounded.rs`, cursors, incarnations, `retains_origin` | ~500 | – | record §13 "BoundedSource" |
| C2 | `feat: streaming tables as bounded AvailableNow microbatches` | `pipelines/streaming/` (binding, append path, event windows, watermarks, late-row rule), STREAM-read schema function | ~4,000 as two PRs: binding and refusals (C2a), windows and watermarks (C2b); carries no Iggy reference once the branch's `iggy` feature unit has landed; the streaming pytest files travel with C2a/C2b | S5, C1, G14 | record §13 "Execution model", "Unit 4 lowering", "Shared windowing code", "Late rows"; measured on Spark 4.2.1 with Delta 4.4.1 |
| C3 | `feat: Apache Iggy as a BoundedSource (optional feature)` | `crates/sail-iggy-bounded/` plus the gated wiring: an `iggy` feature on `sail-spark-connect`, `sail-session` and `sail-cli`, the dependency optional, the Iggy leaf in `append.rs` and `flow_source.rs` under the feature, the `iggy` format refused by name (naming the feature) without it; off by default (owner decision, 2026-11-03). The feature gate is first built as a branch unit, before any C PR is cut (CDC lane, CF-0723) | ~3,050 | C1, C2a | record §13 "Iggy"; the pinned-broker tests; the dependency is opt-in, since Spark has no Iggy source |
| C4 | `feat: sail-sdp-control, the pure control model for durable pipeline runs` | `crates/sail-sdp-control/` | ~4,200 | – | record §14 "Control store", "Store rules"; CDC-CONTROL-STORE-DESIGN.md; pure, no I/O, its own tests |
| C5 | `feat: AutoCDC definitions` | `pipelines/autocdc/` definition parsing (C1–C4 of the record), with its definition and oracle tests; the lowercase tables are G14 | ~3,600, above the norm because the parsing is one grammar and its oracle; the description says so | S3, G14 | record §14 "Definition parsing" |
| C6 | `feat: AutoCDC SCD1 runtime with stateful queries between batches` | `pipelines/autocdc/` runtime in three PRs, in the order the code can refuse in (CDC review, CF-0722). **C6a**, the plain runtime: targets and MERGE for Iceberg, Hive, Unity and catalog-managed Delta, `FlowSource`'s batch path (`batch_plan`, `leaf_streams`, `open_rows`), full refresh; an unmanaged Delta target is refused by name until C6c, and `check_stateless` refuses a stateful query by name until C6b; removes S5's "not admitted" seam; split Iceberg and Hive from Unity if it exceeds 4,000. **C6b**, state: `with_state`, the within and join watermarks, `stateful.rs`, `state.rs`, `carry.rs`, state segments and manifest, watermark recovery; lifts `check_stateless`. **C6c**, the fenced Delta path: the lease, the control-store adapter, `sail-common-datafusion/src/fenced_commit.rs` (`FencedCommitRegistry`, which only AutoCDC registers), recovery. Each carries the AutoCDC pytest files it exercises | ~12,000 | C6a: S4, S5, C2, C5; C6b: C6a; C6c: C6a, C4, G8, G13 | record §14 "Runtime", decisions 14 and 15; `crash.py` process-death qualification; `iceberg_on_spark` |
| C7 | `test: the shared streaming and AutoCDC harness` | what no single C PR owns: `pysail/testing/containers/unity.py`, the moto remote-warehouse tests, the Hive and second-catalog profiles for CDC; the suites themselves travel with C2, C5 and C6 so each PR states its own counts (CDC review, CF-0722). `test_extension_sources.py` (A9) goes with the last X PR, since it needs the extension server | ~1,500 | C6 | record §17 |

### Track X: native extensions

| # | Title | Scope | Size | Needs | Evidence |
| --- | --- | --- | ---: | --- | --- |
| X0 | Discussion post in [#2001](https://github.com/lakehq/sail/discussions/2001): the bounded host contract | `docs/development/extensions/maintainer-request.md` as the post, linking the design review and the record §15; owner decision (2026-11-03): the text is prepared from the request and the record's §0, and the owner posts it under their own account in week 1 alongside the first G PRs | – | – | opened before X1 so the contract is discussed before X2–X5 are written against `main` |
| X1 | `feat: sail-native-resource-ffi, the memory-lease C ABI` | `crates/sail-native-resource-ffi/` | ~200 | – | record §15; the lease probes in `abi-review.md` |
| X2 | `feat: session-owned native extension loader and admission pool` | `sail-session/src/extensions/`, `build.rs` host identity from `Cargo.lock`, `datafusion-ffi` in the root manifest, the two lifecycle host tests | ~2,800 | G7, G8, X1 | record §15 "Version identity", "Host-funded memory", "The session owns the admission pool" |
| X3 | `feat: dispatch Connect extension relations to registered native packages` | `sail-spark-connect` relation dispatch, `proto/plan.rs`, `sail-common-datafusion/src/connect_extension.rs`, error mapping | ~1,200 | X2, G1 | record §15 "A bounded host contract"; discussion #2002 |
| X4 | `feat: driver placement and codec for native extension plans` | `sail-execution/src/proto/codec/` extension plans, `driver_extension.rs`, job-graph placement, replay disabled for driver-local regions | ~3,200 | X3 | record §15; the distributed tests of the matrix |
| X5 | `feat: extension scalar functions resolved by identity on workers` | `sail-plan` resolver extension functions, `spark_array.rs` geometry field metadata | ~500 | X4 | record §15; the Sedona matrix rows |
| X6 | `docs: the extension design review and ABI review` | `docs/development/extensions/{design-review,abi-review,linux-environment,implementation-plan}.md`, the evidence checksums and bundles cited by them | ~3,000 of prose; bundles as binary | X5 | record §15; the audit JSON and benchmark corpus stay out |
| X7 | `sail-extensions-examples` repository | Sedona and Nutmeg wheels, Pecan, the matrix tests and harness scripts, as a separate repository under querygraph referenced from X6 (owner decision, 2026-11-03); not proposed in-tree, since the examples pin exact engine versions and carry their own workspaces and wheel builds |  ~30,000 | X6 | the matrix and ABI evidence cite the repository's tags |

### Track D: documentation

| # | Title | Scope | With |
| --- | --- | --- | --- |
| D1 | `docs: add the design record for declarative pipelines and native extensions` ([#2930](https://github.com/lakehq/sail/pull/2930), draft) | the record (this document's companion) placed as `docs/development/pipelines/index.md` (the development sidebar discovers directory index pages), with the links to the manual, report and book; owner decision (2026-11-03): the record lives in Sail as this docs PR, opened as a draft in week 1 so it is readable while the first code PRs are reviewed, and merged in the wake of the first S PR | week 1 as a draft; merged with the first S PR |
| D2 | `docs: declarative pipelines user guide` | condensed from the manual's chapters: projects, datasets, SQL files, catalogs, streaming, AutoCDC, differences from Spark | S7 |
| D3 | `docs: streaming sources and AutoCDC operator notes` | checkpoints, control store, one pipeline per plain target, recovery limits | C7 |
| D4 | `docs: performance guide and bench record` | `docs/guide/performance/index.md`, `docs/development/benches.md` | P5 |
| D5 | the Sail Rust Book | published from its `work/sdp-chapter` branch; referenced, not in-tree | D1 |

## 4. Prerequisites outside Sail

- **`orc-rust`.** The branch vendors `orc-rust` 0.9.0 with three local
  commits (Arrow 59 test alignment; frame checks, typed read failures and the
  five codec output bounds; the decoder panic fix). Owner decision
  (2026-11-03): the fixes are opened against `datafusion-contrib/orc-rust`
  first, and G12 waits for a release and depends on it from crates.io. No git
  dependency and no vendored copy are proposed; G12's timing follows that
  release.
- **Grust kernels.** `vendor/grust-topology` and `vendor/grust-columns` are
  dependency-free extractions with `SOURCE.json` provenance. Owner decision
  (2026-11-03): they are published to crates.io from querygraph/grust as
  `grust-topology` and `grust-columns` before S3 opens, and S3 depends on
  them as ordinary crates; `vendor/` does not enter Sail.
- **PySpark 4.2.1.** The pipelines client was measured at 4.2.1; S7 moves
  upstream's `pyspark[connect]==4.2.0` pin.
- **Grust 0.24.1 on crates.io** (done) for the Nutmeg example in X7.

## 5. Sequencing and cadence

Owner decision (2026-11-03): the general track leads. Track G and the benches
are offered first, so that value lands even if the pipelines review is slow
and the pipelines PRs arrive on a `main` that already has their prerequisites.

1. **Week 1:** X0 (discussion post) and D1 as a draft PR carrying the record,
   so the maintainers can read the design while the first code PRs are
   reviewed. G1, G3, G5, G6, G11, P1 opened: small, independent, each a day
   of review.
2. **Week 2:** G2, G4, G7, P2–P4. G7 is the one large general PR and sets the
   session layer everything later builds on; ask for a dedicated reviewer.
3. **Weeks 3–4:** G8–G10, G13, P5, C1, C4, X1; then S1–S2.
4. **Weeks 5–8:** S3–S7 in order, C2 alongside S5, C5 alongside S6–S7 (C6's three PRs all need it), X2–X5 alongside S6–S7. G14 opens with C1 and C4 in weeks 3–4, before S3.
5. **Weeks 9–12:** C3 (after the branch's `iggy` feature unit), C6a–c, C7, X6–X7 (as decided), D2–D4.

Owner decision (2026-11-03): both lanes prepare the series, starting once A9
has been fast-forwarded and the branch is final. The batch lane takes tracks
G, P, S, X and D; the CDC lane takes track C (streaming, Iggy, the control
store, AutoCDC) after reviewing its split. Each PR is gated on the branch's
scripts before it opens.

Each PR is prepared on a detached branch from upstream `main` by replaying
the branch's commits for its scope (the branch's commits are already
granular within each unit), gated with the same scripts used for landing
(record §17), and opened with its description drawn from this plan and the
record. The branch stays the integration tree; a PR's review changes flow back
to it as ordinary gated commits, so the branch and the series never diverge.

## 6. Risks

- **Review bandwidth.** Forty-odd PRs over three months is a lot for a small
  maintainer team; the general track is front-loaded so that value lands
  even if the pipelines track slows; the owner chose this order (§5).
- **Upstream movement.** `sail-plan` and `sail-function` moved since the base;
  G1, G2 and G4 are rebased before anything else. `python/pysail` was
  reorganized; S7 and C7 take the new layout.
- **The extensions decision.** Upstream wants an FFI-based contract (record
  §0); the branch has one, but its placement (loader in `sail-session`,
  dispatch in `sail-spark-connect`) may be reshaped in review. X0 exists so
  that reshaping happens before X2–X5 are written against `main`.
- **ORC release timing.** G12 is the largest general PR and waits on an
  external release; nothing in S depends on it except the ORC suites, which
  are skipped until it lands.
