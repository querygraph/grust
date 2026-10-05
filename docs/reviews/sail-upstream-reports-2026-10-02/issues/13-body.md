**Kind:** internal panic on a valid query.

## Summary

A `CASE` whose first `THEN` returns an array of non-null structs, and whose other branch returns an array of structs with a NULL item, fails with a task panic:

```
called `Result::unwrap()` on an `Err` value: InvalidArgumentError("Non-nullable field of ListArray \"item\" cannot contain nulls")
```

The same `CASE` with the branches swapped returns the right rows, and so does the same shape with `INT` items. Spark returns `[{1}]` and `[NULL]` for both orders.

## Environment

- Sail `main` at `d29516a7405b7d997cf8c673c2e12ddeebf0d415` (2026-10-03, version 0.7.2), unmodified, built with `cargo build --release -p sail-cli`.
- DataFusion 55.1.0, as pinned by that commit.
- Client: PySpark 4.2.0 (Spark Connect), Python 3.12.8, pyarrow 25.0.1.
- macOS 26.2 on an Apple M1 Max. Local mode, default settings.

## Reproduce

```sh
python repro.py /path/to/release/sail
```

The script starts its own server, runs three queries, and stops the server. It needs `pyspark[connect]` 4.x and `pyarrow`.

<details>
<summary>repro.py</summary>

```python
"""A CASE over two arrays of structs panics when only a later branch has a NULL item.

    python repro.py /path/to/release/sail

Needs pyspark[connect] 4.x and pyarrow. Starts and stops its own server.
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


def attempt(label, sql):
    """Run `sql`; print its rows or the panic message."""
    try:
        print(f"{label}: {[tuple(r) for r in spark.sql(sql).collect()]}")
    except Exception as error:  # the reproducer reports any failure as text
        text = str(error)
        start = text.find("panicked")
        print(f"{label}: ERROR: {text[start:start + 160] if start >= 0 else text.splitlines()[0][:160]}")


CASES = {
    "struct, non-null array first": """
        SELECT CASE WHEN x = 1 THEN array(named_struct('a', 1))
                    ELSE array(CAST(NULL AS STRUCT<a: INT>)) END AS v
        FROM VALUES (1), (2) AS t(x)""",
    "struct, nullable array first": """
        SELECT CASE WHEN x <> 1 THEN array(CAST(NULL AS STRUCT<a: INT>))
                    ELSE array(named_struct('a', 1)) END AS v
        FROM VALUES (1), (2) AS t(x)""",
    "int, non-null array first   ": """
        SELECT CASE WHEN x = 1 THEN array(1)
                    ELSE array(CAST(NULL AS INT)) END AS v
        FROM VALUES (1), (2) AS t(x)""",
}

with sail(sys.argv[1]) as (spark, root):
    for label, sql in CASES.items():
        attempt(label, sql)
```

</details>

<details>
<summary>Output of the run reported here</summary>

```
struct, non-null array first: ERROR: panicked with message "called `Result::unwrap()` on an `Err` value: InvalidArgumentError(\"Non-nullable field of ListArray \\\"item\\\" cannot contain nulls\")"
struct, nullable array first: [([Row(a=1)],), ([None],)]
int, non-null array first   : [([1],), ([None],)]
```

</details>

## Observed

| `CASE` branches                                                                   | Result            |
| --------------------------------------------------------------------------------- | ----------------- |
| `array(named_struct('a', 1))` first, `array(CAST(NULL AS STRUCT<a: INT>))` second | **task panic**    |
| the same two, swapped                                                             | `[{1}]`, `[NULL]` |
| `array(1)` first, `array(CAST(NULL AS INT))` second                               | `[1]`, `[NULL]`   |

## Expected

`[{1}]` and `[NULL]` in both branch orders, as Spark returns.

## Cause (likely)

DataFusion's `CaseExpr::data_type` (`datafusion-physical-expr` 55.1.0, `src/expressions/case.rs:728`) returns the type of the first `THEN` branch that is not `Null`. `DataType::equals_datatype` ignores the nullability of nested fields, so `List(Struct, item not nullable)` and `List(Struct, item nullable)` count as the same type and no coercion is inserted. The output list therefore takes the first branch's non-nullable item field, and the branch whose list holds a NULL item fails Arrow's validation when the output array is built. `array(1)` does not trigger it because its item field is already nullable; `array(named_struct(...))` gets a non-nullable item field.

## Possible fix

Merge nested field nullability across the `THEN` and `ELSE` branches when resolving the `CASE` type (a nullable item field when any branch's is), or coerce every branch to that merged type during type coercion.

## Notes

- Found while porting a large SQL renderer to Sail, where `explode(CASE WHEN ... THEN array(<struct>) ELSE array(CASE WHEN ... THEN <struct> END, ...) END)` is a natural way to emit a variable number of rows per input row. Swapping the branches so the one that can hold NULL items comes first works around it.
- I did not check whether DataFusion upstream already reports this.
