# WCC: attacking the first round with a per-partition union-find

A design note for Sem, 2026-10-02. No Sail code was written and no new Sail
path was run. Two things were measured to ground it: today's WCC round by
round on graph500-24, and an offline count of what a per-partition
union-find would leave on the two LDBC graphs.

## Summary

- The first round is the cost on graph500-24 (65% of the call, 90% with
  round 2). On cit-Patents it is 36%.
- The hard part of the idea goes away with one observation. A partition's
  union-find result, written as pairs `(vertex, local root)`, **is an edge
  list** with the same components as the partition's edges. Emit it as
  edges. There is no remapping to pull out, no conflict between partitions
  to resolve, and nothing to map back at the end.
- Counted on graph500-24 with 10 partitions in file order: 260M edges
  become 38M (15% kept), in a pass of 3.9 s on 10 threads, not counting
  Parquet decode and the write. Today's first round leaves 78M and took
  21 s on the same loaded machine. On cit-Patents the pass keeps 63%, about
  what today's round 1 keeps (59%), in 0.26 s against 1.45 s.
- What is left is at most `sum of V_p`, the vertices seen per partition, so
  at most `min(E, P * V)`. It pays when partitions are few and the graph is
  dense. It is the whole answer when one process can hold `O(V)`.
- Sail can run it per partition today through `mapInArrow`; a native
  version fits the existing `MapPartitionsExec`. A two-phase aggregate
  (local union-find, then a merge) is the cleanest form.

## 1. The task

Sem, translated: "Assess a possible attack on the first iteration of the
current WCC. Do something like MapPartitions with no sort or repartition,
as is. Inside, a local union-find in one pass, collapsing the edges inside
each partition, to cut the cost of the first contraction round sharply. By
my estimate the first iteration takes 65 to 75% of the wall time. It sounds
trivial but an efficient implementation is not obvious: one has to pull the
remapping out of the partitions, plus the conflicts between partitions (one
partition's union-find gives one thing, another's another), plus the
reverse remapping at the end. Done naively it looks too complex. Think
about design options, maybe a draft. Nothing is to be run."

## 2. Is the first round the cost?

Pecan's randomized contraction, inputs read in place, Capitola (M1 Max),
release host, local mode, 10 partitions. Seconds.

| | cit-Patents (16.5M edges) | graph500-24 (260M edges) |
|---|---|---|
| Call | 4.07 | 33.0 (20.3 on a quiet machine) |
| Round 1 | 1.45 (36%) | 21.3 (65%) |
| Round 2 | 0.80 | 8.1 (25%) |
| Round 3 | 0.41 | 0.33 |
| All later rounds | 0.36 (13 rounds) | 0.62 (16 rounds) |
| Back pass and labels | 0.48 | 1.63 |
| Edges into round 1, 2, 3, 4 | 16.5M, 9.8M, 6.2M, 2.3M | 260M, 78M, 2.3M, 0.35M |

Sources: cit-Patents from
[`../../sem-review-capitola-2026-10-02/A2-local/profile-variants.txt`](../../sem-review-capitola-2026-10-02/A2-local/profile-variants.txt);
graph500-24 from one run today,
[`profile-graph500-24-in-place.txt`](profile-graph500-24-in-place.txt). The
graph500-24 run was on a loaded machine, so its absolute times are high;
the shares are what matters.

Sem's estimate holds on the dense graph. On the sparse one the cost is
spread over three rounds.

## 3. The observation: a local forest is an edge list

Run a union-find over the edges of one partition. Afterwards every vertex
seen in the partition has a root. Write one pair `(v, root(v))` for every
vertex that is not its own root. That is a spanning forest of the
partition's subgraph, each tree drawn as a star.

Claim: replacing each partition's edges by its star pairs does not change
the connected components of the whole graph.

- Two vertices are connected by a partition's edges exactly when they have
  the same local root, which is exactly when the star pairs connect them.
- Connectivity in the whole graph is the transitive closure of the union
  of the per-partition relations. The union of the forests generates the
  same closure.

So the output of the pass is simply a smaller edge table over the same
vertex ids, and everything downstream is unchanged:

