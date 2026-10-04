"""Reproduce only the bucket expression against an already running Sail endpoint.

Run with the recorded PySpark 4.0.1 environment:
  python probe_floor.py --remote sc://127.0.0.1:50051
This submits two tiny scalar queries; it does not benchmark a traversal.
"""
import argparse
import json

from pyspark.sql.connect import functions as F
from pyspark.sql.connect.session import SparkSession


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--remote", required=True)
    args = parser.parse_args()
    spark = SparkSession.builder.remote(args.remote).create()
    try:
        for name, weights, delta in [
            ("infinite_quotient", [1.0], 1e-310),
            ("finite_large_buckets", [1e20, 2e20], 1.0),
        ]:
            edges = spark.createDataFrame(
                [(0, i + 1, w) for i, w in enumerate(weights)],
                "src long, dst long, weight double",
            )
            frame = edges.select(
                "weight",
                (F.col("weight") / delta).alias("quotient"),
                F.floor(F.col("weight") / delta).alias("bucket"),
            )
            print(json.dumps({
                "name": name, "delta": delta, "schema": str(frame.schema),
                "rows": [row.asDict() for row in frame.collect()],
            }))
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
