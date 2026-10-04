"""D1: what a hash-partitioned, key-sorted Parquet write costs on Sail against the plain and
round-robin writes Pecan does today. One process, local mode; paired order per size."""
import argparse, json, pathlib, shutil, time
from pyspark.sql.connect.session import SparkSession
from pyspark.sql.connect import functions as F

parser = argparse.ArgumentParser()
parser.add_argument("--remote", default="sc://127.0.0.1:50178")
parser.add_argument("--root", type=pathlib.Path, required=True)
parser.add_argument("--rows", type=int, nargs="+", default=[16_000_000, 64_000_000, 268_000_000])
parser.add_argument("--partitions", type=int, default=10)
parser.add_argument("--blocks", type=int, default=2)
parser.add_argument("--out", type=pathlib.Path, required=True)
args = parser.parse_args()
spark = SparkSession.builder.remote(args.remote).create()
args.root.mkdir(parents=True, exist_ok=True)

def size_of(path):
    files = [f for f in path.rglob("*.parquet")]
    return len(files), sum(f.stat().st_size for f in files)

MODES = {
    "plain": lambda frame, key: frame,
    "round_robin": lambda frame, key: frame.repartition(args.partitions),
    "hash": lambda frame, key: frame.repartition(args.partitions, key),
    "hash_sorted": lambda frame, key: frame.repartition(args.partitions, key).sortWithinPartitions(key),
}
SHAPES = {
    # A vertex state: a unique-looking key and one value.
    "state": (lambda n: spark.range(n).select(
        F.xxhash64("id").alias("id"), F.xxhash64("id", F.lit(1)).cast("double").alias("value")), "id"),
    # An edge table: n/16 vertices, average degree 16, keyed by src.
    "edges": (lambda n: spark.range(n).select(
        F.xxhash64(F.pmod(F.xxhash64("id", F.lit(2)), F.lit(n // 16))).alias("src"),
        F.xxhash64(F.pmod(F.xxhash64("id", F.lit(3)), F.lit(n // 16))).alias("dst")), "src"),
}
results = []
for rows in args.rows:
    for shape, (make, key) in SHAPES.items():
        source = args.root / f"source-{shape}-{rows}"
        if not source.exists():
            make(rows).write.parquet(source.as_uri())
        frame = spark.read.parquet(source.as_uri())
        assert frame.count() == rows
        order = list(MODES) + list(reversed(MODES))
        for block in range(args.blocks):
            for mode in order:
                target = args.root / "out"
                shutil.rmtree(target, ignore_errors=True)
                started = time.perf_counter()
                MODES[mode](frame, key).write.parquet(target.as_uri())
                seconds = time.perf_counter() - started
                files, size = size_of(target)
                record = dict(rows=rows, shape=shape, mode=mode, block=block, seconds=seconds, files=files, bytes=size)
                results.append(record)
                print(json.dumps(record), flush=True)
        shutil.rmtree(args.root / "out", ignore_errors=True)
args.out.write_text(json.dumps(results, indent=1))
