"""Independent check: does a checkpoint taken after sortWithinPartitions answer correctly on upstream Sail?"""
import os, pathlib, shutil, socket, subprocess, sys, sysconfig, tempfile, time
sail = sys.argv[1]
root = pathlib.Path(tempfile.mkdtemp(prefix="ckpt-repro-"))
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
env = dict(os.environ, PYTHONHOME=sys.base_prefix, PYTHONPATH=sysconfig.get_paths()["purelib"], DYLD_LIBRARY_PATH=sysconfig.get_config_var("LIBDIR") or "", SAIL_MODE="local", SAIL_EXECUTION__CHECKPOINT__PATH=(root / "ckpt").as_uri(), RUST_LOG="warn")
for name in list(env):
    if name.startswith("SAIL_OPTIMIZER") or name == "SAIL_EXPERIMENTAL_EXTENSIONS":
        del env[name]
server = subprocess.Popen([sail, "spark", "server", "--ip", "127.0.0.1", "--port", str(port)], env=env,
                          stdout=open(root / "server.log", "w"), stderr=subprocess.STDOUT)
try:
    while True:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0: break
        assert server.poll() is None, "server exited"; time.sleep(0.05)
    from pyspark.sql.connect.session import SparkSession
    from pyspark.sql.connect import functions as F
    spark = SparkSession.builder.remote(f"sc://127.0.0.1:{port}").create()
    n = 4_000_000
    # src repeats, in scrambled order: a GROUP BY src has far fewer groups than rows.
    e = spark.range(n).select(((F.col("id") * 2654435761) % 1_000_003).alias("src"), F.col("id").alias("dst"))
    truth = e.groupBy("src").count().count()
    plain = e.repartition(10, "src").checkpoint()
    sorted_ = e.repartition(10, "src").sortWithinPartitions("src").checkpoint()
    print("groups, no checkpoint          :", truth)
    print("groups, hash checkpoint        :", plain.groupBy("src").count().count())
    print("groups, hash+sorted checkpoint :", sorted_.groupBy("src").count().count())
    print("rows  , hash+sorted checkpoint :", sorted_.count())
    # Co-partitioning: a join of two hash checkpoints, against the same join without checkpoints.
    v = spark.range(1_000_003).select(F.col("id").alias("id"), (F.col("id") * 0.5).alias("val"))
    vc = v.repartition(10, "id").checkpoint()
    def repartitions(frame):
        text = frame._explain_string(extended=False) if hasattr(frame, "_explain_string") else ""
        return text.count("RepartitionExec: partitioning=Hash")
    plain_join = v.join(e, v.id == e.src)
    ckpt_join = vc.join(plain, vc.id == plain.src)
    print("join rows, no checkpoint       :", plain_join.count(), " hash repartitions in plan:", repartitions(plain_join))
    print("join rows, two hash checkpoints:", ckpt_join.count(), " hash repartitions in plan:", repartitions(ckpt_join))
    print("sum(val), no checkpoint        :", plain_join.agg(F.sum("val")).collect()[0][0])
    print("sum(val), two hash checkpoints :", ckpt_join.agg(F.sum("val")).collect()[0][0])
    spark.stop()
finally:
    server.terminate(); server.wait(); shutil.rmtree(root, ignore_errors=True)
