**Kind:** wrong values, silently.

## Summary

`df.orderBy(k).withColumn("i", monotonically_increasing_id())` is the usual way to number rows in sorted order. When the consumer of that frame does not itself need the order (an aggregate, a join), the optimizer removes the sort under the id operator, and the ids no longer follow `k`. On 2,000,000 rows whose keys are 0 to 1,999,999 in scrambled order, the id should equal the key for every row. Read by an aggregate, it equals the key for 1 row.

When the same frame is written to Parquet instead, the sort is kept and all 2,000,000 ids are right. `row_number() over (order by k)` is right in both cases.

## Environment

- Sail `main` at `99ee46f69a97342e91bf7d4eaedb4509f1d8a9c2` (2026-10-02, version 0.7.2), unmodified, built with `cargo build --release --locked -p sail-cli`.
- DataFusion 55.1.0, as pinned by that commit.
- Client: PySpark 4.0.1 (Spark Connect), Python 3.12.8, pyarrow 25.0.1.
- macOS 26.2 on an Apple M1 Max. Local mode, default settings.

## Reproduce

```sh
python repro.py /path/to/release/sail
```

The script below starts its own server, runs the case, and stops the server. It needs `pyspark[connect]` 4.0 and `pyarrow`.

```python
n = 2_000_000
rows = spark.range(n).select(((F.col("id") * 7919) % n).alias("k"))   # every k once, scrambled
indexed = rows.orderBy("k").select("k", F.monotonically_increasing_id().alias("i"))
indexed.agg(F.sum(F.when(F.col("i") == F.col("k"), 1).otherwise(0)))  # expected: 2,000,000
```

<details>
<summary>repro.py</summary>

```python
"""A sort before monotonically_increasing_id() is removed: the ids do not follow the sort.

    python repro.py /path/to/release/sail

Needs pyspark[connect] 4.0 and pyarrow. Starts and stops its own server.
"""
import contextlib, os, pathlib, shutil, socket, subprocess, sys, sysconfig, tempfile, time


@contextlib.contextmanager
def sail(binary, mode="local", **settings):
    """A Sail server in `mode` with the given environment settings, a Spark Connect session, a scratch directory."""
    root = pathlib.Path(tempfile.mkdtemp(prefix="sail-repro-"))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    # The server embeds Python; point it at this interpreter's environment.
    env = dict(os.environ, PYTHONHOME=sys.base_prefix, PYTHONPATH=sysconfig.get_paths()["purelib"],
               DYLD_LIBRARY_PATH=sysconfig.get_config_var("LIBDIR") or "",
               LD_LIBRARY_PATH=sysconfig.get_config_var("LIBDIR") or "", SAIL_MODE=mode, **settings)
    for name in list(env):
        if name.startswith("SAIL_") and name != "SAIL_MODE" and name not in settings:
            del env[name]
    server = subprocess.Popen([binary, "spark", "server", "--ip", "127.0.0.1", "--port", str(port)], env=env,
                              cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        while True:
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    break
            assert server.poll() is None, "the server exited"
            time.sleep(0.05)
        from pyspark.sql.connect.session import SparkSession
        spark = SparkSession.builder.remote(f"sc://127.0.0.1:{port}").create()
        yield spark, root
        spark.stop()
    finally:
        server.terminate()
        server.wait()
        shutil.rmtree(root, ignore_errors=True)


def attempt(label, action):
    """Run `action`; print its value or the first line of its error."""
    try:
        print(f"{label}: {action()}")
    except Exception as error:  # the reproducer reports any failure as text
        print(f"{label}: ERROR: {str(error).strip().splitlines()[0][:300]}")


def plan_lines(frame, *needles):
    """The physical plan lines that mention any of `needles`."""
    text = frame._explain_string()
    return [line.strip()[:170] for line in text.splitlines() if any(n in line for n in needles)]


from pyspark.sql.connect import functions as F

with sail(sys.argv[1]) as (spark, root):
    n = 2_000_000
    rows = spark.range(n).select(((F.col("id") * 7919) % n).alias("k"))  # every k in 0..n-1 once, scrambled
    print(f"distinct k: {rows.distinct().count():,} of {n:,}")
    indexed = rows.orderBy("k").select("k", F.monotonically_increasing_id().alias("i"))
    matches = F.sum(F.when(F.col("i") == F.col("k"), 1).otherwise(0))
    # After a global sort there is one partition, so the id of a row should be its rank, which is k.
    attempt("orderBy(k) + monotonically_increasing_id(), read by an aggregate: rows where i == k",
            lambda: indexed.agg(matches).collect()[0][0])
    for line in plan_lines(indexed.agg(matches), "SortExec", "MonotonicIdExec", "CoalescePartitionsExec", "RepartitionExec"):
        print("    plan:", line)
    indexed.write.parquet((root / "indexed").as_uri())
    attempt("the same frame written to Parquet, then read: rows where i == k",
            lambda: spark.read.parquet((root / "indexed").as_uri()).agg(matches).collect()[0][0])
    attempt("row_number() over (order by k) - 1, read by an aggregate: rows where it equals k",
            lambda: spark.sql("SELECT sum(CASE WHEN r = k THEN 1 ELSE 0 END) FROM "
                              "(SELECT k, row_number() OVER (ORDER BY k) - 1 AS r FROM {t})", t=rows).collect()[0][0])
```