| Sem's concern | In this form |
|---|---|
| Pull the remapping out of each partition | The remapping is the output. It is emitted as edges. |
| Conflicts: `v` has root `r1` in one partition and `r2` in another | Both pairs are kept. They are two edges, `v-r1` and `v-r2`, and they say `r1` and `r2` are connected. |
| Reverse remapping at the end | None. No id was replaced, so the labels come out over the original ids. |

Vertices are not removed by this step, only edges. That is the right
target: a round's cost follows the edge count (section 2).

Choosing the smallest id as the root makes the output deterministic for a
given partition content, and the row order inside a partition does not
change which components exist. Different partitionings give different
forests and the same final labels.

## 4. How much it removes

A partition with `E_p` edges, `V_p` distinct endpoints and `c_p` local
components emits `V_p - c_p` pairs. So what survives is below
`sum of V_p`, which is below both `E` and `P * V`. The pass removes much
when `E_p` is well above `V_p`: a dense graph, or few partitions.

Counted offline on the LDBC edge files with
[`local-forest-sim`](local-forest-sim/src/main.rs), one union-find per
partition, forests merged afterwards and the component count checked
against a union-find over all edges (3,627 and 2,901, as Pecan reports).
Records: [`forest-cit-Patents.jsonl`](forest-cit-Patents.jsonl),
[`forest-graph500-24.jsonl`](forest-graph500-24.jsonl).

Partitions in file order (the shape of a Parquet scan split by row-group
ranges):

| Graph | P | Edges kept | Fraction | Largest `V_p` | Pass, wall on 10 threads | Pass, CPU |
|---|---|---|---|---|---|---|
| cit-Patents | 1 | 3.77M | 0.23 | 3.77M | 1.35 s | 1.3 s |
| cit-Patents | 4 | 7.27M | 0.44 | 1.90M | 0.38 s | 1.4 s |
| cit-Patents | 10 | 10.41M | 0.63 | 1.10M | 0.26 s | 2.3 s |
| cit-Patents | 16 | 11.95M | 0.72 | 0.80M | 0.21 s | 1.7 s |
| cit-Patents | 64 | 15.02M | 0.91 | 0.26M | 0.15 s | 1.4 s |
| graph500-24 | 1 | 8.87M | 0.034 | 8.87M | 24.1 s | 24.1 s |
| graph500-24 | 4 | 22.5M | 0.087 | 5.65M | 6.5 s | 25.7 s |
| graph500-24 | 10 | 38.2M | 0.147 | 3.85M | 3.9 s | 37.7 s |
| graph500-24 | 16 | 48.7M | 0.187 | 3.09M | 3.9 s | 34.1 s |
| graph500-24 | 64 | 89.7M | 0.345 | 1.50M | 3.9 s | 36.7 s |
| graph500-24 | 256 | 141.7M | 0.544 | 0.65M | 2.8 s | 28.1 s |
| graph500-24 | 2,119 (one per row group) | 215.5M | 0.828 | 0.12M | 1.4 s | 13.9 s |

The same with other partitionings, fraction kept:

| Graph | P | File order | Hash of source | Round-robin |
|---|---|---|---|---|
| cit-Patents | 10 | 0.63 | 0.73 | 0.94 |
| cit-Patents | 64 | 0.91 | 0.96 | 1.00 |
| graph500-24 | 10 | 0.147 | 0.147 | 0.166 |
| graph500-24 | 64 | 0.345 | 0.345 | 0.435 |

What the counts say:

- **The number of partitions is the lever.** Every halving of P removes
  more. One partition is the answer itself. A union-find per batch or per
  row group does little (0.83 kept on graph500-24).
- **"As is, no repartition" is right.** File order is as good as hashing by
  source and better than round-robin. A keyless repartition before the
  pass would hurt, most on the sparse graph.
- Against today's round 1: on graph500-24 the pass keeps half as much as
  the round does (38M against 78M). On cit-Patents it keeps about the same
  (10.4M against 9.8M).

## 5. What the pass costs

The union-find in the counting program keeps a hash map from i64 id to a
local index (no dense ids needed, so the i64 contract holds), parents in a
vector, union by smaller id, path halving.

- Throughput: 7 to 12 million edges per CPU-second on this laptop. The
  whole graph500-24 pass is 28 to 38 CPU-seconds, 3.9 s on 10 threads.
