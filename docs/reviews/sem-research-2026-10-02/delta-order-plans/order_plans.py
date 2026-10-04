"""Sail: which physical layouts survive a write and a read, as seen in the physical plan.

Starts a Sail server (no extensions), writes two small tables in every layout Sail accepts, runs
EXPLAIN for a fixed list of queries, parses the physical plan, and prints layout x query tables:
counts of SortExec / RepartitionExec / SortPreservingMergeExec / CoalescePartitionsExec, the join
operator, the aggregate and window modes, and what the scan node prints.

Four server runs, one server at a time:

    local / hash        SAIL_MODE=local, default settings
    local / smj         SAIL_MODE=local, SAIL_OPTIMIZER__PREFER_HASH_JOIN=false
    cluster / hash      SAIL_MODE=local-cluster, default settings
    cluster / smj       SAIL_MODE=local-cluster, SAIL_OPTIMIZER__PREFER_HASH_JOIN=false

The local runs use EXPLAIN and EXPLAIN ANALYZE. The local-cluster runs execute each query into the
`noop` sink and read the executed plan and the job graph from the driver's debug log. They are the
fallback for cells where EXPLAIN fails, they show how many stages and shuffles a plan becomes, and
they show the plan of each write. Every run checks query results against the plain layout.

    python order_plans.py /path/to/release/sail [--label NAME] [--out DIR]

Needs pyspark[connect] 4.0 and pyarrow. Everything is written under a temporary directory that is
deleted at the end; the plans and tables are saved under --out (default: next to this script).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import sysconfig
import tempfile
import time
from collections.abc import Callable
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

ROWS_V = 2_000_000
ROWS_E = 4_000_000
MULTIPLIER = 1_234_577  # coprime with ROWS_V: id -> id * MULTIPLIER mod ROWS_V is a bijection
POINT = 1_234_567
RANGE = (1_000_000, 1_000_999)

# Every query is SQL over the views `v(id, val)` and `e(src, dst)` of one layout, plus `e0`, the
# plain Parquet edges.
QUERIES: dict[str, str] = {
    "join_same": "SELECT v.id, v.val, e.dst FROM v JOIN e ON v.id = e.src",
    "join_mixed": "SELECT v.id, v.val, e0.dst FROM v JOIN e0 ON v.id = e0.src",
    "round": "SELECT e.dst, sum(v.val) AS msg FROM v JOIN e ON v.id = e.src GROUP BY e.dst",
    "group_by": "SELECT src, count(*) AS c FROM e GROUP BY src",
    "order_by": "SELECT id, val FROM v ORDER BY id",
    "order_by_nulls_last": "SELECT id, val FROM v ORDER BY id ASC NULLS LAST",
    "window": "SELECT src, dst, count(*) OVER (PARTITION BY src) AS deg FROM e",
    "point": f"SELECT id, val FROM v WHERE id = {POINT}",
    "range": f"SELECT id, val FROM v WHERE id BETWEEN {RANGE[0]} AND {RANGE[1]}",
}
ANALYZED = ("point", "range")
# Every way to ask for a plan, tried on the plain layout's join in the local runs.
EXPLAIN_VARIANTS = ("EXPLAIN", "EXPLAIN EXTENDED", "EXPLAIN FORMATTED", "EXPLAIN CODEGEN", "EXPLAIN COST",
                    "EXPLAIN ANALYZE", "EXPLAIN VERBOSE")
# The `noop` sink lets the optimizer drop a top-level ORDER BY, and the filters need no exchange, so
# the local-cluster runs execute only the queries whose plan the sink does not change.
CLUSTER_QUERIES = ("join_same", "join_mixed", "round", "group_by", "window")
SINKS = ("DataSinkExec", "DeltaWriterExec", "RemoteCheckpointWriteExec")
# Result checks: the same aggregate over every layout must equal the plain layout's.
CHECKS: dict[str, str] = {
    "join_same": "SELECT count(*) AS n, sum(v.id + e.dst) AS s, cast(sum(v.val / 1e12) AS BIGINT) AS w "
                 "FROM v JOIN e ON v.id = e.src",
    "join_mixed": "SELECT count(*) AS n, sum(v.id + e0.dst) AS s FROM v JOIN e0 ON v.id = e0.src",
    "group_by": "SELECT count(*) AS n, sum(c) AS s FROM (SELECT src, count(*) AS c FROM e GROUP BY src)",
    "window": "SELECT count(*) AS n, sum(deg) AS s FROM "
              "(SELECT src, count(*) OVER (PARTITION BY src) AS deg FROM e)",
}


@dataclasses.dataclass
class Config:
    name: str
    mode: str  # "local" or "local-cluster"
    prefer_hash_join: bool


CONFIGS = [
    Config("local-hash", "local", True),
    Config("local-smj", "local", False),
    Config("cluster-hash", "local-cluster", True),
    Config("cluster-smj", "local-cluster", False),
]


@dataclasses.dataclass
class Layout:
    name: str
    how: str
    v: DataFrame
    e: DataFrame
    v_files: pathlib.Path | None = None  # directory to inspect with pyarrow
    v_key_column: str = "id"


@dataclasses.dataclass
class PlanFacts:
    sort: int = 0
    repartition_hash: int = 0
    repartition_round_robin: int = 0
    repartition_preserve_order: int = 0
    sort_preserving_merge: int = 0
    coalesce_partitions: int = 0
    join: str = ""
    aggregate: str = ""
    window: str = ""
    scans: list[str] = dataclasses.field(default_factory=list)


class Server:
    """One Sail server process. Environment as in ../../sail-partitionby-write-2026-10-02."""

    def __init__(self, sail: pathlib.Path, root: pathlib.Path, config: Config) -> None:
        self.root = root
        self.log = root / f"server-{config.name}.log"
        self.checkpoints = root / f"checkpoints-{config.name}"
        self.checkpoints.mkdir()
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port: int = s.getsockname()[1]
        lib = sysconfig.get_config_var("LIBDIR") or ""
        env = dict(os.environ, PYTHONHOME=sys.base_prefix, PYTHONPATH=sysconfig.get_paths()["purelib"],
                   DYLD_LIBRARY_PATH=lib, LD_LIBRARY_PATH=lib, SAIL_MODE=config.mode,
                   SAIL_EXECUTION__CHECKPOINT__PATH=self.checkpoints.as_uri(),
                   RUST_LOG="warn,sail_execution::driver::job_scheduler::core=debug"
                   if config.mode != "local" else "warn")
        env.pop("SAIL_EXPERIMENTAL_EXTENSIONS", None)
        env.pop("SAIL_OPTIMIZER__PREFER_HASH_JOIN", None)
        env.pop("SAIL_EXECUTION__DEFAULT_PARALLELISM", None)
        if not config.prefer_hash_join:
            env["SAIL_OPTIMIZER__PREFER_HASH_JOIN"] = "false"
        self.env_set = {k: env[k] for k in ("SAIL_MODE", "SAIL_EXECUTION__CHECKPOINT__PATH", "RUST_LOG",
                                            "SAIL_OPTIMIZER__PREFER_HASH_JOIN") if k in env}
        self.log_handle = self.log.open("wb")
        self.process = subprocess.Popen(
            [str(sail), "spark", "server", "--ip", "127.0.0.1", "--port", str(self.port)],
            env=env, cwd=root, stdout=self.log_handle, stderr=subprocess.STDOUT)
        while True:
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", self.port)) == 0:
                    break
            if self.process.poll() is not None:
                raise RuntimeError(f"server exited: {self.log.read_text()[-2000:]}")
            time.sleep(0.05)

    def stop(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=60)
        self.log_handle.close()

    def log_size(self) -> int:
        return self.log.stat().st_size

    def log_since(self, offset: int) -> str:
        with self.log.open("rb") as f:
            f.seek(offset)
            return f.read().decode("utf-8", "replace")


def error_text(error: BaseException) -> str:
    """The first lines of an error, without the client's stack trace."""
    text = str(error).strip()
    text = text.split("\n\nJVM stacktrace")[0]
    return " | ".join(line.strip() for line in text.splitlines() if line.strip())[:600]


