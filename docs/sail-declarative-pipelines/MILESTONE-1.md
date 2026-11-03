# Sail Declarative Pipelines: milestone 1

This milestone is Sail's implementation of Spark 4.2.1 Spark Declarative Pipelines: the complete batch implementation, plus AutoCDC and streaming. The unchanged `pyspark.pipelines` client and the `spark-pipelines` CLI run against Sail over Spark Connect.

- **Branch:** `work/spark-declarative-pipelines`, tag `sdp-m1`, pushed to `querygraph/sail` on 2026-11-03. The earlier tag `sdp-batch-m1` (`7d6bc1917`) marks the first close; the milestone was reopened to fix every defect the review found and to finish the units that complete it, and closed again here.
- **Root:** `208811eec`. On top of `7d6bc1917` it adds, in order, all gated: `6f45d5d73` (late rows follow Spark's `window.end <= watermark`), `a26a3a9b4` (seven review defects: checkpoint reset version, empty-batch state, stalled-range refusal, bounded calls, root-catalog lowercasing, memory-catalog removal, writer abort reaching every channel, worker-stop task streams), `94d10fd06` (D9: a persisted view needs named columns wherever they come from), `6f862b188` (C3: the driver abandons job output forwarders on stop; the worker joins its task runner before its server), `ae7ca0b5e` (the CDC lane's `838d7b686`), `f575ca5da` (ORC write-default tests pinned to the session's Spark version; shared-catalog visibility test; report corrections), `97be991c5` (a stopped producer's local streams end for their subscribers: the worker-stop cause, measured 0/600), `20f0792f1` (the CDC lane's close at `44fbf378b`: D6, D5, C2 lease renewal, C16, the watermark model in `pipelines/watermark.rs`, C1 authority property and per-server fenced commit registry, enrollment identity checks, `ALTER TABLE` on lakehouse path tables, manual chapters 30-32), `bc96ca901` (the manual's sources and the report's 1.0.1 configuration) and `208811eec` (the built editions).
- **Gate on `208811eec`** (one run for the merge and the docs): native GATE=0 on 15 crates; frozen 300 + 67 PASS; pipelines and ORC 1282 passed, 25 skipped, 4 strict expected failures; CLI with shared memory and catalog visibility clean; Hive 69 passed, 2 xfailed; second catalog 13 passed; Delta failures identical by name to the parity set. The CDC lane's gate 20 on `44fbf378b`, from an empty target: whole Spark Python tree clean; pipelines 1208 passed, 21 skipped, 4 xfailed; local-cluster 100; Iceberg; Hive 93; Unity 230; both oracle files exit 0; Iceberg-on-Spark exactly the 3 known refusals; crash seeds exact.
- **Base:** upstream Sail `0ba425c03`. The branch adds 401 commits, with 911 files changed.
- **Lanes:** the batch lane wrote batch, SQL, catalog, runtime, ORC, the review fixes in its area and the worker-stop fix. The CDC lane wrote AutoCDC, with the streaming, Iggy, lease and fence work it needs, and its review fixes. Both lanes are on this root.

Every settled decision is recorded in [SAIL-SDP-DESIGN-DECISIONS.md](SAIL-SDP-DESIGN-DECISIONS.md), and the evidence is in `evidence/batch-gaps/README.md`.

## What it does

**Batch**
- Pipelines can be defined in Python or SQL, then registered, analyzed, dry-run and run.
- Datasets: materialized views, tables, and temporary and persisted views.
- SQL files are registered all-or-nothing, with Spark's `USE SCHEMA` and `USE CATALOG` directives.
- Flow configuration follows Spark: per-flow settings are fused with the settings of the views a flow reads.
- Errors and event streams match Spark.

**Catalogs**
- The memory catalog, a Hive 4.0.1 metastore, a second catalog, Unity Catalog and Iceberg are covered.
- Sessions can share one in-memory catalog through `catalog.shared_memory`. It is off by default.

**Formats**
- Parquet, CSV, JSON, Delta (including as a source) and ORC (read and write).

**Streaming and CDC**
- Bounded microbatches, run as Spark's AvailableNow trigger.
- An Iggy source, through `BoundedSource`.
- AutoCDC SCD1 into Delta, Iceberg, Hive and Unity targets, with real state between batches: watermarked aggregates, sliding windows, deduplication and inner stream joins.

**Lifecycle**
- Session release and server shutdown never delete what they can't confirm is finished.
- Cluster mode is covered, including canceled jobs and limits on how long stopping a worker can take.

## Evidence on this root

**Gate** (`208811eec`, the closing root; the same steps passed on every root listed above):
- native tests on 15 crates;
- frozen ports: 300 selected public tests and 67 upstream tests, PASS;
- pipelines and ORC: 1282 passed, 25 skipped, 4 strict expected failures;
- CLI: passed, with shared memory on, including two sessions seeing one catalog;
- Hive metastore: 69 passed, 2 xfailed;
- second catalog: 13 passed;
- Delta suite: the same failures by name as the baseline;
- no session cleanup failures at shutdown.

**The CDC lane's gate 20 on `44fbf378b`** (empty target directory):
- whole Spark Python tree clean; pipelines 1208 passed, 21 skipped, 4 xfailed;
- local-cluster: 100 passed;
- Iceberg; Hive: 93 passed; Unity: 230 passed;
- Spark oracles (Delta, AutoCDC with the test catalog): exit 0; Iceberg-on-Spark exactly the 3 known refusals;
- crash seeds: every recovery exact.

**Spark 4.2.1 as the reference.** Batch test files are identical on `df2457e50` and on this root.
- **Batch:** all 61 non-AutoCDC pipelines files were run on Spark 4.2.1, each failure then rerun alone. Only the 4 documented batch differences fail on Spark.
- **Named columns for persisted views:** the 12 lowered shapes in `test_sql_views_metadata.py` were measured on Spark 4.2.1 (12/12) before D9 landed.
- **Late rows:** `test_a_row_behind_the_watermark_counts_while_its_window_is_open` measured on Spark 4.2.1 with Delta 4.4.1.
- **AutoCDC on this root:** `test_autocdc_semantics.py` 42 passed; `test_autocdc_spark_suites.py` 43 passed and 4 skipped (Sail-only cases). `ALTER TABLE delta.`<path>``: the same test file passes on Spark 4.2.1 + Delta 4.4.1.

**Worker stop.** The session-close hammer (`merge/hammer-close.sh`, two tests in cluster mode per round): 0 firings of the 5 s stop bound in 600 rounds on `97be991c5`, against 4 in 500 on the root before it. The diagnosis is in DESIGN.md "Review at milestone 1", item 3.

## Demo and report

- **Demo:** `examples/declarative-pipelines/` in the branch, run with `run.sh` after a build. It runs real projects through the unchanged `spark-pipelines` CLI and checks every result. On `21c1cb498`, with an Iggy broker: 48 passed, 0 failed, 0 skipped. Without a broker, the Iggy checks are reported as SKIP.
- **Bug the demo found:** AutoCDC failed with Sail's default relative warehouse (`spark-warehouse`), because the commit path could not turn a relative location into a URL. It now uses `sail_data_source::resolve_table_url`, as Delta's table source does (`21c1cb498`, declared to the CDC lane in CF-0618). The demo failing before the fix and passing after it is the control.
- **Manual:** *Sail Declarative Pipelines*, the user's book, seventeen chapters from both lanes (introduction, getting started, projects and specs, Python datasets, SQL files, running, sources and formats, catalogs, streaming tables, AutoCDC, Iggy, AutoCDC catalogs, operations, differences from Spark, the demo, and the configuration and error appendices). Source `docs/books/sail-declarative-pipelines-manual/`, built by the root `book.build.json`; editions (PDF, EPUB, HTML, chapters, version `1.0.0-bc96ca90`) in its `dist/`.
- **Report:** the technical report, published as the same title's `report` version: source `docs/books/sail-declarative-pipelines/`, editions `1.0.1-bc96ca90` in its `dist/`, built on this tree with the f575ca5da corrections. The root `FIRSTPAIR.md` names both deliverables. Neither is published to firstpair.org; that needs the user's go-ahead.

## Scope the user set

- Spark's internal Scala suites are excluded. The 300 + 67 ports stand in for them.
- Docker- and S3-backed Hive tests are waived. The Derby Hive profile runs instead, and remote warehouses are tested against moto.
- The 4 strict expected failures and the 37 partial audit entries that can't be seen over the wire are accepted.

## Differences from Spark

**Strict expected failures:**
- Interrupting a run, or releasing its session during the run, stops the flows. Spark lets them finish.
- Added columns follow the target table's order.
- `writeStream` to `memory` outside a pipeline is not supported.

**Other deliberate differences:**
- A SQL file is registered all-or-nothing.
- A flow is rejected before its INSERT runs.
- Sail accepts dotted and hyphenated table names.
- ORC timestamps outside ORC-763's window before the epoch fail rather than read back wrong.
- Sail completes 3 Iceberg nested-type cases that Spark with Iceberg refuses.

## After the milestone

The plan for the next goal is [SDP-WITH-EXTENSIONS-AND-PERFORMANCE.md](SDP-WITH-EXTENSIONS-AND-PERFORMANCE.md): the extensions port (Phase A) and the measured performance work (Phase B) as two lanes on this root after A1, with the Rust book (Phase C) following.

## Open, not in this milestone

- **Worker stop, second half:** why tokio's abort leaves task futures alive for seconds, and releasing the reader-side Flight subscription through the task resource scope (DESIGN.md item 3, shape (a)); and item 11, reporting the stop bounds as cleanup errors.
- **CDC durability:** production durability, fencing and recovery for CDC beyond the qualified process-death cases.
- **Session work:** fallible actor results and cluster worker effects.
- **M2 SDP items** in DESIGN.md's review: the single AutoCDC run path, concurrent flows, state compaction, structured errors.