</details>

<details>
<summary>Output of the run reported here</summary>

```
distinct k: 2,000,000 of 2,000,000
orderBy(k) + monotonically_increasing_id(), read by an aggregate: rows where i == k: 1
    plan: CoalescePartitionsExec
    plan: MonotonicIdExec: col=#2
    plan: RepartitionExec: partitioning=RoundRobinBatch(10), input_partitions=1
the same frame written to Parquet, then read: rows where i == k: 2000000
row_number() over (order by k) - 1, read by an aggregate: rows where it equals k: 2000000
```

</details>

## Observed

| Consumer of `orderBy(k)` + `monotonically_increasing_id()` | Rows where the id equals the key |
|---|---|
| an aggregate | **1** of 2,000,000 |
| a Parquet write, then read | 2,000,000 of 2,000,000 |
| (for comparison) `row_number() over (order by k) - 1`, read by an aggregate | 2,000,000 of 2,000,000 |

The plan of the aggregate has no `SortExec`:

```
CoalescePartitionsExec
MonotonicIdExec: col=#2
RepartitionExec: partitioning=RoundRobinBatch(10), input_partitions=1
```

## Expected

The ids are assigned in the sorted order whatever consumes the frame, as when it is written.

## Cause

`MonotonicIdExec` numbers the rows of each partition stream as they pass (`crates/sail-physical-plan/src/monotonic_id.rs`). It reports `maintains_input_order` (line 100) but does not implement `required_input_ordering`, so the default, no requirement, applies. DataFusion's sort enforcement removes a `SortExec` when nothing above it needs the order. An aggregate does not, so the sort under the id operator goes, and a round-robin repartition is put in its place.

Sail already has a way to pin a sort for order-sensitive windows and aggregates: `RequiredSortNode`, planned as a sort under an output requirement (`crates/sail-session/src/planner.rs:428`). The id function does not use it.

## Possible fix

When the input of the id operator has a sort that the user wrote, keep it: either have `MonotonicIdExec` require the ordering its input declares at planning time, or plan the user's sort through `RequiredSortNode` when an id function sits above it.

## Related

I found no existing issue or pull request about this. #1936 is about the operator's partitioning, not its input order. The same mechanism, an operator that depends on input order without requiring it, is behind #2722 and #2726.

## Notes

- The fix is from reading the code. It was not built or tested.
- `spark_partition_id()` is not affected: it does not depend on row order.
- Workarounds: write the frame before using the id, or use `row_number() over (order by k)`.
- Separately from the dropped sort, an id taken directly over a Parquet scan differs between executions in local mode, because the scan's partition streams share files. That is within the function's documented non-determinism, but it differs from cluster mode, where a scan is repeatable.