def physical_section(text: str) -> str:
    """The `== Physical Plan ==` section of an EXPLAIN output."""
    match = re.search(r"== Physical Plan ==\n(.*?)(?=\n== |\Z)", text, re.S)
    return (match.group(1) if match else text).strip("\n")


def parse_plan(plan: str) -> PlanFacts:
    facts = PlanFacts()
    aggregates: list[str] = []
    for line in plan.splitlines():
        match = re.match(r"\s*(\w+)(?::\s*(.*))?$", line)
        if not match:
            continue
        name, rest = match.group(1), match.group(2) or ""
        if name == "SortExec":
            facts.sort += 1
        elif name == "RepartitionExec":
            if "partitioning=Hash" in rest:
                facts.repartition_hash += 1
            else:
                facts.repartition_round_robin += 1
            if "preserve_order=true" in rest:
                facts.repartition_preserve_order += 1
        elif name == "ExplicitRepartitionExec":
            facts.repartition_round_robin += 1
        elif name == "SortPreservingMergeExec":
            facts.sort_preserving_merge += 1
        elif name == "CoalescePartitionsExec":
            facts.coalesce_partitions += 1
        elif name == "HashJoinExec":
            mode = re.search(r"mode=(\w+)", rest)
            facts.join = f"Hash({mode.group(1) if mode else '?'})"
        elif name in ("SortMergeJoinExec", "NestedLoopJoinExec", "CrossJoinExec"):
            facts.join = name.removesuffix("Exec")
        elif name == "AggregateExec":
            mode = re.search(r"mode=(\w+)", rest)
            ordering = re.search(r"ordering_mode=(\w+)", rest)
            aggregates.append((mode.group(1) if mode else "?") + (f"[{ordering.group(1)}]" if ordering else ""))
        elif name in ("BoundedWindowAggExec", "WindowAggExec"):
            mode = re.search(r"mode=\[(\w+)\]", rest)
            facts.window = name.removesuffix("Exec") + (f"[{mode.group(1)}]" if mode else "")
        elif name in ("DataSourceExec", "DeltaScanByAddsExec", "StageInputExec"):
            groups = re.search(r"file_groups=\{(\d+) groups?", rest)
            ordering = re.search(r"output_ordering=\[([^\]]*)\]", rest)
            partitioning = re.search(r"(?:output_)?partitioning=(\w+\([^)]*\)(?:, \d+\))?)", rest)
            scan = f"{groups.group(1)}g" if groups else name.removesuffix("Exec")
            if ordering:
                scan += f" order=[{ordering.group(1)}]"
            if partitioning:
                scan += f" part={partitioning.group(1)}"
            facts.scans.append(scan)
    facts.aggregate = "+".join(reversed(aggregates))
    return facts


def scan_metrics(plan: str) -> dict[str, str]:
    """Pruning metrics of the first file scan in an EXPLAIN ANALYZE plan."""
    for line in plan.splitlines():
        if "DataSourceExec" in line and "metrics=[" in line:
            out: dict[str, str] = {}
            groups = re.search(r"file_groups=\{(\d+) groups?", line)
            if groups:
                out["file_groups"] = groups.group(1)
            for key in ("output_rows", "files_ranges_pruned_statistics", "row_groups_pruned_statistics",
                        "row_groups_pruned_bloom_filter", "page_index_rows_pruned", "bytes_scanned"):
                match = re.search(rf"\b{key}=([^,\]]+)", line)
                if match:
                    out[key] = match.group(1).strip()
            return out
    return {}


