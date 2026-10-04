**Kind:** silent behaviour difference between save modes. No wrong query results.

## Summary

`df.orderBy(k).write.parquet(path)` writes files sorted by `k`. The same write with `.mode("overwrite")` writes unsorted files. The same holds for `repartition(n, k).sortWithinPartitions(k)`. Nothing reports that the sort was dropped. Anyone who sorts to get clustered files for min/max pruning, and overwrites the output, as any re-run does, silently loses the clustering.

## Environment

- Sail `main` at `99ee46f69a97342e91bf7d4eaedb4509f1d8a9c2` (2026-10-02, version 0.7.2), unmodified, built with `cargo build --release --locked -p sail-cli`.
- DataFusion 55.1.0, as pinned by that commit.
- Client: PySpark 4.0.1 (Spark Connect), Python 3.12.8, pyarrow 25.0.1.
- macOS 26.2 on an Apple M1 Max. Local mode, default settings.

## Reproduce

```sh
python repro.py /path/to/release/sail
```

The script below starts its own server, writes 1,000,000 rows with a scrambled key four ways, and reads every data file back with pyarrow. It needs `pyspark[connect]` 4.0 and `pyarrow`.

<details>
<summary>repro.py</summary>

```python
"""A sort before a Parquet write is kept in the default save mode and dropped with mode("overwrite").

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


import glob
import pyarrow.compute as pc
import pyarrow.parquet as pq
from pyspark.sql.connect import functions as F

def sorted_files(directory):
    flags = []
    for path in sorted(glob.glob(str(directory / "*.parquet"))):
        k = pq.read_table(path, columns=["k"]).column(0)
        flags.append(len(k) < 2 or bool(pc.all(pc.greater_equal(k[1:], k[:-1])).as_py()))
    return f"{sum(flags)} of {len(flags)} files sorted by k"

with sail(sys.argv[1]) as (spark, root):
    rows = spark.range(1_000_000).select(((F.col("id") * 2654435761) % 1_000_003).alias("k"))
    for label, writer in (("orderBy(k).write.parquet(path)", lambda p: rows.orderBy("k").write.parquet(p)),
                          ("orderBy(k).write.mode(overwrite).parquet(path)", lambda p: rows.orderBy("k").write.mode("overwrite").parquet(p)),
                          ("repartition(4,k).sortWithinPartitions(k).write.parquet(path)", lambda p: rows.repartition(4, "k").sortWithinPartitions("k").write.parquet(p)),
                          ("repartition(4,k).sortWithinPartitions(k).write.mode(overwrite).parquet(path)", lambda p: rows.repartition(4, "k").sortWithinPartitions("k").write.mode("overwrite").parquet(p))):
        target = root / label.replace("(", "_").replace(")", "_").replace(",", "_").replace(".", "_")
        writer(target.as_uri())
        print(f"{label}: {sorted_files(target)}")
```

</details>

<details>
<summary>Output of the run reported here</summary>

```
orderBy(k).write.parquet(path): 4 of 4 files sorted by k
orderBy(k).write.mode(overwrite).parquet(path): 0 of 4 files sorted by k
repartition(4,k).sortWithinPartitions(k).write.parquet(path): 4 of 4 files sorted by k
repartition(4,k).sortWithinPartitions(k).write.mode(overwrite).parquet(path): 0 of 4 files sorted by k
```

</details>

## Observed

| Write | Files sorted by `k` |
|---|---|
| `orderBy(k).write.parquet(path)` | 4 of 4 |
| `orderBy(k).write.mode("overwrite").parquet(path)` | **0 of 4** |
| `repartition(4, k).sortWithinPartitions(k).write.parquet(path)` | 4 of 4 |
| `repartition(4, k).sortWithinPartitions(k).write.mode("overwrite").parquet(path)` | **0 of 4** |

## Expected

The save mode does not change what is written inside the files. Both modes keep the sort.

## Cause

From reading the code; the write plan was not inspected. With overwrite, the listing planner wraps the sink in a `BarrierExec` whose precondition deletes the old files (`crates/sail-data-source/src/listing/planner.rs:253-258`). `BarrierExec` (`crates/sail-physical-plan/src/barrier.rs`) does not report that it maintains its input order. DataFusion's sort enforcement then treats the user's `SortExec` below it as unnecessary and removes it. In the default mode the sink is the top node, and DataFusion's `DataSinkExec` reports `maintains_input_order`, so the sort stays.

## Possible fix

Have `BarrierExec` report `maintains_input_order` for its main plan child (not for the preconditions), and pass the child's ordering through its plan properties.

## Related

I found no existing issue or pull request about this. #1862 reports a dropped sort for CTAS with ORDER BY. #2722, #2726 and #2732 are the same family: an operator above a sort that does not declare it maintains or requires the order, so the optimizer removes the sort.

## Notes

- The fix is from reading the code. It was not built or tested.
- Only Parquet and local mode were run. Other file formats share the listing planner and were not checked.
