"""Level table, pseudo-edges and "expand one cell" on Sail, local mode. Shape only: a shared laptop.

    python bench.py <graph> <layout> [--runs 3] [--lc 12] [--pe-levels 2,4,6,8,10,12] [--frontier 5,7]

Reads SCRATCH/<graph>/layout-<layout> (id, x, y) written by layout.py. Writes tables under
SCRATCH/<graph>/<layout>/ and one JSON line per measurement to raw/bench-<graph>-<layout>.jsonl.

Tables (all Parquet; "sorted" = orderBy(key) before the write, "plain" = no sort):
  vk-{plain,sorted}        id, key, x, y                      |V| rows
  ek-{plain,sorted}        src_key, dst_key, src, dst         2|E| rows, both directions, no self loops
  levels/level=l           cell, mass, sx, sy, xmin, xmax, ymin, ymax      l = 0..lc, sorted by cell
  pe-{plain,sorted}/level=l  src_cell, dst_cell, w            both directions, sorted by src_cell
"""
import argparse, json, pathlib, shutil, statistics, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from vizserver import sail, SCRATCH, DATA, host_facts
from quadsql import with_key, cell, key_range, shift, LEVEL_AGGS, ROLLUP_AGGS, LMAX
from pyspark.sql.connect import functions as F
import pyarrow.parquet as pq

ap = argparse.ArgumentParser()
ap.add_argument("graph")
ap.add_argument("layout")
ap.add_argument("--runs", type=int, default=3)
ap.add_argument("--lc", type=int, default=12)
ap.add_argument("--pe-levels", default="2,4,6,8,10,12")
ap.add_argument("--frontier", default="5,7")
ap.add_argument("--skip-build", action="store_true", help="reuse tables of a previous run")
ap.add_argument("--settings", default="", help="extra SAIL_ settings, K=V,K=V")
ap.add_argument("--tag", default="", help="suffix for the scratch directory and the raw file")
args = ap.parse_args()

root = SCRATCH / args.graph / (args.layout + args.tag)
root.mkdir(parents=True, exist_ok=True)
raw = pathlib.Path(__file__).parent / "raw" / f"bench-{args.graph}-{args.layout}{args.tag}.jsonl"
SETTINGS = {"SAIL_EXECUTION__DEFAULT_PARALLELISM": "10"}
SETTINGS.update(dict(kv.split("=", 1) for kv in args.settings.split(",") if kv))


def log(**record):
    record = {"graph": args.graph, "layout": args.layout, "tag": args.tag, **record}
    print(json.dumps(record), flush=True)
    with raw.open("a") as f:
        f.write(json.dumps(record) + "\n")


def measure(name, fn, runs=args.runs, warmup=False, **extra):
    """Run fn() `runs` times (after one untimed warm-up if asked); log median, range and fn's last result."""
    first = None
    if warmup:
        t = time.perf_counter()
        fn()
        first = round(time.perf_counter() - t, 4)
    times, result = [], None
    for _ in range(runs):
        server.reset_peak()
        t = time.perf_counter()
        result = fn()
        times.append(time.perf_counter() - t)
    log(measure=name, median=round(statistics.median(times), 4), min=round(min(times), 4),
        max=round(max(times), 4), runs=[round(x, 4) for x in times], first=first,
        peak_rss_mib=server.peak_rss_mib(), result=result, **extra)
    return result


def arrow(frame):
    """Collect as Arrow, as a service would; return rows and in-memory bytes."""
    table = frame.toArrow()
    return {"rows": table.num_rows, "arrow_bytes": table.nbytes}


