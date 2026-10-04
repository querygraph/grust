"""What the checkpoint route is worth in time: one Pregel-shaped round, state and edges read by path
against state and edges read from hash checkpoints. Added by the reviewer of the plan study; the plan
study itself measured no time.

    python checkpoint_round_cost.py <sail binary> <vertices.parquet> <edges.parquet> [runs]

The round is `v JOIN e ON v.id = e.src`, then `GROUP BY e.dst` with `sum(v.val)`, reduced to one row so
no result write is timed. Prints one JSON object per measurement.
"""
import json, os, pathlib, shutil, socket, subprocess, sys, sysconfig, tempfile, time

sail, vertices, edges = sys.argv[1], sys.argv[2], sys.argv[3]
runs = int(sys.argv[4]) if len(sys.argv) > 4 else 3
T = 10
root = pathlib.Path(tempfile.mkdtemp(prefix="ckpt-round-"))
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
env = dict(os.environ, PYTHONHOME=sys.base_prefix, PYTHONPATH=sysconfig.get_paths()["purelib"],
           DYLD_LIBRARY_PATH=sysconfig.get_config_var("LIBDIR") or "", SAIL_MODE="local",
           SAIL_EXECUTION__DEFAULT_PARALLELISM=str(T), SAIL_EXECUTION__CHECKPOINT__PATH=(root / "ckpt").as_uri(),
           RUST_LOG="warn")
for name in list(env):
    if name.startswith("SAIL_OPTIMIZER") or name == "SAIL_EXPERIMENTAL_EXTENSIONS":
        del env[name]
server = subprocess.Popen([sail, "spark", "server", "--ip", "127.0.0.1", "--port", str(port)], env=env,
                          cwd=root, stdout=open(root / "server.log", "w"), stderr=subprocess.STDOUT)

def timed(label, action, **extra):
    started = time.perf_counter()
    value = action()
    print(json.dumps(dict(what=label, seconds=round(time.perf_counter() - started, 3), **extra)), flush=True)
    return value

try:
    while True:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
        assert server.poll() is None, "server exited"
        time.sleep(0.05)
    from pyspark.sql.connect.session import SparkSession
    from pyspark.sql.connect import functions as F
    spark = SparkSession.builder.remote(f"sc://127.0.0.1:{port}").create()
    e_path = spark.read.parquet(edges).select(F.col("source").alias("src"), F.col("target").alias("dst"))
    state = spark.read.parquet(vertices).select("id", (F.col("id") % 1000 * 0.001).alias("val"))
    state_dir = (root / "state").as_uri()
    timed("state written plain, read by path", lambda: state.write.mode("overwrite").parquet(state_dir))
    v_path = spark.read.parquet(state_dir)

    def round_of(v, e):
        messages = v.join(e, v.id == e.src).groupBy("dst").agg(F.sum("val").alias("s"))
        return messages.agg(F.count("*").alias("rows"), F.sum("s").alias("total")).collect()[0]

    e_ckpt = timed("edges: repartition(T, src).checkpoint(), once", lambda: e_path.repartition(T, "src").checkpoint())
    v_ckpt = timed("state: repartition(T, id).checkpoint(), per round", lambda: v_path.repartition(T, "id").checkpoint())
    answers = set()
    for run in range(runs):
        for label, v, e in (("round, state and edges by path", v_path, e_path),
                            ("round, state checkpoint, edges by path", v_ckpt, e_path),
                            ("round, state and edges from hash checkpoints", v_ckpt, e_ckpt)):
            row = timed(label, lambda: round_of(v, e), run=run)
            answers.add((row["rows"], round(row["total"], 3)))
    print(json.dumps(dict(what="distinct answers across all rounds", count=len(answers), answers=sorted(answers))))
    for run in range(runs):
        timed("state: plain write (today's checkpoint)", lambda: v_path.write.mode("overwrite").parquet((root / "w").as_uri()), run=run)
        timed("state: repartition(T, id).checkpoint()", lambda: v_path.repartition(T, "id").checkpoint(), run=run)
    spark.stop()
finally:
    server.terminate(); server.wait(); shutil.rmtree(root, ignore_errors=True)
