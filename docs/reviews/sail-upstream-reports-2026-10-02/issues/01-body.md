**Kind:** wrong results, silently.

## Summary

`DataFrame.checkpoint()` taken after `sortWithinPartitions(k)` or `orderBy(k)` gives a frame that answers later queries wrongly. On 4,000,000 rows with 1,000,003 distinct keys, `GROUP BY k` over the checkpoint returns 4,000,000 groups and `SELECT DISTINCT k` returns 4,000,000 keys. There is no error and no warning, and the settings are the defaults.

The checkpoint records that its data is sorted by `k`. The files it writes are not sorted, because the optimizer removes the sort before the write. Every later plan trusts the recorded order.

## Environment

- Sail `main` at `99ee46f69a97342e91bf7d4eaedb4509f1d8a9c2` (2026-10-02, version 0.7.2), unmodified, built with `cargo build --release --locked -p sail-cli`.
- DataFusion 55.1.0, as pinned by that commit.
- Client: PySpark 4.0.1 (Spark Connect), Python 3.12.8, pyarrow 25.0.1.
- macOS 26.2 on an Apple M1 Max. Local mode, with `SAIL_EXECUTION__CHECKPOINT__PATH` set to a local directory.

## Reproduce

```sh
python repro.py /path/to/release/sail
```

The script below starts its own server, runs the case, and stops the server. It needs `pyspark[connect]` 4.0 and `pyarrow`.

The frame:

```python
rows = spark.range(4_000_000).select(
    ((F.col("id") * 2654435761) % 1_000_003).alias("k"), F.col("id").alias("v"))
```

<details>
<summary>repro.py</summary>

```python
"""A checkpoint taken after a sort answers later queries wrongly.

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

checkpoints = pathlib.Path(tempfile.mkdtemp(prefix="sail-checkpoints-"))
with sail(sys.argv[1], SAIL_EXECUTION__CHECKPOINT__PATH=checkpoints.as_uri()) as (spark, root):
    # 4,000,000 rows; the key has 1,000,003 distinct values, in scrambled order.
    rows = spark.range(4_000_000).select(((F.col("id") * 2654435761) % 1_000_003).alias("k"), F.col("id").alias("v"))
    truth = rows.select("k").distinct().count()
    print(f"truth: {rows.count():,} rows, {truth:,} distinct k")
    cases = {
        "repartition(10, k).checkpoint()": lambda: rows.repartition(10, "k").checkpoint(),
        "repartition(10, k).sortWithinPartitions(k).checkpoint()":
            lambda: rows.repartition(10, "k").sortWithinPartitions("k").checkpoint(),
        "orderBy(k).checkpoint()": lambda: rows.orderBy("k").checkpoint(),
    }
    for label, make in cases.items():
        frame = make()
        groups = frame.groupBy("k").count().count()
        distinct = frame.select("k").distinct().count()
        verdict = "correct" if (groups, distinct) == (truth, truth) else "WRONG"
        print(f"{label}\n    rows {frame.count():,}; GROUP BY k: {groups:,} groups; DISTINCT k: {distinct:,}  -> {verdict}")
        if verdict == "WRONG":
            for line in plan_lines(frame.groupBy("k").count(), "AggregateExec", "SortExec"):
                print("    plan:", line)

# The same checkpoint under a sort-merge join: the join trusts the recorded order too.
with sail(sys.argv[1], SAIL_EXECUTION__CHECKPOINT__PATH=checkpoints.as_uri(), SAIL_OPTIMIZER__PREFER_HASH_JOIN="false") as (spark, root):
    rows = spark.range(4_000_000).select(((F.col("id") * 2654435761) % 1_000_003).alias("k"), F.col("id").alias("v"))
    keys = spark.range(1_000_003).select(F.col("id").alias("k2")).repartition(10, "k2").sortWithinPartitions("k2").checkpoint()
    for label, frame in (("repartition(10, k).checkpoint()", rows.repartition(10, "k").checkpoint()),
                         ("repartition(10, k).sortWithinPartitions(k).checkpoint()",
                          rows.repartition(10, "k").sortWithinPartitions("k").checkpoint())):
        joined = frame.join(keys, frame.k == keys.k2)
        print(f"prefer_hash_join=false, {label} JOIN keys ON k: {joined.count():,} rows (truth 4,000,000); "
              f"SortExec in plan: {len(plan_lines(joined, 'SortExec'))}")
shutil.rmtree(checkpoints, ignore_errors=True)
```

</details>

<details>
<summary>Output of the run reported here</summary>

