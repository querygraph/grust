"""Dense ids on Sail: options (a), (b), (e) for the vertices and the edge mapping + sort of item 4.

    python bench_dense_ids.py [local|local-cluster] [runs]

Every case does its whole job, ending in a Parquet write, and is timed from the first request to the
end of the write. The written files are then checked outside the engine with PyArrow and NumPy:

  dense_is_0_to_n_minus_1   sorted(dense) == arange(n): no gap, no duplicate
  ids_match_input           the set of origin ids equals the input's
  dense_follows_id_order    origin ids, taken in dense order, are strictly increasing
  files_sorted              concatenating the files in name order gives rows already sorted by dense
  each_file_sorted          every single file is sorted by dense
  fingerprint               BLAKE2 of the origin ids taken in dense order (equal across runs = same mapping)

One JSON record per run on stdout. Plans go to plans-<mode>.txt.
"""
import hashlib, json, os, pathlib, shutil, statistics, sys, tempfile, time

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from sailserver import EDGES, VERTICES, bucket_of, host_facts, sail

mode = sys.argv[1] if len(sys.argv) > 1 else "local"
RUNS = int(sys.argv[2]) if len(sys.argv) > 2 else 3
here = pathlib.Path(__file__).resolve().parent
scratch = pathlib.Path(tempfile.mkdtemp(prefix="dense-ids-bench-", dir=os.environ.get("PROBE_TMP")))
MASK33 = (1 << 33) - 1
BUCKETS = 64


def emit(**record):
    print(json.dumps(record, default=str), flush=True)


def read_columns(directory, columns):
    files = sorted(pathlib.Path(directory).glob("*.parquet"))
    tables = [pq.read_table(f, columns=columns) for f in files]
    return [np.concatenate([t.column(c).to_numpy() for t in tables]) for c in columns], [t.num_rows for t in tables]


def each_sorted(values, rows, second=None):
    """Is every file sorted on its own? rows: the row count of each file, in name order."""
    start, ok = 0, True
    for count in rows:
        a = values[start:start + count]
        if second is None:
            ok = ok and bool((np.diff(a) >= 0).all())
        else:
            b = second[start:start + count]
            ok = ok and bool(((np.diff(a) > 0) | ((np.diff(a) == 0) & (np.diff(b) >= 0))).all())
        start += count
    return ok


truth_ids = np.sort(pq.read_table(VERTICES, columns=["id"]).column("id").to_numpy())
N = len(truth_ids)
edge_table = pq.read_table(EDGES)
M = edge_table.num_rows


def check_mapping(directory, expected_ids):
    (ids, dense), rows = read_columns(directory, ["id", "dense"])
    n = len(expected_ids)
    order = np.argsort(dense, kind="stable")
    ids_by_dense = ids[order]
    is_dense = len(dense) == n and bool((dense[order] == np.arange(n, dtype=np.int64)).all())
    return dict(
        rows=len(dense), files=len(rows), dense_min=int(dense.min()), dense_max=int(dense.max()),
        duplicates=int(len(dense) - len(np.unique(dense))),
        dense_is_0_to_n_minus_1=is_dense,
        ids_match_input=len(ids) == n and bool((np.sort(ids) == expected_ids).all()),
        dense_follows_id_order=bool((np.diff(ids_by_dense) > 0).all()),
        files_sorted=bool((np.diff(dense) >= 0).all()),
        each_file_sorted=each_sorted(dense, rows),
        dense_type=str(pq.read_schema(sorted(pathlib.Path(directory).glob("*.parquet"))[0]).field("dense").type),
        fingerprint=hashlib.blake2b(np.ascontiguousarray(ids_by_dense).tobytes(), digest_size=8).hexdigest())


