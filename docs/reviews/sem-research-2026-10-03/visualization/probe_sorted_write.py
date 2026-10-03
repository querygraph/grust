"""Does a sort before a Parquet write reach the files? Writes the same 3.77M-row frame several ways and
checks each file with pyarrow. Output: raw/probe-sorted-write.txt."""
import glob, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import numpy as np, pyarrow.parquet as pq
from vizserver import sail, SCRATCH, host_facts
from pyspark.sql.connect import functions as F

out = SCRATCH / "probe-sorted-write"
lines = []
def report(label, path, col="k"):
    files = sorted(glob.glob(f"{path}/*.parquet"))
    stats = []
    for f in files:
        a = pq.read_table(f, columns=[col])[col].to_numpy()
        stats.append("sorted" if (np.diff(a) >= 0).all() else f"{(np.diff(a) >= 0).mean():.3f} nondecreasing")
    lines.append(f"{label}: {len(files)} files: {', '.join(stats)}")
    print(lines[-1], flush=True)

with sail(settings={"SAIL_EXECUTION__DEFAULT_PARALLELISM": "10"}) as (spark, server):
    lines.append(str(host_facts()))
    base = spark.range(3_774_768).select(F.col("id"), F.xxhash64("id").alias("k"))
    cases = {
        "orderBy(k) write overwrite": lambda p: base.orderBy("k").write.mode("overwrite").parquet(p),
        "orderBy(k) write default mode": lambda p: base.orderBy("k").write.parquet(p),
        "repartition(10,k).sortWithinPartitions(k) write": lambda p: base.repartition(10, "k").sortWithinPartitions("k").write.mode("overwrite").parquet(p),
        "orderBy(k) from a parquet scan": None,
    }
    src = str(out / "src")
    base.write.mode("overwrite").parquet(src)
    cases["orderBy(k) from a parquet scan"] = lambda p: spark.read.parquet(src).orderBy("k").write.mode("overwrite").parquet(p)
    cases["orderBy(k) from a parquet scan, coalesce(1)"] = lambda p: spark.read.parquet(src).orderBy("k").coalesce(1).write.mode("overwrite").parquet(p)
    for i, (label, make) in enumerate(cases.items()):
        p = str(out / f"case{i}")
        make(p)
        report(label, p)
    plan = spark.read.parquet(src).orderBy("k")._explain_string() if hasattr(spark.read.parquet(src), "_explain_string") else ""
    lines.append("plan of the orderBy(k) frame (not the write):\n" + plan)
(pathlib.Path(__file__).parent / "raw" / "probe-sorted-write.txt").write_text("\n".join(lines) + "\n")