```
truth: 4,000,000 rows, 1,000,003 distinct k
repartition(10, k).checkpoint()
    rows 4,000,000; GROUP BY k: 1,000,003 groups; DISTINCT k: 1,000,003  -> correct
repartition(10, k).sortWithinPartitions(k).checkpoint()
    rows 4,000,000; GROUP BY k: 4,000,000 groups; DISTINCT k: 4,000,000  -> WRONG
    plan: AggregateExec: mode=SinglePartitioned, gby=[#0@0 as #0], aggr=[count(Int64(1))], ordering_mode=Sorted
orderBy(k).checkpoint()
    rows 4,000,000; GROUP BY k: 3,960,618 groups; DISTINCT k: 3,960,618  -> WRONG
    plan: AggregateExec: mode=FinalPartitioned, gby=[#0@0 as #0], aggr=[count(Int64(1))], ordering_mode=Sorted
    plan: AggregateExec: mode=Partial, gby=[#0@0 as #0], aggr=[count(Int64(1))], ordering_mode=Sorted
prefer_hash_join=false, repartition(10, k).checkpoint() JOIN keys ON k: 4,000,000 rows (truth 4,000,000); SortExec in plan: 1
prefer_hash_join=false, repartition(10, k).sortWithinPartitions(k).checkpoint() JOIN keys ON k: 139 rows (truth 4,000,000); SortExec in plan: 0
```

</details>

## Observed

| Checkpoint taken after | Rows | `GROUP BY k`: groups | `DISTINCT k` | |
|---|---|---|---|---|
| (no checkpoint) | 4,000,000 | 1,000,003 | 1,000,003 | |
| `repartition(10, k)` | 4,000,000 | 1,000,003 | 1,000,003 | correct |
| `repartition(10, k).sortWithinPartitions(k)` | 4,000,000 | **4,000,000** | **4,000,000** | wrong |
| `orderBy(k)` | 4,000,000 | **3,960,618** | **3,960,618** | wrong |

The wrong aggregate's plan has no sort and aggregates in sorted mode:

```
AggregateExec: mode=SinglePartitioned, gby=[#0@0 as #0], aggr=[count(Int64(1))], ordering_mode=Sorted
```

A sorted-mode aggregate closes a group when the key changes. Over unsorted input it emits a new group at each change.

Reading the checkpoint's Parquet files with pyarrow (checked separately from the script below) shows that none is sorted by `k`: 0 of 10 files, and 0 of 1 for `orderBy`. The `orderBy` count varies a little between runs; that it is wrong does not.

With `SAIL_OPTIMIZER__PREFER_HASH_JOIN=false` a join on `k` between the sorted checkpoint and a sorted checkpoint of the 1,000,003 keys becomes a sort-merge join with no `SortExec`, and returns **139 rows instead of 4,000,000** (the reproducer's last line). The same join over the unsorted checkpoint returns 4,000,000. With the default hash join the join is correct, because it does not use the order.

## Expected

The same answers as over the frame before the checkpoint.

## Cause

1. **The order is recorded before the optimizer runs.** `crates/sail-session/src/planner.rs:195-200` builds the checkpoint command during physical planning and takes `input.output_ordering()` and `input.output_partitioning()` from the unoptimized physical input. The user's `SortExec` is still there, so the order is recorded.
2. **The writer does not ask for that order.** `RemoteCheckpointWriteExec` (`crates/sail-physical-plan/src/remote_checkpoint.rs:478`) implements neither `required_input_ordering` nor `maintains_input_order`. DataFusion's sort enforcement treats a `SortExec` under such a node as unnecessary and removes it.
3. **The recorded order is carried to the committed checkpoint unchanged** (`remote_checkpoint.rs:334-353`) and declared by every later scan of it (`planner.rs:335-336`).

The existing test of this behaviour, `test_checkpoint_preserves_partitioning_and_ordering` (`python/pysail/tests/spark/dataframe/test_checkpoint.py:145-160`), compares plan snapshots, not results, so it passes.

## Possible fix

Any one of these:

1. Give `RemoteCheckpointWriteExec` the recorded ordering as its `required_input_ordering`, and have it report `maintains_input_order`. The sort then stays, the files are sorted, and the declaration is true.
2. Record ordering and partitioning from the writer's optimized input when the write runs, not from the unoptimized plan. A dropped sort is then not recorded.
3. As a stopgap, record no ordering.

A regression test should compare query results over the checkpoint with the same queries over the source frame, for `sortWithinPartitions` and for `orderBy`.

## Related

The feature was added in #2270. I found no existing issue or pull request about this.

## Notes

- The fixes are from reading the code. None was built or tested.
- `localCheckpoint()` was not run. It goes through the same planner code.
- The same wrong results were seen in `local-cluster` mode. No multi-process cluster was run.
