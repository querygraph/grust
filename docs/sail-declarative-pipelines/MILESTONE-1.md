# Sail Declarative Pipelines: milestone 1

This milestone is Sail's implementation of Spark 4.2.1 Spark Declarative Pipelines: the complete batch implementation, plus AutoCDC and streaming. The unchanged `pyspark.pipelines` client and the `spark-pipelines` CLI run against Sail over Spark Connect.

- **Branch:** `work/spark-declarative-pipelines`, tag `sdp-batch-m1`, pushed to `querygraph/sail`.
- **Root:** `7d6bc1917`, tagged `sdp-batch-m1` and pushed with the branch to `querygraph/sail` on 2026-11-02. On top of the gated `fb3a6ab03` it adds: `21c1cb498` (the demo, the report source, and a fix to AutoCDC target locations; gated), `53790f575` (the built report editions only), and `7d6bc1917`, the CDC lane's `6c6c9d447` (a watermark after a transformation keeps only open rows; gated). The report was built at `21c1cb49`, before that last merge, so its results tables do not include it.
- **Gate on `7d6bc1917`:** native GATE=0; frozen 300 + 67 PASS; pipelines 1263 passed, 23 skipped, 4 strict expected failures; Hive 69 passed; second catalog 13 passed; Delta unchanged. Demo: 48 passed, 0 failed, 0 skipped, with Iggy.
- **Base:** upstream Sail `0ba425c03`. The branch adds 371 commits, with 801 files changed.
- **Lanes:** the batch lane wrote batch, SQL, catalog, runtime and ORC. The CDC lane wrote AutoCDC, with the streaming and Iggy work it needs. Both lanes are on this root.

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

**Gate** (`fb3a6ab03`):
- native tests on 15 crates;
- frozen ports: 300 selected public tests and 67 upstream tests, PASS;
- pipelines and ORC: 1262 passed, 23 skipped, 4 strict expected failures;
- CLI: passed, with shared memory on;
- Hive metastore: 69 passed, 2 xfailed;
- second catalog: 13 passed;
- Delta suite: the same failures by name as the baseline;
- no session cleanup failures at shutdown.

**The CDC lane's gate on the same tree** (`44b2f5f73`):
- whole Spark Python tree: 12133 passed, 0 errors;
- local-cluster: 95 passed;
- Iceberg: 86 passed;
- Hive: 88 passed;
- Unity: 230 passed;
- crash seeds: every recovery exact.

**Spark 4.2.1 as the reference.** Batch test files are identical on `df2457e50` and on this root.
- **Batch:** all 61 non-AutoCDC pipelines files were run on Spark 4.2.1, each failure then rerun alone. Only the 4 documented batch differences fail on Spark.
- **AutoCDC on this root:** `test_autocdc_semantics.py` 41 passed; `test_autocdc_spark_suites.py` 43 passed and 4 skipped (Sail-only cases).

## Demo and report

- **Demo:** `examples/declarative-pipelines/` in the branch, run with `run.sh` after a build. It runs real projects through the unchanged `spark-pipelines` CLI and checks every result. On `21c1cb498`, with an Iggy broker: 48 passed, 0 failed, 0 skipped. Without a broker, the Iggy checks are reported as SKIP.
- **Bug the demo found:** AutoCDC failed with Sail's default relative warehouse (`spark-warehouse`), because the commit path could not turn a relative location into a URL. It now uses `sail_data_source::resolve_table_url`, as Delta's table source does (`21c1cb498`, declared to the CDC lane in CF-0618). The demo failing before the fix and passing after it is the control.
- **Report:** *Sail Declarative Pipelines*, built with the First Pair Press toolchain. The source is `docs/books/sail-declarative-pipelines/`; the builds (PDF, EPUB, HTML, version `1.0.0-21c1cb49`) are in its `dist/`. It is not published to firstpair.org.
- **Gate on `21c1cb498`:**
  - native: GATE=0;
  - frozen 300 + 67: PASS;
  - pipelines and ORC: 1262 passed, 23 skipped, 4 xfailed;
  - Hive: 69 passed, 2 xfailed;
  - second catalog: 13 passed;
  - Delta failures identical by name;
  - no cleanup failures at shutdown.

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

- `6f45d5d73` (gated, on top of `sdp-batch-m1`): late rows in the append path now follow Spark. The AutoCDC Spark oracle was rerun on `7d6bc1917`: semantics 42 passed; spark_suites 43 passed and 4 Sail-only skipped. Delta AutoCDC targets are policy (user decision 21).

- `97be991c5` (gated): a stopped producer's local streams end for their subscribers. This was the worker-stop cause: a stage-0 shuffle response subscribed by a peer worker at the instant of the stop, held by a sink mid-commit in a task future the abort had not reached. Measured 0 firings in 600 rounds of the session-close hammer against 4 in 500 without it. The diagnosis is DESIGN.md "Review at milestone 1", item 3.

## Open, not in this milestone

- **Worker stop, second half:** why tokio's abort leaves task futures alive for seconds, and releasing the reader-side Flight subscription through the task resource scope.
- **CDC durability:** production durability, fencing and recovery for CDC beyond the qualified process-death cases.
- **Session work:** fallible actor results and cluster worker effects.
