"""Placeholder layouts. NOT a graph layout algorithm: only inputs with known locality for the level-table benchmark.

    python layout.py <graph>        # graph: cit-Patents | graph500-24

Writes SCRATCH/<graph>/layout-random and SCRATCH/<graph>/layout-hierarchical as Parquet (id, x, y),
and appends one JSON line per step to raw/layout-<graph>.jsonl.

random        x, y = two independent hashes of the id. Edges have no locality: the worst case for pseudo-edges.
hierarchical  Min-priority propagation over the undirected edges, priority p(v) = xxhash64(v): after r rounds
              p_r(v) is the lowest priority within r hops of v, a cluster label. Labels after r = 8, 4, 2, 1
              rounds give four nested-ish scales. Each coordinate is
                  0.5 + 0.5 (u(p_8) - 0.5) + 0.25 (u(p_4) - 0.5) + 0.125 (u(p_2) - 0.5) + 0.0625 (u(p_1) - 0.5)
                      + 0.03125 (u(v) - 0.5)
              with u() an independent hash to [0, 1) per coordinate and term. Vertices that share the 8-round
              label lie in a box of side about 0.5, those that also share the 4-round label in one of about
              0.25, and so on. So edges are short at every scale, which is what a real layout gives.
"""
import json, pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from vizserver import sail, DATA, SCRATCH, host_facts
from quadsql import unit
from pyspark.sql.connect import functions as F

graph = sys.argv[1]
out = SCRATCH / graph
out.mkdir(parents=True, exist_ok=True)
raw = pathlib.Path(__file__).parent / "raw" / f"layout-{graph}.jsonl"
SETTINGS = {"SAIL_EXECUTION__DEFAULT_PARALLELISM": "10"}
KEEP = {1: 0.0625, 2: 0.125, 4: 0.25, 8: 0.5}


def log(**record):
    print(json.dumps(record))
    with raw.open("a") as f:
        f.write(json.dumps(record) + "\n")


with sail(settings=SETTINGS) as (spark, server):
    log(step="start", graph=graph, settings=server.settings, host=host_facts())
    v = spark.read.parquet(str(DATA / graph / f"{graph}-v.parquet")).select(F.col("id").cast("bigint"))
    e = spark.read.parquet(str(DATA / graph / f"{graph}-e.parquet")).select(
        F.col("source").cast("bigint").alias("src"), F.col("target").cast("bigint").alias("dst"))
    n = v.count()

    t = time.time()
    v.select("id", unit("id", 11).alias("x"), unit("id", 12).alias("y")).write.mode("overwrite").parquet(
        str(out / "layout-random"))
    log(step="layout-random", seconds=round(time.time() - t, 3), rows=n)

    u = e.filter("src <> dst").select("src", "dst").unionByName(e.filter("src <> dst").select(
        F.col("dst").alias("src"), F.col("src").alias("dst")))
    path = out / "lp-0"
    v.select("id", F.xxhash64("id", F.lit(7)).alias("p")).write.mode("overwrite").parquet(str(path))
    for r in range(1, max(KEEP) + 1):
        t = time.time()
        cur = spark.read.parquet(str(path))
        msg = u.join(cur.select(F.col("id").alias("src"), F.col("p").alias("q")), "src").groupBy("dst").agg(
            F.min("q").alias("q"))
        nxt = cur.join(msg, cur.id == msg.dst, "left").select("id", F.least("p", F.coalesce("q", "p")).alias("p"))
        path = out / f"lp-{r}"
        nxt.write.mode("overwrite").parquet(str(path))
        stats = spark.read.parquet(str(path)).groupBy("p").count().agg(
            F.count(F.lit(1)).alias("labels"), F.max("count").alias("largest")).toPandas().iloc[0]
        log(step=f"propagation-round-{r}", seconds=round(time.time() - t, 3), labels=int(stats["labels"]),
            largest=int(stats["largest"]))

    t = time.time()
    frame = v
    for r in KEEP:
        frame = frame.join(spark.read.parquet(str(out / f"lp-{r}")).select("id", F.col("p").alias(f"p{r}")), "id")
    coord = lambda axis: F.lit(0.5) + sum(
        (F.lit(w) * (unit(f"p{r}", 100 * axis + r) - F.lit(0.5)) for r, w in KEEP.items()),
        F.lit(0.03125) * (unit("id", 100 * axis) - F.lit(0.5)))
    frame.select("id", coord(1).alias("x"), coord(2).alias("y")).write.mode("overwrite").parquet(
        str(out / "layout-hierarchical"))
    log(step="layout-hierarchical", seconds=round(time.time() - t, 3), rows=n)
