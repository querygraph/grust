**Kind:** performance. The time is in DataFusion's Hive-style demultiplexer, which Sail calls unchanged.

## Summary

`DataFrameWriter.partitionBy(col).parquet(path)` costs about 60 ns a row on a 10-core laptop, against 12 ns a row for the same frame written without `partitionBy`. It keeps two cores busy where the plain write keeps six. With many partition values in each batch it is far worse: 512 ns a row for 1,000 values, 45 times the plain write.

One task handles every batch of the write, and for every row it formats the partition value as a string and allocates a `Vec<String>` key for a hash map.

## Environment

- Sail `main` at `99ee46f69a97342e91bf7d4eaedb4509f1d8a9c2` (2026-10-02, version 0.7.2), unmodified, built with `cargo build --release --locked -p sail-cli`.
- DataFusion 55.1.0, as pinned by that commit.
- Client: PySpark 4.0.1 (Spark Connect), Python 3.12.8, pyarrow 25.0.1.
- macOS 26.2 on an Apple M1 Max. Local mode, default settings.

## Reproduce

```sh
python repro.py /path/to/release/sail 16000000 10
```

The script below starts a server, writes one frame four ways three times each, and prints wall seconds and the server's CPU seconds for every write as JSON lines. The frame has three columns: a BIGINT, a DOUBLE and an INT bucket in `[0, buckets)`. The first two are incompressible by construction.

<details>
<summary>repro.py</summary>

```python
"""Sail: the cost of DataFrameWriter.partitionBy against a plain Parquet write of the same rows.

Starts a Sail server in local mode (no extensions), writes one frame four ways, and reports wall
seconds and the server process's CPU seconds for each write.

    python repro.py /path/to/release/sail [rows] [buckets]
"""
import json, os, pathlib, shutil, socket, subprocess, sys, sysconfig, tempfile, time

sail = pathlib.Path(sys.argv[1]).resolve()
rows = int(sys.argv[2]) if len(sys.argv) > 2 else 16_000_000
buckets = int(sys.argv[3]) if len(sys.argv) > 3 else 10
root = pathlib.Path(tempfile.mkdtemp(prefix="sail-partitionby-", dir=os.environ.get("PROBE_TMP")))
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
env = dict(os.environ, PYTHONHOME=sys.base_prefix, PYTHONPATH=sysconfig.get_paths()["purelib"],
           DYLD_LIBRARY_PATH=sysconfig.get_config_var("LIBDIR") or "",
           LD_LIBRARY_PATH=sysconfig.get_config_var("LIBDIR") or "", SAIL_MODE="local", RUST_LOG="warn")
env.pop("SAIL_EXPERIMENTAL_EXTENSIONS", None)
server = subprocess.Popen([str(sail), "spark", "server", "--ip", "127.0.0.1", "--port", str(port)],
                          env=env, cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

def cpu_seconds():
    text = subprocess.run(["ps", "-o", "cputime=", "-p", str(server.pid)], capture_output=True, text=True).stdout.strip()
    days, _, clock = text.rpartition("-")
    parts = [float(p) for p in clock.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    return (int(days) if days else 0) * 86400 + parts[0] * 3600 + parts[1] * 60 + parts[2]

try:
    while True:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
        assert server.poll() is None, "server exited"
        time.sleep(0.05)
    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F
    spark = SparkSession.builder.remote(f"sc://127.0.0.1:{port}").getOrCreate()
    source = root / "source"
    # Two incompressible columns and a bucket in [0, buckets).
    spark.range(rows).select(
        F.xxhash64("id").alias("id"), F.xxhash64("id", F.lit(1)).cast("double").alias("value"),
        F.pmod(F.xxhash64("id"), F.lit(buckets)).cast("int").alias("bucket")).write.parquet(source.as_uri())
    frame = spark.read.parquet(source.as_uri())
    assert frame.count() == rows
    modes = {
        "plain": lambda: frame.write,
        "repartition(n, bucket)": lambda: frame.repartition(buckets, "bucket").write,
        "partitionBy(bucket)": lambda: frame.write.partitionBy("bucket"),
        "repartition(n, bucket) + partitionBy(bucket)": lambda: frame.repartition(buckets, "bucket").write.partitionBy("bucket"),
    }
    results = []
    for repeat in range(3):
        for mode, writer in modes.items():
            target = root / "out"
            shutil.rmtree(target, ignore_errors=True)
            cpu, started = cpu_seconds(), time.perf_counter()
            writer().parquet(target.as_uri())
            wall, used = time.perf_counter() - started, cpu_seconds() - cpu
            files = list(target.rglob("*.parquet"))
            written = spark.read.parquet(target.as_uri()).count()
            assert written == rows, (mode, written)
            record = dict(rows=rows, buckets=buckets, mode=mode, repeat=repeat, wall_seconds=round(wall, 3),
                          server_cpu_seconds=round(used, 2), cores_busy=round(used / wall, 1), files=len(files),
                          directories=len({f.parent for f in files}), bytes=sum(f.stat().st_size for f in files))
            results.append(record)
            print(json.dumps(record), flush=True)
    spark.stop()
finally:
    server.terminate(); server.wait(timeout=60)
    shutil.rmtree(root, ignore_errors=True)
```

