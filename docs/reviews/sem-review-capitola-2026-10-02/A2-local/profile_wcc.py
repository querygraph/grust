"""Step-level timing of Pecan randomized WCC: every staging write and every count, by round."""
import argparse, json, pathlib, time
from pyspark.sql.connect.session import SparkSession
from pyspark.sql.connect.dataframe import DataFrame
from pyspark.sql.connect import functions as F
from pyspark_pecan import GraphAlgorithms
from pyspark_pecan.staging import StagingRun

parser = argparse.ArgumentParser()
parser.add_argument("--remote", default="sc://127.0.0.1:50178")
parser.add_argument("--vertices", required=True)
parser.add_argument("--edges", required=True)
parser.add_argument("--src", default="src")
parser.add_argument("--dst", default="dst")
parser.add_argument("--partitions", type=int, default=10)
parser.add_argument("--no-repartition", action="store_true")
parser.add_argument("--no-snapshot", action="store_true")
parser.add_argument("--raw-labels", action="store_true")
parser.add_argument("--conf", action="append", default=[])
args = parser.parse_args()

spark = SparkSession.builder.remote(args.remote).create()
for item in args.conf:
    key, value = item.split("=", 1)
    spark.conf.set(key, value)
vertices = spark.read.parquet(args.vertices).select("id")
edges = spark.read.parquet(args.edges).select(F.col(args.src).alias("src"), F.col(args.dst).alias("dst"))

log = []
started = time.perf_counter()
state = {"round": 0}

def timed(kind, original):
    def wrapper(self, *a, **k):
        t = time.perf_counter()
        try:
            return original(self, *a, **k)
        finally:
            log.append((state["round"], kind, time.perf_counter() - t))
    return wrapper

StagingRun.materialize = timed("write", StagingRun.materialize)
StagingRun.remove = timed("remove", StagingRun.remove)
StagingRun.touch = timed("touch", StagingRun.touch)
DataFrame.count = timed("count", DataFrame.count)

def observer(event):
    if event.kind == "iteration_start":
        state["round"] = event.iteration
    elif event.kind == "iteration_end":
        state["round"] = -event.iteration  # work after a round's end belongs to the tail until the next start
        state.setdefault("edges", []).append((event.edges_before, event.edges_after))

graph = GraphAlgorithms(spark, observer=observer, repartition_checkpoints=not args.no_repartition,
                        snapshot_inputs=not args.no_snapshot)
t0 = time.perf_counter()
with graph.wcc(vertices, edges, method="randomized", partitions=args.partitions,
               canonical_labels=not args.raw_labels) as result:
    ready = time.perf_counter() - t0
    components = result.frame.select("component").distinct().count()
    rounds = result.iterations
total = time.perf_counter() - t0
print(f"ready {ready:.2f} s, rounds {rounds}, components {components}")
last = max(r for r, _, _ in log if r > 0)
def bucket(r):
    if r == 0: return "before round 1 (snapshot, first count)"
    if r == -last: return "after last round (back pass, labels)"
    return f"round {abs(r):2d}"
summary = {}
for r, kind, seconds in log:
    entry = summary.setdefault(bucket(r), {})
    entry.setdefault(kind, []).append(seconds)
for name, kinds in summary.items():
    parts = ", ".join(f"{kind} {len(v)}x {sum(v):.2f}s" + (f" ({', '.join(f'{x:.2f}' for x in v)})" if kind in ('write', 'count') and len(v) <= 4 else "")
                      for kind, v in kinds.items())
    print(f"{name}: {parts}")
print("edges by round:", state.get("edges"))
