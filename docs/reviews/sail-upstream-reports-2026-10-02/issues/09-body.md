**Kind:** missed optimization; the code that would use it is unreachable.

## Summary

A Parquet file whose footer declares `sorting_columns` is read with no declared order. `ORDER BY` on that column still plans a `SortExec`. Sail has code to derive a scan's order from Parquet footers, but the path that reaches it is never taken for a read by path.

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

The file holds `id` from 0 to 199,999 in order, written by pyarrow with `sorting_columns=[SortingColumn(0, descending=False, nulls_first=True)]`.

<details>
<summary>repro.py</summary>

```python
"""The sort order recorded in a Parquet footer (sorting_columns) is never used: ORDER BY still sorts.

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
    (root / "t").mkdir()
    table = pa.table({"id": pa.array(range(200_000), pa.int64())})
    pq.write_table(table, root / "t" / "part-0.parquet",
                   sorting_columns=[pq.SortingColumn(0, descending=False, nulls_first=True)])
    footer = pq.ParquetFile(root / "t" / "part-0.parquet").metadata.row_group(0).sorting_columns
    print("footer sorting_columns:", footer)
    spark.read.parquet((root / "t").as_uri()).createOrReplaceTempView("t")
    for order in ("ORDER BY id", "ORDER BY id ASC NULLS FIRST", "ORDER BY id ASC NULLS LAST"):
        frame = spark.sql(f"SELECT id FROM t {order}")
        print(f"{order:28} | SortExec in plan: {len(plan_lines(frame, 'SortExec'))}")
```

</details>

<details>
<summary>Output of the run reported here</summary>

```
footer sorting_columns: (SortingColumn(column_index=0, descending=False, nulls_first=True),)
ORDER BY id                  | SortExec in plan: 1
ORDER BY id ASC NULLS FIRST  | SortExec in plan: 1
ORDER BY id ASC NULLS LAST   | SortExec in plan: 1
```

</details>

## Observed

```
footer sorting_columns: (SortingColumn(column_index=0, descending=False, nulls_first=True),)
ORDER BY id                  | SortExec in plan: 1
ORDER BY id ASC NULLS FIRST  | SortExec in plan: 1
ORDER BY id ASC NULLS LAST   | SortExec in plan: 1
```

## Expected

`ORDER BY id` (ascending, nulls first) over this file needs no sort.

## Cause

The listing planner derives an order from the footers only when the source has no configured sort order: `try_create_output_ordering` in `crates/sail-data-source/src/listing/planner.rs:264-276` returns early when `file_sort_order` is not empty, and otherwise calls `ordering_from_parquet_metadata` (`crates/sail-data-source/src/formats/parquet/read.rs:206`). But the listing source always passes `file_sort_order: vec![sort_order]` (`crates/sail-data-source/src/listing/source.rs:268`), a list of one element even when `sort_order` itself is empty. So the early return is always taken.

## Possible fix

Pass an empty `file_sort_order` when the table has no sort order: `if sort_order.is_empty() { vec![] } else { vec![sort_order] }`.

## Related

#1857 also wires `file_sort_order`, from table metadata rather than from footers. I found no existing issue about the footer path.

## Notes

- Not checked: whether the derived order is then correct for a multi-file scan, where the files' key ranges may overlap. The declared order must hold per partition, so file grouping matters.
- Sail does not write `sorting_columns` itself: DataFusion writes them only when the sink is given a sort requirement, which would come from `sortBy`.
