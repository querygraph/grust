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
