"""A sort before monotonically_increasing_id() is removed: the ids do not follow the sort.

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
    n = 2_000_000
    rows = spark.range(n).select(((F.col("id") * 7919) % n).alias("k"))  # every k in 0..n-1 once, scrambled
    print(f"distinct k: {rows.distinct().count():,} of {n:,}")
    indexed = rows.orderBy("k").select("k", F.monotonically_increasing_id().alias("i"))
    matches = F.sum(F.when(F.col("i") == F.col("k"), 1).otherwise(0))
    # After a global sort there is one partition, so the id of a row should be its rank, which is k.
    attempt("orderBy(k) + monotonically_increasing_id(), read by an aggregate: rows where i == k",
            lambda: indexed.agg(matches).collect()[0][0])
    for line in plan_lines(indexed.agg(matches), "SortExec", "MonotonicIdExec", "CoalescePartitionsExec", "RepartitionExec"):
        print("    plan:", line)
    indexed.write.parquet((root / "indexed").as_uri())
    attempt("the same frame written to Parquet, then read: rows where i == k",
            lambda: spark.read.parquet((root / "indexed").as_uri()).agg(matches).collect()[0][0])
    attempt("row_number() over (order by k) - 1, read by an aggregate: rows where it equals k",
            lambda: spark.sql("SELECT sum(CASE WHEN r = k THEN 1 ELSE 0 END) FROM "
                              "(SELECT k, row_number() OVER (ORDER BY k) - 1 AS r FROM {t})", t=rows).collect()[0][0])
