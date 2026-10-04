# Dense ids on Sail: drafts for an analogue of `zipWithIndex`

Written 2026-10-02. A research note for the reviewer's task: how Sail could
give every vertex group a dense index 0..n-1, so that GraphAr and icebug-disk
work out of the box and the CSR mapping happens inside the engine. Drafts,
small prototypes and micro-benchmarks only. No engine code was written.

## Summary

1. GraphAr's internal vertex id is the row number of a vertex inside its
   type, an i64 from 0. The 16 + 48 bit split is not in the specification,
   not in GraphAr's code and not in icebug-format; I did not find its origin.
2. Sail has `row_number` (INT, one stream), `monotonically_increasing_id`,
   `spark_partition_id` and `mapInArrow`; no RDD API, no range partitioning,
   and no exposed file row index, although DataFusion 55.1.0 ships one.
3. A dense, sorted, repeatable index works today with client code only:
   `row_number() over (order by id)` gave exactly 0..n-1 in id order in every
   run, in local and in local-cluster mode.
4. The classic two-pass `zipWithIndex` is unsafe in local mode: a Parquet scan
   is not repeatable there, and 6 of 6 runs gave duplicate ids or gaps. It is
   exact after a checkpoint, with work stealing off, or in cluster mode.
5. Recommendation: build the contract with client code first (index, two
   joins, sort), measure Banda on dense sorted input, then decide on engine
   work; the first engine changes are small (`file_row_index()`, real range
   partitioning).

## How to read this

Three kinds of statement are kept apart.

- **run**: verified by running. The raw record is named.
- **code**: read from source. File and line are given.
- **inferred**: my reasoning from the two above. Not tested.

Source trees and versions.

| Short name | What | Revision |
|---|---|---|
| `sail/` | fork worktree `~/src/sail-pecan-integrated`, branch `work/nutmeg-int64-identity` | HEAD `4b88c8fb4` |
| upstream | `~/src/sail-upstream-main` | `99ee46f69` |
| `df/` | DataFusion 55.1.0 crates in the Cargo registry (`datafusion-*-55.1.0/`) | 55.1.0 |
| `parquet/` | `parquet-59.3.0/` in the Cargo registry (the version in `sail/Cargo.lock`) | 59.3.0 |
| `graphar/` | `apache/incubator-graphar`, shallow clone | `c7f31bc9d` (2026-09-29) |
| `icebug/` | `Ladybug-Memory/icebug-format`, shallow clone | `be7ca65f` (2026-08-22) |

Line numbers for Sail are those of the fork worktree. The Sail files cited
for operators and functions (`monotonic_id.rs`, `spark_partition_id.rs`,
`function/scalar/misc.rs`, `function/window.rs`, `function/common.rs`,
`proto/encode.rs`, `plan/shuffle_write.rs`, `listing/planner.rs`) are
byte-identical in upstream. The engine probes were also run on the unmodified
upstream binary, see section 5.5.

Measurements: Apple M1 Max, 10 cores, 64 GiB, macOS 26.2. One Sail server at a
time, release build `sail/target/host/release/sail`, PySpark Connect 4.0.1.
The laptop was shared: other agents ran Sail servers and builds during the
runs, and the load average was between 10 and 75. **All timings are shape
only.**

## 1. What GraphAr specifies

Source: <https://graphar.apache.org/docs/specification/format> and
<https://graphar.apache.org/docs/specification/implementation-status>. I read
the Markdown sources of the two pages in `graphar/docs/specification/`
(`format.md`, `implementation-status.md`); line numbers refer to those files.
The rendered format page was fetched as well and carries the same sentences.

### Internal vertex id

"Each type of vertices (with the same label) constructs a logical vertex
table, with each vertex assigned with a global index inside this type (called
internal vertex id) starting from 0, corresponding to the row number of the
vertex in the logical vertex table." (`format.md:92`)

"Given an internal vertex id and the vertex label, a vertex is uniquely
identifiable". The id is "further used to identify the source and destination
vertices when maintaining the topology of the graph." (`format.md:94`)

So the id is dense per vertex type. The type is carried next to the id (by
the label, the file path and the edge type triplet), not inside it.

### Vertex chunks, and how chunk and offset give the id

- The logical table is cut into "multiple continuous vertex chunks". "To
  maintain the ability of random access, the size of vertex chunks for the
  same label is fixed." (`format.md:106`). The last chunk may be shorter
  (`format.md:108`). The recommended size is 2^18 (`format.md:57-59`).
- Columns are split into property groups, each group stored in its own files
  (`format.md:106-108`).
- The spec does not print the formula. It follows from "continuous" and
  "fixed": id = chunk_index * chunk_size + offset_in_chunk. The C++ reader
  implements exactly that: `chunk_index_ = id / vertex_info_->GetChunkSize()`
  (`graphar/cpp/src/graphar/arrow/chunk_reader.cc:227`) and
  `row_offset = seek_id_ - chunk_index_ * chunk_size` (same file, line 279).
- File path of a chunk: `<prefix>/<property group>/chunk<i>`
  (`graphar/maven-projects/spark/graphar/src/main/scala/org/apache/graphar/VertexInfo.scala:238-256`),
  for example `vertex/person/firstName_lastName_gender/chunk0`
  (`graphar/docs/libraries/cpp/getting-started.md:93`).
- The id is also stored: "the internal vertex id is stored in the payload file
  as a column", to help filter push-down; it is continuous, so delta encoding
  keeps it small (`format.md:114`). The column is named `_graphArVertexIndex`
  (`graphar/cpp/src/graphar/general_params.h:25`).

### Primary key

"In the logical vertex table, some property can be marked as the primary key,
such as the "id" column of the "person" table." (`format.md:100`). In the
vertex YAML every property has `is_primary` (`format.md:182`, example at
`format.md:187-209`). The original id is therefore an ordinary property column
in one of the property groups. Primary keys are implemented in all four
libraries (`implementation-status.md:65-68`).

### Edges

- One logical edge table per triplet (source label, edge label, destination
  label) (`format.md:122`).
- Four adjacency list types (`format.md:83-86`):

  | Type | Order | Partitioned by | The spec calls it |
  |---|---|---|---|
  | `ordered_by_source` | by source internal id | source | CSR |
  | `ordered_by_dest` | by destination internal id | destination | CSC |
  | `unordered_by_source` | none inside a part | source | COO |
  | `unordered_by_dest` | none inside a part | destination | COO |

- In the edge YAML a type is written as two fields: `ordered: true|false` and
  `aligned_by: src|dst` (`format.md:236-245`). "Aligned" means: the edge table
  is first cut into sub-tables, one per vertex chunk of the source (or the
  destination), and each sub-table is then cut into edge chunks of a fixed
  row count (`format.md:130-132`). Every type is aligned to one side. The spec
  has no unaligned layout. Recommended edge chunk size: 2^22 (`format.md:66-68`).
- An edge chunk has an adjList table with exactly two columns, the internal
  ids of source and destination, plus zero or more property group tables
  (`format.md:134-135`). Path:
  `<prefix>/<adjList type>/adj_list/part<vertex chunk>/chunk<edge chunk>`
  (`graphar/.../EdgeInfo.scala:440-441`).
- Offsets exist only for the two ordered types. "The offset table is used to
  record the starting point of the edges for each vertex. The partition of the
  offset table should be in alignment with the partition of the corresponding
  vertex table. The first row of each offset chunk is always 0"
  (`format.md:137`). So offsets restart at 0 in every vertex chunk: they are
  local to the `part<i>` sub-table, not global. Path:
  `<adjList type>/offset/chunk<i>` (`graphar/.../EdgeInfo.scala:397-398`).
- Ordered adjList plus offsets is the CSR (by source) or the CSC (by
  destination) (`format.md:145`). Several types may be stored for the same
  edges (`format.md:257`). All three layouts are implemented in all libraries
  (`implementation-status.md:94-98`).

### The 16 + 48 bit split

Not in the specification: `format.md` has no statement about bits of an id.
Not in GraphAr's code either: the id type is `using IdType = int64_t`
(`graphar/cpp/src/graphar/fwd.h:72`), and a search of the repository for a
48-bit or 16-bit shift or mask found nothing (two unrelated hits for the
number 48). `icebug/` has no such statement either: its mapping is "per node
type", with `csr_index` a "BIGINT-like integer" (`icebug/doc/spec.md:155-187`).