</details>

<details>
<summary>Output of the runs reported here</summary>

`output-16m-rows-10-buckets.jsonl`:

```json
{"rows": 16000000, "buckets": 10, "mode": "plain", "repeat": 0, "wall_seconds": 0.206, "server_cpu_seconds": 1.1, "cores_busy": 5.3, "files": 4, "directories": 1, "bytes": 265135458}
{"rows": 16000000, "buckets": 10, "mode": "repartition(n, bucket)", "repeat": 0, "wall_seconds": 0.208, "server_cpu_seconds": 1.21, "cores_busy": 5.8, "files": 4, "directories": 1, "bytes": 261316882}
{"rows": 16000000, "buckets": 10, "mode": "partitionBy(bucket)", "repeat": 0, "wall_seconds": 1.031, "server_cpu_seconds": 2.21, "cores_busy": 2.1, "files": 10, "directories": 10, "bytes": 260464981}
{"rows": 16000000, "buckets": 10, "mode": "repartition(n, bucket) + partitionBy(bucket)", "repeat": 0, "wall_seconds": 0.929, "server_cpu_seconds": 2.04, "cores_busy": 2.2, "files": 10, "directories": 10, "bytes": 260469320}
{"rows": 16000000, "buckets": 10, "mode": "plain", "repeat": 1, "wall_seconds": 0.193, "server_cpu_seconds": 1.04, "cores_busy": 5.4, "files": 4, "directories": 1, "bytes": 265134298}
{"rows": 16000000, "buckets": 10, "mode": "repartition(n, bucket)", "repeat": 1, "wall_seconds": 0.198, "server_cpu_seconds": 1.26, "cores_busy": 6.4, "files": 4, "directories": 1, "bytes": 261301162}
{"rows": 16000000, "buckets": 10, "mode": "partitionBy(bucket)", "repeat": 1, "wall_seconds": 1.06, "server_cpu_seconds": 2.23, "cores_busy": 2.1, "files": 10, "directories": 10, "bytes": 260471898}
{"rows": 16000000, "buckets": 10, "mode": "repartition(n, bucket) + partitionBy(bucket)", "repeat": 1, "wall_seconds": 0.966, "server_cpu_seconds": 2.07, "cores_busy": 2.1, "files": 10, "directories": 10, "bytes": 260469526}
{"rows": 16000000, "buckets": 10, "mode": "plain", "repeat": 2, "wall_seconds": 0.176, "server_cpu_seconds": 1.05, "cores_busy": 6.0, "files": 4, "directories": 1, "bytes": 265136095}
{"rows": 16000000, "buckets": 10, "mode": "repartition(n, bucket)", "repeat": 2, "wall_seconds": 0.193, "server_cpu_seconds": 1.22, "cores_busy": 6.3, "files": 4, "directories": 1, "bytes": 261333459}
{"rows": 16000000, "buckets": 10, "mode": "partitionBy(bucket)", "repeat": 2, "wall_seconds": 1.017, "server_cpu_seconds": 2.21, "cores_busy": 2.2, "files": 10, "directories": 10, "bytes": 260466410}
{"rows": 16000000, "buckets": 10, "mode": "repartition(n, bucket) + partitionBy(bucket)", "repeat": 2, "wall_seconds": 0.913, "server_cpu_seconds": 2.03, "cores_busy": 2.2, "files": 10, "directories": 10, "bytes": 260467554}
```

