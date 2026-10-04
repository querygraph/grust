"""spark_partition_id() and monotonically_increasing_id() fail anywhere but in a projection.

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
    frame = spark.range(1000).repartition(4)
    frame.createOrReplaceTempView("t")
    pid, mid = F.spark_partition_id, F.monotonically_increasing_id
    attempt("select(spark_partition_id()), distinct values", lambda: sorted({r[0] for r in frame.select(pid()).collect()}))
    attempt("withColumn(p, spark_partition_id()).groupBy(p).count()",
            lambda: sorted(tuple(r) for r in frame.withColumn("p", pid()).groupBy("p").count().collect()))
    attempt("groupBy(spark_partition_id()).count()", lambda: frame.groupBy(pid()).count().collect())
    attempt("filter(spark_partition_id() == 0).count()", lambda: frame.filter(pid() == 0).count())
    attempt("orderBy(spark_partition_id()).limit(2)", lambda: frame.orderBy(pid()).limit(2).collect())
    attempt("SQL: GROUP BY spark_partition_id()",
            lambda: spark.sql("SELECT spark_partition_id() AS p, count(*) FROM t GROUP BY spark_partition_id()").collect())
    attempt("groupBy(monotonically_increasing_id() % 2).count()", lambda: frame.groupBy((mid() % 2).alias("m")).count().collect())
    attempt("filter(monotonically_increasing_id() < 5).count()", lambda: frame.filter(mid() < 5).count())
