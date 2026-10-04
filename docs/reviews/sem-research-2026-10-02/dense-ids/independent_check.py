"""An independent check of two claims of the dense-id study: a sort removed under
monotonically_increasing_id(), and a Parquet scan that is not repeatable in local mode.

    python independent_check.py /path/to/release/sail
"""
import contextlib, glob, os, pathlib, shutil, socket, subprocess, sys, sysconfig, tempfile, time
import pyarrow as pa, pyarrow.compute as pc, pyarrow.parquet as pq
sail = sys.argv[1]

@contextlib.contextmanager
def server(mode="local", **extra):
    root = pathlib.Path(tempfile.mkdtemp(prefix="sail-probe-"))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    env = dict(os.environ, PYTHONHOME=sys.base_prefix, PYTHONPATH=sysconfig.get_paths()["purelib"],
               DYLD_LIBRARY_PATH=sysconfig.get_config_var("LIBDIR") or "", SAIL_MODE=mode, **extra)
    for name in list(env):
        if (name.startswith("SAIL_OPTIMIZER") and name not in extra) or name == "SAIL_EXPERIMENTAL_EXTENSIONS":
            del env[name]
    proc = subprocess.Popen([sail, "spark", "server", "--ip", "127.0.0.1", "--port", str(port)], env=env, cwd=root,
                            stdout=open(root / "server.log", "w"), stderr=subprocess.STDOUT)
    try:
        while True:
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", port)) == 0: break
            assert proc.poll() is None, "server exited"; time.sleep(0.05)
        from pyspark.sql.connect.session import SparkSession
        spark = SparkSession.builder.remote(f"sc://127.0.0.1:{port}").create()
        yield spark, root
        spark.stop()
    finally:
        proc.terminate(); proc.wait(); shutil.rmtree(root, ignore_errors=True)

def attempt(label, action):
    try:
        print(f"[{label}] ->", action())
    except Exception as error:
        print(f"[{label}] ERROR:", str(error).strip().splitlines()[0][:300])

def sorted_files(directory, column):
    flags = []
    for path in sorted(glob.glob(str(directory / "**" / "*.parquet"), recursive=True)):
        k = pq.read_table(path, columns=[column]).column(0)
        flags.append(bool(pc.all(pc.greater_equal(k[1:], k[:-1])).as_py()) if len(k) > 1 else True)
    return f"{sum(flags)} of {len(flags)} files sorted"


from pyspark.sql.connect import functions as F
with server() as (spark, root):
    n = 2_000_000
    # k is a permutation of 0..n-1 in scrambled order (2654435761 is odd, so the map is a bijection mod 2^21... use a prime modulus instead)
    rows = spark.range(n).select(((F.col("id") * 7919) % n).alias("k"))
    print("distinct k:", rows.distinct().count(), "of", n)
    indexed = rows.orderBy("k").select("k", F.monotonically_increasing_id().alias("i"))
    attempt("orderBy(k) + monotonically_increasing_id: rows where i == k, read by an aggregate", lambda: indexed.agg(F.sum(F.when(F.col("i") == F.col("k"), 1).otherwise(0))).collect()[0][0])
    attempt("plan of that aggregate", lambda: [l.strip()[:120] for l in indexed.agg(F.count("*"), F.sum(F.when(F.col("i") == F.col("k"), 1).otherwise(0)))._explain_string().splitlines() if "Sort" in l or "MonotonicId" in l or "Coalesce" in l or "Repartition" in l])
    indexed.write.parquet((root / "w").as_uri())
    back = spark.read.parquet((root / "w").as_uri())
    attempt("the same frame written to Parquet first: rows where i == k", lambda: back.where(F.col("i") == F.col("k")).count())
    attempt("row_number() over (order by k) - 1 == k, read by an aggregate", lambda: spark.sql("SELECT sum(CASE WHEN r = k THEN 1 ELSE 0 END) FROM (SELECT k, row_number() OVER (ORDER BY k) - 1 AS r FROM {t})", t=rows).collect()[0][0])
    print("== repeatability of a parquet scan in local mode")
    spark.range(8_000_000).select(F.col("id").alias("k")).write.parquet((root / "p").as_uri())
    scan = spark.read.parquet((root / "p").as_uri())
    for run in range(3):
        sizes = sorted(tuple(r) for r in scan.select(F.spark_partition_id().alias("p")).groupBy("p").count().collect())
        ids = scan.select("k", F.monotonically_increasing_id().alias("i")).where("k in (0, 1000000, 4000000, 7999999)").orderBy("k").collect()
        print("run", run, "partition sizes", [c for _, c in sizes], "ids of four keys", [r[1] for r in ids])