def inspect_files(directory: pathlib.Path, key: str) -> dict[str, Any]:
    """What is physically in a table directory: files, sortedness by key, range overlap, footers."""
    files = sorted(p for p in directory.rglob("*.parquet") if "_delta_log" not in p.parts)
    all_sorted, footer = True, False
    spans: list[tuple[Any, Any]] = []
    for path in files:
        handle = pq.ParquetFile(path)
        column = key if key in handle.schema_arrow.names else handle.schema_arrow.names[0]
        values = handle.read(columns=[column]).column(0).combine_chunks()
        if len(values) > 1:
            all_sorted &= bool(pc.all(pc.less_equal(values[:-1], values[1:])).as_py())
        if len(values):
            spans.append((pc.min(values).as_py(), pc.max(values).as_py()))
        footer |= any(handle.metadata.row_group(i).sorting_columns for i in range(handle.metadata.num_row_groups))
    spans.sort()
    disjoint: bool | str = "one file"
    if len(spans) > 1:
        disjoint = all(spans[i][1] <= spans[i + 1][0] for i in range(len(spans) - 1))
    return dict(files=len(files), each_file_sorted_by_key=all_sorted, key_ranges_disjoint=disjoint,
                footer_sorting_columns=footer)


def target_partitions(spark: SparkSession) -> int:
    plan = physical_section(spark.sql("EXPLAIN SELECT src, count(*) FROM e0 GROUP BY src").collect()[0][0])
    match = re.search(r"partitioning=Hash\(\[[^\]]*\], (\d+)\)", plan)
    if not match:
        raise RuntimeError(f"cannot find the target partition count in:\n{plan}")
    return int(match.group(1))


def probe_writes(spark: SparkSession, root: pathlib.Path, v0: DataFrame) -> list[dict[str, str]]:
    """What Sail accepts for a declared write layout. Each attempt is recorded with its exact error."""
    out = root / "probe"
    out.mkdir()
    small = v0.limit(1000)

    def uri(name: str) -> str:
        return (out / name).as_uri()

    def sql(text: str) -> Callable[[], Any]:
        return lambda: spark.sql(text).collect()

    attempts: list[tuple[str, Callable[[], Any]]] = [
        ("parquet: write.partitionBy(col)",
         lambda: small.withColumn("b", F.col("id") % 4).write.partitionBy("b").parquet(uri("p_part"))),
        ("parquet: write.sortBy(col)", lambda: small.write.sortBy("id").parquet(uri("p_sortby"))),
        ("parquet: write.bucketBy(n, col).sortBy(col).saveAsTable",
         lambda: small.write.bucketBy(4, "id").sortBy("id").format("parquet")
         .option("path", uri("p_bucket")).saveAsTable("probe_p_bucket")),
        ("parquet: write.bucketBy(n, col).saveAsTable",
         lambda: small.write.bucketBy(4, "id").format("parquet")
         .option("path", uri("p_bucket_only")).saveAsTable("probe_p_bucket_only")),
        ("parquet: CREATE TABLE ... WITH ORDER (col)",
         sql(f"CREATE TABLE probe_p_wo (id BIGINT, val DOUBLE) USING parquet LOCATION '{uri('p_wo')}' WITH ORDER (id)")),
        ("parquet: repartition(n, col).sortWithinPartitions(col).write",
         lambda: small.repartition(4, "id").sortWithinPartitions("id").write.parquet(uri("p_sorted"))),
        ("parquet: CREATE TABLE ... CLUSTERED BY (col) SORTED BY (col) INTO n BUCKETS",
         sql(f"CREATE TABLE probe_p_cs (id BIGINT, val DOUBLE) USING parquet CLUSTERED BY (id) "
             f"SORTED BY (id) INTO 4 BUCKETS LOCATION '{uri('p_cs')}'")),
        ("parquet: INSERT INTO that bucketed table", sql("INSERT INTO probe_p_cs SELECT id, id * 1.0 FROM range(100)")),
        ("delta: write.partitionBy(col)",
         lambda: small.withColumn("b", F.col("id") % 4).write.format("delta").partitionBy("b").save(uri("d_part"))),
        ("delta: write.sortBy(col)", lambda: small.write.format("delta").sortBy("id").save(uri("d_sortby"))),
        ("delta: write.bucketBy(n, col)", lambda: small.write.format("delta").bucketBy(4, "id").save(uri("d_bucket"))),
        ("delta: write.clusterBy(col)", lambda: small.write.format("delta").clusterBy("id").save(uri("d_cluster"))),
        ("delta: writeTo(t).using('delta').clusterBy(col).create()",
         lambda: small.writeTo("probe_d_v2").using("delta").clusterBy("id").create()),
        ("delta: repartition(n, col).sortWithinPartitions(col).write",
         lambda: small.repartition(4, "id").sortWithinPartitions("id").write.format("delta").save(uri("d_sorted"))),
        ("delta: CREATE TABLE ... CLUSTER BY (col)",
         sql(f"CREATE TABLE probe_d_cl (id BIGINT, val DOUBLE) USING delta CLUSTER BY (id) LOCATION '{uri('d_cl')}'")),
        ("delta: CREATE TABLE ... CLUSTER BY (col) AS SELECT",
         sql(f"CREATE TABLE probe_d_ctas USING delta CLUSTER BY (id) LOCATION '{uri('d_ctas')}' "
             f"AS SELECT id, id * 1.0 AS val FROM range(100)")),
        ("delta: CREATE TABLE ... CLUSTERED BY (col) SORTED BY (col) INTO n BUCKETS",
         sql(f"CREATE TABLE probe_d_cs (id BIGINT, val DOUBLE) USING delta CLUSTERED BY (id) "
             f"SORTED BY (id) INTO 4 BUCKETS LOCATION '{uri('d_cs')}'")),
        ("delta: CREATE TABLE (plain)",
         sql(f"CREATE TABLE probe_d_t (id BIGINT, val DOUBLE) USING delta LOCATION '{uri('d_t')}'")),
        ("delta: INSERT INTO (plain)", sql("INSERT INTO probe_d_t SELECT id, id * 1.0 FROM range(100)")),
        ("delta: ALTER TABLE ... CLUSTER BY (col)", sql("ALTER TABLE probe_d_t CLUSTER BY (id)")),
        ("delta: OPTIMIZE t", sql("OPTIMIZE probe_d_t")),
        ("delta: OPTIMIZE t ZORDER BY (col)", sql("OPTIMIZE probe_d_t ZORDER BY (id)")),
        ("sql: SELECT ... DISTRIBUTE BY col", sql("SELECT id FROM range(100) DISTRIBUTE BY id")),
        ("sql: SELECT ... CLUSTER BY col", sql("SELECT id FROM range(100) CLUSTER BY id")),
        ("sql: SELECT ... SORT BY col", sql("SELECT id FROM range(100) SORT BY id")),
        ("dataframe: repartitionByRange(n, col)", lambda: small.repartitionByRange(4, "id").count()),
        ("dataframe: checkpoint()", lambda: small.checkpoint().count()),
        ("dataframe: localCheckpoint()", lambda: small.localCheckpoint().count()),
        ("dataframe: checkpoint(eager=False)", lambda: small.checkpoint(eager=False).count()),
    ]
    results: list[dict[str, str]] = []
    for name, attempt in attempts:
        try:
            attempt()
            results.append(dict(attempt=name, outcome="accepted", error=""))
        except Exception as error:  # noqa: BLE001 - the error text is the result
            results.append(dict(attempt=name, outcome="rejected", error=error_text(error)))
    return results