- Memory: a map entry, an id and a parent per vertex seen, roughly 30 to
  50 bytes. The largest partition of graph500-24 at P = 10 sees 3.85M
  vertices: under 200 MB a task, about 2 GB for ten at once. This is an
  estimate from the structure, not a measurement.
- The pass holds a partition's forest until the partition ends. A cap on
  the map (emit the stars and start again when it is full) bounds the
  memory and degrades smoothly toward the many-partitions rows above.

These times exclude Parquet decoding and the write of the forest, which
the engine does either way.

## 6. Design options

### A. The forest as a sparsifier, contraction unchanged

`edges -> per-partition forest -> the existing randomized contraction`.
One extra pass with no shuffle, then the same rounds over fewer edges.
Nothing in the algorithm, its history or its back pass changes. This is
the smallest change and it is safe at any size: memory is per partition.

Expected, not measured: on graph500-24 the pass (about 4 s plus its write)
replaces a 260M-edge round by a 38M-edge one. If a round's time follows
its edge count, the call goes from about 20 s to 10 to 12 s on a quiet
machine. Whether a round over star pairs contracts as fast as a round
over the original edges is not known. On cit-Patents it replaces round 1
(1.4 s) by a 0.3 s pass and leaves the other rounds, so a quarter off at
best.

### B. Forest, then merge: the whole answer in one two-phase aggregate

Merge the forests in one more union-find and the result is the component
of every vertex. As a plan this is an aggregate with no grouping key:

- partial phase, one accumulator per partition: the local union-find, its
  state the star pairs;
- final phase, one accumulator: union of all the states, output
  `(id, component)`.

DataFusion plans an ungrouped aggregate as a partial phase per partition
and one final phase. Sail's cluster planner should then run the partial
phase on the workers, as for any aggregate; that was not checked in the
code. The state that crosses the exchange is the forest, not the edges.

Measured in the counting program on one thread: merging the P = 10 forests
takes 3.3 s on graph500-24 and 0.7 s on cit-Patents. So the whole of
graph500-24 is about 4 s of pass plus 3 s of merge, plus scan and write,
with no rounds. For comparison: today's call 20 s, graphframes-rs 25 s,
Banda on Grust 0.24.0 7 to 8 s from launch.

The limit is the final merge: one process holds `O(V)` and receives up to
`P * V` pairs. For 8.9M vertices that is a few hundred MB. At a billion
vertices it is tens of GB in one task. That is the semi-streaming regime:
it needs memory for the vertices, never for the edges.

### C. A bounded merge tree, falling back to A

Merge forests in groups (the fan-in fixed), level by level. Each merge
holds at most the vertices of its group. When a level's output no longer
shrinks, or a merge would exceed its memory budget, stop and hand the
remaining pairs to the contraction (A). B is the case where the tree
reaches one node. This is the form to build if one path has to serve both
a graph whose vertices fit a process and one whose vertices do not.

### D. The naive form, and why not

Contract each partition to its local roots, relabel edges by local root,
reconcile roots across partitions, and compose the mappings at the end.
Inside a partition no edge survives relabelling (both ends have the same
root), so all that remains of the partition is the mapping, which is the
star pairs. Reconciling the mappings is then a connectivity problem on
those pairs. D is A with extra bookkeeping.

### Where vertices could also be removed

A vertex seen in exactly one partition and not a root there is finished:
its component is its root's. It could be set aside with its root, like a
contraction round's representatives, and joined back at the end. Finding
those vertices is a grouped count over the pairs, which costs about what
the next round costs. Not worth doing first.

## 7. How it would run in Sail

Read from the fork's code (`querygraph/sail` `4b88c8fb4`).

