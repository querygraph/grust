"""A checkpoint taken after a sort answers later queries wrongly.

    python checkpoint_sorted_repro.py /path/to/release/sail

Starts a Sail server in local mode with a checkpoint directory, builds one frame of 4,000,000 rows whose
key `k` has 1,000,003 distinct values in scrambled order, checkpoints it three ways, and asks each
checkpoint the same questions. Needs pyspark[connect] 4.0 and pyarrow. Default settings throughout.
"""
import glob, os, pathlib, shutil, socket, subprocess, sys, sysconfig, tempfile, time

import pyarrow.compute as pc
import pyarrow.parquet as pq

sail = sys.argv[1]
root = pathlib.Path(tempfile.mkdtemp(prefix="sail-checkpoint-"))
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
env = dict(os.environ, PYTHONHOME=sys.base_prefix, PYTHONPATH=sysconfig.get_paths()["purelib"],
           DYLD_LIBRARY_PATH=sysconfig.get_config_var("LIBDIR") or "", SAIL_MODE="local",
           SAIL_EXECUTION__CHECKPOINT__PATH=(root / "checkpoints").as_uri())
for name in list(env):
    if name.startswith("SAIL_OPTIMIZER") or name == "SAIL_EXPERIMENTAL_EXTENSIONS":
        del env[name]
server = subprocess.Popen([sail, "spark", "server", "--ip", "127.0.0.1", "--port", str(port)], env=env,
                          cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
try:
    while True:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
        assert server.poll() is None, "server exited"
        time.sleep(0.05)
    from pyspark.sql.connect import functions as F
    from pyspark.sql.connect.session import SparkSession

    spark = SparkSession.builder.remote(f"sc://127.0.0.1:{port}").create()
    rows = spark.range(4_000_000).select(((F.col("id") * 2654435761) % 1_000_003).alias("k"), F.col("id").alias("v"))
    groups = rows.groupBy("k").count().count()
    print(f"truth: {rows.count():,} rows, {groups:,} distinct k")

    def files_sorted(before: set[str]) -> str:
        new = sorted(set(glob.glob(str(root / "checkpoints" / "**" / "*.parquet"), recursive=True)) - before)
        flags = []
        for path in new:
            k = pq.read_table(path, columns=None).column(0)
            flags.append(bool(pc.all(pc.greater_equal(k[1:], k[:-1])).as_py()) if len(k) > 1 else True)
        return f"{sum(flags)} of {len(flags)} files sorted by k"

    cases = {
        "repartition(10, k).checkpoint()": lambda: rows.repartition(10, "k").checkpoint(),
        "repartition(10, k).sortWithinPartitions(k).checkpoint()": lambda: rows.repartition(10, "k").sortWithinPartitions("k").checkpoint(),
        "orderBy(k).checkpoint()": lambda: rows.orderBy("k").checkpoint(),
    }
    for label, make in cases.items():
        before = set(glob.glob(str(root / "checkpoints" / "**" / "*.parquet"), recursive=True))
        frame = make()
        got = frame.groupBy("k").count().count()
        distinct = frame.select("k").distinct().count()
        joined = frame.join(rows.select(F.col("k").alias("k2")).distinct(), F.col("k") == F.col("k2")).count()
        verdict = "ok" if (got, distinct, joined) == (groups, groups, 4_000_000) else "WRONG"
        print(f"{label}\n    rows {frame.count():,}; GROUP BY k: {got:,} groups; DISTINCT k: {distinct:,}; "
              f"join on k: {joined:,} rows; {files_sorted(before)}  -> {verdict}")
    sorted_ = cases["repartition(10, k).sortWithinPartitions(k).checkpoint()"]()
    print("\nplan of GROUP BY k over the sorted checkpoint:")
    sorted_.groupBy("k").count().explain()
    spark.stop()
finally:
    server.terminate()
    server.wait()
    shutil.rmtree(root, ignore_errors=True)