So the split is a convention outside the format. I could not find its origin.
As a design it is one expression on top of a per-group dense id:
`global = (group << 48) | dense`. One caution for this project's interface
rule (ids are i64 everywhere): 16 unsigned bits of group need the sign bit.
With i64 either the group is limited to 15 bits (32,768 groups) or ids of
groups 32,768 and above are negative.

### How GraphAr's own Spark library builds the index

This is the code the reviewer's `df.rdd.zipWithIndex` refers to.

- `IndexGenerator.generateVertexIndexColumn`: count rows per partition with
  `mapPartitionsWithIndex`, collect, prefix sums on the driver, broadcast, then
  a second `mapPartitionsWithIndex` that adds `start + j`
  (`graphar/.../util/IndexGenerator.scala:100-119`). The same in
  `constructVertexIndexMapping` (lines 62-78). No persist between the two
  passes: it relies on Spark recomputing the same partitions.
- Edges: join with the mapping for the source, then for the destination (two
  SQL inner joins, lines 174-211).
- Chunks: `ChunkPartitioner` sends a row to partition `index / chunk_size`
  and `repartitionAndSortWithinPartitions` sorts inside
  (`graphar/.../writer/VertexWriter.scala:47-53`, `util/Patitioner.scala:44-47`).
- Edge writer: global `sort`, `persist`, the same two-pass index, then
  repartition by vertex chunk (`graphar/.../writer/EdgeWriter.scala:68-90`).

icebug-format does the same job with SQL: `row_number() OVER (ORDER BY pk) - 1
AS csr_index` (`icebug/icebug_format/_convert_duckdb.py:90`,
`icebug/icebug_format/cli.py:592-597`). Its spec lists what any backend must
provide (`icebug/doc/spec.md:485-500`): "assigning zero-based dense IDs with
deterministic ordering", "joining edge tables to source and destination
mapping tables", "grouping emitted edges by `csr_source` to compute degrees",
"creating cumulative CSR offsets for all source node IDs from `0` to `N - 1`,
including nodes with degree zero". Section 4 below is that list, run on Sail.

## 2. What Sail has today for row indexing

### What exists and what does not

