**Kind:** `EXPLAIN` failure; execution is unaffected.

## Summary

With `optimizer.prefer_hash_join` set to false, `EXPLAIN` of a join between two multi-partition inputs fails:

```
Physical plan error: error in DataFusion: Invariant for ExecutionPlan node 'SortMergeJoinExec' failed
caused by
Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned.
```

The same query executes and returns the right rows. Every variant fails: `DataFrame.explain`, `EXPLAIN`, `EXPLAIN EXTENDED`, `EXPLAIN FORMATTED`, `EXPLAIN ANALYZE`.

## Environment

- Sail `main` at `99ee46f69a97342e91bf7d4eaedb4509f1d8a9c2` (2026-10-02, version 0.7.2), unmodified, built with `cargo build --release --locked -p sail-cli`.
- DataFusion 55.1.0, as pinned by that commit.
- Client: PySpark 4.0.1 (Spark Connect), Python 3.12.8, pyarrow 25.0.1.
- macOS 26.2 on an Apple M1 Max. Local mode, with `SAIL_OPTIMIZER__PREFER_HASH_JOIN=false`.

## Reproduce

```sh
python repro.py /path/to/release/sail
```

The script below starts its own server, runs the case, and stops the server. It needs `pyspark[connect]` 4.0 and `pyarrow`.

Two Parquet directories of 1,000,000 rows each, joined on an equality.

<details>
<summary>repro.py</summary>

```python
"""EXPLAIN fails for a sort-merge join that executes correctly (optimizer.prefer_hash_join = false).

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

with sail(sys.argv[1], SAIL_OPTIMIZER__PREFER_HASH_JOIN="false") as (spark, root):
    spark.range(1_000_000).select(F.col("id").alias("a")).write.parquet((root / "a").as_uri())
    spark.range(1_000_000).select((F.col("id") % 1000).alias("b")).write.parquet((root / "b").as_uri())
    a, b = spark.read.parquet((root / "a").as_uri()), spark.read.parquet((root / "b").as_uri())
    a.createOrReplaceTempView("a")
    b.createOrReplaceTempView("b")
    joined = a.join(b, a.a == b.b)
    attempt("the join executes, rows", joined.count)
    attempt("DataFrame.explain", lambda: joined._explain_string().strip().replace("\n", " | ")[:260])
    for variant in ("EXPLAIN", "EXPLAIN EXTENDED", "EXPLAIN FORMATTED", "EXPLAIN ANALYZE"):
        attempt(variant, lambda: spark.sql(f"{variant} SELECT * FROM a JOIN b ON a.a = b.b").collect()[0][0]
                .strip().replace("\n", " | ")[-230:])
```

</details>

<details>
<summary>Output of the run reported here</summary>

```
the join executes, rows: 1000000
DataFrame.explain: == Physical Plan == | Physical plan error: error in DataFusion: Invariant for ExecutionPlan node 'SortMergeJoinExec' failed | caused by | Internal error: SortMergeJoinExec requires children [0, 1] to be co-partitioned. | This issue was likely caused by a bug i
EXPLAIN: c requires children [0, 1] to be co-partitioned. | This issue was likely caused by a bug in DataFusion's code. Please help us to resolve this by filing a bug report in our issue tracker: https://github.com/apache/datafusion/issues
EXPLAIN EXTENDED: c requires children [0, 1] to be co-partitioned. | This issue was likely caused by a bug in DataFusion's code. Please help us to resolve this by filing a bug report in our issue tracker: https://github.com/apache/datafusion/issues
EXPLAIN FORMATTED: c requires children [0, 1] to be co-partitioned. | This issue was likely caused by a bug in DataFusion's code. Please help us to resolve this by filing a bug report in our issue tracker: https://github.com/apache/datafusion/issues
EXPLAIN ANALYZE: c requires children [0, 1] to be co-partitioned. | This issue was likely caused by a bug in DataFusion's code. Please help us to resolve this by filing a bug report in our issue tracker: https://github.com/apache/datafusion/issues
```

</details>

## Observed

| Step | Result |
|---|---|
| `a.join(b, a.a == b.b).count()` | 1,000,000 |
| `DataFrame.explain()` | the error above |
| `EXPLAIN`, `EXTENDED`, `FORMATTED`, `ANALYZE` | the error above |

It does not fail when both inputs already have a single partition, or the same hash partitioning, before optimization.

## Expected

`EXPLAIN` prints the plan that would execute.

## Cause

`crates/sail-plan/src/explain.rs:215-222` builds the initial physical plan with a session state whose physical optimizer rule list is empty. DataFusion's planner still ends with its invariant check for an executable plan, and a sort-merge join needs co-partitioned inputs, which only the optimizer's distribution enforcement establishes. Execution uses the full optimizer and passes.

## Possible fix

Do not run the executable-plan invariant on the unoptimized plan that `EXPLAIN` builds for display, or build that plan with the distribution and sorting enforcement rules kept.

## Related

The option was exposed in #2451. I found no existing issue or pull request about this.

## Notes

- A workaround to see the plan: in `local-cluster` mode with `RUST_LOG=warn,sail_execution::driver::job_scheduler::core=debug` the driver logs each executed plan.
