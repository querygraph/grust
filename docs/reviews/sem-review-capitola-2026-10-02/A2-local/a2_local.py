"""Stage A's launch-to-exit contrast repeated on Capitola: Pecan on a release Sail host in local
mode against the graphframes-rs binary, same LDBC Parquet files, ABBA blocks, an oracle per pair."""
import argparse, json, os, pathlib, shutil, socket, subprocess, sys, sysconfig, time
import pyarrow.parquet as pq

HOME = pathlib.Path.home()
W = HOME / "src/sail-pecan-integrated"
SAIL = W / "target/host/release/sail"
GF = HOME / "src/reference/graphframes-rs/target/release/graphframes"
DATA = HOME / "src/reference/data"
parser = argparse.ArgumentParser()
parser.add_argument("--graph", default="cit-Patents")
parser.add_argument("--contrasts", nargs="+", default=["wcc", "pagerank"])
parser.add_argument("--blocks", type=int, default=2)
parser.add_argument("--workers", type=int, default=10)
parser.add_argument("--source", type=int, default=5795784, help="BFS source (the A2 source for cit-Patents)")
parser.add_argument("--root", type=pathlib.Path, default=W / "target/parity/a2")
parser.add_argument("--out", type=pathlib.Path, required=True)
parser.add_argument("--server-env", action="append", default=[])
parser.add_argument("--no-snapshot", action="store_true")
parser.add_argument("--no-repartition", action="store_true")
args = parser.parse_args()
V = DATA / args.graph / f"{args.graph}-v.parquet"
E = DATA / args.graph / f"{args.graph}-e.parquet"

def pecan(contrast, out):
    """Server launch to server exit, with session, input handles, algorithm and Parquet export inside."""
    from pyspark.sql.connect.session import SparkSession
    from pyspark.sql.connect import functions as F
    from pyspark_pecan import GraphAlgorithms
    staging = out / "staging"; staging.mkdir(parents=True)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    env = dict(os.environ, PYTHONHOME=sys.base_prefix, PYTHONPATH=sysconfig.get_paths()["purelib"],
               DYLD_LIBRARY_PATH=sysconfig.get_config_var("LIBDIR") or "", SAIL_EXPERIMENTAL_EXTENSIONS="1",
               SAIL_MODE="local", SAIL_EXECUTION__DEFAULT_PARALLELISM=str(args.workers),
               SAIL_RUNTIME__MEMORY_POOL__TYPE="greedy", SAIL_RUNTIME__MEMORY_POOL__GREEDY__MAX_SIZE=str(30 * 2**30),
               SAIL_GRAPH_UTILS_ROOT=staging.as_uri(), TOKIO_WORKER_THREADS=str(args.workers),
               RAYON_NUM_THREADS=str(args.workers), RUST_LOG="warn")
    env.update(dict(item.split("=", 1) for item in args.server_env))
    started = time.perf_counter()
    with (out / "server.log").open("w") as log:
        server = subprocess.Popen([str(SAIL), "spark", "server", "--ip", "127.0.0.1", "--port", str(port)],
                                  env=env, cwd=out, stdout=log, stderr=subprocess.STDOUT)
    try:
        while True:
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    break
            assert server.poll() is None, "server exited"
            time.sleep(0.01)
        spark = SparkSession.builder.remote(f"sc://127.0.0.1:{port}").create()
        vertices = spark.read.parquet(V.as_uri()).select("id")
        edges = spark.read.parquet(E.as_uri()).select(F.col("source").alias("src"), F.col("target").alias("dst"))
        graph = GraphAlgorithms(spark, snapshot_inputs=not args.no_snapshot,
                                repartition_checkpoints=not args.no_repartition)
        algorithm = time.perf_counter()
        if contrast == "wcc":
            handle = graph.wcc(vertices, edges, method="randomized", seed=42, canonical_labels=True,
                               max_iterations=100, partitions=args.workers)
        elif contrast == "bfs":
            handle = graph.bfs(vertices, edges, source=args.source, method="frontier", directed=True,
                               max_iterations=1000, partitions=args.workers)
        else:
            handle = graph.pagerank(vertices, edges, method="pregel_delta", tolerance=0.01, max_iterations=10,
                                    normalize=True, partitions=args.workers)
        algorithm_seconds = time.perf_counter() - algorithm
        with handle:
            handle.write_parquet((out / "result").as_uri())
            iterations = handle.iterations
        spark.stop()
    finally:
        server.terminate(); server.wait(timeout=60)
    return time.perf_counter() - started, dict(algorithm_seconds=algorithm_seconds, iterations=iterations)

