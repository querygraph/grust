"""D1, second half: what one relational round over E costs today on Sail, to set beside the write costs.
A round here is a Pregel-style step: join the vertex state to the edges on src, sum a message by dst, write."""
import argparse, json, pathlib, shutil, time
from pyspark.sql.connect.session import SparkSession
from pyspark.sql.connect import functions as F

parser = argparse.ArgumentParser()
parser.add_argument("--root", type=pathlib.Path, required=True)
parser.add_argument("--rows", type=int, nargs="+", default=[16_000_000, 64_000_000, 268_000_000])
parser.add_argument("--repeats", type=int, default=3)
parser.add_argument("--out", type=pathlib.Path, required=True)
args = parser.parse_args()
REMOTES = {"hash join": "sc://127.0.0.1:50178", "sort-merge preferred": "sc://127.0.0.1:50179"}
sessions = {name: SparkSession.builder.remote(remote).create() for name, remote in REMOTES.items()}
results = []
for rows in args.rows:
    vertices = rows // 16
    state_path = args.root / f"round-state-{vertices}"
    if not state_path.exists():
        first = next(iter(sessions.values()))
        first.range(vertices).select(F.xxhash64("id").alias("id"),
                                     F.xxhash64("id", F.lit(1)).cast("double").alias("value")
                                     ).write.parquet(state_path.as_uri())
    for repeat in range(args.repeats):
        for name in (list(sessions) if repeat % 2 == 0 else list(reversed(sessions))):
            spark = sessions[name]
            edges = spark.read.parquet((args.root / f"source-edges-{rows}").as_uri())
            state = spark.read.parquet(state_path.as_uri())
            step = edges.join(state, edges.src == state.id).select(
                edges.dst.alias("id"), state.value.alias("message")).groupBy("id").agg(F.sum("message").alias("incoming"))
            target = args.root / "round-out"
            shutil.rmtree(target, ignore_errors=True)
            started = time.perf_counter()
            step.write.parquet(target.as_uri())
            seconds = time.perf_counter() - started
            written = spark.read.parquet(target.as_uri()).count()
            record = dict(edges=rows, vertices=vertices, plan=name, repeat=repeat, seconds=seconds, rows_written=written)
            if repeat == 0:
                plan = step._explain_string(extended=True).split("== Physical Plan ==")[-1]
                record["join"] = next((line.strip().split(":")[0] for line in plan.splitlines() if "Join" in line), None)
            results.append(record)
            print(json.dumps(record), flush=True)
    shutil.rmtree(args.root / "round-out", ignore_errors=True)
args.out.write_text(json.dumps(results, indent=1))
