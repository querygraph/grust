**Kind:** wrong result order, silently. Also a missed optimization.

## Summary

For a catalog table created with `CLUSTERED BY (c) SORTED BY (c) INTO n BUCKETS`, Sail declares the scan's order as `c ASC NULLS LAST`. Spark's ascending order is nulls first, and that is how such a table's files are sorted. So:

- `ORDER BY c ASC NULLS LAST` is planned with no sort, and returns the nulls **first**;
- the default `ORDER BY c`, which is nulls first, keeps its `SortExec` although the files already have that order.

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

The table is one Parquet file holding five nulls followed by 0 to 99,999, which is ascending with nulls first.

<details>
<summary>repro.py</summary>

```python
"""A table declared SORTED BY (c) is read as sorted NULLS LAST; ORDER BY c NULLS LAST then returns nulls first.

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

with sail(sys.argv[1]) as (spark, root):
    # One file, sorted ascending with nulls first: what Spark writes for SORTED BY (id).
    (root / "t").mkdir()
    pq.write_table(pa.table({"id": pa.array([None] * 5 + list(range(100_000)), pa.int64())}), root / "t" / "part-0.parquet")
    spark.sql(f"CREATE TABLE t (id BIGINT) USING parquet CLUSTERED BY (id) SORTED BY (id) INTO 1 BUCKETS "
              f"LOCATION '{(root / 't').as_uri()}'")
    plain = spark.read.parquet((root / "t").as_uri())
    plain.createOrReplaceTempView("p")
    for order in ("ORDER BY id ASC NULLS LAST", "ORDER BY id", "ORDER BY id ASC NULLS FIRST"):
        for name in ("t", "p"):
            frame = spark.sql(f"SELECT id FROM {name} {order}")
            rows = [r[0] for r in frame.collect()]
            kind = "table with SORTED BY" if name == "t" else "same file read by path"
            print(f"{order:28} | {kind:23} | SortExec in plan: {len(plan_lines(frame, 'SortExec'))} "
                  f"| first 3: {rows[:3]} | last 3: {rows[-3:]}")
```

</details>

<details>
<summary>Output of the run reported here</summary>

```
ORDER BY id ASC NULLS LAST   | table with SORTED BY    | SortExec in plan: 0 | first 3: [None, None, None] | last 3: [99997, 99998, 99999]
ORDER BY id ASC NULLS LAST   | same file read by path  | SortExec in plan: 1 | first 3: [0, 1, 2] | last 3: [None, None, None]
ORDER BY id                  | table with SORTED BY    | SortExec in plan: 1 | first 3: [None, None, None] | last 3: [99997, 99998, 99999]
ORDER BY id                  | same file read by path  | SortExec in plan: 1 | first 3: [None, None, None] | last 3: [99997, 99998, 99999]
ORDER BY id ASC NULLS FIRST  | table with SORTED BY    | SortExec in plan: 1 | first 3: [None, None, None] | last 3: [99997, 99998, 99999]
ORDER BY id ASC NULLS FIRST  | same file read by path  | SortExec in plan: 1 | first 3: [None, None, None] | last 3: [99997, 99998, 99999]
```

</details>

## Observed

| Query | Source | `SortExec` in plan | First rows | Last rows | |
|---|---|---|---|---|---|
| `ORDER BY id ASC NULLS LAST` | table with `SORTED BY` | 0 | `NULL, NULL, NULL` | 99997, 99998, 99999 | **wrong** |
| `ORDER BY id ASC NULLS LAST` | same file read by path | 1 | 0, 1, 2 | `NULL, NULL, NULL` | correct |
| `ORDER BY id` | table with `SORTED BY` | 1 | `NULL, NULL, NULL` | 99997, 99998, 99999 | correct, sort not avoided |
| `ORDER BY id` | same file read by path | 1 | `NULL, NULL, NULL` | 99997, 99998, 99999 | correct |

## Expected

`ORDER BY id ASC NULLS LAST` returns the nulls last. Ideally the default `ORDER BY id` over the table needs no sort.

## Cause

The conversion of a catalog sort column to a sort expression hard-codes `nulls_first: false` (`crates/sail-common-datafusion/src/catalog/mod.rs:84-90`). The listing source passes that order to the scan (`crates/sail-data-source/src/listing/source.rs:268`), and the optimizer removes a sort that the declared order already satisfies.

## Possible fix

Set `nulls_first` to match Spark's default for the direction: nulls first for ascending, nulls last for descending.

## Related

#1857 changes the cause: its description says it stores `nulls_first` in `CatalogTableSort`, which "was always `false`, mismatching Spark's convention". It presents that as a performance change; the wrong result order shown here is not mentioned there.

## Notes

- The file in the reproducer was written with pyarrow, in the order Spark uses for an ascending sort. Sail itself cannot write into a bucketed table today.
- Any declared order is trusted without a check. That is the nature of a declaration; this issue is only about which order is declared.
