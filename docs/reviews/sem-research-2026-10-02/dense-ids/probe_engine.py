"""What Sail gives today for row indexing: each probe prints one JSON record.

    python probe_engine.py [local|local-cluster]

Probes: which calls exist (row_number, monotonically_increasing_id, spark_partition_id, file_row_index,
input_file_name, _metadata, df.rdd, mapInArrow, mapInPandas, repartitionByRange, approxQuantile,
persist, checkpoint), the physical plans, and whether a direct Parquet scan gives the same
(partition, row order) on every execution.
"""
import json, sys, time, traceback

from sailserver import EDGES, VERTICES, host_facts, sail

mode = sys.argv[1] if len(sys.argv) > 1 else "local"


def emit(**record):
    print(json.dumps(record, default=str), flush=True)


def attempt(name, fn):
    started = time.perf_counter()
    try:
        value = fn()
        emit(probe=name, ok=True, seconds=round(time.perf_counter() - started, 3), value=value)
        return value
    except Exception as e:  # the error text is the finding
        text = str(e).strip().splitlines()
        emit(probe=name, ok=False, seconds=round(time.perf_counter() - started, 3),
             error=type(e).__name__, message=" | ".join(text[:3])[:600])
        return None


with sail(mode) as (spark, server):
    from pyspark.sql import Window, functions as F
    emit(probe="host", mode=mode, settings=server.settings, **host_facts())
    v = spark.read.parquet(VERTICES.as_uri())
    e = spark.read.parquet(EDGES.as_uri())
    n = v.count()
    emit(probe="input", vertices=n, distinct_ids=v.select("id").distinct().count(), edges=e.count(),
         id_min_max=v.agg(F.min("id"), F.max("id")).first())

    mid = F.monotonically_increasing_id()
    pid = F.spark_partition_id()

    def plan(name, frame):
        frame.createOrReplaceTempView("probe_view")
        rows = spark.sql("explain select * from probe_view").collect()
        emit(probe="plan: " + name, plan=[r[-1] for r in rows])

    # 1. What exists.
    attempt("row_number over (order by id)", lambda: v.select(
        "id", (F.row_number().over(Window.orderBy("id")) - 1).alias("dense")).agg(
        F.count("*"), F.min("dense"), F.max("dense")).first())
    attempt("monotonically_increasing_id", lambda: v.select(mid.alias("m")).agg(
        F.count("*"), F.min("m"), F.max("m"), F.countDistinct(F.shiftright("m", 33))).first())
    attempt("spark_partition_id as a grouping expression", lambda: sorted(
        (r[0], r[1]) for r in v.groupBy(pid.alias("p")).count().collect()))
    attempt("spark_partition_id in a projection, then group", lambda: sorted(
        (r[0], r[1]) for r in v.select(pid.alias("p")).groupBy("p").count().collect()))
    attempt("row_number result type", lambda: v.select(
        F.row_number().over(Window.orderBy("id")).alias("r"),
        F.count(F.lit(1)).over(Window.orderBy("id").rowsBetween(Window.unboundedPreceding, 0)).alias("c"),
    ).dtypes)
    attempt("file_row_index() via call_function", lambda: v.select(
        F.call_function("file_row_index").alias("r")).agg(F.min("r"), F.max("r")).first())
    attempt("file_row_index() via SQL", lambda: spark.sql(
        f"select min(file_row_index()), max(file_row_index()) from parquet.`{VERTICES}`").first())
    attempt("input_file_name()", lambda: v.select(F.input_file_name().alias("f")).distinct().count())
    attempt("_metadata.row_index", lambda: v.select("_metadata.row_index").agg(F.max("row_index")).first())
    attempt("_metadata.file_path", lambda: v.select("_metadata.file_path").distinct().count())
    attempt("df.rdd.zipWithIndex", lambda: v.rdd.zipWithIndex().take(1))

    def map_in_arrow():
        def index(batches):
            import pyarrow as pa
            seen = 0
            for batch in batches:
                yield pa.RecordBatch.from_arrays(
                    [batch.column(0), pa.array(range(seen, seen + batch.num_rows), pa.int64())], ["id", "local"])
                seen += batch.num_rows
        out = v.mapInArrow(index, "id long, local long")
        return out.agg(F.count("*"), F.max("local")).first()
    attempt("mapInArrow running index", map_in_arrow)

    def map_in_pandas():
        def index(frames):
            seen = 0
            for frame in frames:
                frame["local"] = range(seen, seen + len(frame))
                seen += len(frame)
                yield frame
        return v.mapInPandas(index, "id long, local long").agg(F.count("*"), F.max("local")).first()
    attempt("mapInPandas running index", map_in_pandas)

    attempt("repartitionByRange(4, id) partition bounds", lambda: [
        tuple(r) for r in v.repartitionByRange(4, "id").select("id", pid.alias("p")).groupBy("p").agg(
            F.count("*"), F.min("id"), F.max("id")).orderBy("p").collect()])
    attempt("plan repartitionByRange", lambda: plan("repartitionByRange(4, id)", v.repartitionByRange(4, "id")))
    attempt("approxQuantile", lambda: v.approxQuantile("id", [0.25, 0.5, 0.75], 0.001))
    attempt("percentile_approx aggregate", lambda: v.agg(
        F.percentile_approx("id", [0.25, 0.5, 0.75], 10000)).first()[0])
    attempt("persist then two counts (is it a no-op?)", lambda: (v.persist().count(), v.count()))
    attempt("checkpoint without execution.checkpoint.path", lambda: v.checkpoint().count())
    attempt("localCheckpoint", lambda: v.localCheckpoint().count())
    attempt("range(n) with monotonically_increasing_id", lambda: spark.range(n).select(
        mid.alias("m")).agg(F.countDistinct(F.shiftright("m", 33)), F.max("m")).first())

    # 2. Plans.
    attempt("plan row_number", lambda: plan("row_number over (order by id)", v.select(
        "id", (F.row_number().over(Window.orderBy("id")) - 1).alias("dense"))))
    attempt("plan monotonic", lambda: plan("spark_partition_id + monotonically_increasing_id", v.select(
        "id", pid.alias("p"), mid.alias("m"))))
    attempt("plan bucketed row_number", lambda: plan("row_number over (partition by bucket order by id)", v.select(
        "id", (F.col("id") % 16).alias("b")).select(
        "id", "b", F.row_number().over(Window.partitionBy("b").orderBy("id")).alias("r"))))

    # 3. Is a direct Parquet scan the same on every execution?
    def scan_signature(frame, key):
        """Per-partition row counts, and a fingerprint of (key, monotonic id) over all rows."""
        counts = tuple(sorted((r[0], r[1]) for r in frame.select(pid.alias("p")).groupBy("p").count().collect()))
        finger = frame.select(F.xxhash64(*key, mid).alias("h")).agg(
            F.bit_xor("h"), F.sum(F.col("h") % 1000003)).first()
        return counts, tuple(finger)

    for name, frame, key in (("vertices", v, ["id"]), ("edges", e, ["source", "target"])):
        signatures = [scan_signature(frame, key) for _ in range(6)]
        emit(probe=f"scan determinism: {name}", executions=len(signatures),
             partitions=len(signatures[0][0]),
             distinct_partition_count_vectors=len({s[0] for s in signatures}),
             distinct_key_to_monotonic_id_fingerprints=len({s[1] for s in signatures}),
             partition_counts_first=signatures[0][0], partition_counts_other=next(
                 (s[0] for s in signatures if s[0] != signatures[0][0]), None))