with sail(mode, {"SAIL_EXECUTION__CHECKPOINT__PATH": (scratch / "checkpoints").as_uri()}) as (spark, server):
    from pyspark.sql import Window, functions as F
    mid, pid = F.monotonically_increasing_id(), F.spark_partition_id()
    emit(record="host", mode=mode, runs=RUNS, settings=server.settings, vertices=N, edges=M, buckets=BUCKETS,
         note="shared laptop; another agent may run a small Sail server at the same time", **host_facts())
    plans = open(here / "raw" / f"plans-{mode}.txt", "w")

    def save_plan(name, frame):
        frame.createOrReplaceTempView("plan_view")
        text = spark.sql("explain select * from plan_view").collect()[0][-1]
        plans.write(f"### {name}\n{text}\n\n")
        plans.flush()

    def vertices():
        return spark.read.parquet(VERTICES.as_uri())

    def edges():
        return spark.read.parquet(EDGES.as_uri())

    def offsets_of(counts):
        """counts: {partition: rows}. Prefix sums in partition order, as a list indexed by partition."""
        size = max(counts) + 1
        out, total = [0] * size, 0
        for p in range(size):
            out[p] = total
            total += counts.get(p, 0)
        return out

    def lookup(values, index):
        return F.get(F.array(*[F.lit(int(x)).cast("long") for x in values]), index)

    # ---- (a) row_number over a global order ----------------------------------------------------
    def a_row_number(out):
        frame = vertices().select("id", (F.row_number().over(Window.orderBy("id")) - 1).cast("long").alias("dense"))
        save_plan("a_row_number", frame)
        frame.write.parquet(out.as_uri())
        return {}

    # ---- (a') one stream, numbered as it passes: what works today without a window over a sort key ----
    def a_coalesce1_monotonic_id(out):
        """One partition, so monotonically_increasing_id() is 0..n-1 (below 2^33 rows). Arrival order."""
        frame = vertices().coalesce(1).select("id", mid.alias("dense"))
        save_plan("a_coalesce1_monotonic_id", frame)
        frame.write.parquet(out.as_uri())
        return {}

    def a_orderby_monotonic_id(out):
        """A global sort ends in one partition; the id then follows the sort order and is BIGINT."""
        frame = vertices().orderBy("id").select("id", mid.alias("dense"))
        save_plan("a_orderby_monotonic_id", frame)
        frame.write.parquet(out.as_uri())
        return {}

    def a_running_count_bigint(out):
        """The same window as row_number, as a BIGINT running count (row_number is INT in Spark and in Sail)."""
        running = F.count(F.lit(1)).over(Window.orderBy("id").rowsBetween(Window.unboundedPreceding, 0))
        frame = vertices().select("id", (running - 1).alias("dense"))
        save_plan("a_running_count_bigint", frame)
        frame.write.parquet(out.as_uri())
        return {}

    # ---- (b) two passes: partition counts, driver prefix sums, offset + index inside the partition ----
    def two_pass(source, out, name):
        counted = source.select(pid.alias("p")).groupBy("p").count()
        counts = {r[0]: r[1] for r in counted.collect()}                               # pass 1
        offsets = offsets_of(counts)
        frame = source.select("id", pid.alias("p"), mid.alias("m")).select(
            "id", (lookup(offsets, F.col("p")) + F.col("m").bitwiseAND(MASK33)).alias("dense"))
        save_plan(name, frame)
        frame.write.parquet(out.as_uri())                                              # pass 2
        return dict(partitions=len(counts))

    def b_two_pass_direct_scan(out):
        return two_pass(vertices(), out, "b_two_pass_direct_scan")

    def b_two_pass_checkpoint(out):
        return two_pass(vertices().checkpoint(), out, "b_two_pass_checkpoint")

    def b_one_pass_materialized(out):
        """Pass 1 writes (id, m). The partition and the position are then data, not execution artefacts."""
        staged = scratch / "b-staged"
        shutil.rmtree(staged, ignore_errors=True)
        vertices().select("id", mid.alias("m")).write.parquet(staged.as_uri())
        table = spark.read.parquet(staged.as_uri())
        part = F.shiftright("m", 33)
        counts = {r[0]: r[1] for r in table.groupBy(part.alias("p")).count().collect()}
        offsets = offsets_of(counts)
        frame = table.select("id", (lookup(offsets, part) + F.col("m").bitwiseAND(MASK33)).alias("dense"))
        save_plan("b_one_pass_materialized (second step)", frame)
        frame.write.parquet(out.as_uri())
        return dict(partitions=len(counts))

    def b_map_in_arrow_checkpoint(out):
        """The index inside the partition from a small Arrow map function instead of the native operator."""
        source = vertices().checkpoint()
        counts = {r[0]: r[1] for r in source.select(pid.alias("p")).groupBy("p").count().collect()}
        offsets = offsets_of(counts)

        def index(batches):
            import pyarrow as pa
            seen = 0
            for batch in batches:
                local = pa.array(range(seen, seen + batch.num_rows), pa.int64())
                seen += batch.num_rows
                yield pa.RecordBatch.from_arrays([batch.column(0), batch.column(1), local], ["id", "p", "local"])
        frame = source.select("id", pid.alias("p")).mapInArrow(index, "id long, p int, local long").select(
            "id", (lookup(offsets, F.col("p")) + F.col("local")).alias("dense"))
        save_plan("b_map_in_arrow_checkpoint", frame)
        frame.write.parquet(out.as_uri())
        return dict(partitions=len(counts))

    # ---- (e) sorted dense ids for vertices keyed by an origin id ----------------------------------
    def e_distinct_row_number(out):
        ids = vertices().select("id").distinct()
        frame = ids.select("id", (F.row_number().over(Window.orderBy("id")) - 1).cast("long").alias("dense"))
        save_plan("e_distinct_row_number", frame)
        frame.write.parquet(out.as_uri())
        return {}

    def bucketed(ids, out, name):
        """Range buckets from a sample; counts per bucket; offset + row_number inside the bucket."""
        sample = sorted(r[0] for r in ids.sample(False, min(1.0, 20000 / N), 7).collect())     # pass 0
        bounds = sorted({sample[len(sample) * k // BUCKETS] for k in range(1, BUCKETS)})
        bucket = bucket_of(F.col("id"), bounds, F)
        with_bucket = ids.select("id", bucket.alias("b"))
        counts = {r[0]: r[1] for r in with_bucket.groupBy("b").count().collect()}                # pass 1
        offsets = offsets_of(counts)
        frame = with_bucket.select(
            "id", (lookup(offsets, F.col("b")) + F.row_number().over(
                Window.partitionBy("b").orderBy("id")) - 1).cast("long").alias("dense"))
        save_plan(name, frame)
        frame.write.parquet(out.as_uri())                                                        # pass 2
        return dict(buckets=len(counts), largest_bucket=max(counts.values()), sample=len(sample))

    def e_bucketed_row_number(out):
        return bucketed(vertices().select("id"), out, "e_bucketed_row_number")

    def e_from_edges_bucketed(out):
        e = edges()
        ids = e.select(F.col("source").alias("id")).union(e.select(F.col("target").alias("id"))).distinct()
        return bucketed(ids, out, "e_from_edges_bucketed")

    def e_from_edges_row_number(out):
        e = edges()
        ids = e.select(F.col("source").alias("id")).union(e.select(F.col("target").alias("id"))).distinct()
        frame = ids.select("id", (F.row_number().over(Window.orderBy("id")) - 1).cast("long").alias("dense"))
        save_plan("e_from_edges_row_number", frame)
        frame.write.parquet(out.as_uri())
        return {}

    endpoint_ids = np.unique(np.concatenate([edge_table.column("source").to_numpy(),
                                             edge_table.column("target").to_numpy()]))
    vertex_cases = [
        (a_row_number, truth_ids), (a_running_count_bigint, truth_ids), (a_orderby_monotonic_id, truth_ids),
        (a_coalesce1_monotonic_id, truth_ids), (b_two_pass_direct_scan, truth_ids), (b_two_pass_checkpoint, truth_ids),
        (b_one_pass_materialized, truth_ids), (b_map_in_arrow_checkpoint, truth_ids),
        (e_distinct_row_number, truth_ids), (e_bucketed_row_number, truth_ids),
        (e_from_edges_row_number, endpoint_ids), (e_from_edges_bucketed, endpoint_ids),
    ]

    def run(case, check, repeat, keep=None):
        out = scratch / "out"
        shutil.rmtree(out, ignore_errors=True)
        cpu, started = server.cpu_seconds(), time.perf_counter()
        try:
            extra = case(out)
            wall, used = time.perf_counter() - started, server.cpu_seconds() - cpu
            record = dict(record="run", case=case.__name__, repeat=repeat, ok=True, wall_seconds=round(wall, 3),
                          server_cpu_seconds=round(used, 2), server_rss_after_mib=server.rss_mib(), **extra)
            record.update(check(out))
            if keep is not None and not keep.exists():
                shutil.copytree(out, keep)
        except Exception as e:
            record = dict(record="run", case=case.__name__, repeat=repeat, ok=False, error=type(e).__name__,
                          message=str(e).strip().splitlines()[0][:400])
        emit(**record)
        return record

    # warm the page cache and the session
    vertices().count(), edges().count()
    mapping_dir = scratch / "mapping"
    for repeat in range(RUNS):
        for case, expected in vertex_cases:
            run(case, lambda out, expected=expected: check_mapping(out, expected), repeat,
                keep=mapping_dir if case is a_row_number else None)

    # ---- item 4: map the edge endpoints, sort, offsets ---------------------------------------------
    # Reference outside the engine: dense id = position in the sorted id array.
    ref_s = np.searchsorted(truth_ids, edge_table.column("source").to_numpy()).astype(np.int64)
    ref_d = np.searchsorted(truth_ids, edge_table.column("target").to_numpy()).astype(np.int64)
    ref_order = np.lexsort((ref_d, ref_s))
    ref_sorted = np.stack([ref_s[ref_order], ref_d[ref_order]])
    ref_finger = hashlib.blake2b(np.ascontiguousarray(ref_sorted).tobytes(), digest_size=8).hexdigest()
    ref_offsets = np.concatenate([[0], np.cumsum(np.bincount(ref_s, minlength=N))]).astype(np.int64)

    def mapping():
        return spark.read.parquet(mapping_dir.as_uri())

    def check_edges(directory):
        (s, d), rows = read_columns(directory, ["s", "d"])
        files_sorted = bool(((np.diff(s) > 0) | ((np.diff(s) == 0) & (np.diff(d) >= 0))).all())
        order = np.lexsort((d, s))
        mine = np.stack([s[order], d[order]])
        return dict(rows=len(s), files=len(rows), files_sorted=files_sorted,
                    each_file_sorted=each_sorted(s, rows, d),
                    matches_reference=mine.shape == ref_sorted.shape and bool((mine == ref_sorted).all()),
                    fingerprint=hashlib.blake2b(np.ascontiguousarray(mine).tobytes(), digest_size=8).hexdigest(),
                    reference_fingerprint=ref_finger)

    def mapped(e=None, m=None):
        e = edges() if e is None else e
        m = mapping() if m is None else m
        src = m.select(F.col("id").alias("source"), F.col("dense").alias("s"))
        dst = m.select(F.col("id").alias("target"), F.col("dense").alias("d"))
        return e.join(src, "source").join(dst, "target").select("s", "d")

    def map_two_joins(out):
        frame = mapped()
        save_plan("map_two_joins", frame)
        frame.write.parquet(out.as_uri())
        return {}

    def map_two_joins_inline_row_number(out):
        """The mapping is not materialised: the row_number plan is part of the join plan, twice."""
        m = vertices().select("id", (F.row_number().over(Window.orderBy("id")) - 1).cast("long").alias("dense"))
        frame = mapped(m=m)
        save_plan("map_two_joins_inline_row_number", frame)
        frame.write.parquet(out.as_uri())
        return {}

    def map_two_joins_inline_orderby_monotonic_id(out):
        """The same with orderBy + monotonically_increasing_id as the inline mapping."""
        m = vertices().orderBy("id").select("id", mid.alias("dense"))
        frame = mapped(m=m)
        save_plan("map_two_joins_inline_orderby_monotonic_id", frame)
        frame.write.parquet(out.as_uri())
        return {}

    def map_two_joins_sort(out):
        frame = mapped().orderBy("s", "d")
        save_plan("map_two_joins_sort", frame)
        frame.write.parquet(out.as_uri())
        return {}

    def rekey(halves, out, name):
        joined = halves.join(mapping(), "id")
        frame = joined.groupBy("edge").agg(
            F.max(F.when(F.col("side") == 0, F.col("dense"))).alias("s"),
            F.max(F.when(F.col("side") == 1, F.col("dense"))).alias("d")).select("s", "d")
        save_plan(name, frame)
        frame.write.parquet(out.as_uri())
        return {}

    def map_one_join_rekey(out):
        """One join on the unpivoted endpoints (one scan, explode), then a re-key by edge."""
        e = edges().select(mid.alias("edge"), "source", "target")
        halves = e.select("edge", F.posexplode(F.array("source", "target")).alias("side", "id"))
        return rekey(halves, out, "map_one_join_rekey")

    def map_one_join_rekey_two_scans(out):
        """The same with a union of two selections: the edge id is computed by two separate scans."""
        e = edges().select(mid.alias("edge"), "source", "target")
        halves = e.select("edge", F.lit(0).alias("side"), F.col("source").alias("id")).union(
            e.select("edge", F.lit(1).alias("side"), F.col("target").alias("id")))
        return rekey(halves, out, "map_one_join_rekey_two_scans")

    mapped_dir, sorted_dir = scratch / "mapped", scratch / "sorted"

    def sort_only(out):
        frame = spark.read.parquet(mapped_dir.as_uri()).orderBy("s", "d")
        save_plan("sort_only (mapped edges from Parquet)", frame)
        frame.write.parquet(out.as_uri())
        return {}

    def offsets_from_sorted(out):
        """n + 1 offsets: degree per source (group count), every vertex kept, exclusive prefix sum."""
        degree = spark.read.parquet(sorted_dir.as_uri()).groupBy("s").count()
        every = spark.range(N + 1).select(F.col("id").alias("v"))
        frame = every.join(degree, every.v == degree.s, "left").select(
            "v", F.coalesce(F.col("count"), F.lit(0)).alias("degree")).select(
            "v", F.coalesce(F.sum("degree").over(
                Window.orderBy("v").rowsBetween(Window.unboundedPreceding, -1)), F.lit(0)).cast("long").alias("offset"))
        save_plan("offsets_from_sorted", frame)
        frame.write.parquet(out.as_uri())
        return {}

    def check_offsets(directory):
        (v, offset), rows = read_columns(directory, ["v", "offset"])
        order = np.argsort(v)
        return dict(rows=len(v), files=len(rows), files_sorted=bool((np.diff(v) > 0).all()),
                    matches_reference=len(v) == N + 1 and bool((offset[order] == ref_offsets).all()),
                    last_offset=int(offset[order][-1]), zero_degree_vertices=int((np.diff(ref_offsets) == 0).sum()))

    for repeat in range(RUNS):
        run(map_two_joins, check_edges, repeat, keep=mapped_dir)
        run(map_two_joins_sort, check_edges, repeat, keep=sorted_dir)
        run(map_two_joins_inline_row_number, check_edges, repeat)
        run(map_two_joins_inline_orderby_monotonic_id, check_edges, repeat)
        run(map_one_join_rekey, check_edges, repeat)
        run(map_one_join_rekey_two_scans, check_edges, repeat)
        run(sort_only, check_edges, repeat)
        run(offsets_from_sorted, check_offsets, repeat)

    # ---- last: the direct-scan two-pass again with work stealing off (the setting stays for the session) ----
    spark.sql("SET datafusion.execution.enable_file_stream_work_stealing = false").collect()

    def b_two_pass_direct_scan_no_work_stealing(out):
        return two_pass(vertices(), out, "b_two_pass_direct_scan_no_work_stealing")

    for repeat in range(RUNS):
        run(b_two_pass_direct_scan_no_work_stealing, lambda out: check_mapping(out, truth_ids), repeat)

    # ---- and with one output file, so that the written file itself is in order ----
    spark.sql("SET datafusion.execution.minimum_parallel_output_files = 1").collect()

    def a_row_number_one_output_file(out):
        return a_row_number(out)

    def sort_only_one_output_file(out):
        return sort_only(out)

    def a_row_number_then_order_one_output_file(out):
        """row_number leaves a round-robin repartition above the window; ask for the order again."""
        frame = vertices().select(
            "id", (F.row_number().over(Window.orderBy("id")) - 1).cast("long").alias("dense")).orderBy("dense")
        save_plan("a_row_number_then_order", frame)
        frame.write.parquet(out.as_uri())
        return {}

    for repeat in range(RUNS):
        run(a_row_number_one_output_file, lambda out: check_mapping(out, truth_ids), repeat)
        run(a_row_number_then_order_one_output_file, lambda out: check_mapping(out, truth_ids), repeat)
        run(sort_only_one_output_file, check_edges, repeat)
    plans.close()

shutil.rmtree(scratch, ignore_errors=True)
