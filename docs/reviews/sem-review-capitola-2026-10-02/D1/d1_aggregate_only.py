"""D1: the part of a round no join layout removes: scan E, sum a per-edge value by dst, write."""
import json, pathlib, shutil, sys, time
from pyspark.sql.connect.session import SparkSession
from pyspark.sql.connect import functions as F

root = pathlib.Path(sys.argv[1]).resolve()
spark = SparkSession.builder.remote("sc://127.0.0.1:50178").create()
records = []
for rows in (16_000_000, 64_000_000, 268_000_000):
    edges = spark.read.parquet((root / f"source-edges-{rows}").as_uri())
    step = edges.select(edges.dst.alias("id"), edges.src.cast("double").alias("message")
                        ).groupBy("id").agg(F.sum("message").alias("incoming"))
    for repeat in range(3):
        target = root / "round-out"
        shutil.rmtree(target, ignore_errors=True)
        started = time.perf_counter()
        step.write.parquet(target.as_uri())
        records.append(dict(edges=rows, plan="aggregate only, no join", repeat=repeat, seconds=time.perf_counter() - started))
        print(json.dumps(records[-1]), flush=True)
    shutil.rmtree(root / "round-out", ignore_errors=True)
pathlib.Path("d1-aggregate-only.json").write_text(json.dumps(records, indent=1))
