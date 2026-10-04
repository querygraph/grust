"""The same vertex-indexing options on a synthetic id column, to see the shape beyond 3.77M rows.

    python bench_scale.py [rows] [runs] [pool]

rows: default 50,000,000 distinct pseudo-random BIGINT ids (xxhash64 of 0..rows-1), unsorted, written by
Sail to Parquet first. pool: "unbounded" (default), "greedy:<MiB>" or "fair:<MiB>": a bounded memory pool,
under which the sorts have to spill. Local mode. One JSON record per run. Checks are done outside the engine with NumPy.
"""
import hashlib, json, os, pathlib, shutil, sys, tempfile, time

import numpy as np
import pyarrow.parquet as pq

from sailserver import bucket_of, host_facts, sail

ROWS = int(sys.argv[1]) if len(sys.argv) > 1 else 50_000_000
RUNS = int(sys.argv[2]) if len(sys.argv) > 2 else 3
POOL = sys.argv[3] if len(sys.argv) > 3 else "unbounded"
BUCKETS = 256
MASK33 = (1 << 33) - 1
scratch = pathlib.Path(tempfile.mkdtemp(prefix="dense-ids-scale-", dir=os.environ.get("PROBE_TMP")))
settings = {}
if POOL != "unbounded":
    kind, _, mib = POOL.partition(":")  # greedy:512 or fair:512
    settings = {"SAIL_RUNTIME__MEMORY_POOL__TYPE": kind,
                f"SAIL_RUNTIME__MEMORY_POOL__{kind.upper()}__MAX_SIZE": str(int(mib) * 2**20)}


def emit(**record):
    print(json.dumps(record, default=str), flush=True)


def read_columns(directory, columns):
    files = sorted(pathlib.Path(directory).glob("*.parquet"))
    tables = [pq.read_table(f, columns=columns) for f in files]
    return [np.concatenate([t.column(c).to_numpy() for t in tables]) for c in columns], len(files)


with sail("local", settings) as (spark, server):
    from pyspark.sql import Window, functions as F
    mid, pid = F.monotonically_increasing_id(), F.spark_partition_id()
    source = scratch / "ids"
    spark.range(ROWS).select(F.xxhash64("id").alias("id")).write.parquet(source.as_uri())
    (truth,), source_files = read_columns(source, ["id"])
    truth = np.sort(truth)
    assert len(np.unique(truth)) == ROWS, "the synthetic ids are not distinct"
    emit(record="host", rows=ROWS, runs=RUNS, pool=POOL, settings=server.settings, source_files=source_files,
         source_bytes=sum(f.stat().st_size for f in source.glob("*.parquet")), buckets=BUCKETS,
         note="shared laptop; another agent may run a small Sail server at the same time", **host_facts())

    def ids():
        return spark.read.parquet(source.as_uri())

    def offsets_of(counts):
        out, total = [0] * (max(counts) + 1), 0
        for p in range(len(out)):
            out[p] = total
            total += counts.get(p, 0)
        return out

    def lookup(values, index):
        return F.get(F.array(*[F.lit(int(x)).cast("long") for x in values]), index)

    def a_row_number(out):
        ids().select("id", (F.row_number().over(Window.orderBy("id")) - 1).cast("long").alias("dense")
                     ).write.parquet(out.as_uri())
        return {}

    def a_sort_only(out):
        """The sort alone, without the window: what the index adds on top of ORDER BY."""
        ids().orderBy("id").write.parquet(out.as_uri())
        return {}

    def b_one_pass_materialized(out):
        staged = scratch / "staged"
        shutil.rmtree(staged, ignore_errors=True)
        ids().select("id", mid.alias("m")).write.parquet(staged.as_uri())
        table = spark.read.parquet(staged.as_uri())
        part = F.shiftright("m", 33)
        counts = {r[0]: r[1] for r in table.groupBy(part.alias("p")).count().collect()}
        table.select("id", (lookup(offsets_of(counts), part) + F.col("m").bitwiseAND(MASK33)).alias("dense")
                     ).write.parquet(out.as_uri())
        return dict(partitions=len(counts))

    def b_two_pass_no_work_stealing(out):
        spark.sql("SET datafusion.execution.enable_file_stream_work_stealing = false").collect()
        try:
            frame = ids()
            counts = {r[0]: r[1] for r in frame.select(pid.alias("p")).groupBy("p").count().collect()}
            frame.select("id", pid.alias("p"), mid.alias("m")).select(
                "id", (lookup(offsets_of(counts), F.col("p")) + F.col("m").bitwiseAND(MASK33)).alias("dense")
            ).write.parquet(out.as_uri())
            return dict(partitions=len(counts))
        finally:
            spark.sql("SET datafusion.execution.enable_file_stream_work_stealing = true").collect()

    def e_bucketed_row_number(out):
        frame = ids()
        sample = sorted(r[0] for r in frame.sample(False, min(1.0, 100_000 / ROWS), 7).collect())
        bounds = sorted({sample[len(sample) * k // BUCKETS] for k in range(1, BUCKETS)})
        with_bucket = frame.select("id", bucket_of(F.col("id"), bounds, F).alias("b"))
        counts = {r[0]: r[1] for r in with_bucket.groupBy("b").count().collect()}
        with_bucket.select("id", (lookup(offsets_of(counts), F.col("b")) + F.row_number().over(
            Window.partitionBy("b").orderBy("id")) - 1).cast("long").alias("dense")).write.parquet(out.as_uri())
        return dict(buckets=len(counts), largest_bucket=max(counts.values()), sample=len(sample))

    def check(out, case):
        if case is a_sort_only:
            (got,), files = read_columns(out, ["id"])
            return dict(rows=len(got), files=files, ids_match_input=bool((np.sort(got) == truth).all()))
        (got, dense), files = read_columns(out, ["id", "dense"])
        order = np.argsort(dense, kind="stable")
        by_dense = got[order]
        return dict(rows=len(dense), files=files,
                    dense_is_0_to_n_minus_1=len(dense) == ROWS and bool(
                        (dense[order] == np.arange(ROWS, dtype=np.int64)).all()),
                    ids_match_input=len(got) == ROWS and bool((np.sort(got) == truth).all()),
                    dense_follows_id_order=bool((np.diff(by_dense) > 0).all()),
                    fingerprint=hashlib.blake2b(np.ascontiguousarray(by_dense).tobytes(), digest_size=8).hexdigest())

    ids().count()
    for repeat in range(RUNS):
        for case in (a_sort_only, a_row_number, b_one_pass_materialized, b_two_pass_no_work_stealing,
                     e_bucketed_row_number):
            out = scratch / "out"
            shutil.rmtree(out, ignore_errors=True)
            server.reset_peak()
            cpu, started = server.cpu_seconds(), time.perf_counter()
            try:
                extra = case(out)
                wall, used = time.perf_counter() - started, server.cpu_seconds() - cpu
                record = dict(record="run", case=case.__name__, rows=ROWS, pool=POOL, repeat=repeat, ok=True,
                              wall_seconds=round(wall, 3), server_cpu_seconds=round(used, 2),
                              server_peak_rss_mib=server.peak_rss_mib(), **extra)
                record.update(check(out, case))
            except Exception as e:
                record = dict(record="run", case=case.__name__, rows=ROWS, pool=POOL, repeat=repeat, ok=False,
                              wall_seconds=round(time.perf_counter() - started, 3), error=type(e).__name__,
                              message=str(e).strip().splitlines()[0][:500])
            emit(**record)

shutil.rmtree(scratch, ignore_errors=True)
