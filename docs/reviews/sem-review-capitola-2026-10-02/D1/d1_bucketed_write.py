"""D1: the bucketed write a declared layout needs, plain and sorted. Run after d1_write_cost.py (same --root)."""
import json, pathlib, shutil, sys, time
from pyspark.sql.connect.session import SparkSession
from pyspark.sql.connect import functions as F

root = pathlib.Path(sys.argv[1]).resolve()
spark = SparkSession.builder.remote("sc://127.0.0.1:50178").create()
P = 10
records = []
for rows in (16_000_000, 64_000_000, 268_000_000):
    for shape, key in (("state", "id"), ("edges", "src")):
        frame = spark.read.parquet((root / f"source-{shape}-{rows}").as_uri())
        bucketed = frame.withColumn("bucket", F.pmod(F.xxhash64(key), F.lit(P)).cast("int"))
        modes = {
            "partitionBy(bucket)": lambda: bucketed.write.partitionBy("bucket"),
            "partitionBy(bucket), sorted by key": lambda: bucketed.repartition(P, "bucket").sortWithinPartitions(key).write.partitionBy("bucket"),
        }
        for repeat in range(2):
            for mode, make in modes.items():
                target = root / "out"
                shutil.rmtree(target, ignore_errors=True)
                started = time.perf_counter()
                make().parquet(target.as_uri())
                seconds = time.perf_counter() - started
                files = list(target.rglob("*.parquet"))
                records.append(dict(rows=rows, shape=shape, mode=mode, repeat=repeat, seconds=seconds, files=len(files),
                                    directories=len({f.parent.name for f in files}), bytes=sum(f.stat().st_size for f in files)))
                print(json.dumps(records[-1]), flush=True)
        shutil.rmtree(root / "out", ignore_errors=True)
pathlib.Path("d1-bucketed-write.json").write_text(json.dumps(records, indent=1))
