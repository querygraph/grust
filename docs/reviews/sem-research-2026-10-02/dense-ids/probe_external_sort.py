"""Does a sort larger than the memory pool complete (spill) or fail?

    python probe_external_sort.py [rows]

For each memory-pool setting: a fresh local-mode server, the same synthetic BIGINT column (xxhash64 of
0..rows-1, about 8 bytes a row), then ORDER BY id written to Parquet, and row_number() over the same order.
Records success or the error, wall seconds, and the server's peak resident set during the statement.
"""
import json, os, pathlib, shutil, sys, tempfile, time

from sailserver import sail

ROWS = int(sys.argv[1]) if len(sys.argv) > 1 else 50_000_000
POOLS = ["unbounded", "greedy:2048", "greedy:1024", "greedy:512", "fair:2048", "fair:1024", "fair:512", "fair:256"]
scratch = pathlib.Path(tempfile.mkdtemp(prefix="dense-ids-sort-", dir=os.environ.get("PROBE_TMP")))

for pool in POOLS:
    settings = {}
    if pool != "unbounded":
        kind, _, mib = pool.partition(":")
        settings = {"SAIL_RUNTIME__MEMORY_POOL__TYPE": kind,
                    f"SAIL_RUNTIME__MEMORY_POOL__{kind.upper()}__MAX_SIZE": str(int(mib) * 2**20)}
    with sail("local", settings) as (spark, server):
        from pyspark.sql import Window, functions as F
        source = scratch / "ids"
        shutil.rmtree(source, ignore_errors=True)
        spark.range(ROWS).select(F.xxhash64("id").alias("id")).write.parquet(source.as_uri())
        frame = spark.read.parquet(source.as_uri())
        statements = {
            "orderBy(id)": lambda: frame.orderBy("id"),
            "row_number() over (order by id)": lambda: frame.select(
                "id", (F.row_number().over(Window.orderBy("id")) - 1).cast("long").alias("dense")),
        }
        for name, make in statements.items():
            out = scratch / "out"
            shutil.rmtree(out, ignore_errors=True)
            server.reset_peak()
            cpu, started = server.cpu_seconds(), time.perf_counter()
            try:
                make().write.parquet(out.as_uri())
                rows = spark.read.parquet(out.as_uri()).count()
                record = dict(ok=rows == ROWS, rows_written=rows)
            except Exception as e:
                record = dict(ok=False, error=type(e).__name__, message=str(e).strip().splitlines()[0][:300])
            print(json.dumps(dict(pool=pool, settings=server.settings, rows=ROWS, statement=name,
                                  wall_seconds=round(time.perf_counter() - started, 3),
                                  server_cpu_seconds=round(server.cpu_seconds() - cpu, 2),
                                  server_peak_rss_mib=server.peak_rss_mib(), **record)), flush=True)

shutil.rmtree(scratch, ignore_errors=True)