def build_layouts(spark: SparkSession, root: pathlib.Path, server: Server, partitions: int,
                  notes: dict[str, str], write_plans: dict[str, list[str]]) -> list[Layout]:
    """Write `v(id, val)` and `e(src, dst)` in every layout Sail accepts and read each back."""
    data, checkpoints = root / "data", server.checkpoints
    v0 = spark.read.parquet((root / "base" / "v").as_uri())
    e0 = spark.read.parquet((root / "base" / "e").as_uri())
    layouts: list[Layout] = []
    p = partitions

    def directory(name: str) -> pathlib.Path:
        path = data / name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def add(name: str, how: str, make: Callable[[], Layout | tuple[DataFrame, DataFrame, pathlib.Path | None]]) -> None:
        offset = server.log_size()
        try:
            made = make()
            layouts.append(Layout(name, how, *made) if isinstance(made, tuple) else made)
        except Exception as error:  # noqa: BLE001 - a layout Sail rejects is a result
            notes[name] = f"not built: {error_text(error)}"
        # In local-cluster mode the driver logs the plan of every job, including the writes.
        write_plans[name] = [plan for _, plan in job_plans(server.log_since(offset))
                             if any(sink in plan for sink in SINKS)]

    def files(fmt: str, name: str, shape: Callable[[DataFrame, str], DataFrame],
              partition_by: str | None = None) -> tuple[DataFrame, DataFrame, pathlib.Path]:
        base = directory(name)
        for frame, key, part in ((v0, "id", "v"), (e0, "src", "e")):
            writer = shape(frame, key).write.format(fmt)
            if partition_by:
                writer = writer.partitionBy(partition_by)
            writer.save((base / part).as_uri())
        return (spark.read.format(fmt).load((base / "v").as_uri()),
                spark.read.format(fmt).load((base / "e").as_uri()), base / "v")

    def bucketed(frame: DataFrame, key: str) -> DataFrame:
        with_bucket = frame.withColumn("bucket", F.pmod(F.xxhash64(key), F.lit(p)).cast("int"))
        return with_bucket.repartition(p, "bucket").sortWithinPartitions(key)

    def checkpoint(shape: Callable[[DataFrame, str], DataFrame]) -> tuple[DataFrame, DataFrame, pathlib.Path | None]:
        before = {d for d in checkpoints.glob("*/*") if d.is_dir()}
        v = shape(v0, "id").checkpoint()
        created = sorted({d for d in checkpoints.glob("*/*") if d.is_dir()} - before)
        e = shape(e0, "src").checkpoint()
        return v, e, (created[0] if len(created) == 1 else None)

    def pinned_sort(frame: DataFrame, key: str) -> DataFrame:
        # A control for the read side: a checkpoint whose files really are sorted. A window function
        # over the key requires its input sorted by the key, so the optimizer cannot drop that sort.
        # The column `rn` stays in the frame, otherwise the window is pruned and the sort with it.
        # The checkpoint records the ordering of the plan before optimization, where only the final
        # sortWithinPartitions is visible; the optimizer then removes that one as redundant.
        window = Window.partitionBy(key).orderBy(key)
        return (frame.repartition(p, key).withColumn("rn", F.row_number().over(window))
                .sortWithinPartitions(key))

    def aggregated(repartition: bool) -> tuple[DataFrame, DataFrame, pathlib.Path | None]:
        # The state of a round is the output of an aggregation by vertex id. `max(val)` over the
        # unique ids reproduces `v` exactly.
        def shape(frame: DataFrame, key: str) -> DataFrame:
            if key != "id":
                return frame.repartition(p, key)
            state = frame.groupBy("id").agg(F.max("val").alias("val"))
            return state.repartition(p, "id") if repartition else state
        return checkpoint(shape)

    def catalog_sorted() -> tuple[DataFrame, DataFrame, pathlib.Path]:
        base = data / "parquet-hash-sorted"
        spark.sql(f"CREATE TABLE cat_v (id BIGINT, val DOUBLE) USING parquet CLUSTERED BY (id) SORTED BY (id) "
                  f"INTO {p} BUCKETS LOCATION '{(base / 'v').as_uri()}'").collect()
        spark.sql(f"CREATE TABLE cat_e (src BIGINT, dst BIGINT) USING parquet CLUSTERED BY (src) SORTED BY (src) "
                  f"INTO {p} BUCKETS LOCATION '{(base / 'e').as_uri()}'").collect()
        return spark.table("cat_v"), spark.table("cat_e"), base / "v"

    def delta_catalog_sorted() -> tuple[DataFrame, DataFrame, pathlib.Path]:
        base = data / "delta-hash-sorted"
        for table, key, part in (("dcat_v", "id", "v"), ("dcat_e", "src", "e")):
            spark.sql(f"CREATE TABLE {table} USING delta CLUSTERED BY ({key}) SORTED BY ({key}) INTO {p} BUCKETS "
                      f"LOCATION '{(base / part).as_uri()}'").collect()
        return spark.table("dcat_v"), spark.table("dcat_e"), base / "v"

    def footer_sorted() -> tuple[DataFrame, DataFrame, pathlib.Path]:
        # A control for the read side: the bucket files of `parquet-bucket-dirs`, rewritten by pyarrow
        # as one flat file per bucket with `sorting_columns` in the footer. Sail did not write these.
        source, base = data / "parquet-bucket-dirs", directory("parquet-footer-sorted")
        for part in ("v", "e"):
            (base / part).mkdir(parents=True)
            for index, path in enumerate(sorted((source / part).rglob("*.parquet"))):
                table = pq.read_table(path)
                table = table.drop_columns([c for c in table.column_names if c == "bucket"])
                pq.write_table(table, base / part / f"part-{index:05d}.parquet", compression="zstd",
                               sorting_columns=[pq.SortingColumn(0, descending=False, nulls_first=True)])
        return spark.read.parquet((base / "v").as_uri()), spark.read.parquet((base / "e").as_uri()), base / "v"

    def clustered_input() -> tuple[DataFrame, DataFrame, pathlib.Path]:
        # A control for file pruning: what a clustered Delta table would look like. Sail drops a sort
        # placed before a Delta write, so the rows are generated in key order instead: the inverse of
        # the base table's id permutation gives the same (id, val) rows.
        base, rows = directory("delta-clustered-input"), v0.count()
        inverse = pow(MULTIPLIER, -1, rows)
        ordered = spark.range(0, rows, 1, p).select(
            F.col("id"), F.xxhash64(F.pmod(F.col("id") * inverse, F.lit(rows))).cast("double").alias("val"))
        ordered.write.format("delta").save((base / "v").as_uri())
        return (spark.read.format("delta").load((base / "v").as_uri()),
                spark.read.format("delta").load((data / "delta-plain" / "e").as_uri()), base / "v")

    add("parquet-plain", "write.parquet", lambda: (v0, e0, root / "base" / "v"))
    add("parquet-hash-sorted", f"repartition({p}, k).sortWithinPartitions(k).write.parquet",
        lambda: files("parquet", "parquet-hash-sorted", lambda f, k: f.repartition(p, k).sortWithinPartitions(k)))
    add("parquet-range-sorted", f"repartitionByRange({p}, k).sortWithinPartitions(k).write.parquet",
        lambda: files("parquet", "parquet-range-sorted",
                      lambda f, k: f.repartitionByRange(p, k).sortWithinPartitions(k)))
    add("parquet-global-sorted", "orderBy(k).write.parquet",
        lambda: files("parquet", "parquet-global-sorted", lambda f, k: f.orderBy(k)))
    add("parquet-catalog-sorted",
        f"the parquet-hash-sorted files behind CREATE TABLE ... CLUSTERED BY (k) SORTED BY (k) INTO {p} BUCKETS",
        catalog_sorted)
    add("parquet-bucket-dirs",
        f"bucket = pmod(xxhash64(k), {p}); repartition({p}, bucket).sortWithinPartitions(k).write.partitionBy(bucket)",
        lambda: files("parquet", "parquet-bucket-dirs", bucketed, "bucket"))
    add("parquet-footer-sorted",
        "control, not written by Sail: the bucket files rewritten by pyarrow with footer sorting_columns",
        footer_sorted)
    add("delta-plain", "write.format('delta')", lambda: files("delta", "delta-plain", lambda f, k: f))
    add("delta-hash-sorted", f"repartition({p}, k).sortWithinPartitions(k).write.format('delta')",
        lambda: files("delta", "delta-hash-sorted", lambda f, k: f.repartition(p, k).sortWithinPartitions(k)))
    add("delta-catalog-sorted",
        f"the delta-hash-sorted table behind CREATE TABLE ... CLUSTERED BY (k) SORTED BY (k) INTO {p} BUCKETS",
        delta_catalog_sorted)
    add("delta-global-sorted", "orderBy(k).write.format('delta')",
        lambda: files("delta", "delta-global-sorted", lambda f, k: f.orderBy(k)))
    add("delta-bucket-dirs", "as parquet-bucket-dirs, write.format('delta').partitionBy(bucket)",
        lambda: files("delta", "delta-bucket-dirs", bucketed, "bucket"))
    add("delta-clustered-input",
        f"control: the same rows generated in key order in {p} contiguous ranges, then write.format('delta')",
        clustered_input)
    add("checkpoint-hash", f"repartition({p}, k).checkpoint()", lambda: checkpoint(lambda f, k: f.repartition(p, k)))
    add("checkpoint-hash-fewer", f"repartition({p - 2}, k).checkpoint()",
        lambda: checkpoint(lambda f, k: f.repartition(p - 2, k)))
    add("checkpoint-hash-more", f"repartition({p + 6}, k).checkpoint()",
        lambda: checkpoint(lambda f, k: f.repartition(p + 6, k)))
    add("checkpoint-hash-sorted", f"repartition({p}, k).sortWithinPartitions(k).checkpoint()",
        lambda: checkpoint(lambda f, k: f.repartition(p, k).sortWithinPartitions(k)))
    add("checkpoint-range-sorted", f"repartitionByRange({p}, k).sortWithinPartitions(k).checkpoint()",
        lambda: checkpoint(lambda f, k: f.repartitionByRange(p, k).sortWithinPartitions(k)))
    add("checkpoint-hash-sorted-pinned",
        f"control: repartition({p}, k), a row_number() window over k that pins a sort, "
        "sortWithinPartitions(k), checkpoint()", lambda: checkpoint(pinned_sort))
    add("checkpoint-aggregate", "v = groupBy(id).agg(max(val)).checkpoint(); e as checkpoint-hash",
        lambda: aggregated(False))
    add("checkpoint-aggregate-repartition",
        f"v = groupBy(id).agg(max(val)).repartition({p}, id).checkpoint(); e as checkpoint-hash",
        lambda: aggregated(True))
    for layout in layouts:
        if layout.name.startswith("checkpoint"):
            layout.v_key_column = "_c0"
    return layouts


