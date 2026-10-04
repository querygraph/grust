**Kind:** query failure in cluster mode; the same query runs in local mode.

## Summary

A catalog table created with `SORTED BY (k)` over several files makes `GROUP BY k` plan a sorted aggregation with an order-preserving hash repartition. In `local-cluster` mode the job planner refuses that repartition:

```
internal error: repartition is order-preserving and would result in incorrect results in distributed execution
```

## Environment

- Sail `main` at `99ee46f69a97342e91bf7d4eaedb4509f1d8a9c2` (2026-10-02, version 0.7.2), unmodified, built with `cargo build --release --locked -p sail-cli`.
- DataFusion 55.1.0, as pinned by that commit.
- Client: PySpark 4.0.1 (Spark Connect), Python 3.12.8, pyarrow 25.0.1.
- macOS 26.2 on an Apple M1 Max. Local mode and `local-cluster` mode, default settings.

## Reproduce

```sh
python repro.py /path/to/release/sail
```

The script below starts its own server, runs the case, and stops the server. It needs `pyspark[connect]` 4.0 and `pyarrow`.

The table is four Parquet files, each sorted by `k`, behind `CREATE TABLE t (k BIGINT) USING parquet CLUSTERED BY (k) SORTED BY (k) INTO 4 BUCKETS LOCATION ...`.

<details>
<summary>repro.py</summary>

```python
"""In cluster mode, GROUP BY over a table with a declared sort order fails with an internal error.

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


import pyarrow as pa
import pyarrow.parquet as pq

for mode in ("local", "local-cluster"):
    with sail(sys.argv[1], mode=mode) as (spark, root):
        # Four files, each sorted by k, behind a table declared SORTED BY (k).
        (root / "t").mkdir()
        for part in range(4):
            keys = sorted((i * 7 + part) % 1000 for i in range(500_000))
            pq.write_table(pa.table({"k": pa.array(keys, pa.int64())}), root / "t" / f"part-{part}.parquet")
        spark.sql(f"CREATE TABLE t (k BIGINT) USING parquet CLUSTERED BY (k) SORTED BY (k) INTO 4 BUCKETS "
                  f"LOCATION '{(root / 't').as_uri()}'")
        query = spark.sql("SELECT k, count(*) AS c FROM t GROUP BY k")
        attempt(f"{mode}: GROUP BY k over the table, groups", query.count)
        attempt(f"{mode}: GROUP BY k over the same files read by path, groups",
                spark.read.parquet((root / "t").as_uri()).groupBy("k").count().count)
        for line in plan_lines(query, "RepartitionExec"):
            print(f"{mode}: plan: {line}")
```

</details>

<details>
<summary>Output of the run reported here</summary>

```
local: GROUP BY k over the table, groups: 1000
local: GROUP BY k over the same files read by path, groups: 1000
local: plan: RepartitionExec: partitioning=Hash([#0@0], 10), input_partitions=10, preserve_order=true, sort_exprs=#0@0 ASC NULLS LAST
local-cluster: GROUP BY k over the table, groups: ERROR: internal error: repartition is order-preserving and would result in incorrect results in distributed execution
local-cluster: GROUP BY k over the same files read by path, groups: 1000
local-cluster: plan: RepartitionExec: partitioning=Hash([#0@0], 10), input_partitions=10, preserve_order=true, sort_exprs=#0@0 ASC NULLS LAST
```

</details>

## Observed

| Mode | `SELECT k, count(*) FROM t GROUP BY k` | The same files read by path |
|---|---|---|
| `local` | 1,000 groups | 1,000 groups |
| `local-cluster` | **internal error** | 1,000 groups |

The plan in both modes contains:

```
RepartitionExec: partitioning=Hash([#0@0], 10), input_partitions=10, preserve_order=true, sort_exprs=#0@0 ASC NULLS LAST
```

## Expected

The query runs in cluster mode and returns 1,000 groups.

## Cause

`crates/sail-execution/src/job_graph/planner.rs:463-471` returns the error for any `RepartitionExec` with `preserve_order()`. Its comment says no case had been found in which an order-preserving repartition is constructed. This is one: a scan with a declared order, several partitions, and an aggregate on the ordered key.

## Possible fix

Either support the order-preserving exchange (merge the sorted streams on the read side of the shuffle), or, when planning for cluster mode, replace it with a plain repartition and let the aggregate run in its unsorted mode.

## Related

#1448 (bucketed Parquet read with shuffle elimination) works in the same area and lists distributed execution as not yet validated. I found no existing issue about this failure.

## Notes

- Only `local-cluster` mode was run, not a multi-process cluster.
- A join on the ordered key was not checked for the same failure.