`output-16m-rows-1000-buckets.jsonl`:

```json
{"rows": 16000000, "buckets": 1000, "mode": "plain", "repeat": 0, "wall_seconds": 0.178, "server_cpu_seconds": 1.11, "cores_busy": 6.2, "files": 4, "directories": 1, "bytes": 278439259}
{"rows": 16000000, "buckets": 1000, "mode": "repartition(n, bucket)", "repeat": 0, "wall_seconds": 0.297, "server_cpu_seconds": 1.87, "cores_busy": 6.3, "files": 4, "directories": 1, "bytes": 261225088}
{"rows": 16000000, "buckets": 1000, "mode": "partitionBy(bucket)", "repeat": 0, "wall_seconds": 8.55, "server_cpu_seconds": 33.4, "cores_busy": 3.9, "files": 1000, "directories": 1000, "bytes": 306009730}
{"rows": 16000000, "buckets": 1000, "mode": "repartition(n, bucket) + partitionBy(bucket)", "repeat": 0, "wall_seconds": 1.236, "server_cpu_seconds": 4.18, "cores_busy": 3.4, "files": 1000, "directories": 1000, "bytes": 306009758}
{"rows": 16000000, "buckets": 1000, "mode": "plain", "repeat": 1, "wall_seconds": 0.182, "server_cpu_seconds": 1.09, "cores_busy": 6.0, "files": 4, "directories": 1, "bytes": 278439468}
{"rows": 16000000, "buckets": 1000, "mode": "repartition(n, bucket)", "repeat": 1, "wall_seconds": 0.299, "server_cpu_seconds": 1.9, "cores_busy": 6.3, "files": 4, "directories": 1, "bytes": 261215957}
{"rows": 16000000, "buckets": 1000, "mode": "partitionBy(bucket)", "repeat": 1, "wall_seconds": 7.551, "server_cpu_seconds": 32.72, "cores_busy": 4.3, "files": 1000, "directories": 1000, "bytes": 306009710}
{"rows": 16000000, "buckets": 1000, "mode": "repartition(n, bucket) + partitionBy(bucket)", "repeat": 1, "wall_seconds": 1.345, "server_cpu_seconds": 4.06, "cores_busy": 3.0, "files": 1000, "directories": 1000, "bytes": 306009734}
{"rows": 16000000, "buckets": 1000, "mode": "plain", "repeat": 2, "wall_seconds": 0.18, "server_cpu_seconds": 1.06, "cores_busy": 5.9, "files": 4, "directories": 1, "bytes": 278439479}
{"rows": 16000000, "buckets": 1000, "mode": "repartition(n, bucket)", "repeat": 2, "wall_seconds": 0.305, "server_cpu_seconds": 1.76, "cores_busy": 5.8, "files": 4, "directories": 1, "bytes": 261222507}
{"rows": 16000000, "buckets": 1000, "mode": "partitionBy(bucket)", "repeat": 2, "wall_seconds": 8.187, "server_cpu_seconds": 36.21, "cores_busy": 4.4, "files": 1000, "directories": 1000, "bytes": 306009727}
{"rows": 16000000, "buckets": 1000, "mode": "repartition(n, bucket) + partitionBy(bucket)", "repeat": 2, "wall_seconds": 1.252, "server_cpu_seconds": 4.21, "cores_busy": 3.4, "files": 1000, "directories": 1000, "bytes": 306009725}
```

