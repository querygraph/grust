"""Which inputs give the same (partition, row order) on every execution?

    python probe_determinism.py [local|local-cluster]

Each case builds a frame, adds spark_partition_id() and monotonically_increasing_id(), and writes
(key, p, m) to Parquet. The written rows are then data, so the signature below is not disturbed by
the optimizer. A case is executed several times and reports:

  distinct_partition_count_vectors   how many different per-partition row-count vectors were seen
  distinct_fingerprints              how many different (key -> m) assignments were seen
  rows_out_of_key_order              rows whose key is smaller than the key of the previous m in the
                                     same partition (0 means m follows the key order inside a partition)

The aggregate-only variant at the end shows what the optimizer does to a sort under
monotonically_increasing_id() when the consumer is an aggregate.
"""
import json, os, pathlib, shutil, sys, tempfile

from sailserver import EDGES, VERTICES, sail

mode = sys.argv[1] if len(sys.argv) > 1 else "local"
scratch = pathlib.Path(tempfile.mkdtemp(prefix="dense-ids-determinism-", dir=os.environ.get("PROBE_TMP")))


def emit(**record):
    print(json.dumps(record, default=str), flush=True)


with sail(mode, {"SAIL_EXECUTION__CHECKPOINT__PATH": (scratch / "checkpoints").as_uri()}) as (spark, server):
    from pyspark.sql import Window, functions as F
    mid, pid = F.monotonically_increasing_id(), F.spark_partition_id()
    emit(case="settings", mode=mode, settings=server.settings)
    key = ["source", "target"]

    def signature(frame):
        out = scratch / "signature"
        shutil.rmtree(out, ignore_errors=True)
        frame.select(*key, pid.alias("p"), mid.alias("m")).write.parquet(out.as_uri())
        w = spark.read.parquet(out.as_uri())
        counts = tuple(sorted((r[0], r[1]) for r in w.groupBy("p").count().collect()))
        finger = tuple(w.select(F.xxhash64(*key, "m").alias("h")).agg(
            F.bit_xor("h"), F.sum(F.col("h") % 1000003)).first())
        packed = F.col("source") * 10_000_000 + F.col("target")
        disorder = w.select("p", "m", packed.alias("k")).select(
            (F.lag("k").over(Window.partitionBy("p").orderBy("m")) > F.col("k")).cast("int").alias("bad")
        ).agg(F.sum("bad")).first()[0]
        dense = w.agg(F.count("*"), F.countDistinct("m")).first()
        return counts, finger, int(disorder or 0), tuple(dense)

    def case(name, make, executions=4):
        try:
            frame = make()
            seen = [signature(frame) for _ in range(executions)]
            emit(case=name, ok=True, executions=executions, partitions=len(seen[0][0]),
                 distinct_partition_count_vectors=len({s[0] for s in seen}),
                 distinct_fingerprints=len({s[1] for s in seen}),
                 rows_out_of_key_order=sorted({s[2] for s in seen}),
                 rows_and_distinct_m=sorted({s[3] for s in seen}))
        except Exception as e:
            emit(case=name, ok=False, error=type(e).__name__, message=str(e).strip().splitlines()[0][:400])

    e = spark.read.parquet(EDGES.as_uri())
    case("direct scan", lambda: e, executions=6)
    case("checkpoint (execution.checkpoint.path set)", lambda: e.checkpoint(), executions=6)
    rewritten = scratch / "edges-rewritten"
    e.write.parquet(rewritten.as_uri())
    emit(case="rewrite", files=len(list(rewritten.glob("*.parquet"))))
    case("scan of the directory Sail wrote", lambda: spark.read.parquet(rewritten.as_uri()), executions=6)
    case("orderBy(source, target)", lambda: e.orderBy(*key))
    case("repartition(10, source)", lambda: e.repartition(10, "source"))
    case("repartition(10, source).sortWithinPartitions(source, target)",
         lambda: e.repartition(10, "source").sortWithinPartitions(*key))

    # The same sorted frame, consumed by an aggregate instead of a write.
    sorted_frame = e.repartition(10, "source").sortWithinPartitions(*key)
    aggregate = sorted_frame.select(F.xxhash64(*key, mid).alias("h")).agg(F.bit_xor("h").alias("x"))
    aggregate.createOrReplaceTempView("aggregate_over_sorted")
    plan = spark.sql("explain select * from aggregate_over_sorted").collect()[0][-1]
    emit(case="aggregate over sortWithinPartitions + monotonically_increasing_id",
         sort_in_physical_plan="SortExec" in plan, plan=plan,
         distinct_fingerprints=len({aggregate.first()[0] for _ in range(4)}))

    # Last, because the setting stays for the session.
    for how in ("spark.conf.set", "sql SET"):
        try:
            if how == "spark.conf.set":
                spark.conf.set("datafusion.execution.enable_file_stream_work_stealing", "false")
            else:
                spark.sql("SET datafusion.execution.enable_file_stream_work_stealing = false").collect()
            case(f"direct scan after {how} datafusion.execution.enable_file_stream_work_stealing=false",
                 lambda: spark.read.parquet(EDGES.as_uri()), executions=6)
        except Exception as ex:
            emit(case=how, ok=False, error=type(ex).__name__, message=str(ex).strip().splitlines()[0][:300])

shutil.rmtree(scratch, ignore_errors=True)
