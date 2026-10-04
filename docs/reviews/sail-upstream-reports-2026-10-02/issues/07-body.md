**Kind:** semantic difference from Spark. Query results are correct; the partition contents are not what was asked for.

## Summary

`df.repartitionByRange(n, "id")` plans `RepartitionExec: partitioning=Hash([id], n)`. The partitions' key ranges overlap completely. There is no warning. Anything that relies on range partitions is affected: sorted files with disjoint key ranges after `sortWithinPartitions`, per-partition processing by key range, and file pruning on the result.

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

<details>
<summary>repro.py</summary>

```python
"""repartitionByRange hash-partitions: the partitions' key ranges overlap.

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
    frame = spark.range(1_000_000).repartitionByRange(4, "id")
    for line in plan_lines(frame, "RepartitionExec"):
        print("plan:", line)
    per_partition = (frame.select("id", F.spark_partition_id().alias("partition"))
                     .groupBy("partition").agg(F.min("id").alias("min"), F.max("id").alias("max"), F.count("*").alias("rows"))
                     .orderBy("partition").collect())
    for row in per_partition:
        print(f"partition {row['partition']}: ids {row['min']:,} to {row['max']:,}, {row['rows']:,} rows")
```

</details>

<details>
<summary>Output of the run reported here</summary>

```
plan: RepartitionExec: partitioning=Hash([#0@0], 4), input_partitions=1
partition 0: ids 2 to 999,991, 250,006 rows
partition 1: ids 1 to 999,994, 249,999 rows
partition 2: ids 10 to 999,999, 249,997 rows
partition 3: ids 0 to 999,995, 249,998 rows
```

</details>

## Observed

```
plan: RepartitionExec: partitioning=Hash([#0@0], 4), input_partitions=1
partition 0: ids 2 to 999,991, 250,006 rows
partition 1: ids 1 to 999,994, 249,999 rows
partition 2: ids 10 to 999,999, 249,997 rows
partition 3: ids 0 to 999,995, 249,998 rows
```

## Expected

Four partitions with disjoint, ordered key ranges, about 250,000 rows each, as Spark's `repartitionByRange` produces. Or an error saying range partitioning is not supported.

## Cause

`repartitionByRange` arrives as a repartition by expression and is always resolved to `ExplicitRepartitionKind::Hash` (`crates/sail-plan/src/resolver/query/repartition.rs:52-58`). The kinds are `Coalesce`, `RoundRobin` and `Hash` (`crates/sail-logical-plan/src/repartition.rs:9-13`). The sort direction of the range expression is dropped.

DataFusion 55.1.0 has `Partitioning::Range` with explicit split points, and `RepartitionExec` executes it. Sail's shuffle writer, job graph and checkpoint code already pass such a partitioning through. Nothing constructs one, and nothing samples the input to choose split points.

## Possible fix

Add a range kind to the explicit repartition, choose split points by sampling the input as Spark does, and plan `Partitioning::Range`. Until then, reject `repartitionByRange` or log that it is hash-partitioned.

## Related

I found no existing issue or pull request about this.

## Notes

- "Nothing constructs one" rests on a search of the source for `Partitioning::Range` and `RangePartitioning::`.