def graphframes(contrast, out):
    out.mkdir(parents=True)
    subcommand = {"wcc": "wcc", "pagerank": "page-rank", "bfs": "shortest-path"}[contrast]
    command = [str(GF), subcommand, "--vertices", str(V), "--edges", str(E),
               "--src-col-name", "source", "--dst-col-name", "target", "--output", (out / "result").as_uri() + "/",
               "--max-memory", "30G", "--num-workers", str(args.workers), "--checkpoint-dir", str(out / "gf_workdir")]
    command += {"wcc": ["--seed", "42"], "pagerank": ["--tol", "0.01", "--max-iter", "10"],
                "bfs": ["--landmarks", str(args.source)]}[contrast]
    started = time.perf_counter()
    done = subprocess.run(command, capture_output=True, text=True, cwd=out)
    seconds = time.perf_counter() - started
    assert done.returncode == 0, done.stderr[-1500:]
    (out / "engine.log").write_text(done.stdout + done.stderr)
    return seconds, {}

def oracle(contrast, ours, theirs):
    a = pq.read_table(ours / "result").to_pandas().set_index("id").sort_index()
    b = pq.read_table(theirs / "result").to_pandas().set_index("id").sort_index()
    assert len(a) == len(b) and (a.index == b.index).all(), "vertex sets differ"
    if contrast == "wcc":
        mismatches = int((a["component"] != b["component"]).sum())
        assert mismatches == 0, f"{mismatches} component labels differ"
        return dict(rows=len(a), components=int(a["component"].nunique()), label_mismatches=0)
    if contrast == "bfs":
        # Pecan: null hops when unreachable. graphframes-rs: INT32 max.
        ours = a["hops"].fillna(-1).astype("int64")
        theirs = b[f"dist_{args.source}"].astype("int64").where(b[f"dist_{args.source}"] != 2**31 - 1, -1)
        mismatches = int((ours != theirs).sum())
        assert mismatches == 0, f"{mismatches} hop distances differ"
        return dict(rows=len(a), reached=int((ours >= 0).sum()), depth=int(ours.max()), hop_mismatches=0)
    difference = (a["pagerank"] - b["pagerank"]).abs()
    assert difference.max() < 1e-12, difference.max()
    return dict(rows=len(a), max_abs_difference=float(difference.max()),
                max_relative_difference=float((difference / b["pagerank"]).max()))

shutil.rmtree(args.root, ignore_errors=True)
records = []
for contrast in args.contrasts:
    for block in range(args.blocks):
        last = {}
        for position, engine in enumerate(("graphframes", "pecan", "pecan", "graphframes")):
            out = args.root / f"{contrast}-b{block}-p{position}-{engine}"
            seconds, extra = (pecan if engine == "pecan" else graphframes)(contrast, out)
            record = dict(contrast=contrast, block=block, position=position, engine=engine, seconds=seconds, **extra)
            if engine in last or (engine == "pecan" and "graphframes" in last) or (engine == "graphframes" and "pecan" in last):
                other = "graphframes" if engine == "pecan" else "pecan"
                pair = {engine: out, other: last[other]}
                record["oracle"] = oracle(contrast, pair["pecan"], pair["graphframes"])
            last[engine] = out
            records.append(record)
            print(json.dumps(record), flush=True)
            for name in ("staging", "gf_workdir"):
                shutil.rmtree(out / name, ignore_errors=True)
args.out.write_text(json.dumps(records, indent=1))
import statistics
for contrast in args.contrasts:
    med = {e: statistics.median(r["seconds"] for r in records if r["contrast"] == contrast and r["engine"] == e)
           for e in ("pecan", "graphframes")}
    print(contrast, "medians", {k: round(v, 2) for k, v in med.items()}, "pecan over graphframes", round(med["pecan"] / med["graphframes"], 2))
