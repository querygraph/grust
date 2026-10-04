**Kind:** misleading error; `sortBy` unusable.

## Summary

Any write that uses `sortBy` fails with

```
attribute ObjectName([Identifier("k")]) is missing from the schema: cannot resolve attribute
```

although `k` is a column of the frame. It happens for Parquet and Delta, with and without `bucketBy`, for `save` and `saveAsTable`.

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
"""DataFrameWriter.sortBy fails to resolve a column that exists.

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
    rows = spark.range(1000).select(F.col("id").alias("k"), (F.col("id") * 2).alias("v"))
    print("columns:", rows.columns)
    attempt("write.bucketBy(4, k).sortBy(k).saveAsTable",
            lambda: rows.write.bucketBy(4, "k").sortBy("k").format("parquet").option("path", (root / "a").as_uri()).saveAsTable("a"))
    attempt("write.bucketBy(4, k).saveAsTable (no sortBy)",
            lambda: rows.write.bucketBy(4, "k").format("parquet").option("path", (root / "b").as_uri()).saveAsTable("b"))
    attempt("write.sortBy(k).parquet(path)", lambda: rows.write.sortBy("k").parquet((root / "c").as_uri()))
    attempt("write.format(delta).sortBy(k).save(path)", lambda: rows.write.format("delta").sortBy("k").save((root / "d").as_uri()))
```

</details>

<details>
<summary>Output of the run reported here</summary>

```
columns: ['k', 'v']
write.bucketBy(4, k).sortBy(k).saveAsTable: ERROR: attribute ObjectName([Identifier("k")]) is missing from the schema: cannot resolve attribute
write.bucketBy(4, k).saveAsTable (no sortBy): ERROR: bucketing for writing listing data source
write.sortBy(k).parquet(path): ERROR: attribute ObjectName([Identifier("k")]) is missing from the schema: cannot resolve attribute
write.format(delta).sortBy(k).save(path): ERROR: attribute ObjectName([Identifier("k")]) is missing from the schema: cannot resolve attribute
```

</details>

## Observed

The frame has columns `k` and `v`.

| Write | Result |
|---|---|
| `write.bucketBy(4, "k").sortBy("k").saveAsTable(...)` | `attribute ... "k" is missing from the schema` |
| `write.bucketBy(4, "k").saveAsTable(...)` | `bucketing for writing listing data source` (a clear "not supported") |
| `write.sortBy("k").parquet(path)` | `attribute ... "k" is missing from the schema` |
| `write.format("delta").sortBy("k").save(path)` | `attribute ... "k" is missing from the schema` |

## Expected

The sort column resolves. The write then either sorts, or reports plainly that bucketing or `sortBy` is not supported, as the second row does.

## Cause

Inferred from the code, not confirmed by a fix: `crates/sail-plan/src/resolver/command/write.rs:240` resolves the sort columns against the write input after that input has been renamed to user-facing column names (`write.rs:550-558`), while the resolver state knows the columns by their internal names.

## Possible fix

Resolve the sort columns before the input is renamed, as the partition columns are, or resolve them against the renamed schema by name.

## Related

I found no existing issue or pull request about this.

## Notes

- Both sinks already accept a sort order (`crates/sail-data-source/src/formats/parquet/write.rs:36`, `crates/sail-delta-lake/src/lake_source.rs:602`), so only the resolution stands in the way.