def file_layout(path, column):
    """Files, row groups, and the key span of each row group as a fraction of the whole (pyarrow footer read)."""
    ranges, files = [], sorted(pathlib.Path(path).rglob("*.parquet"))
    for f in files:
        md = pq.ParquetFile(f).metadata
        index = md.schema.to_arrow_schema().get_field_index(column)
        for g in range(md.num_row_groups):
            st = md.row_group(g).column(index).statistics
            ranges.append((st.min, st.max, md.row_group(g).num_rows) if st is not None and st.has_min_max else None)
    ok = [r for r in ranges if r]
    ok.sort()
    disjoint = all(ok[i][1] < ok[i + 1][0] for i in range(len(ok) - 1))
    total = (max(r[1] for r in ok) - min(r[0] for r in ok)) or 1
    spans = sorted((r[1] - r[0]) / total for r in ok)
    return {"files": len(files), "row_groups": len(ranges), "row_group_rows_max": max((r[2] for r in ok), default=0),
            "disjoint_row_group_ranges": disjoint, "row_group_key_span_median": round(spans[len(spans) // 2], 6),
            "row_group_key_span_max": round(spans[-1], 6),
            "bytes": sum(f.stat().st_size for f in files)}


def write(frame, path, sort_col=None):
    """Write with the default save mode into a fresh directory. mode("overwrite") is avoided on purpose:
    on this binary it drops a sort placed before the write (raw/probe-sorted-write.txt)."""
    if sort_col is not None:
        frame = frame.orderBy(sort_col)
    shutil.rmtree(path, ignore_errors=True)
    frame.write.parquet(str(path))


with sail(settings=SETTINGS) as (spark, server):
    log(measure="start", settings=server.settings, host=host_facts(), args=vars(args), lmax=LMAX)
    read = lambda p: spark.read.parquet(str(p))
    lay = read(SCRATCH / args.graph / f"layout-{args.layout}")
    edges = read(DATA / args.graph / f"{args.graph}-e.parquet").select(
        F.col("source").cast("bigint").alias("src"), F.col("target").cast("bigint").alias("dst"))

    measure("trivial-query", lambda: arrow(spark.range(1)), warmup=True)

    # ---- 1. vertex keys -------------------------------------------------------------------
    def bbox():
        b = lay.agg(F.min("x"), F.max("x"), F.min("y"), F.max("y")).toPandas().iloc[0].tolist()
        side = max(b[1] - b[0], b[3] - b[2]) * (1 + 1e-9)
        return b[0], b[2], side
    if not args.skip_build:
        box = measure("bbox", lambda: list(bbox()))
        vk = with_key(lay, *box).select("id", "key", "x", "y")
        measure("build-vk-plain", lambda: write(vk, root / "vk-plain"))
        measure("build-vk-sorted", lambda: write(vk, root / "vk-sorted", "key"))
        log(measure="layout-vk-sorted", result=file_layout(root / "vk-sorted", "key"))
        log(measure="layout-vk-plain", result=file_layout(root / "vk-plain", "key"))

        # ---- 2. edge keys: one join per endpoint ------------------------------------------
        def ek_frame():
            vks = read(root / "vk-plain").select("id", "key")
            e = edges.filter("src <> dst")
            e = e.join(vks.select(F.col("id").alias("src"), F.col("key").alias("src_key")), "src") \
                 .join(vks.select(F.col("id").alias("dst"), F.col("key").alias("dst_key")), "dst")
            back = e.select(F.col("dst_key").alias("src_key"), F.col("src_key").alias("dst_key"),
                            F.col("dst").alias("src"), F.col("src").alias("dst"))
            return e.select("src_key", "dst_key", "src", "dst").unionByName(back)
        measure("build-ek-plain", lambda: write(ek_frame(), root / "ek-plain"))
        measure("build-ek-sorted", lambda: write(ek_frame(), root / "ek-sorted", "src_key"))
        log(measure="layout-ek-sorted", result=file_layout(root / "ek-sorted", "src_key"))

        # ---- 3. level table: finest level from the vertices, coarser levels rolled up --------
        def build_levels():
            vks = read(root / "vk-plain")
            write(vks.groupBy(cell("key", args.lc).alias("cell")).agg(*LEVEL_AGGS), root / f"levels/level={args.lc}", "cell")
            for l in range(args.lc - 1, -1, -1):
                below = read(root / f"levels/level={l + 1}")
                write(below.groupBy(F.shiftright("cell", 2).alias("cell")).agg(*ROLLUP_AGGS), root / f"levels/level={l}", "cell")
        measure("build-levels-all", build_levels, levels=args.lc + 1)

    rows = {}
    for l in range(args.lc + 1):
        lv = read(root / f"levels/level={l}")
        rows[l] = lv.agg(F.count(F.lit(1)).alias("n"), F.max("mass").alias("m")).toPandas().iloc[0].tolist()
    log(measure="levels-rows", result={l: {"cells": int(r[0]), "max_mass": int(r[1])} for l, r in rows.items()})
    # Size of the adaptive tree: cells whose parent holds more than T vertices (the root always counts).
    adaptive = {}
    for T in (1_000, 10_000, 100_000):
        total = 1
        for l in range(1, args.lc + 1):
            parents = read(root / f"levels/level={l - 1}").filter(F.col("mass") > T).select(F.col("cell").alias("p"))
            total += read(root / f"levels/level={l}").join(parents, F.shiftright("cell", 2) == F.col("p")).count()
        adaptive[T] = total
    log(measure="adaptive-tree-cells", result=adaptive, note="cells (levels 0..lc) whose parent mass > T")

    # One level on demand: one GROUP BY over the vertex keys.
    for l in (6, 8):
        measure(f"level-on-demand-{l}", lambda l=l: arrow(read(root / "vk-plain").groupBy(cell("key", l).alias("cell")).agg(*LEVEL_AGGS)))

    # ---- 4. pseudo-edges ----------------------------------------------------------------
    pe_levels = [int(x) for x in args.pe_levels.split(",")]
    if not args.skip_build:
        for l in pe_levels:
            def pe(l=l):
                ek = read(root / "ek-plain")
                frame = ek.groupBy(cell("src_key", l).alias("src_cell"), cell("dst_key", l).alias("dst_cell")).agg(
                    F.count(F.lit(1)).alias("w"))
                write(frame, root / f"pe-sorted/level={l}", "src_cell")
                return read(root / f"pe-sorted/level={l}").count()
            measure(f"pe-direct-{l}", pe)
        # The same levels from raw edges and the vertex keys, joins included, at one level.
        l = pe_levels[len(pe_levels) // 2]
        def pe_joins(l=l):
            vks = read(root / "vk-plain").select("id", "key")
            e = edges.filter("src <> dst").join(vks.select(F.col("id").alias("src"), F.col("key").alias("sk")), "src") \
                     .join(vks.select(F.col("id").alias("dst"), F.col("key").alias("dk")), "dst")
            a = e.select(cell("sk", l).alias("s"), cell("dk", l).alias("d"))
            b = a.select(F.col("d").alias("s"), F.col("s").alias("d"))
            return arrow(a.unionByName(b).groupBy("s", "d").agg(F.count(F.lit(1)).alias("w")).agg(F.count(F.lit(1))))
        measure(f"pe-from-raw-edges-{l}", pe_joins)
        # All levels by rollup from the finest one.
        def pe_rollup():
            top = max(pe_levels)
            for l in range(top - 1, -1, -1):
                below = read(root / (f"pe-sorted/level={top}" if l == top - 1 else f"pe-rollup/level={l + 1}"))
                frame = below.groupBy(F.shiftright("src_cell", 2).alias("src_cell"),
                                      F.shiftright("dst_cell", 2).alias("dst_cell")).agg(F.sum("w").alias("w"))
                write(frame, root / f"pe-rollup/level={l}", "src_cell")
        measure("pe-rollup-all-levels", pe_rollup, levels=max(pe_levels))
        for l in pe_levels:   # "plain": the same rows scrambled by a hash, so no row group is narrow
            write(read(root / f"pe-sorted/level={l}"), root / f"pe-plain/level={l}", F.xxhash64("src_cell", "dst_cell"))
    pe_rows = {l: read(root / f"pe-sorted/level={l}").count() for l in pe_levels}
    log(measure="pe-rows", result=pe_rows)

    # ---- 5. interaction queries -----------------------------------------------------------
    for lf in [int(x) for x in args.frontier.split(",")]:
        lc1 = lf + 1
        if not (root / f"pe-sorted/level={lc1}").exists():
            write(read(root / f"pe-rollup/level={lc1}"), root / f"pe-sorted/level={lc1}")  # already sorted by src_cell
            write(read(root / f"pe-rollup/level={lc1}"), root / f"pe-plain/level={lc1}", F.xxhash64("src_cell", "dst_cell"))
        if not (root / f"pe-sorted/level={lf}").exists():
            write(read(root / f"pe-rollup/level={lf}"), root / f"pe-sorted/level={lf}")
        cells = read(root / f"levels/level={lf}").select("cell", "mass").toPandas().sort_values("mass")
        picks = {"heaviest": int(cells.iloc[-1]["cell"]), "median": int(cells.iloc[len(cells) // 2]["cell"])}
        log(measure=f"frontier-{lf}", result={"cells": len(cells), **{k: {"cell": c, "mass": int(cells.set_index("cell").loc[c, "mass"])} for k, c in picks.items()}})

        n_pe = read(root / f"pe-sorted/level={lf}").count()
        if n_pe <= 10_000_000:
            measure(f"initial-view-{lf}", lambda: {"cells": arrow(read(root / f"levels/level={lf}")),
                                                   "pseudo_edges": arrow(read(root / f"pe-sorted/level={lf}"))}, warmup=True)
        else:
            log(measure=f"initial-view-{lf}", skipped=f"{n_pe} pseudo-edges, more than a client should take")
        for which, c in picks.items():
            lo, hi = key_range(c, lf)
            kids = (4 * c, 4 * c + 3)
            tag = f"f{lf}-{which}"

            measure(f"children-precomputed-{tag}", lambda: arrow(read(root / f"levels/level={lc1}").filter(
                F.col("cell").between(*kids))), warmup=True)
            for order in ("sorted", "plain"):
                measure(f"children-on-demand-{order}-{tag}", lambda order=order: arrow(
                    read(root / f"vk-{order}").filter((F.col("key") >= lo) & (F.col("key") < hi))
                    .groupBy(cell("key", lc1).alias("cell")).agg(*LEVEL_AGGS)), warmup=True)

            def frontier_dst(col):
                """Map a level-(lf+1) cell to the visible frontier: itself inside c, its level-lf parent outside."""
                inside = F.shiftright(col, 2) == F.lit(c)
                return (F.when(inside, F.lit(lc1)).otherwise(F.lit(lf)).alias("dst_level"),
                        F.when(inside, col).otherwise(F.shiftright(col, 2)).alias("dst_cell"))
            for order in ("sorted", "plain"):
                def pre(order=order):
                    p = read(root / f"pe-{order}/level={lc1}").filter(F.col("src_cell").between(*kids))
                    return arrow(p.groupBy("src_cell", *frontier_dst(F.col("dst_cell"))).agg(F.sum("w").alias("w")))
                measure(f"expand-pe-precomputed-{order}-{tag}", pre, warmup=True)
                def ondemand(order=order):
                    ek = read(root / f"ek-{order}").filter((F.col("src_key") >= lo) & (F.col("src_key") < hi))
                    ek = ek.select(cell("src_key", lc1).alias("src_cell"), cell("dst_key", lc1).alias("d"))
                    return arrow(ek.groupBy("src_cell", *frontier_dst(F.col("d"))).agg(F.count(F.lit(1)).alias("w")))
                measure(f"expand-pe-on-demand-{order}-{tag}", ondemand, warmup=True)

    # Real nodes: the cell nearest to 10,000 vertices among levels >= 4; its vertices and their edges.
    best = None
    for l in range(4, args.lc + 1):
        cand = read(root / f"levels/level={l}").withColumn("d", F.abs(F.col("mass") - F.lit(10_000))).orderBy("d").limit(1).toPandas()
        if best is None or cand.iloc[0]["d"] < best[2]:
            best = (l, int(cand.iloc[0]["cell"]), float(cand.iloc[0]["d"]), int(cand.iloc[0]["mass"]))
    l, c, _, mass = best
    lo, hi = key_range(c, l)
    log(measure="leaf-cell", result={"level": l, "cell": c, "mass": mass})
    for order in ("sorted", "plain"):
        measure(f"leaf-vertices-{order}", lambda order=order: arrow(
            read(root / f"vk-{order}").filter((F.col("key") >= lo) & (F.col("key") < hi)).select("id", "x", "y", "key")), warmup=True)
        measure(f"leaf-edges-{order}", lambda order=order: arrow(
            read(root / f"ek-{order}").filter((F.col("src_key") >= lo) & (F.col("src_key") < hi))), warmup=True)

    # Pruning evidence: EXPLAIN ANALYZE of the on-demand expand over sorted and plain edge tables.
    lf = int(args.frontier.split(",")[0])
    c = int(read(root / f"levels/level={lf}").orderBy(F.desc("mass")).limit(1).toPandas().iloc[0]["cell"])
    lo, hi = key_range(c, lf)
    for order in ("sorted", "plain"):
        q = read(root / f"ek-{order}").filter((F.col("src_key") >= lo) & (F.col("src_key") < hi)).groupBy(
            cell("src_key", lf + 1).alias("s")).count()
        q.createOrReplaceTempView("q")
        text = "\n".join(r[0] if len(r) == 1 else " | ".join(map(str, r)) for r in spark.sql("EXPLAIN ANALYZE SELECT * FROM q").collect())
        (pathlib.Path(__file__).parent / "raw" / f"explain-analyze-{args.graph}-{args.layout}{args.tag}-ek-{order}.txt").write_text(text)
    log(measure="done")