def job_plans(log: str) -> list[tuple[str, str]]:
    """(job id, executed plan) for every job in a slice of the local-cluster driver log."""
    return re.findall(r"job (\d+) execution plan\n(.*?)\n\n", log, re.S)


def last_job(log: str) -> tuple[str, str]:
    """The last executed plan in a slice of the local-cluster driver log, and that job's graph."""
    plans = job_plans(log)
    if not plans:
        return "", ""
    job, plan = plans[-1]
    graph = re.search(rf"job {job} job graph \n(.*?)(?=\n\[\d{{4}}-\d\d-\d\dT|\Z)", log, re.S)
    return plan, (graph.group(1).strip() if graph else "")


def run_config(sail: pathlib.Path, root: pathlib.Path, raw: pathlib.Path, config: Config) -> dict[str, Any]:
    """One server: build the layouts, collect a plan for every layout x query cell."""
    server = Server(sail, root, config)
    result: dict[str, Any] = dict(config=dataclasses.asdict(config), server_environment=server.env_set, cells=[],
                                  layouts=[], notes={})
    cell_dir = raw / config.name
    cell_dir.mkdir(parents=True)
    try:
        spark = SparkSession.builder.remote(f"sc://127.0.0.1:{server.port}").create()
        v0 = spark.read.parquet((root / "base" / "v").as_uri())
        e0 = spark.read.parquet((root / "base" / "e").as_uri())
        e0.createOrReplaceTempView("e0")
        partitions = target_partitions(spark)
        result["target_partitions"] = partitions
        if config.name == "local-hash":
            result["write_support"] = probe_writes(spark, root, v0)
            plan = physical_section(v0.repartitionByRange(partitions, "id")._explain_string())
            (cell_dir / "repartitionByRange.txt").write_text(plan + "\n")
            result["repartition_by_range_plan"] = plan
        data = root / "data"
        shutil.rmtree(data, ignore_errors=True)
        write_plans: dict[str, list[str]] = {}
        layouts = build_layouts(spark, root, server, partitions, result["notes"], write_plans)
        reference: dict[str, tuple[Any, ...]] = {}
        for layout in layouts:
            layout.v.createOrReplaceTempView("v")
            layout.e.createOrReplaceTempView("e")
            described: dict[str, Any] = dict(name=layout.name, how=layout.how)
            if layout.v_files is not None:
                described["v_files"] = inspect_files(layout.v_files, layout.v_key_column)
            if write_plans.get(layout.name):
                (cell_dir / f"_write__{layout.name}.txt").write_text("\n\n".join(write_plans[layout.name]) + "\n")
                operators = re.findall(r"^\s*(\w+)", write_plans[layout.name][0], re.M)
                described["v_write_operators"] = " > ".join(
                    x.removesuffix("Exec") for x in operators if x != "CooperativeExec")
            checks: dict[str, Any] = {}
            for check, sql in CHECKS.items():
                try:
                    row = tuple(spark.sql(sql).collect()[0])
                except Exception as error:  # noqa: BLE001
                    checks[check] = dict(error=error_text(error))
                    continue
                reference.setdefault(check, row)
                checks[check] = dict(result=list(row), equals_plain=row == reference[check])
            described["result_checks"] = checks
            result["layouts"].append(described)
            if config.mode == "local" and layout.name == "parquet-plain":
                variants: dict[str, str] = {}
                texts: list[str] = []
                for variant in EXPLAIN_VARIANTS:
                    try:
                        text = spark.sql(f"{variant} {QUERIES['join_same']}").collect()[0][0]
                    except Exception as error:  # noqa: BLE001
                        text = "Request failed: " + error_text(error)
                    plan = physical_section(text)
                    variants[variant] = (" ".join(plan.split())[:240] if plan.startswith(
                        ("Physical plan error", "Request failed")) else "physical plan shown")
                    texts.append(f"##### {variant}\n{text}")
                (cell_dir / "_explain_variants__parquet-plain__join_same.txt").write_text("\n\n".join(texts) + "\n")
                result["explain_variants"] = variants
            for query, sql in QUERIES.items():
                if config.mode != "local" and query not in CLUSTER_QUERIES:
                    continue
                cell: dict[str, Any] = dict(layout=layout.name, query=query)
                stem = f"{layout.name}__{query}"
                if config.mode == "local":
                    text = spark.sql("EXPLAIN " + sql).collect()[0][0]
                    plan = physical_section(text)
                    (cell_dir / f"{stem}.txt").write_text(text + "\n")
                    if plan.startswith("Physical plan error"):
                        lines = plan.splitlines()
                        cell["explain_error"] = (lines[2] if len(lines) > 2 else lines[0]).strip()
                    else:
                        cell["facts"] = dataclasses.asdict(parse_plan(plan))
                    if query in ANALYZED:
                        analyzed = spark.sql("EXPLAIN ANALYZE " + sql).collect()[0][0]
                        (cell_dir / f"{stem}__analyze.txt").write_text(analyzed + "\n")
                        cell["scan_metrics"] = scan_metrics(physical_section(analyzed))
                else:
                    offset = server.log_size()
                    try:
                        spark.sql(sql).write.format("noop").mode("overwrite").save()
                    except Exception as error:  # noqa: BLE001
                        cell["execution_error"] = error_text(error)
                    plan, graph = last_job(server.log_since(offset))
                    (cell_dir / f"{stem}.txt").write_text(
                        f"== Executed plan (driver debug log) ==\n{plan}\n\n== Job graph ==\n{graph}\n"
                        + (f"\n== Execution error ==\n{cell['execution_error']}\n" if "execution_error" in cell else ""))
                    if plan:
                        cell["facts"] = dataclasses.asdict(parse_plan(plan))
                        cell["stages"] = len(re.findall(r"=== stage \d+ ===", graph))
                        cell["shuffle_inputs"] = len(re.findall(r"mode=Shuffle", graph))
                result["cells"].append(cell)
        spark.stop()
    finally:
        server.stop()
    return result


