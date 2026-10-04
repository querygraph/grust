# Grust and graphs on Sail: a proposed design

A response to Sem's draft,
[`../../sem-research-2026-10-02/grust-model/PROPOSED_DESIGN_DRAFT.md`](../../sem-research-2026-10-02/grust-model/PROPOSED_DESIGN_DRAFT.md)
(pull request #35), written 2026-10-03. It follows his rule: design first,
with who owns what, what is collected where, and the memory and time of
every step. No product code was written. One measurement was made, because
his draft says the trade-off "needs to be measured at scale".

## Summary

1. **Sem's split holds, with one correction.** Grust becomes an LPG schema,
   a GQL compiler, CSR kernels and an `io` module. It knows nothing about
   Sail. Sail owns the tables, the dense ids and the mapping back.
2. **The engine should make ids dense, but should not sort.** On
   graph500-24, Sail maps both endpoints to dense ids in 5.1 s at a 1.4 GiB
   peak. A local counting build turns unsorted dense pairs into a CSR in
   1.2 s, holding 1.16 GiB. Sorting in Sail first costs 18 to 25 s at an
   11 to 13 GiB peak, and failed once under a 4 GiB pool.
3. **The local process then holds the CSR and nothing else.** That is
   1.16 GiB for graph500-24, against 8.0 GiB for an in-process build that
   maps ids itself, and 12.7 GB for Banda on Grust 0.24.0 today. The time
   end to end is about the same, 7 s.
4. **The contract between them is four Arrow arrays and a count.** The
   kernel receives `n`, the offsets, the targets and optional weights. It
   returns a record batch whose row `i` is dense vertex `i`. There is no id
   type, and no hash map.
5. **What survives of today's Grust:** the kernels, the work budgets and
   cancellation, the parallel primitives, and the Cypher parser and
   semantics. What goes: `NodeId` in the analytics path, the projection's
   id structures and edge table, and string results.

## 1. The rules this design keeps

| Rule | Source | How this design keeps it |
|---|---|---|
| Grust knows nothing about Sail | Sem's draft | Grust defines its traits; Sail implements them. No Grust crate depends on a Sail crate. |
| Ids are i64 at every interface | the project's `AGENTS.md` | Origin keys stay in Sail tables. Dense ids cross only the engine-to-kernel boundary, and never reach a user. |
| On the relational path, nothing of size O(\|V\|) goes to the driver | Sem's draft | The driver receives scalars per round. Everything else is a table. |
| Every component states its memory before it allocates | Sem's draft ("memory / perf complexity estimations everywhere") | A kernel publishes `estimate(n, m, options)`. The host admits that much first. |
| Scalability over wall time on the relational path | Sem's draft | The local-projection path is the fast one, and it states its fit limit. |

## 2. Components and owners

| Component | Owner | Holds in memory | Knows about |
|---|---|---|---|
| `grust-lpg`: the schema graph of vertex property groups (VPGs) and edge property groups (EPGs) | Grust | the schema only | nothing outside Grust |
| `grust-gql`: parse, resolve against the LPG, plan, emit | Grust | a query plan | the LPG and a backend's statistics, through a trait |
| `grust-kernels`: CSR in, Arrow out | Grust | the CSR it is lent, plus its declared scratch | Arrow, and three small traits (budget, cancel, threads) |
| `grust-io`: GraphAr and icebug-disk metadata | Grust | metadata | file formats, not engines |
| Graph catalog: VPG and EPG tables, dense-id tables | Sail | nothing beyond its catalog | the LPG schema, as data |
| Relational algorithms (Pecan) | Sail, client side | per-round scalars on the driver | DataFrames |
| Local projection host (the successor to Banda) | Sail, as a driver-side extension | the CSR and kernel scratch | the kernel contract |
| Mapping results back | Sail | nothing; it is a join | the dense-id table |

## 3. The contracts

### 3.1 The LPG schema

| Element | Fields |
|---|---|
| VPG | name; key columns (the origin id, any type); property columns with types; where its rows live (a table, or files) |
| EPG | name; source VPG and destination VPG; source and destination key columns; property columns with types; directed or not; where its rows live |
| Dense-id table, one per VPG | `(origin key, dense: Int64)`, `dense` in `0..n` with no gaps. Optional global id `(group << 48) \| dense` at the outside (section 8). |

The schema is a small graph: VPGs as nodes, EPGs as edges. A query's
pattern is resolved against it before any data is read.

### 3.2 Statistics the backend lends the compiler

Row counts per VPG and EPG; distinct counts of key columns; out-degree and
in-degree summaries per EPG (mean, maximum, a few quantiles). Grust defines
the trait; Sail fills it from table metadata or a cheap aggregate. Grust
uses it to order joins. It never reads data itself.

### 3.3 The CSR handed to a kernel

| Array | Arrow type | Length | Bytes |
|---|---|---|---|
| `n` | a scalar | | |
| offsets | UInt64 | n + 1 | 8(n + 1) |
| targets | UInt32 while n < 2^32, else UInt64 | m | 4m |
| weights (optional) | Float64 | m | 8m |

- An edge's position in `targets` is its id for kernels that report edges
  (paths, trees, flows). Sail can map a position back to an edge row
  because it built the table in that order. No separate edge table is kept.
- The buffers cross the Arrow C data interface. The host owns them; the
  kernel reads them and never frees them.
- Neighbours inside a row are in arrival order. A kernel that needs them
  sorted (set intersections for triangles) sorts each row itself: O(m log d)
  work, parallel, in place.
- A transpose, when a kernel needs one, is built by the kernel host from the
  same arrays, in the same way.

### 3.4 What a kernel returns

A record batch with `n` rows, where row `i` is dense vertex `i`, or `m` rows
for per-edge results. Kernel-declared schema, no id column. Sail attaches
the origin key with one join on `dense`.

### 3.5 Resources

| Trait, defined by Grust | Implemented by | Purpose |
|---|---|---|
| `estimate(n, m, options) -> bytes` | each kernel | The host admits this much before calling |
| `Budget` | Sail's memory pool | Scratch beyond the estimate asks here, and can be refused |
| `Cancel` | Sail's query cancellation | Kernels poll it at the same points they do today |
| A thread pool | the host | Kernels never create threads |

Today's `ExecutionContext` already has budgets, cancellation and a
concurrency setting. What changes is that its interface becomes three small
traits, so that Grust holds no pool of its own.

### 3.6 `grust-io`

It reads GraphAr YAML or icebug-disk's schema and returns, for each VPG and
EPG: file paths, columns, chunk sizes and the adjacency layout. Sail turns
that into tables. A GraphAr internal id is already a dense id. A GraphAr
CSR (`ordered_by_source` with offsets) can be handed to a kernel almost as
is: its offsets restart at 0 in every vertex chunk, so they need one prefix
sum over the chunks.

### 3.7 What the GQL compiler emits

Sem's phrase is "Calcite for ISO-GQL / Cypher over columnar data". The
compiler parses a query, resolves it against the LPG, splits it into paths
along the schema graph, marks shared relations, orders the joins using the
statistics, and emits a plan.

| Option | For | Against |
|---|---|---|
| **Spark Connect relations** (protobuf, built on the client) | Runs on Sail and on Spark unchanged, which Sem valued in discussion #2001. No server code. | No form of recursion that both engines are known to support. Variable-length and shortest paths must become graph operators (next paragraph). |
| SQL text per dialect | What Grust does today for its SQL backends | String building; each dialect is its own surface |
| Substrait | Engine-neutral by design | Sail does not consume it today (no Substrait in its dependencies) |
| A DataFusion logical plan | Exact control | Ties Grust to one DataFusion version, against "Grust knows nothing about Sail" |

Recommendation: Spark Connect relations for Sail and Spark, and SQL text for
the SQL backends. Recursive patterns become explicit **graph operator**
nodes in the plan (bounded expansion, shortest path, connected
components). A backend implements each either relationally (Pecan's
frontier rounds) or by the local-projection path.

What exists today: `grust-cypher` has about 71,000 lines with a parser, a
typed AST, semantics, a reference executor, and about ten
shape-specific pushdowns that render SQL strings
(`crates/grust-cypher/src/pushdown.rs`), falling back to the in-memory
reference for anything else. The parser, AST and semantics carry over. The
shape-specific pushdowns would be replaced by one plan and its emitters.

## 4. The two paths on Sail, step by step

### 4.1 The relational path (Pecan)

| Step | Where | Time | Memory |
|---|---|---|---|
| Read VPG and EPG tables | workers | O(\|V\| + \|E\|) / P | streaming |
| A round: join state with edges, aggregate by vertex | workers | O(\|E\|) / P, one shuffle of messages | bounded by the pool, spills |
| Write the round's state | workers | O(\|V\|) / P | streaming |
| Round scalars (counts, convergence) | driver | O(1) | O(1) |

Two findings of 2026-10-02 apply. A state checkpoint written with
`repartition(T, key).checkpoint()` makes the next join shuffle-free on that
side; with the edges checkpointed the same way, a Pregel round on
graph500-24 was 15% shorter. A checkpoint taken after a sort returns wrong
results (lakehq/sail #2722), so the path must never sort before a
checkpoint.

### 4.2 The local-projection path

Measured on graph500-24 (8,870,942 vertices, 260,379,520 edges) on Capitola,
release Sail, local mode, 10 partitions, greedy pool 30 GiB. Records in
`raw/`.

| Step | Where | Measured | Memory | General cost |
|---|---|---|---|---|
| 1. Dense ids: `row_number() over (order by id) - 1`, written | Sail | 0.44 s | 0.3 GiB server peak | one sort of \|V\| keys |
| 2. Map both endpoints: two joins, written unsorted | Sail | 5.1 s | 1.4 GiB server peak | two shuffles of \|E\|; hash tables of 16 bytes a vertex |
| 3. Build the CSR from unsorted dense pairs: count, prefix sum, fill | local process | 1.17 s (1.15 to 1.39) | **1.16 GiB** resident | two streaming passes; O(\|E\|) work; holds 8(n+1) + 4m bytes |
| 4. Run the kernel | local process | kernel-dependent | its declared estimate | |
| 5. Map a dense result back: one join of n rows | Sail | 0.44 s | negligible | one join of \|V\| rows |

For comparison, other ways to the same CSR on the same machine:

| Way | Time | Local memory | Source |
|---|---|---|---|
| Steps 1 to 3 above | 6.7 s | 1.16 GiB local, 1.4 GiB in the engine | this study |
| Steps 1 and 2, then a sort in Sail, then a one-pass local build | 0.4 + 25.1 + 3.4 s | 1.05 GiB local, **12.7 GiB** in the engine | this study |
| In-process: read, map ids, build (the F0 floor), 10 threads | 3.6 s | 8.7 GiB | `../../sem-review-capitola-2026-10-02/F0/runs.jsonl` |
| Banda on Grust 0.24.0, Int64 ids, 8 workers: stage and project | 1.6 + 3.3 to 4.0 s | **12.7 GB** native peak (staged rows 5.95 GiB and the projection 4.65 GiB) | `../../sem-review-capitola-2026-10-02/F1/` |

All three ways produce the same CSR: 260,379,520 targets, maximum
out-degree 406,416, target sum 1,154,601,406,379,500 for both local modes.
The F0 floor reports the same maximum degree.

### What the measurement decides

- **Dense, not sorted.** Sem's draft has Banda receive "already sorted dense
  ids". The sort is the expensive part, in time and in memory, and the
  local side does not need it: a counting build places each edge in O(1).
  Sorting in Sail took 18 s alone and 25 s together with the mapping, at an
  11 to 13 GiB peak. Under a 4 GiB fair pool the sort on its own failed in
  its merge phase ("Failed to allocate additional 208.1 KB for
  ExternalSorterMerge"); the combined map-and-sort job did finish under the
  same pool. With sorted input the local build is one pass but sequential,
  and slower (3.4 s against 1.2 s).
- **The memory moves out of the local process.** The local process holds
  the CSR: 1.16 GiB here. The mapping lives in a Sail table. Banda today
  holds the staged rows and its projection in the driver.
- **The time does not.** About 7 s end to end either way, for one graph on
  one machine. The gain is memory, and with it the size of graph that fits.

### At 1e9 edges and 1e8 vertices

| Item | Formula | Value |
|---|---|---|
| Local CSR, unweighted | 8(n + 1) + 4m | 4.8 GB |
| Local CSR, weighted | 8(n + 1) + 12m | 12.8 GB |
| Engine mapping, hash tables | about 16 bytes a vertex, split across partitions | 1.6 GB in all |
| Engine mapping, data moved | two shuffles of the edges, 16 bytes an edge each | about 32 GB |
| Mapping back | one join of n rows | 1e8 rows |

The local path fits one large machine at this size. Beyond about 2^32
vertices the targets widen to 8 bytes.

## 5. The handover inside Sail

Step 3 reads the dense pairs twice. Inside Sail there are two ways to give
the kernel host two passes:

| Way | Memory in the host | Note |
|---|---|---|
| Write the dense pairs as a table (Parquet or a hash checkpoint), and let the host read it twice | the CSR only | The table is reusable: a second projection of the same graph skips steps 1 and 2. |
| Stream once and keep the pairs as two u32 columns, then count and fill in memory | 8m more than the CSR (2.1 GB for graph500-24) | No intermediate table. |

Recommendation: the table. It is what was measured, and it is the cache that
makes a second call cheap.

## 6. What happens to today's Grust

| Today | In this design |
|---|---|
| About 30 kernels in `grust-algorithms`, over rows and arcs | Kept. They already read a CSR of 4-byte targets. |
| Work budgets, cancellation, `with_concurrency`, the parallel primitives | Kept, behind the three traits of section 3.5 |
| `GraphProjection`: `Buffer<NodeId>`, the id map, the edge table, string results | Dropped from the analytics path. Positions replace them. |
| `from_graph`, `from_arrow_batches` with Utf8 or Int64 ids | Dropped from the kernels. Id mapping is the engine's job. |
| `grust-cypher` parser, AST, semantics | Kept, as the front of `grust-gql` |
| Shape-specific SQL pushdowns, and the in-memory reference as a fallback | Replaced by one plan and its emitters. The reference stays as the test oracle. |
| Backend adapters (PostgreSQL, Turso, and the others) | Become emitters and statistics providers. That scope is Alexy's call, not this note's. |
| The Nutmeg extension (Banda) | Replaced by a kernel host that takes dense pairs |

## 7. What was not measured

- A kernel run on the engine-fed CSR. The CSR is identical to the one the
  kernels read today (same counts, same maximum degree), so this was not
  needed for the memory question.
- The time to hand the pairs from Sail to a driver-side host. Here the local
  process read Parquet that Sail wrote.
- Cluster mode. Step 2's two shuffles are where a cluster would pay.
- Any graph but graph500-24 at scale; cit-Patents was the check run.
- The GQL compiler. Section 3.7 is a design reading of what exists.

## 8. Open decisions for Sem

| # | Decision | Options | Recommendation |
|---|---|---|---|
| 1 | What the engine hands to a kernel | dense and sorted; dense and unsorted | **Dense and unsorted**, by the measurement |
| 2 | Where the dense pairs live between the engine and the kernel | a written table; an in-memory stream | A written table, which doubles as the cache |
| 3 | What the GQL compiler emits for Sail | Spark Connect relations; SQL; Substrait; a DataFusion plan | Spark Connect relations |
| 4 | Recursive patterns | graph-operator nodes, implemented relationally or locally; no recursion | Graph-operator nodes |
| 5 | Global ids | `(group << 48) \| dense` with 16 group bits; 15 group bits; a separate group column | **A separate group column at the interface**. Sixteen unsigned group bits need the sign bit of an i64, so either 15 bits (32,768 groups) or negative ids. A column has neither problem, and the packed form can stay internal. |
| 6 | The memory interface | Grust's own pool, as today; three small traits implemented by the host | The traits |
| 7 | Neighbour order | arrival order, with kernels sorting rows as they need; always sorted | Arrival order |

## 9. Limits

- One graph at scale, one laptop, local mode, one engine run per pool
  setting, three local runs per mode. The laptop was shared with another
  agent's Sail runs at the time. Shape only.
- The 4 GiB failure of the standalone sort was seen once. The combined job
  under the same pool succeeded. Neither was repeated.
- The extrapolations in section 4.2 are arithmetic from the structures, not
  measurements.
- Section 6's "dropped" and "kept" are proposals. Nothing in Grust has been
  changed.

## Files

| File | What |
|---|---|
| `sail_feeds_csr.py` | the engine half: dense ids, mapped edges, the sort, and mapping back; times each step and samples the server's memory |
| `csr-from-dense/` | the local half: a CSR from dense pairs, two-pass counting or one-pass sorted (Rust) |
| `raw/engine-graph500-24-greedy30.jsonl`, `raw/engine-graph500-24-fair4.jsonl` | the engine runs |
| `raw/local-graph500-24.jsonl` | the local runs, with peak resident memory |

To repeat:

```sh
python sail_feeds_csr.py <release sail> graph500-24 <work dir>
cd csr-from-dense && cargo build --release
target/release/csr-from-dense --edges <work dir>/edges-dense --vertices 8870942
```
