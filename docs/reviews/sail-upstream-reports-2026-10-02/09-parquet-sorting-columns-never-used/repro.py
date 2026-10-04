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
