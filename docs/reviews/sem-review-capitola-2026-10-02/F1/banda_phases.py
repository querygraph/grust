"""Banda end to end on the LDBC Parquet files, in Sem's phases: read and stage, projection (CSR), algorithm
with Parquet out; then two more algorithm calls on the same staged graph. Launch to exit of the Sail server."""
import argparse, json, os, pathlib, shutil, socket, subprocess, sys, sysconfig, time

HOME = pathlib.Path.home()
W = HOME / "src/sail-pecan-integrated"
parser = argparse.ArgumentParser()
parser.add_argument("--graph", default="cit-Patents")
parser.add_argument("--order", choices=["canonical", "asStaged"], default="asStaged")
parser.add_argument("--threads", type=int, default=10)
parser.add_argument("--ids", choices=["string", "int64"], default="string")
parser.add_argument("--workers", type=int, default=0, help="NUTMEG_WORKERS for projection builds; 0 leaves it unset")
parser.add_argument("--quota-gib", type=int, default=40)
parser.add_argument("--sail", type=pathlib.Path, default=W / "target/host/release/sail")
parser.add_argument("--root", type=pathlib.Path, default=W / "target/parity/banda")
parser.add_argument("--out", type=pathlib.Path, required=True)
args = parser.parse_args()
V = HOME / f"src/reference/data/{args.graph}/{args.graph}-v.parquet"
E = HOME / f"src/reference/data/{args.graph}/{args.graph}-e.parquet"
shutil.rmtree(args.root, ignore_errors=True)
(args.root / "staging").mkdir(parents=True)
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
env = dict(os.environ, PYTHONHOME=sys.base_prefix, PYTHONPATH=sysconfig.get_paths()["purelib"],
           DYLD_LIBRARY_PATH=sysconfig.get_config_var("LIBDIR") or "", SAIL_EXPERIMENTAL_EXTENSIONS="1",
           SAIL_MODE="local", SAIL_EXECUTION__DEFAULT_PARALLELISM=str(args.threads),
           SAIL_RUNTIME__MEMORY_POOL__TYPE="greedy",
           SAIL_RUNTIME__MEMORY_POOL__GREEDY__MAX_SIZE=str((args.quota_gib + 8) * 2**30),
           SAIL_NUTMEG_MEMORY_BYTES=str(args.quota_gib * 2**30), SAIL_GRAPH_UTILS_ROOT=(args.root / "staging").as_uri(),
           TOKIO_WORKER_THREADS=str(args.threads), RAYON_NUM_THREADS=str(args.threads), RUST_LOG="warn")
if args.workers:
    env["NUTMEG_WORKERS"] = str(args.workers)
record = dict(graph=args.graph, order=args.order, threads=args.threads, ids=args.ids, workers=args.workers, phases={})
launched = time.perf_counter()
with (args.root / "server.log").open("w") as log:
    server = subprocess.Popen([str(args.sail), "spark", "server", "--ip", "127.0.0.1", "--port", str(port)],
                              env=env, cwd=args.root, stdout=log, stderr=subprocess.STDOUT)
try:
    while True:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
        assert server.poll() is None, "server exited"
        time.sleep(0.01)
    from pyspark.sql.connect.session import SparkSession
    from pyspark.sql.connect import functions as F
    from sail_nutmeg.client import Nutmeg
    spark = SparkSession.builder.remote(f"sc://127.0.0.1:{port}").create()
    nm = Nutmeg(spark)
    record["phases"]["server_and_session"] = time.perf_counter() - launched

    def phase(name, action):
        started = time.perf_counter()
        value = action()
        record["phases"][name] = time.perf_counter() - started
        print(name, round(record["phases"][name], 2), flush=True)
        return value

    # Ids as text (the harness's contract until now) or kept BIGINT.
    kind = "long" if args.ids == "int64" else "string"
    mapping = {"ids": "int64"} if args.ids == "int64" else None
    nodes = spark.read.parquet(V.as_uri()).select(F.col("id").cast(kind).alias("node_id"))
    links = spark.read.parquet(E.as_uri()).select(F.col("source").cast(kind).alias("source"),
                                                  F.col("target").cast(kind).alias("target"))
    receipt = phase("read_and_stage", lambda: nm.stage("g", nodes, links, node_mapping=mapping, edge_mapping=mapping,
                                                     order=None if args.order == "canonical" else args.order))
    record["stage_receipt"] = receipt.asDict()

    def run_and_write(name, kernel, select, **options):
        out = args.root / f"result-{name}"
        frame = nm.run("g", kernel, concurrency=args.threads, **options)
        phase(name, lambda: select(frame).write.parquet(out.as_uri()))
        record.setdefault("rows", {})[name] = spark.read.parquet(out.as_uri()).count()

    components = lambda f: f.select(F.col("nodeId").cast("long").alias("id"), F.col("componentId").cast("long").alias("component"))
    run_and_write("wcc_call_1", "wcc", components)
    run_and_write("wcc_call_2", "wcc", components)
    stats = phase("projection_stats_outgoing", lambda: nm.run("g", "projectionStats", orientation="outgoing").first())
    record["projection_stats"] = stats.asDict()
    ranks = lambda f: f.select(F.col("nodeId").cast("long").alias("id"), "score")
    run_and_write("pagerank_10_steps", "pagerank", ranks, damping=0.85, tolerance=1e-30, maxIterations=10,
                  precision="f64", orientation="outgoing")
    record["status"] = nm.status()
    spark.stop()
finally:
    server.terminate(); server.wait(timeout=120)
record["launch_to_exit_seconds"] = time.perf_counter() - launched
args.out.write_text(json.dumps(record, indent=1, default=str))
print(json.dumps({k: (round(v, 2) if isinstance(v, float) else v) for k, v in record["phases"].items()}), "total", round(record["launch_to_exit_seconds"], 2), record.get("rows"))
