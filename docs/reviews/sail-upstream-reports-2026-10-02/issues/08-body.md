**Kind:** query failure for expressions Spark accepts.

## Summary

Both functions work in `select` and `withColumn`. In a filter, a grouping expression or a sort key they fail:

```
spark_partition_id() was not rewritten into a partition-aware operator
```

In SQL, `GROUP BY spark_partition_id()` fails with a different message: `Non-deterministic expression spark_partition_id should not appear in an aggregate query`.

`df.groupBy(spark_partition_id()).count()` is the usual way to look at partition sizes in Spark.

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
"""spark_partition_id() and monotonically_increasing_id() fail anywhere but in a projection.

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
    frame = spark.range(1000).repartition(4)
    frame.createOrReplaceTempView("t")
    pid, mid = F.spark_partition_id, F.monotonically_increasing_id
    attempt("select(spark_partition_id()), distinct values", lambda: sorted({r[0] for r in frame.select(pid()).collect()}))
    attempt("withColumn(p, spark_partition_id()).groupBy(p).count()",
            lambda: sorted(tuple(r) for r in frame.withColumn("p", pid()).groupBy("p").count().collect()))
    attempt("groupBy(spark_partition_id()).count()", lambda: frame.groupBy(pid()).count().collect())
    attempt("filter(spark_partition_id() == 0).count()", lambda: frame.filter(pid() == 0).count())
    attempt("orderBy(spark_partition_id()).limit(2)", lambda: frame.orderBy(pid()).limit(2).collect())
    attempt("SQL: GROUP BY spark_partition_id()",
            lambda: spark.sql("SELECT spark_partition_id() AS p, count(*) FROM t GROUP BY spark_partition_id()").collect())
    attempt("groupBy(monotonically_increasing_id() % 2).count()", lambda: frame.groupBy((mid() % 2).alias("m")).count().collect())
    attempt("filter(monotonically_increasing_id() < 5).count()", lambda: frame.filter(mid() < 5).count())
```

</details>

<details>
<summary>Output of the run reported here</summary>

```
select(spark_partition_id()), distinct values: [0, 1, 2, 3]
withColumn(p, spark_partition_id()).groupBy(p).count(): [(0, 250), (1, 250), (2, 250), (3, 250)]
groupBy(spark_partition_id()).count(): ERROR: spark_partition_id() was not rewritten into a partition-aware operator
filter(spark_partition_id() == 0).count(): ERROR: round-robin repartition failed while reading input partition 0: Execution error: spark_partition_id() was not rewritten into a partition-aware operator
orderBy(spark_partition_id()).limit(2): ERROR: spark_partition_id() was not rewritten into a partition-aware operator
SQL: GROUP BY spark_partition_id(): ERROR: Non-deterministic expression spark_partition_id should not appear in an aggregate query
groupBy(monotonically_increasing_id() % 2).count(): ERROR: monotonically_increasing_id() was not rewritten into a partition-aware operator
filter(monotonically_increasing_id() < 5).count(): ERROR: round-robin repartition failed while reading input partition 0: Execution error: monotonically_increasing_id() was not rewritten into a partition-aware operator
```

</details>

## Observed

On `spark.range(1000).repartition(4)`:

| Expression | Result |
|---|---|
| `select(spark_partition_id())` | values 0 to 3 |
| `withColumn("p", spark_partition_id()).groupBy("p").count()` | four groups of 250 |
| `groupBy(spark_partition_id()).count()` | **error**: not rewritten into a partition-aware operator |
| `filter(spark_partition_id() == 0).count()` | **error**: the same, inside a round-robin repartition |
| `orderBy(spark_partition_id())` | **error**: the same |
| SQL `GROUP BY spark_partition_id()` | **error**: non-deterministic expression in an aggregate query |
| `groupBy(monotonically_increasing_id() % 2).count()` | **error**: not rewritten |
| `filter(monotonically_increasing_id() < 5).count()` | **error**: not rewritten |

## Expected

The functions evaluate wherever an expression is allowed, as in the projection case. Spark accepts them in filters and grouping expressions; that is stated from Spark's documented behaviour and common use, and Spark was not run for this issue. The sort-key case is not claimed for Spark.

## Cause

The functions are placeholders that a plan rewriter replaces with a column produced by a partition-aware operator. The rewriters are applied to projection lists only (`crates/sail-plan/src/resolver/query/lateral.rs:129-131`, `crates/sail-plan/src/resolver/query/aggregate.rs:272-274`). In a filter, a grouping expression or a sort key the placeholder survives to execution and raises the error (`crates/sail-function/src/scalar/misc/spark_partition_id.rs:45`, `monotonically_increasing_id.rs:45`).

## Possible fix

Apply the same rewrite to filter predicates, grouping expressions and sort keys: add the generated column below the operator and reference it. This is what the workaround does by hand with `withColumn`.

## Related

#1361 lists `monotonically_increasing_id()` in `GROUP BY` and `ORDER BY` of aggregate queries as cases to handle. A review comment on #1727 names the filter case, and it was deferred as follow-up work with a pointer to #1361. I found no issue that tracks the filter and sort-key cases, so this one adds them with a reproducer.

## Notes

- The workaround is to materialise the value with `withColumn` first.