| Feature | State | Evidence |
|---|---|---|
| `row_number()` window | works; result type INT | run: `raw/probe-engine-local.jsonl` ("row_number result type": `int`). code: DataFusion's UInt64 result is cast to Int32, `sail/crates/sail-plan/src/function/common.rs:354`; registered at `sail/crates/sail-plan/src/function/window.rs:704` |
| running count as BIGINT | `count(1) over (order by k rows between unbounded preceding and current row)` gives `bigint` | run: same record, column `c` |
| `monotonically_increasing_id()` | works in a projection | code below; run: 10 partitions, max id 77,309,779,967 |
| `spark_partition_id()` | works in a projection; fails as a grouping expression ("was not rewritten into a partition-aware operator") | run: `raw/probe-engine-local.jsonl` |
| `mapInArrow`, `mapInPandas` | work; the function sees one partition as a batch stream and can keep a running index | run: same file (0.56 s and 0.51 s for 3.77M rows). code: `sail/crates/sail-physical-plan/src/map_partitions.rs` |
| `df.rdd`, `zipWithIndex` | not available: PySpark Connect raises `[NOT_IMPLEMENTED] rdd is not implemented` on the client | run: same file |
| `persist()` / `cache()` | accepted, does nothing | code: `sail/crates/sail-spark-connect/src/service/plan_analyzer.rs:166-173` ("not yet supported and is a no-op") |
| `checkpoint()` | works when `execution.checkpoint.path` is set; eager only; `localCheckpoint` takes the same path | run: error without the setting in `raw/probe-engine-local.jsonl`, success in `raw/probe-determinism-*.jsonl`. code: `sail/crates/sail-spark-connect/src/service/plan_executor.rs:508-531`, `sail/crates/sail-common/src/config/application.yaml:461-469` |
| `repartitionByRange` | accepted, but planned as hash partitioning | run: partition bounds overlap fully (`raw/probe-engine-local.jsonl`), plan shows `Hash([#0], 4)`. code: `sail/crates/sail-plan/src/resolver/query/repartition.rs:37-58` |
| `approxQuantile` | not implemented ("approx quantile") | run; code: `sail/crates/sail-plan/src/resolver/query/mod.rs:329-331` |
| `percentile_approx(col, array)` | fails in planning (array of percentages not accepted) | run: `raw/probe-engine-local.jsonl` |
| `input_file_name()` | unknown function | run; code: `sail/crates/sail-plan/src/function/scalar/misc.rs:284-286` (a TODO to map it to DataFusion's function) |
| `_metadata.row_index`, `_metadata.file_path` | not resolvable | run: `raw/probe-engine-local.jsonl` |
| `file_row_index()` | unknown function in Sail | run; see below |

### `monotonically_increasing_id` and `spark_partition_id`

code. The function is a marker. A resolver rewrite replaces it by a column of
a `MonotonicIdNode` placed under the projection
(`sail/crates/sail-plan/src/resolver/tree/monotonic_id.rs:38-67`). The physical
operator numbers the rows of each partition stream as they pass:
`(partition << 33) + position` (`sail/crates/sail-physical-plan/src/monotonic_id.rs:203-217`),
with an error above 2^33 rows in one partition (line 206). `partition` is the
index passed to `execute` (lines 131-143). `SparkPartitionIdExec` emits that
same index (`sail/crates/sail-physical-plan/src/spark_partition_id.rs:131-143, 206-208`).

Two properties matter for indexing.

1. The operator keeps its input's partitioning and says it maintains input
   order (`monotonic_id.rs:49, 100-102`), but it does **not** require an input
   order: there is no `required_input_ordering`, so the default "none" applies
   (`df/datafusion-physical-plan-55.1.0/src/execution_plan.rs:221-223`). The
   optimizer may therefore remove a sort below it (see "A sort under the id is
   not safe" below).
2. The id is a function of (partition index, position in the partition
   stream). It is exactly as repeatable as those two are.

### Is it deterministic across re-execution?

run: `raw/probe-determinism-local.jsonl`, `raw/probe-determinism-local-cluster.jsonl`.
Each case writes (key, partition, id) to Parquet several times and compares.
Input: the edge file (16.5M rows, 135 row groups, sorted by source and target).

| Input of the id | local: same partition sizes | local: same key-to-id | local-cluster: same partition sizes | local-cluster: same key-to-id |
|---|---|---|---|---|
| direct Parquet scan | no (6 different in 6) | no (6 in 6) | yes (1 in 6) | yes (1 in 6) |
| direct scan after SQL `SET datafusion.execution.enable_file_stream_work_stealing = false` | yes | yes | yes | yes |
| the same setting through `spark.conf.set` | no (6 in 6): the setting has no effect | no | yes | yes |
| `checkpoint()` | yes | yes | yes | yes |
| scan of a 4-file directory written by Sail | no (6 in 6) | no | yes | yes |
| `orderBy(key)` (one partition) | yes | yes | yes | yes |
| `repartition(10, source)` (hash shuffle) | yes | no (4 in 4): row order inside a partition is arrival order | yes | no (4 in 4) |
| `repartition(10, source).sortWithinPartitions(key)`, written to Parquet | yes | yes | yes | yes |

Why local mode is not repeatable. DataFusion 55 lets the partition streams of
one file scan take files (or byte ranges of a file) from a shared queue:
"Whichever stream becomes idle first may take the next unopened file"
(`df/datafusion-datasource-55.1.0/src/file_stream/work_source.rs:58-63`). The
option `enable_file_stream_work_stealing` is on by default
(`df/datafusion-common-55.1.0/src/config.rs:1002-1010`) and applies unless the
scan has `preserve_order` or a declared output partitioning
(`df/datafusion-datasource-55.1.0/src/file_scan_config/mod.rs:175-179, 1185-1196`).
Sail's listing scan sets `preserve_order: false`
(`sail/crates/sail-data-source/src/listing/planner.rs:192`).

Why cluster mode is repeatable. Each task runs partition `key.partition` of
its stage plan (`sail/crates/sail-execution/src/task_runner/preparation.rs:116`),
and the task runner rewrites every file scan with `with_preserve_order(true)`,
with the comment that otherwise "every task would scan every file" (same file,
lines 127-134). A checkpoint is read back with `with_preserve_order(true)` too
(`sail/crates/sail-session/src/planner.rs:335`).

So: deterministic in cluster mode for a file scan, not in local mode, and in
neither mode after a shuffle unless the partition is sorted on a unique key.

### A sort under the id is not safe

run: `raw/probe-determinism-local.jsonl`, record "aggregate over
sortWithinPartitions + monotonically_increasing_id". The frame
`repartition(10, source).sortWithinPartitions(source, target)` followed by
`monotonically_increasing_id()` and then an aggregate has **no `SortExec` in
its physical plan**, and gave 4 different results in 4 executions. The same
frame followed by a write keeps the sort.

run: `raw/bench-local.jsonl`, case `map_two_joins_inline_orderby_monotonic_id`.
A mapping built as `orderBy(id)` plus `monotonically_increasing_id()` and used
directly in two joins was planned as `MonotonicIdExec` over
`CoalescePartitionsExec` over the scan, twice (`raw/plans-local.txt`). The sort
is gone and the two copies number the rows independently. The mapped edges
differed from the reference in 3 of 3 runs, without any error.

code. Sort enforcement "removes an already-existing `SortExec` if it is
possible to prove that this sort is unnecessary"
(`df/datafusion-physical-optimizer-55.1.0/src/ensure_requirements/enforce_sorting/mod.rs:26-30`).
Nothing above the sort asks for the order, so the proof succeeds. Sail already
has the device to pin a sort for order-sensitive windows and aggregates:
`RequiredSortNode`, planned as a `SortExec` under an `OutputRequirementExec`
(`sail/crates/sail-session/src/planner.rs:427-450`). `monotonically_increasing_id`
does not use it.

Consequence for every option below: an id that comes from
`monotonically_increasing_id` must be written to storage (or checkpointed)
before it is used in a join or read twice. An id from a window function has
relational semantics and stays correct inline (run: case
`map_two_joins_inline_row_number`, 3 of 3 correct).

### Per-file row index and row counts

code. DataFusion 55.1.0 has a scalar function `file_row_index()`: "Returns the
zero-based row offset within the source file that produced the current row"
(`df/datafusion-functions-55.1.0/src/core/file_row_index.rs:30-49`). The
Parquet source rewrites it into a virtual column of extension type `RowNumber`
(`df/datafusion-datasource-parquet-55.1.0/src/source.rs:700-717, 1206-1251`;
`parquet/src/arrow/schema/virtual_type.rs:78-84`). Predicates on virtual
columns are not pushed into the reader's row filter (same `source.rs`,
lines 827-831), so the value stays the physical position.

run. Sail does not expose it: `unknown function: file_row_index` through
`call_function` and through SQL. code: Sail's own TODO, "Add SQL planner
support and distributed SQL tests for DataFusion's `file_row_index()`"
(`sail/crates/sail-execution/src/proto/encode.rs:39-40`). Sail uses the same
virtual column internally for Delta deletion vectors
(`sail/crates/sail-delta-lake/src/datasource/deletion_vector.rs:529`).

Row counts: Parquet footers hold them per file and per row group, and
DataFusion keeps per-partition statistics
(`df/datafusion-physical-plan-55.1.0/src/execution_plan.rs:723`). Sail collects
statistics by default (`application.yaml:410-412`). They are not exposed as a
column or a function, and the file a row came from is not exposed either.

## 3. Options for a dense index 0..n-1

n is the number of rows, P the number of partitions. "Repeatable" means a
second execution gives the same id to the same row.

| Option | Passes over the data | Shuffle | Sort | Driver memory | Result in key order | Repeatable | Engine work |
|---|---|---|---|---|---|---|---|
| a. `row_number() over (order by key)` | 1 | none in local mode; one gather in cluster mode | n log n, parallel per partition, one merge stream | none | yes | yes, if the key is unique | none |
| a'. `orderBy(key)` + `monotonically_increasing_id()` | 1 | as (a) | as (a) | none | yes | only when written at once (section 2) | none |
| b. two-pass `zipWithIndex` | 2 (count, then index) | none | none | P counts | no: partition order, then position | only on a repeatable input | none, but needs a checkpoint or a setting in local mode |
| c. native `RowIndexExec` | 1, or 1 + a count stage | none, or one range shuffle for the ordered form | none, or per partition | P counts in the plan | optional | yes, by construction | change in Sail; a one-stream form fits an extension |
| d. index from file metadata | 1, counts come from footers | none | none | one count per file | no: file order, then position | yes while the files do not change | small change in Sail |
| e. distinct + sort + index | 1 plus a hash aggregate | one hash shuffle for the distinct | as (a), or per bucket | none, or B bucket counts | yes | yes | none |
| f. write in fixed-size chunks | after any of the above: 1 | one hash shuffle by chunk | inside a chunk | none | by construction | yes | client-only for a Hive-style layout; a sink for GraphAr's file names |

### a. `row_number() over (order by key)`

Plan today (run: `raw/plans-local.txt`, `a_row_number`):

```
RepartitionExec: RoundRobinBatch(10), input_partitions=1
  BoundedWindowAggExec: row_number() ORDER BY [id ASC]      one partition
    SortPreservingMergeExec: [id ASC]                       one stream
      SortExec: [id ASC], preserve_partitioning=[true]      one sort per partition, in parallel
        DataSourceExec: 10 file groups
```

A window without `PARTITION BY` requires a single partition
(`df/datafusion-physical-plan-55.1.0/src/windows/bounded_window_agg_exec.rs:451-455`).
So it is not "a global sort in one partition": the sort is parallel, and the
merge and the numbering are one stream.

- Correct when: always (window semantics). Repeatable when the key is unique;
  ties are numbered in arrival order.
- Cost: one scan, P parallel sorts, a P-way merge and a counter on one core.
  The sort holds its input in memory, or spills with a bounded pool
  (`df/datafusion-physical-plan-55.1.0/src/sorts/sort.rs:97-112`; measured in
  section 5.4).
- Cluster mode: `SortPreservingMergeExec` is a stage boundary
  (`sail/crates/sail-execution/src/job_graph/planner.rs:371-376`). Workers sort,
  then one task receives every row, merges and numbers. All data passes
  through one task.
- Where it breaks.
  1. The result is INT (`common.rs:354`). Above 2^31 - 1 rows the cast cannot
     hold the value. I did not run that many rows, so the behaviour (error or
     wrap) is unknown. The BIGINT running count has the same plan (case
     `a_running_count_bigint`) and no such limit.
  2. One stream: throughput is bounded by one core for the merge and the
     counter, and in cluster mode by one task's network input.
  3. The rows leave the window through a round-robin repartition. A write
     after it is not in id order (run: `a_row_number_one_output_file`, the
     single output file was sorted in 2 of 3 runs). Ask for the order again
     (`orderBy("dense")`, case `a_row_number_then_order_one_output_file`,
     sorted in 3 of 3 in local mode).
- Engine work: none.

Variant a': `orderBy(key)` ends in one partition, so
`monotonically_increasing_id()` is 0..n-1 in key order and BIGINT, up to 2^33
rows (run: `a_orderby_monotonic_id`, correct 3 of 3 when written at once). It
saves the window. It is only safe when the frame is written immediately
(section 2). `coalesce(1)` plus the id gives 0..n-1 in arrival order with no
sort at all (run: `a_coalesce1_monotonic_id`, exact, a different order in
every run).

### b. The classic two-pass `zipWithIndex`

Recipe: pass 1 counts rows per partition
(`select(spark_partition_id()).groupBy().count()`), the driver takes prefix
sums, pass 2 computes `offset[partition] + (monotonically_increasing_id() & (2^33 - 1))`.
The offsets travel in the plan as an array literal (plan in `raw/plans-local.txt`,
`b_two_pass_direct_scan`).

- What it needs from the engine: both passes must see the same rows in the
  same partition, in the same order. Sail has no `persist` (a no-op), so every
  action re-executes its plan.
- What Sail guarantees (section 2): nothing in local mode on a file scan; a
  repeatable scan in cluster mode; a repeatable scan of a checkpoint in both
  modes; never after a shuffle unless sorted on a unique key.
- run: on a direct scan in local mode the result was wrong in 3 of 3 runs,
  and in 3 of 3 runs of the first pass: 122,880 or 157,392 duplicate ids, or
  no duplicate and a gap. With the SQL setting, after a checkpoint, and in
  local-cluster mode: exact 0..n-1 in 3 of 3.
- Safe forms.
  - `b_two_pass_checkpoint`: `checkpoint()` first. Needs
    `execution.checkpoint.path`. One extra write and read of the table.
  - `b_one_pass_materialized`: write `(id, monotonically_increasing_id())`
    once; the partition (`m >> 33`) and the position (`m & mask`) are then
    data. Count and add offsets from that table. Needs no setting and does not
    depend on how the engine partitions the second read.
  - `SET datafusion.execution.enable_file_stream_work_stealing = false` in SQL
    (it stays for the session; `spark.conf.set` does not work).
- Cost: two cheap passes, no sort, no shuffle. Driver memory: P integers.
- Order: partition, then position. With a repeatable scan of a sorted file
  that is file order. It is not key order in general. A mapping built this way
  is not repeatable across runs unless the checkpoint is kept (run: each run
  of the checkpoint cases gave a different mapping in local mode).
- Limits: 2^33 rows per partition.
- A small Arrow map function in place of the native operator works too
  (`b_map_in_arrow_checkpoint`). It needs the partition id passed in as a
  column and costs a Python worker per partition.
- Engine work: none. In local mode it needs the checkpoint path or the SQL
  setting.

### c. A native operator (design only)

Three forms, from small to large.

**c1. One stream, numbered as it passes.** `RowIndexExec { input, column, order: Option<LexOrdering> }`.

- `required_input_distribution` = `SinglePartition`; `required_input_ordering`
  = the order, when one is given. That pins the sort, which
  `MonotonicIdExec` does not do.
- `execute(0)`: wrap the input stream, append an `Int64` column from a
  running counter. It is `MonotonicIdExec` with the partition term removed
  (`monotonic_id.rs:203-217`), about the same 250 lines.
- Local mode: the planner inserts `CoalescePartitionsExec` or
  `SortPreservingMergeExec` below it. One pass, no state, BIGINT, output in
  order. Cluster mode: the gather is a stage boundary
  (`job_graph/planner.rs:371-376`); one task numbers all rows.
- It is option (a) without the INT cast, without the window machinery, and
  with its order pinned. The gain over (a) is safety and width, not speed.
- inferred: this form fits an extension relation today. The extension
  contract gives a relation plugin its inputs as execution plans and asks for a
  table provider back (`sail/examples/extensions/WRITING-AN-EXTENSION.md:156-162`),
  and a driver-resident relation "must produce exactly one partition"
  (`sail/crates/sail-session/src/extensions/driver.rs:89-91`). A
  `zip_with_index(df)` relation that drains its input and numbers the rows
  satisfies both. It runs on the driver in cluster mode
  (`WRITING-AN-EXTENSION.md:30-31`).

**c2. Parallel, with offsets in the plan.** `RowIndexExec { input, column, offsets: Vec<u64> }`.

- Keeps the input partitioning. `execute(p)` adds `offsets[p]` plus a running
  counter. Row order inside a partition and partition membership must be
  fixed, so the operator has to force `preserve_order(true)` on file scans
  below it, as the cluster task runner already does (`preparation.rs:127-134`).
- Where the offsets come from.
  1. Plan time, no pass: exact per-partition row counts from statistics
     (`execution_plan.rs:723`) when the child is a file scan of whole files
     with footer counts and no filter. This is option (d) inside the operator.
  2. A count stage: run the child once to count, then again with the offsets.
     Local mode: inside the operator, behind a shared `OnceCell`. Cluster
     mode: stage A = child fragment, output = one count per partition to the
     driver; stage B = child fragment again + `RowIndexExec(offsets)`.
  3. A count stage that also materialises: stage A = child, written to
     shuffle storage one-to-one, row counts reported; stage B = shuffle read +
     `RowIndexExec(offsets)`. The child runs once, so its determinism no
     longer matters.
- What Sail already has for this: stage boundaries whose output can be read
  more than once ("the shuffle writer can materialize the data for multiple
  consumption", `job_graph/planner.rs:378-379`), driver stages
  (`job_graph/planner.rs:909-924`), and a job that runs first and whose result
  is placed into the consumer's plan for uncorrelated scalar subqueries
  (`job_graph/planner.rs:223-226, 293-297`). What it lacks: a stage whose plan
  is completed from the row counts of an earlier stage. That is a change in
  the driver.
- The scalar-subquery route also gives a form with no new job-graph feature:
  express the offsets as an uncorrelated scalar subquery over the count query.
  inferred, not tried.

**c3. Ordered and parallel.** `RangeRepartition(split points)` then
`SortExec(preserve_partitioning)` then `RowIndexExec(offsets)`.

- DataFusion 55.1.0 has `Partitioning::Range` with explicit split points
  (`df/datafusion-physical-expr-55.1.0/src/partitioning.rs:127-128, 155-208`),
  and `RepartitionExec` executes it
  (`df/datafusion-physical-plan-55.1.0/src/repartition/mod.rs:1054-1056`).
  Sail's distributed shuffle writer accepts it
  (`sail/crates/sail-execution/src/plan/shuffle_write.rs:37, 232-238`;
  `job_graph/planner.rs:443, 761`). Nothing in Sail's resolver produces it
  today: `repartitionByRange` becomes a hash (section 2). DataFusion's own note
  on the type reads: "Optimizer and execution behavior for this partitioning is
  intentionally not implemented and will be introduced incrementally"
  (`partitioning.rs:200-202`), so this path is new and thinly used.
- Split points come from a sample (one more small job) or from Parquet
  min/max statistics.
- Result: P sorted, range-disjoint partitions with dense ids in key order.
  No single stream anywhere. Each partition sorts externally on its own.
- This is the form that scales out. It is also the largest change.

**What an extension can and cannot add today** (code:
`WRITING-AN-EXTENSION.md:39-43, 134-162, 178-183`).

| Can | Cannot |
|---|---|
| a relation that takes DataFrames and returns a table provider (c1) | a new physical operator that runs per partition on workers inside a host stage |
| a scalar UDF that runs on workers | a scalar UDF that knows its partition or keeps a counter across batches: it sees one batch at a time (inferred from the scalar UDF interface) |
| a mutating relation that consumes inputs and writes files (a GraphAr sink, on the driver) | a new plan-rewriting function such as `monotonically_increasing_id` (resolver, logical node, physical node, codec: `planner.rs:383-409`, `sail/crates/sail-execution/src/proto/codec.rs:1434-1445, 2672-2684`) |
| | a change to the job graph (c2, c3), or exposing `file_row_index()` |

The fork also has a `worker` placement for relations
(`sail/crates/sail-session/src/extensions/manifest.rs:48-68`). I did not study
whether it could host c2.

### d. Index from file metadata

Idea: `dense = base[file] + file_row_index()`, with `base` the prefix sums of
the footers' row counts over the files in a fixed order.

- No counting pass and no dependence on partitioning, work stealing, file
  splitting or pushed-down filters: the row number is the physical position in
  the file (section 2).
- Requires: a defined file order (sort by path), files that do not change
  (for Delta or Iceberg: one snapshot), and the row's file. Sail exposes
  neither `file_row_index()` nor the file of a row.
- Order: file order, then position. Key order only if the files were written
  sorted.
- Engine work, inferred: (1) register `file_row_index` and cover the
  distributed codec, which is Sail's own TODO (`encode.rs:39-40`); (2) give the
  listing table a per-file constant, the base or the file ordinal, in the way
  partition columns are attached to a file. With (1) alone and
  `input_file_name()` the client could do the rest.
- For GraphAr this is the read side of (f): the chunk file `chunk<i>` has
  base `i * chunk_size`. In practice it is not even needed there: the chunk
  files carry the id as a column (`format.md:114`).

### e. Sorted dense ids for vertices keyed by an origin id

The mapping table `(origin_id, dense_id)` with dense order equal to origin
order. Sorted by one column means sorted by the other, so it merges on either
side. It also needs no stored `dense_id`: the dense id is the row position in
the sorted list of origin ids. A GraphAr vertex chunk with the primary key
property is exactly that table.

- e1. `select distinct id` then (a). Plan: partial and final hash aggregate
  around a hash shuffle, then the plan of (a) (`raw/plans-local.txt`,
  `e_distinct_row_number`). From an edge table: union of the two endpoint
  columns, then the same (`e_from_edges_row_number`).
- e2. Range buckets, client only (`e_bucketed_row_number`). Take a sample,
  choose B - 1 bounds, compute a bucket per row with a binary-search `CASE`,
  count rows per bucket (an aggregate, so it is data and repeatable), prefix
  sums on the driver, then
  `offset[bucket] + row_number() over (partition by bucket order by id) - 1`.
  Plan: hash shuffle on the bucket, sort by (bucket, id) per partition, window
  per partition. No single stream, so it runs in parallel in cluster mode
  today. The INT limit applies per bucket only. Skewed bounds cost time, not
  correctness. A linear chain of comparisons for the bucket is a trap: at 255
  comparisons a row it cost 100 CPU seconds for 50M rows (run:
  `raw/bench-scale-unbounded-linear-buckets.jsonl`).
- e3. The native form is c3.
- Correct when: always. Repeatable: yes, the id is the rank of the key.
- Engine work: none for e1 and e2.

### f. Writing with a fixed chunk size, as GraphAr does

Given dense ids, `chunk = dense div chunk_size`, one file per chunk, rows in
id order inside. Then id = chunk * chunk_size + offset holds by construction
and a reader needs no index at all.

- Today, client only: `repartition(k, chunk).sortWithinPartitions("dense")`
  then `write.partitionBy("chunk")`. The hash repartition puts a whole chunk in
  one partition. The layout is Hive-style (`chunk=<i>/<name>.parquet`), not
  GraphAr's `chunk<i>`; a rename pass or a sink is needed for the exact names.
  Not run here. The sibling note
  [`../../sail-partitionby-write-2026-10-02/README.md`](../../sail-partitionby-write-2026-10-02/README.md)
  measured `partitionBy` writes at 5 to 45 times a plain write, worst with
  many partition values; a 2^18-row chunk size on 3.77M vertices means 15
  values, on 280M vertices more than 1,000.
- One sorted file needs one more thing: DataFusion's writer spreads one
  stream over `minimum_parallel_output_files` = 4 files round robin
  (`df/datafusion-common-55.1.0/src/config.rs:951-955`,
  `df/datafusion-datasource-55.1.0/src/write/demux.rs:158-226`). run: after
  `orderBy` every file is sorted on its own, but the files are interleaved.
  `SET datafusion.execution.minimum_parallel_output_files = 1` gave one sorted
  file in local mode (3 of 3) and had no effect in local-cluster mode (4 files,
  3 of 3).
- Engine work: client-only for the Hive layout; an extension sink (driver) or
  a writer option for GraphAr's names and for exact chunk boundaries.

## 4. From the index to a CSR inside the engine

Input: the mapping `(id, dense)` per vertex group, and an edge table
`(source, target)`. All steps below were run on cit-Patents and checked against
a NumPy reference (section 5).

| Step | DataFrame code | Physical plan today (run: `raw/plans-local.txt`) | Shuffles | Sorts |
|---|---|---|---|---|
| map both endpoints | `e.join(m_src, "source").join(m_dst, "target")` | two `HashJoinExec mode=Partitioned`; each side of each join goes through `RepartitionExec Hash(key, 10)` | 4 hash repartitions: edges by source, joined edges by target, the mapping twice | none |
| sort | `.orderBy("s", "d")` | `SortExec` per partition, `SortPreservingMergeExec` | none in local mode; one gather in cluster mode | one, external with a bounded fair pool |
| offsets | `groupBy("s").count()`, left join onto `range(n + 1)`, running sum | partial and final hash aggregate, `HashJoinExec Left`, sort by vertex, `SortPreservingMergeExec`, `BoundedWindowAggExec sum(...) ROWS UNBOUNDED PRECEDING AND 1 PRECEDING` in one partition | 2 hash repartitions | one over n + 1 rows |

Notes.

- Two joins against one join plus a re-key. The one-join form unpivots every
  edge into two rows, joins once, and groups by an edge id to put the halves
  together. It needs an edge id, which is another index, and it aggregates 2m
  rows. It was slower than two joins (section 5.2). When the edge id came from
  `monotonically_increasing_id()` over two separate scans (a union of two
  selections), the result was wrong in local mode in 3 of 3 runs: 16.76M to
  17.82M output rows for 16.52M edges (case `map_one_join_rekey_two_scans`).
- If both endpoints belong to the same vertex group, the mapping is read
  twice. For two groups the two joins use two mappings. A CSR is per edge
  type, as in GraphAr and icebug.
- The planner chose partitioned joins. The mapping is small (n rows of 16
  bytes), so a broadcast join would avoid shuffling the edges. Not explored.
- Vertices without edges: the left join from `range(n + 1)` keeps them. On
  cit-Patents 1,685,423 of 3,774,768 vertices have no outgoing edge, and the
  offsets matched the reference.
- The running sum for offsets is the same primitive as the dense index: a
  prefix scan in one stream. The consumer can also derive the offsets from the
  sorted source column in one pass, so the engine-side offsets are optional.
- If the input is already GraphAr or icebug-disk, the edges are stored with
  dense ids, sorted, with offsets. None of the steps above is needed on read.
  The index is needed on conversion into those formats.

### The contract this gives the consumer

1. `edges(s BIGINT, d BIGINT)`: dense ids in [0, n), sorted by (s, d). As a
   stream it is in order. As Parquet, one file in order with the setting of
   3f, otherwise several files that are each in order.
2. `n`: the vertex count of the group.
3. Optional `offsets(v BIGINT, offset BIGINT)`: n + 1 rows, offset[n] = m.
4. The mapping `(id, dense)` stays in the engine. Results come back as
   `(dense, value)`. Mapping back is `result.join(mapping, "dense")`, or a
   positional lookup when the mapping is stored sorted.

Banda then needs no id map and no sort. Today its staging does both in
process: the stage receipt reports the memory of its own sort and copy
(`nodeSortPermutationBytes`, `edgeSortedCopyBytes` and others,
`sail/examples/extensions/nutmeg/src/mutation.rs:94-112`). Pecan gets i64 ids
in a known order from the same tables.

## 5. Prototypes and micro-benchmarks

Scripts: `bench_dense_ids.py` (cit-Patents), `bench_scale.py` (50M synthetic
ids), `probe_engine.py`, `probe_determinism.py`, `probe_external_sort.py`,
`sailserver.py` (starts one server on a free port, as
`partitionby_probe.py` does), `summarize.py`.

To run again (one server at a time; `SAIL_BIN` selects another binary):

```sh
PY=~/src/sail-pecan-integrated/.venv/bin/python
$PY probe_engine.py local            > raw/probe-engine-local.jsonl
$PY probe_determinism.py local       > raw/probe-determinism-local.jsonl
$PY bench_dense_ids.py local 3       > raw/bench-local.jsonl      # also local-cluster
$PY bench_scale.py 50000000 3 unbounded > raw/bench-scale-unbounded.jsonl   # or fair:512
$PY probe_external_sort.py 50000000  > raw/probe-external-sort.jsonl
$PY summarize.py raw/bench-local.jsonl
```

Server settings: `SAIL_MODE=local` (or `local-cluster`), every other setting
at its default: `execution.default_parallelism` 0, which gave 10 partitions;
memory pool `unbounded`. `SAIL_EXECUTION__CHECKPOINT__PATH` pointed at a
scratch directory. Extensions off. One server for all cases of a file, input
files read once before timing. The tables are from the final pass (load
average 11 to 23 during the local run); an earlier complete pass under heavier
load is kept in `raw/first-pass/` and agrees on every exactness check.

Every case ends in a Parquet write and is timed from the first request to the
end of the write, three runs. The written files are then checked outside the
engine with PyArrow and NumPy: sorted(dense) equals 0..n-1 (no gap, no
duplicate), the id set equals the input's, ids taken in dense order are
strictly increasing, and a BLAKE2 fingerprint of that sequence is compared
across the three runs.

Input: `cit-Patents-v.parquet`, 3,774,768 rows, column `id` BIGINT, distinct,
range 1 to 6,009,554, stored in id order, 31 row groups;
`cit-Patents-e.parquet`, 16,518,947 rows, 135 row groups.

### 5.1 Indexing the vertices, local mode

run: `raw/bench-local.jsonl`, plans in `raw/plans-local.txt`. Wall seconds:
median of three, range in brackets. "Exact" is the NumPy check: sorted(dense)
equals 0..n-1 and the id set equals the input's.

| Case | Option | Wall s | Server CPU s | Exact 0..n-1 | Dense follows id order | Same mapping in all three runs |
|---|---|---|---|---|---|---|
| `a_row_number` | a | 0.19 (0.19 to 0.20) | 0.46 | 3 of 3 | yes | yes |
| `a_running_count_bigint` | a, BIGINT | 0.35 (0.34 to 0.37) | 0.61 | 3 of 3 | yes | yes |
| `a_orderby_monotonic_id` | a' | 0.13 (0.12 to 0.13) | 0.38 | 3 of 3 | yes | yes |
| `a_coalesce1_monotonic_id` | a', no sort | 0.05 (0.05 to 0.06) | 0.27 | 3 of 3 | no | no |
| `b_two_pass_direct_scan` | b, as in Spark | 0.08 (0.08 to 0.10) | 0.42 | **0 of 3** | | |
| `b_two_pass_direct_scan_no_work_stealing` | b, with the SQL setting | 0.09 (0.08 to 0.10) | 0.42 | 3 of 3 | yes (the file is in id order) | yes |
| `b_two_pass_checkpoint` | b, after `checkpoint()` | 0.12 (0.12 to 0.12) | 0.64 | 3 of 3 | no | no |
| `b_one_pass_materialized` | b, id written once | 0.14 (0.13 to 0.15) | 0.71 | 3 of 3 | no | no |
| `b_map_in_arrow_checkpoint` | b, Arrow map function | 0.39 (0.36 to 0.59) | 0.99 | 3 of 3 | no | no |
| `e_distinct_row_number` | e1 | 0.27 (0.27 to 0.30) | 0.76 | 3 of 3 | yes | yes |
| `e_bucketed_row_number` | e2, 64 buckets | 0.28 (0.26 to 0.28) | 0.91 | 3 of 3 | yes | yes |
| `e_from_edges_row_number` | e1, ids from the edge endpoints | 0.41 (0.40 to 0.43) | 1.82 | 3 of 3 | yes | yes |
| `e_from_edges_bucketed` | e2, ids from the edge endpoints | 0.91 (0.84 to 0.92) | 4.83 | 3 of 3 | yes | yes |

What the table shows.

- (a) and (e) are exact, in id order and identical in every run. That is the
  reviewer's "sorted dense ids" with no engine work.
- (b) on a direct scan failed every time. The three runs had 157,392
  duplicates; a gap (largest id 3,932,159 for 3,774,768 rows); 122,880
  duplicates. The first pass (`raw/first-pass/bench-local.jsonl`) failed 3 of 3
  as well. 122,880 is one row group.
- The safe forms of (b) are exact but give a different mapping in every run in
  local mode, because every run takes a new checkpoint from a scan that is
  itself not repeatable. With the SQL setting the mapping is repeatable and
  follows file order.
- The BIGINT running count costs 0.16 s more than `row_number` on 3.77M rows.
- The vertex file is stored in id order, so the sort here is the easy case.
  Section 5.3 has unsorted input.
- These are 0.05 to 0.9 s statements. Fixed costs (planning, the write, the
  round trip) are a large share. Read the order of magnitude, not the ratios.

### 5.2 Mapping and sorting the edges, local mode

run: `raw/bench-local.jsonl`. The mapping is the output of `a_row_number`,
read back from Parquet (4 files). "Matches" compares the full sorted (s, d)
list with a NumPy reference (`searchsorted` on the sorted ids, `lexsort`).

| Case | What | Wall s | Server CPU s | Matches the reference | Written files |
|---|---|---|---|---|---|
| `map_two_joins` | two joins, no sort | 0.54 (0.53 to 0.69) | 3.14 | 3 of 3 | 4, unordered |
| `map_two_joins_sort` | two joins, `orderBy(s, d)` | 1.58 (1.56 to 1.60) | 6.09 | 3 of 3 | 4, each sorted, interleaved |
| `sort_only` | `orderBy(s, d)` of already mapped edges | 1.06 (1.05 to 1.09) | 4.57 | 3 of 3 | 4, each sorted, interleaved |
| `sort_only_one_output_file` | the same with `minimum_parallel_output_files = 1` | 1.12 (1.05 to 1.31) | 4.59 | 3 of 3 | 1, sorted, 3 of 3 |
| `map_two_joins_inline_row_number` | two joins, mapping computed inline by `row_number` | 0.79 (0.79 to 0.83) | 3.48 | 3 of 3 | 4, unordered |
| `map_two_joins_inline_orderby_monotonic_id` | two joins, mapping inline by `orderBy` + `monotonically_increasing_id` | 0.53 (0.46 to 0.79) | 3.18 | **0 of 3** | |
| `map_one_join_rekey` | one join on unpivoted endpoints, group by edge id | 1.44 (1.24 to 2.54) | 8.11 | 3 of 3 | 4, unordered |
| `map_one_join_rekey_two_scans` | the same, edge id computed in two scans | 0.94 (0.86 to 1.52) | 5.36 | **0 of 3** (16.76M to 17.82M rows for 16.52M edges) | |
| `offsets_from_sorted` | n + 1 offsets from the sorted edges | 0.69 (0.69 to 0.75) | 1.40 | 3 of 3 | 4 |
| `a_row_number_one_output_file` | the vertex index, one output file | 0.20 (0.19 to 0.29) | 0.45 | exact 3 of 3 | 1, sorted in 2 of 3 |
| `a_row_number_then_order_one_output_file` | the same, then `orderBy(dense)` | 0.29 (0.28 to 0.33) | 0.59 | exact 3 of 3 | 1, sorted in 3 of 3 |

What the table shows.

- The whole contract for cit-Patents: index 0.2 s, map and sort 1.6 s,
  offsets 0.7 s. About 2.5 s, of which the sort of 16.5M pairs is about 1 s.
- Two joins are cheaper than one join plus a re-key (0.54 s against 1.44 s).
- The two failing rows are the hazard of section 2, reached with ordinary
  DataFrame code and no error.
- For comparison only, a different program under different conditions: the
  native floor F0 reads the same two files, maps the ids and builds a directed
  CSR in 0.22 s on 4 threads (0.42 s undirected)
  ([`../../sem-review-capitola-2026-10-02/F0/README.md`](../../sem-review-capitola-2026-10-02/F0/README.md)).
  For a graph that fits in memory, mapping and sorting in the engine is not
  faster than doing it in process. What the engine can add is a bounded peak
  and sizes beyond memory. That has to be measured (section 6).

### 5.2b The same cases in local-cluster mode

run: `raw/bench-local-cluster.jsonl`, plans in `raw/plans-local-cluster.txt`.
`SAIL_MODE=local-cluster`: a driver and four workers as threads of one
process, tasks and shuffles as in a cluster, no network. It shows behaviour,
not cluster performance.

| Case | Wall s | Server CPU s | Exact, or matches the reference | Dense follows id order | Same result in all three runs |
|---|---|---|---|---|---|
| `a_row_number` | 0.19 (0.19 to 0.20) | 0.88 | 3 of 3 | yes | yes |
| `a_running_count_bigint` | 0.36 (0.35 to 0.38) | 1.05 | 3 of 3 | yes | yes |
| `a_orderby_monotonic_id` | 0.12 (0.11 to 0.14) | 0.46 | 3 of 3 | yes | yes |
| `a_coalesce1_monotonic_id` | 0.07 (0.06 to 0.08) | 0.35 | 3 of 3 | no | yes here; no in the first pass (3 different) |
| `b_two_pass_direct_scan` | 0.13 (0.12 to 0.14) | 0.59 | **3 of 3** | yes (file order) | yes |
| `b_two_pass_checkpoint` | 0.15 (0.15 to 0.16) | 0.78 | 3 of 3 | yes | yes |
| `b_one_pass_materialized` | 0.21 (0.21 to 0.25) | 1.04 | 3 of 3 | yes | yes |
| `b_map_in_arrow_checkpoint` | 0.41 (0.37 to 0.66) | 1.16 | 3 of 3 | yes | yes |
| `e_distinct_row_number` | 0.30 (0.29 to 0.31) | 1.31 | 3 of 3 | yes | yes |
| `e_bucketed_row_number` | 0.29 (0.29 to 0.31) | 1.18 | 3 of 3 | yes | yes |
| `e_from_edges_row_number` | 0.54 (0.53 to 0.58) | 2.97 | 3 of 3 | yes | yes |
| `e_from_edges_bucketed` | 1.34 (1.32 to 1.40) | 7.35 | 3 of 3 | yes | yes |
| `map_two_joins` | 0.95 (0.91 to 1.10) | 6.37 | 3 of 3 | | yes |
| `map_two_joins_sort` | 2.08 (2.04 to 2.22) | 9.44 | 3 of 3 | | yes |
| `map_two_joins_inline_row_number` | 1.16 (1.12 to 1.26) | 7.42 | 3 of 3 | | yes |
| `map_two_joins_inline_orderby_monotonic_id` | 1.13 (1.06 to 1.57) | 6.39 | **0 of 3** | | yes |
| `map_one_join_rekey` | 2.44 (2.44 to 2.62) | 15.23 | 3 of 3 | | yes |
| `map_one_join_rekey_two_scans` | 1.83 (1.82 to 1.88) | 12.71 | 3 of 3 | | yes |
| `sort_only` | 1.39 (1.38 to 1.40) | 5.48 | 3 of 3 | | yes |
| `offsets_from_sorted` | 0.75 (0.72 to 0.75) | 2.40 | 3 of 3 | | yes |

What changes against local mode.

- The two-pass index on a direct scan is exact and repeatable, as the code
  says it should be. So is the re-key with an edge id from two scans.
- The inline `orderBy` + `monotonically_increasing_id` mapping still differs
  from the id-ordered reference in 3 of 3 runs: the plan has lost the sort in
  this mode too. The result is the same in every run. I did not check whether
  it is a consistent relabelling in arrival order or an inconsistent one.
- The joins cost twice the CPU: every hash repartition is a shuffle through
  the workers.
- `SET datafusion.execution.minimum_parallel_output_files = 1` has no effect:
  4 output files in 3 of 3 runs, each sorted, interleaved. inferred: the
  session setting does not reach the worker's writer. A consumer of the files
  has to merge them.

### 5.3 The vertex options at 50M rows

run: `raw/bench-scale-unbounded.jsonl`, `raw/bench-scale-fair-512.jsonl`.
50,000,000 distinct pseudo-random BIGINT ids (`xxhash64` of 0..n-1), unsorted,
written by Sail to 4 Parquet files (412 MB). Local mode, 10 partitions, three
runs, median and range of wall seconds. 256 buckets for the bucketed case.

| Case | Unbounded pool: wall s | Server CPU s | Fair pool of 512 MiB: wall s | Exact 0..n-1 | Dense follows id order | Same mapping in every run |
|---|---|---|---|---|---|---|
| `a_sort_only`: `orderBy(id)`, no index | 2.20 (2.18 to 2.21) | 7.8 | 3.02 (2.90 to 3.83) | | | |
| `a_row_number` | 3.11 (3.10 to 3.12) | 10.1 | 4.43 (3.72 to 4.58) | 3 of 3 | 3 of 3 | yes |
| `b_one_pass_materialized` | 1.23 (1.20 to 1.31) | 7.0 | 1.33 (1.22 to 1.59) | 3 of 3 | no | no |
| `b_two_pass_no_work_stealing` | 0.65 (0.65 to 0.79) | 4.1 | 0.71 (0.69 to 0.77) | 3 of 3 | no | yes |
| `e_bucketed_row_number` | 6.38 (6.36 to 6.95) | 37.1 | 7.64 (6.58 to 8.68) | 3 of 3 | 3 of 3 | yes |

What the table shows.

- The index costs about 0.9 s on top of a 2.2 s sort: 50M rows through the
  one-stream merge, the counter and a write that is twice as wide. On one
  machine the single stream is not the bottleneck at this size.
- Without a sort (b) the index is 3 to 5 times cheaper than (a). That is the
  price of key order.
- The bucketed form is twice as slow as (a) in local mode: it adds a hash
  shuffle of every row, a second pass for the counts and the bucket
  expression. Its reason to exist is cluster mode, where (a) sends every row
  through one task. With the first, linear bucket expression it took 17.6 s
  and 100 CPU seconds (`raw/bench-scale-unbounded-linear-buckets.jsonl`).

### 5.4 Does the sort spill, or fail?

run: `raw/probe-external-sort.jsonl`. The same 50M ids (about 400 MB of keys).
A fresh local-mode server per pool setting, one run each. Peak RSS is the
server's resident set during the statement, sampled with `ps` every 0.02 s; it
includes what the process already held after generating the input.

| Memory pool | `orderBy(id)` to Parquet | Peak RSS | `row_number() over (order by id)` to Parquet | Peak RSS |
|---|---|---|---|---|
| unbounded (default) | 2.16 s | 1,021 MiB | 3.10 s | 1,083 MiB |
| greedy, 2,048 MiB | 2.14 s | 1,031 MiB | 3.07 s | 1,115 MiB |
| greedy, 1,024 MiB | 2.14 s | 1,045 MiB | 3.07 s | 1,130 MiB |
| greedy, 512 MiB | **fails** after 0.05 s | | **fails** after 0.32 s | |
| fair, 2,048 MiB | 2.17 s | 1,007 MiB | 3.87 s | 1,137 MiB |
| fair, 1,024 MiB | 2.86 s | 1,084 MiB | 3.97 s | 1,124 MiB |
| fair, 512 MiB | 3.01 s | 793 MiB | 3.70 s | 830 MiB |
| fair, 256 MiB | 2.79 s | 672 MiB | 3.73 s | 817 MiB |

- With the `fair` pool the sort completes below its data size, 0.6 to 0.9 s
  slower, with a lower peak. That is the external sort the reviewer counts on.
- With the `greedy` pool at 512 MiB the statement fails: "Failed to allocate
  additional 64.0 KB for ExternalSorterMerge[7] ... 23.0 KB remain available
  for the total memory pool: greedy(used: 512.0 MB, pool_size: 512.0 MB)".
  The same in 3 of 3 runs of the earlier pass
  (`raw/bench-scale-greedy-512-linear-buckets.jsonl`). I did not find out why
  the pool is full that early. A deployment that relies on spilling should use
  the `fair` pool (`runtime.memory_pool.type`, `application.yaml:21-32`).
- RSS stays above the pool size: the pool counts what operators reserve, not
  readers, writers and the allocator.

### 5.5 The probes on unmodified upstream

run: `raw/upstream/probe-engine-local.jsonl`,
`raw/upstream/probe-determinism-local.jsonl`. Binary
`~/src/sail-upstream-main/target/release/sail`, worktree at `99ee46f69`, local
mode. The findings of section 2 are the same:

- the same functions exist and the same are missing (`file_row_index`,
  `input_file_name`, `_metadata`, `approxQuantile`); `row_number` is INT;
  `persist` is a no-op; `repartitionByRange` is a hash;
- a direct scan is not repeatable (6 different key-to-id assignments in 6);
  it is after the SQL setting, not after `spark.conf.set`; a checkpoint is
  repeatable; a hash shuffle is not (4 in 4);
- the sort under `monotonically_increasing_id` is removed when an aggregate
  consumes the result.

One difference. On upstream a partition of a direct scan is not in file order:
73 to 84 of 16.5M rows are out of key order on the sorted edge file, 20 with
work stealing off, 65 after a checkpoint. On the fork binary these counts are
0. So on upstream the index of option (b) does not follow file order even when
it is repeatable. The benchmark itself was run on the fork binary only.

## 6. Recommendation

### Build first: nothing in the engine

A client-side "dense projection" step, in the Pecan and Banda client code:

1. `mapping` = the distinct ids with `row_number() over (order by id) - 1`
   (the BIGINT running count when a group may exceed 2^31 rows), **written to
   Parquet or checkpointed**.
2. `edges` = two joins against the mapping, then `orderBy(s, d)`.
3. Banda's `stage` gets a mode for input that is already dense and sorted. It
   skips its own id map and its own sort and takes `n` as a parameter.
4. Results come back as `(dense, value)` and are joined to the mapping in the
   engine.

Why this first.

- It is exact, in id order and repeatable today, in local and in
  local-cluster mode (sections 5.1, 5.2, 5.2b). It is what icebug-format's own
  converter does with SQL (section 1).
- It costs no engine work and can be dropped if the measurement below goes the
  wrong way.
- It tests the reviewer's premise before anything is built for it.

What it costs (laptop, shape only): cit-Patents index 0.2 s, map and sort
1.6 s, offsets 0.7 s. 50M ids: index 3.1 s, of which the sort is 2.2 s. Under
a 512 MiB fair pool: 4.4 s.

Rules the client code must follow, all from failures seen here.

- Never use an id from `monotonically_increasing_id()` before it is written.
  Not in a join, not in a union, not read twice.
- Do not use the two-pass index on a direct scan in local mode.
- Ask for the order last (`orderBy`), and do not expect one sorted file in
  cluster mode: read the stream, or merge the files.
- Use the `fair` memory pool where a sort may exceed memory.

### The smallest next experiment

Banda on dense sorted input against Banda today. One table, release build, on
the measuring host, not on this laptop.

- Graphs: cit-Patents and graph500-24.
- Arms: (1) Banda today (Grust 0.24.0, Int64 identity), mapping and sorting
  in process;
  (2) the recipe above, then Banda in the dense mode.
- Measures: seconds for index, map and sort, stage, projection; the server's
  peak RSS; end to end with Parquet in and Parquet out.
- The question it answers: does moving the mapping and the sort into the
  engine lower the peak, and what does it cost in time. The F0 floor does the
  mapping and a directed CSR build of cit-Patents in process in 0.22 s (0.42 s
  undirected); the engine needed 1.6 s for the map and the sort alone here. So
  a gain in time is not expected for graphs that fit. A gain in peak memory,
  and graphs that do not fit, are what the experiment has to show.

### Engine work, in this order, each small and separately reviewable

1. **Expose `file_row_index()`** (and `input_file_name()`). It is upstream's
   own TODO. It gives option (d) and positional reads of chunked formats. Cost:
   a function registration and the distributed codec test, inferred from the
   TODO.
2. **Real range partitioning for `repartitionByRange`.** DataFusion's
   `Partitioning::Range` and Sail's shuffle writer already carry it. Missing:
   the resolver and a way to get split points (a sampling job, or bounds given
   by the client). It gives the ordered index with no single stream (c3, e3)
   with client-side offsets. Cost: larger than 1; the sampling job is the open
   design point.
3. **Pin the order under the id.** Either `MonotonicIdExec` declares the order
   it was given, or a `RowIndexExec` (c1) is added, about the size of
   `monotonic_id.rs` plus resolver, logical node and codec entries. It removes
   the silent wrong results of section 2 and gives a BIGINT index.
4. **`RowIndexExec` with a count stage (c2)** only if a measurement shows the
   one-task gather of (a) to be the limit in a real cluster.

The local-mode scan that is not repeatable, and the sort that disappears under
`monotonically_increasing_id`, are worth a short note to upstream whatever is
built. Spark users expect both to hold.

### What remains open

- Behaviour of `row_number` above 2^31 rows, and of any option above 2^33
  rows a partition.
- The gather of (a) on a real cluster: one task receives every row.
- Memory at sizes where the sort must spill for real, and the hash joins of
  item 4 under a bounded pool. I did not check whether they spill.
- Split points for range partitioning: who computes them, and when.
- Several vertex groups, string or composite keys, duplicate keys, skew.
- Reading and writing GraphAr's exact file layout from Sail.
- Where the 16 + 48 bit split comes from, and whether ids must stay
  non-negative.

## Checked independently

Added by the reviewer of this study, with a script written apart from its
probes ([`independent_check.py`](independent_check.py), output in
`raw/independent-check-upstream.txt`), on unmodified upstream `99ee46f69`,
local mode, default settings.

| Claim | Check | Result |
|---|---|---|
| A sort under `monotonically_increasing_id` is removed | 2,000,000 distinct keys in scrambled order; `orderBy(k)` then the id; an aggregate counts rows where the id equals the key | **1 of 2,000,000**. The plan has no `SortExec`. Written to Parquet first: 2,000,000 of 2,000,000 |
| `row_number() over (order by k)` is exact inline | the same count with `row_number() - 1` | 2,000,000 of 2,000,000 |
| A Parquet scan is not repeatable in local mode | partition sizes and the ids of four fixed keys, three executions | different in every execution |

So both hazards are real on upstream, and the rule "never use an id from
`monotonically_increasing_id()` before it is written" stands.

## Files

| File | What |
|---|---|
| `README.md` | this report |
| `sailserver.py` | starts one Sail server on a free port; host facts; the bucket expression |
| `probe_engine.py` | what exists: functions, plans, first determinism check |
| `probe_determinism.py` | which inputs give the same partitions and row order on every execution |
| `probe_external_sort.py` | sort and `row_number` of 50M rows under bounded memory pools |
| `bench_dense_ids.py` | options (a), (b), (e) and item 4 on cit-Patents, with checks |
| `bench_scale.py` | the vertex options on 50M synthetic ids |
| `summarize.py` | Markdown tables from the raw records |
| `raw/probe-engine-{local,local-cluster}.jsonl` | records of `probe_engine.py` |
| `raw/probe-determinism-{local,local-cluster}.jsonl` | records of `probe_determinism.py` |
| `raw/bench-{local,local-cluster}.jsonl` | records of `bench_dense_ids.py`, three runs a case |
| `raw/plans-{local,local-cluster}.txt` | physical plans of every case |
| `raw/bench-scale-*.jsonl` | records of `bench_scale.py` |
| `raw/probe-external-sort.jsonl` | records of `probe_external_sort.py` |
| `raw/first-pass/` | an earlier complete pass of `bench_dense_ids.py`, under heavier load and with the linear bucket expression |
| `raw/upstream/` | the probes on the unmodified upstream binary |
| `raw/*.stderr` | client warnings of each run |

## Limits

- **Shared, loaded laptop.** Other agents ran Sail servers and builds during
  every run; load average 10 to 75. Timings are shape only. Three runs a case.
  Most cit-Patents statements take under a second, where fixed costs dominate.
- **Small inputs.** cit-Patents has 3.77M vertices and 16.5M edges, and its
  vertex file is already in id order. The 50M-row runs use synthetic unsorted
  ids, one BIGINT column. Nothing here was run at graph500-24 scale.
- **Local-cluster is not a cluster.** One process, workers as threads, no
  network. No multi-host or Kubernetes run.
- **Binary provenance.** The fork binary was built at 00:19 local time on
  2026-10-02; the worktree HEAD `4b88c8fb4` was committed at 05:43. I did not
  rebuild, so the binary may predate HEAD. The upstream binary (02:06) was used
  for the probes only.
- **Not run.** `row_number` above 2^31 rows; more than 2^33 rows in a
  partition; any GraphAr file read or written by Sail; `file_row_index()` and
  range partitioning inside Sail (neither is reachable from the client);
  option (f); joins under a bounded memory pool.
- **Designs on paper.** Options (c), (d) and (f) and the engine-work estimates
  are inferred from reading code. No Rust was written.
- **Write plans not inspected.** `EXPLAIN` of a write is not available from
  the client. What is said about file order comes from reading the written
  files, three runs a case.
- **Memory.** In the cit-Patents benchmark one server runs all cases, so RSS
  accumulates and is not a per-case figure (`server_rss_after_mib` in the raw
  records). The only memory evidence is section 5.4, one run a setting.
- **GraphAr.** Read from the Markdown sources of the two specification pages
  at `c7f31bc9d`, which the site renders. The figures of the spec were not
  read. The origin of the 16 + 48 split was not found.
- **Keys.** One BIGINT key, unique. No strings, no composite keys, no
  duplicates, no skew.
