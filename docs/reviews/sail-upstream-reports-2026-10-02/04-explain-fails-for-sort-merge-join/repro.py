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