def facts_row(cell: dict[str, Any], fallback: dict[str, Any] | None = None) -> list[str]:
    note = ""
    if "explain_error" in cell:
        note = "EXPLAIN failed: " + cell["explain_error"]
        if fallback and "facts" in fallback:
            cell, note = fallback, note + " Plan taken from the local-cluster run."
    if "execution_error" in cell:
        note = "execution FAILED: " + cell["execution_error"][:200]
    if "facts" not in cell:
        return ["", "", "", "", "", "", "", note or "no plan"]
    f = cell["facts"]
    repartition = f"{f['repartition_hash']}h"
    if f["repartition_round_robin"]:
        repartition += f"+{f['repartition_round_robin']}rr"
    if f["repartition_preserve_order"]:
        repartition += f" ({f['repartition_preserve_order']} order-preserving)"
    operators = "; ".join(x for x in (f["join"], f["aggregate"], f["window"]) if x)
    return [str(f["sort"]), repartition, str(f["sort_preserving_merge"]), str(f["coalesce_partitions"]),
            operators or "-", ", ".join(f["scans"]) or "-",
            f"{cell['stages']} stages, {cell['shuffle_inputs']} shuffles" if cell.get("stages") else "", note]


def table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(x).replace("|", "\\|") for x in row) + " |" for row in rows]
    return "\n".join(lines)