`output-64m-rows-10-buckets.jsonl`:

```json
{"rows": 64000000, "buckets": 10, "mode": "plain", "repeat": 0, "wall_seconds": 0.747, "server_cpu_seconds": 4.19, "cores_busy": 5.6, "files": 4, "directories": 1, "bytes": 1060539604}
{"rows": 64000000, "buckets": 10, "mode": "repartition(n, bucket)", "repeat": 0, "wall_seconds": 0.876, "server_cpu_seconds": 4.92, "cores_busy": 5.6, "files": 4, "directories": 1, "bytes": 1045210053}
{"rows": 64000000, "buckets": 10, "mode": "partitionBy(bucket)", "repeat": 0, "wall_seconds": 4.067, "server_cpu_seconds": 8.42, "cores_busy": 2.1, "files": 10, "directories": 10, "bytes": 1035733309}
{"rows": 64000000, "buckets": 10, "mode": "repartition(n, bucket) + partitionBy(bucket)", "repeat": 0, "wall_seconds": 3.746, "server_cpu_seconds": 8.03, "cores_busy": 2.1, "files": 10, "directories": 10, "bytes": 1035743359}
{"rows": 64000000, "buckets": 10, "mode": "plain", "repeat": 1, "wall_seconds": 0.714, "server_cpu_seconds": 4.28, "cores_busy": 6.0, "files": 4, "directories": 1, "bytes": 1060540250}
{"rows": 64000000, "buckets": 10, "mode": "repartition(n, bucket)", "repeat": 1, "wall_seconds": 0.796, "server_cpu_seconds": 4.88, "cores_busy": 6.1, "files": 4, "directories": 1, "bytes": 1045148648}
{"rows": 64000000, "buckets": 10, "mode": "partitionBy(bucket)", "repeat": 1, "wall_seconds": 4.126, "server_cpu_seconds": 8.51, "cores_busy": 2.1, "files": 10, "directories": 10, "bytes": 1035751566}
{"rows": 64000000, "buckets": 10, "mode": "repartition(n, bucket) + partitionBy(bucket)", "repeat": 1, "wall_seconds": 3.682, "server_cpu_seconds": 8.1, "cores_busy": 2.2, "files": 10, "directories": 10, "bytes": 1035740356}
{"rows": 64000000, "buckets": 10, "mode": "plain", "repeat": 2, "wall_seconds": 0.74, "server_cpu_seconds": 4.23, "cores_busy": 5.7, "files": 4, "directories": 1, "bytes": 1060541134}
{"rows": 64000000, "buckets": 10, "mode": "repartition(n, bucket)", "repeat": 2, "wall_seconds": 0.803, "server_cpu_seconds": 4.83, "cores_busy": 6.0, "files": 4, "directories": 1, "bytes": 1045304479}
{"rows": 64000000, "buckets": 10, "mode": "partitionBy(bucket)", "repeat": 2, "wall_seconds": 4.02, "server_cpu_seconds": 8.39, "cores_busy": 2.1, "files": 10, "directories": 10, "bytes": 1035744623}
{"rows": 64000000, "buckets": 10, "mode": "repartition(n, bucket) + partitionBy(bucket)", "repeat": 2, "wall_seconds": 3.623, "server_cpu_seconds": 7.93, "cores_busy": 2.2, "files": 10, "directories": 10, "bytes": 1035747178}
```

</details>

## Observed

Median of three; the three span at most 16% of the median.