| Mechanism | Exists today | Runs on workers | Notes |
|---|---|---|---|
| `mapInArrow` with a native helper called from Python | yes | yes | `MapPartitionsExec` (`crates/sail-physical-plan/src/map_partitions.rs`) keeps the input partitioning and maps each partition's stream. The Python function would hand batches to a compiled union-find. Per-batch Python glue; the embedded interpreter's lock is held only between batches if the helper releases it. |
| A native `StreamUDF` under `MapPartitionsExec` | no | after a codec entry | The trait is `StreamUDF::invoke(stream, context) -> stream` (`crates/sail-common-datafusion/src/udf.rs:13`). The worker codec knows only the PySpark kinds and rejects others with "unknown StreamUDF type" (`crates/sail-execution/src/proto/codec.rs`, `try_encode_stream_udf`). A native kind needs one enum arm each way and a client-visible way to ask for it. |
| A native aggregate (option B) | no | yes, by ordinary two-phase aggregation | The graph utilities register scalar functions only (`crates/sail-session/src/extensions/graph_utils/functions.rs:22`, and `register_worker_functions` in `mod.rs`). An aggregate would be registered the same way, in the host, next to `gf_axpb`. |
| A driver-placed relation in an extension wheel (the Nutmeg shape) | yes | no | It gathers its inputs on the driver (`examples/extensions/WRITING-AN-EXTENSION.md`). Fine in local mode; in cluster mode every edge would travel to the driver. |
| A worker-placed relation in an extension wheel (the Argentea shape) | yes, experimental | yes | A native region that runs per partition on the workers, with state scoped to one job (`crates/sail-common-datafusion/src/worker_extension.rs`). Its payload is at most 262,144 bytes, which a union-find needs none of. One attempt, no retry. This is the existing native route that needs no change to Sail's codec. |

For a first experiment, `mapInArrow` needs no change to Sail, and a
worker-placed relation is the native form that needs none either. For the
product form, the aggregate is the least code and the least new surface:
no new operator, no codec change for a new plan node, and the planner
already knows how to split it.

One caveat for B as an aggregate: its final value is one row holding a
list of `V` pairs, to be unnested. That is a single Arrow list of 142 MB
at 8.9M vertices and it needs a large-list type past 2^31 entries. A table
function or a small operator that streams `(id, component)` batches avoids
the single value. This is a detail of the output side, not of the method.

## 8. What would have to be shown before building

One small experiment decides it:

1. `mapInArrow` over the edges in place with a compiled union-find, forest
   written as the checkpoint, then the unchanged contraction. graph500-24
   and cit-Patents, 10 partitions, launch to exit, labels checked against
   the oracle on every vertex.
2. The same with the forests merged in the client or in one more
   `mapInArrow` over a single partition, to price option B.

It would answer what the counts cannot: what the forest's write costs in
Sail, how much the Python glue costs, and whether the rounds after the
pass shrink as the edge counts say.

## 9. Limits

- The counts are exact. The times are one run each of a helper program on
  a laptop that was also running other work. They are shape only.
- The pass was timed without Parquet decode and without writing its
  output.
- Two graphs. Both have a giant component. A graph of many small
  components was not counted.
- Local mode reasoning. In cluster mode the unit that matters is whatever
  one task sees; a per-worker union-find across that worker's partitions
  would remove more and was not looked at.
- The estimates in section 6 assume a round's time is proportional to its
  edge count. Section 2 supports that for rounds 1 and 2 only roughly
  (260M edges 21 s, 78M edges 8 s).
- Skewed partitions, and inputs with very many partitions (thousands of
  small files), land in the weak rows of the table unless partitions are
  coalesced first. Coalescing without a shuffle was not examined in Sail.

## 10. Prior work

The idea is known as filtering or sparsification: partition the edges,
keep a spanning forest of each part, repeat on the union.

- Karloff, Suri, Vassilvitskii. "A Model of Computation for MapReduce."
  SODA 2010, pages 938 to 948. Minimum spanning tree by partitioning the
  edges and keeping each part's spanning forest.
  https://theory.stanford.edu/~sergei/papers/soda10-mrc.pdf
- Lattanzi, Moseley, Suri, Vassilvitskii. "Filtering: a method for solving
  graph problems in MapReduce." SPAA 2011, pages 85 to 94.
- Feigenbaum, Kannan, McGregor, Suri, Zhang. "On graph problems in a
  semi-streaming model." Theoretical Computer Science 348 (2005), pages
  207 to 216. Memory for the vertices, edges as a stream: the regime of
  option B.

## Files

| File | What |
|---|---|
| `local-forest-sim/` | the counting program (Rust, reads the Parquet edge file) |
| `forest-cit-Patents.jsonl`, `forest-graph500-24.jsonl` | its output, one object per partitioning and P |
| `profile-graph500-24-in-place.txt` | today's WCC round by round on graph500-24 |

To repeat the counts:

```sh
cd local-forest-sim && cargo build --release
target/release/local-forest-sim graph500-24-e.parquet source target 1,4,10,16,64,256
```