def render(results: dict[str, Any]) -> str:
    runs: dict[str, dict[str, Any]] = {run["config"]["name"]: run for run in results["runs"]}
    cells: dict[tuple[str, str, str], dict[str, Any]] = {
        (name, c["layout"], c["query"]): c for name, run in runs.items() for c in run["cells"]}

    def fallback(run: str, layout: str, query: str) -> dict[str, Any] | None:
        return cells.get((run.replace("local-", "cluster-"), layout, query)) if run.startswith("local-") else None

    def counts(run: str, layout: str, query: str, keys: tuple[str, ...]) -> str:
        cell = cells.get((run, layout, query))
        mark = ""
        if cell is not None and "facts" not in cell:
            cell, mark = fallback(run, layout, query), " †"
        if cell is None or "facts" not in cell:
            return "no plan"
        return ", ".join(str(cell["facts"][k]) for k in keys) + mark

    out: list[str] = [f"# Plan tables: {results['label']}", "",
                      f"Binary `{results['sail']}` (modified {results['binary_modified']}; its source tree is "
                      f"at `{results['revision']}`, which the binary may predate), "
                      f"{results['rows_v']:,} vertices, {results['rows_e']:,} edges, "
                      f"pyspark {results['pyspark']}, {results['cpus']} CPUs, {results['when']}. "
                      "Written by `order_plans.py`; do not edit.", ""]
    first = results["runs"][0]
    layouts = [x["name"] for x in first["layouts"]]

    out += ["## Summary", "",
            "Operator counts in the physical plan. `ORDER BY k` and `GROUP BY k` are from the default run. "
            "`h` = hash `RepartitionExec`. † = EXPLAIN failed in local mode and the plan is the one the "
            "local-cluster run executed. Results = whether every result check in every run equals the plain "
            "layout.", ""]
    rows = []
    for layout in layouts:
        checked = [(name, check, value) for name, run in runs.items() for x in run["layouts"]
                   if x["name"] == layout for check, value in x.get("result_checks", {}).items()]
        wrong = [f"{name} {check}" for name, check, value in checked if value.get("equals_plain") is False]
        failed = [f"{name} {check}" for name, check, value in checked if "error" in value]
        verdict = "equal" if not wrong else "**WRONG**: " + "; ".join(wrong)
        if failed:
            verdict += ". Query FAILED: " + "; ".join(failed)
        rows.append([layout,
                     counts("local-hash", layout, "order_by", ("sort",)),
                     counts("local-hash", layout, "order_by_nulls_last", ("sort",)),
                     counts("local-hash", layout, "group_by", ("repartition_hash",)),
                     counts("local-hash", layout, "join_same", ("repartition_hash",)),
                     counts("local-smj", layout, "join_same", ("sort", "repartition_hash")),
                     counts("local-smj", layout, "join_mixed", ("sort", "repartition_hash")),
                     counts("local-smj", layout, "round", ("sort", "repartition_hash")),
                     verdict])
    out += [table(["Layout", "ORDER BY k: SortExec", "ORDER BY k NULLS LAST: SortExec", "GROUP BY k: h",
                   "Hash join, both sides in layout: h", "Sort-merge join, both sides: SortExec, h",
                   "Sort-merge join, edges plain: SortExec, h", "Round (join, GROUP BY dst), sort-merge: SortExec, h",
                   "Results"], rows), ""]

    out += ["## What Sail accepts", "", table(["Attempt", "Outcome", "Error"], [
        [w["attempt"], w["outcome"], w["error"]] for w in first.get("write_support", [])]), ""]
    out += ["## `repartitionByRange` in local mode", "", "```", first.get("repartition_by_range_plan", ""), "```", ""]

    out += ["## Layouts: what is on disk", "",
            "`Sorted` = every data file of `v` is sorted by the key. `Disjoint` = the files' key ranges do "
            "not overlap. `Footer` = a Parquet footer carries `sorting_columns`. `Write plan` = the operators "
            "of the job that wrote `v`, top down, from the driver log of the `cluster-hash` run.", ""]
    writes = {x["name"]: x.get("v_write_operators", "") for x in runs.get("cluster-hash", {}).get("layouts", [])}
    out += [table(["Layout", "How", "Files", "Sorted", "Disjoint", "Footer", "Write plan"], [
        [x["name"], x["how"], *[str(x.get("v_files", {}).get(k, "")) for k in (
            "files", "each_file_sorted_by_key", "key_ranges_disjoint", "footer_sorting_columns")],
         writes.get(x["name"], "")] for x in first["layouts"]]), ""]

    out += ["## Result checks", "",
            "Each cell is the row a check query returned: `join_same` = count, sum(id + dst), sum(val); "
            "`join_mixed` = count, sum(id + dst); `group_by` = groups, rows; `window` = rows, sum(deg). **WRONG** = differs from the plain layout "
            "in the same run.", ""]
    rows = []
    for layout in layouts:
        for name, run in runs.items():
            same = [x for x in run["layouts"] if x["name"] == layout]
            checks = same[0].get("result_checks", {}) if same else {}
            row = [layout, name]
            for check in CHECKS:
                value = checks.get(check, {})
                if "error" in value:
                    row.append("error: " + value["error"][:120])
                elif "result" not in value:
                    row.append("not run")
                else:
                    row.append(", ".join(str(x) for x in value["result"])
                               + ("" if value["equals_plain"] else " **WRONG**"))
            rows.append(row)
    out += [table(["Layout", "Run", *CHECKS], rows), ""]

    for name, run in runs.items():
        out += [f"## Plans: {name}", "", f"Server environment: `{json.dumps(run['server_environment'])}`. "
                f"Target partitions: {run['target_partitions']}.", ""]
        if run["notes"]:
            out += ["Layouts not built: " + "; ".join(f"`{k}`: {v}" for k, v in run["notes"].items()), ""]
        header = ["Layout", "Query", "Sort", "Repartition", "SPM", "Coalesce", "Join; aggregate; window",
                  "Scans (file groups, printed properties)", "Job graph", "Note"]
        out += [table(header, [[c["layout"], c["query"], *facts_row(c, fallback(name, c["layout"], c["query"]))]
                               for c in run["cells"]]), ""]
        if run.get("explain_variants"):
            out += [f"### Every EXPLAIN variant on `parquet-plain` / `join_same`: {name}", "",
                    table(["Statement", "Outcome"], [[k, v] for k, v in run["explain_variants"].items()]), ""]
        if run["config"]["mode"] == "local":
            metrics = [c for c in run["cells"] if c.get("scan_metrics")]
            keys = ["file_groups", "output_rows", "files_ranges_pruned_statistics", "row_groups_pruned_statistics",
                    "row_groups_pruned_bloom_filter", "page_index_rows_pruned", "bytes_scanned"]
            out += [f"### Pruning (EXPLAIN ANALYZE, first file scan): {name}", "",
                    table(["Layout", "Query", *keys],
                          [[c["layout"], c["query"], *[c["scan_metrics"].get(k, "") for k in keys]] for c in metrics]),
                    ""]
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sail", type=pathlib.Path, help="path to a release `sail` binary")
    parser.add_argument("--label", default="sail", help="names the output files")
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parent)
    parser.add_argument("--rows-v", type=int, default=ROWS_V)
    parser.add_argument("--rows-e", type=int, default=ROWS_E)
    parser.add_argument("--configs", default=",".join(c.name for c in CONFIGS))
    args = parser.parse_args()
    sail: pathlib.Path = args.sail.resolve()
    assert math.gcd(MULTIPLIER, args.rows_v) == 1, "the id permutation needs gcd(MULTIPLIER, rows_v) = 1"
    raw = args.out / "raw" / args.label
    shutil.rmtree(raw, ignore_errors=True)
    root = pathlib.Path(tempfile.mkdtemp(prefix="sail-order-plans-", dir=os.environ.get("PROBE_TMP"))).resolve()
    revision = "unknown"
    for parent in sail.parents:
        if (parent / ".git").exists():
            revision = subprocess.run(["git", "-C", str(parent), "rev-parse", "--short=9", "HEAD"],
                                      capture_output=True, text=True, check=False).stdout.strip() or revision
            break
    import pyspark
    modified = time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(sail.stat().st_mtime))
    results: dict[str, Any] = dict(label=args.label, sail=str(sail), revision=revision, binary_modified=modified,
                                   rows_v=args.rows_v,
                                   rows_e=args.rows_e, pyspark=pyspark.__version__, pyarrow=pa.__version__,
                                   cpus=os.cpu_count(), when=time.strftime("%Y-%m-%d %H:%M:%S %Z"), runs=[])
    try:
        # The base tables are written once, by the first server, in scrambled key order.
        server = Server(sail, root, Config("base", "local", True))
        try:
            spark = SparkSession.builder.remote(f"sc://127.0.0.1:{server.port}").create()
            spark.range(args.rows_v).select(
                F.pmod(F.col("id") * MULTIPLIER, F.lit(args.rows_v)).alias("id"),
                F.xxhash64("id").cast("double").alias("val")).write.parquet((root / "base" / "v").as_uri())
            spark.range(args.rows_e).select(
                F.pmod(F.xxhash64("id"), F.lit(args.rows_v)).alias("src"),
                F.pmod(F.xxhash64("id", F.lit(7)), F.lit(args.rows_v)).alias("dst"),
            ).write.parquet((root / "base" / "e").as_uri())
            spark.stop()
        finally:
            server.stop()
        for config in CONFIGS:
            if config.name not in args.configs.split(","):
                continue
            started = time.perf_counter()
            results["runs"].append(run_config(sail, root, raw, config))
            print(f"{config.name}: {time.perf_counter() - started:.1f} s", file=sys.stderr, flush=True)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    (args.out / f"results-{args.label}.json").write_text(json.dumps(results, indent=1) + "\n")
    rendered = render(results)
    (args.out / f"results-{args.label}.md").write_text(rendered + "\n")
    print(rendered)


if __name__ == "__main__":
    main()