| Rows | Buckets | Write | Wall | Times plain | Server CPU | Cores busy | Files | ns per row |
|---|---|---|---|---|---|---|---|---|
| 16M | 10 | plain | 0.19 s | 1.0 | 1.05 s | 5.4 | 4 | 12 |
| 16M | 10 | `repartition(10, bucket)` | 0.20 s | 1.0 | 1.22 s | 6.2 | 4 | 12 |
| 16M | 10 | `partitionBy(bucket)` | 1.03 s | 5.3 | 2.21 s | 2.1 | 10 | 64 |
| 16M | 10 | `repartition(10, bucket)` then `partitionBy(bucket)` | 0.93 s | 4.8 | 2.04 s | 2.2 | 10 | 58 |
| 64M | 10 | plain | 0.74 s | 1.0 | 4.23 s | 5.7 | 4 | 12 |
| 64M | 10 | `partitionBy(bucket)` | 4.07 s | 5.5 | 8.42 s | 2.1 | 10 | 64 |
| 64M | 10 | `repartition(10, bucket)` then `partitionBy(bucket)` | 3.68 s | 5.0 | 8.03 s | 2.2 | 10 | 58 |
| 16M | 1,000 | plain | 0.18 s | 1.0 | 1.09 s | 6.1 | 4 | 11 |
| 16M | 1,000 | `partitionBy(bucket)` | 8.19 s | 45.5 | 33.40 s | 4.1 | 1,000 | 512 |
| 16M | 1,000 | `repartition(1000, bucket)` then `partitionBy(bucket)` | 1.25 s | 7.0 | 4.18 s | 3.3 | 1,000 | 78 |

- The cost is linear in rows: 64 ns a row at 16M and at 64M.
- The partitioned write is close to serial. Its CPU time doubles while its wall time grows fivefold.
- Arranging the input so each batch holds one partition value removes the 1,000-bucket blow-up but not the base cost.
- The plain write is fast and parallel, so the gap is in the partitioning step, not in Parquet encoding.

## Expected

A partitioned write within a small factor of the plain write, and parallel.

## Cause

`crates/sail-data-source/src/formats/parquet/write.rs` hands the write to DataFusion's `ParquetFormat::create_writer_physical_plan`. With partition columns set, `datafusion-datasource` 55.1.0 runs `hive_style_partitions_demuxer` in `src/write/demux.rs`:

1. **One task for the whole write.** `start_demuxer_task` spawns a single task over one input stream. Every batch of every input partition passes through it in turn.
2. **A string per row.** `compute_partition_keys_by_row` formats each partition value to text for every row, even for an integer column.
3. **A heap-allocated key per row.** `compute_take_arrays` builds a `Vec<String>` for each row and looks it up in a `HashMap<Vec<String>, UInt64Builder>`.
4. **A `take` per distinct value per batch.** With 1,000 values in every batch that is 1,000 gathers of a few rows each, and 1,000 tiny batches sent downstream.

Items 2 and 3 explain the base cost of about 50 ns a row. Item 4 explains the 1,000-bucket case. Item 1 explains why none of it runs in parallel.

## Possible fix

In rough order of gain for the work:

1. **Skip the demultiplexer when the input is already partitioned by the partition columns.** After `repartition(n, cols)` or an aggregation on those columns, each input partition holds whole partition values. Each input partition could write its own files directly, in parallel, with a scan for value changes instead of a hash per row. This can be done in Sail's planner or sink.
2. **Compute keys per batch, not per row.** Encode the partition columns once per batch (for example with the Arrow row format), group row indices by the encoded key, and format the directory name once per distinct key.
3. **A fast path for a batch with a single partition value.**
4. **Run the demultiplexer per input partition.**

Items 2 to 4 belong in DataFusion and would help every engine built on it.

## Related

#1360 addresses partitioned writes for Delta Lake. I found no existing issue for the Parquet path, and did not find one in DataFusion's tracker about the per-row cost of `hive_style_partitions_demuxer`.

## Notes

- One machine, a laptop with a fast internal SSD and a warm page cache.
- Local mode only. In cluster mode the single demultiplexer task is per write task, so the picture may differ.
- DataFusion was read at 55.1.0. A later version may have changed this function.
- Server CPU seconds come from `ps`, to 10 ms.
