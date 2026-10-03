# A multi-scale graph visualization service over Sail: design, contracts, costs

Written 2026-10-03 for Sem's draft
[`VIZUALIZATION_SERVICE_DRAFT_FOR_LLM_ANALYSIS.md`](../../sem-research-2026-10-02/forceatlas2/VIZUALIZATION_SERVICE_DRAFT_FOR_LLM_ANALYSIS.md).
It builds on the ForceAtlas2 study in the same folder
([`../../sem-research-2026-10-02/forceatlas2/README.md`](../../sem-research-2026-10-02/forceatlas2/README.md)),
the Delta/Parquet layout study (`delta-order-plans/README.md`) and the dense-id study (`dense-ids/README.md`).
It does not redo them.

## Summary

1. **The draft works, and its scaling is governed by one quantity: the rows behind one "expand".** The quadtree
   becomes three sorted Parquet tables: vertices keyed by a Morton key, edges keyed by the Morton keys of
   both endpoints, and per-level cell aggregates. An expand is then one key-range read. Measured on
   cit-Patents (3.8M vertices, 33M edge rows) and graph500-24 (8.9M vertices, 521M edge rows), it takes
   3 to 43 ms on both graphs when the tables are sorted by key. Unsorted, it takes up to 0.54 s on
   graph500-24, 40 times more.
2. **The tree "head" is small enough to hold in RAM at any scale.** That head is the set of cells whose
   parent holds more than T vertices. Its size is at most (16/3)|V|/T: 530k cells (34 MiB) at |V| = 1e9 with
   T = 1e4. The service can hold it, so a level never has to be computed on demand.
3. **Pseudo-edges are the expensive part, and only coarse levels need precomputing.** An on-demand expand
   scans every edge of the cell: about 32|V|/4^l rows at level l. At 1e9 vertices that is 3.1e7 rows
   (432 MiB) at level 5. A precomputed block of the next level has at most 4 x 4^(l+1) rows. So
   precompute P_l for l up to about 6 or 7 at 1e9, and compute deeper levels on demand. The level table
   carries `deg_sum`, so the service can choose the path per cell.
4. **Sail can serve this today, with two cautions, both measured here.** First, a Parquet write keeps a
   preceding sort only in the default save mode: `mode("overwrite")` drops it
   ([lakehq/sail#2741](https://github.com/lakehq/sail/issues/2741)). Second, Delta cannot be clustered ([lakehq/sail#2726](https://github.com/lakehq/sail/issues/2726)). The related Sail issues
   filed on 2026-10-02 are listed in section 3.4. Sorted Parquet then prunes row groups and pages (EXPLAIN ANALYZE: 32 row groups to 4,
   152 pages to 4, 3.2 MB scanned instead of 220 MB). Sail has no result cache, because `persist` is a
   no-op, so the cache lives in the service.
5. **Keep the layout separate.** The service only needs `(vid i64, x, y)` plus a version. A multilevel layout
   matches the zoom levels, but its clusters are not quadtree cells. Coupling the two buys nothing that
   the level table does not already give. Cornac (Perrot and Auber, IEEE TBD) is the closest prior
   system: Spark plus HBase map-style tiles at 174M nodes. It stored about 20 times the raw data because
   it precomputed every level. This design avoids that with the head plus on-demand rule.

Tags: **[run]** measured here, raw record named; **[code]** read from code at the cited file and line;
**[lit]** from the cited literature; **[calc]** arithmetic shown or in [`estimates.py`](estimates.py)
([`estimates.out`](estimates.out)); **[inf]** my inference.

Sail tree: fork worktree `~/src/sail-pecan-integrated`, HEAD `4b88c8fb4`, release binary
`target/host/release/sail` built 2026-10-02 00:19 (older than HEAD; the dense-ids and delta-order studies
note the same binary). DataFusion 55.1.0. Line numbers refer to that tree.

## 1. Components, owners, and what crosses each boundary

### 1.1 The components

| # | Component | Owner | Holds in memory | Reads | Writes / returns |
|---|---|---|---|---|---|
| C1 | Layout job | Sail batch job (any route of the ForceAtlas2 study; section 6) | per the layout route; for the driver-native kernel 29 B per vertex (FA2 study section 3.3) | `V`, `E` | `L(vid i64, x f64, y f64)` + `layout_version`, \|V\| rows, 24 B per row raw |
| C2 | Index builder | Sail batch job, plain DataFrame code, run once per layout version | nothing resident; shuffles and sorts | `L`, `E` | `VK`, `EK`, `LEVELS`, `PE_l` (section 2, 3), all immutable Parquet under one version directory |
| C3 | Cell server | separate service process (remote shape) or driver-resident extension (in-process shape) | the head of `LEVELS` (section 2.4): at most (16/3)\|V\|/T rows of 64 B; an LRU of `PE` and leaf blocks | `LEVELS`, `PE_l`, `EK`, `VK` by key range, through Sail (Spark Connect or Flight SQL) or directly from Parquet | Arrow IPC responses (section 8.2) |
| C4 | Pseudo-edge aggregator | inside C2 (precomputed levels) and C3 (on-demand levels) | per request: one cell's edge rows, streamed | `EK` key range, or `PE_(l+1)` key range | `(child, frontier cell, w)` rows |
| C5 | Gateway | part of C3: HTTP or WebSocket endpoint | nothing beyond C3 | requests from the browser | Arrow IPC stream per request |
| C6 | Client / UI | browser, WebGL renderer | the frontier (visible cells, at most K, about 1e4), visible pseudo-edges (top k per cell), real nodes of leaf cells (at most about 1e5) | Arrow IPC | nothing |
| C7 | Transport | Arrow everywhere: Spark Connect `ArrowBatch` messages [code: `crates/sail-spark-connect/src/executor.rs:279-283`], Flight `DoGet` [code: `crates/sail-flight/src/service.rs:178-207`], Arrow IPC over HTTP to the browser | | | |

The draft names a "level-table builder", a "pseudo-edge aggregator", a "tile/cell server" and a "cache".
Here the first two are one batch job (C2) for the precomputed part and one function of the cell server
(C4) for the on-demand part. The cache is part of C3 and of C6, because Sail has no result cache:
`Persist` and `Unpersist` are no-ops with a warning
(`crates/sail-spark-connect/src/service/plan_analyzer.rs:166-181`) and `CACHE TABLE` is a planning TODO
(`crates/sail-plan/src/resolver/command/mod.rs:194`) **[code]**. Sail does cache Parquet footers and
statistics ("global" by default, `crates/sail-common/src/config/application.yaml:757-800`) **[code]**,
which is what makes repeated small range reads cheap.

### 1.2 What crosses each boundary

Sizes for |E| = 16|V| stored in both directions (32 edge rows per vertex). Bytes per row are the measured
Parquet sizes on cit-Patents (`raw/file-layouts.json`) **[run]**, or Arrow in-memory sizes of the
returned tables **[run]**.

| Boundary | What | Rows | Bytes | When |
|---|---|---|---|---|
| C1 to C2 | layout table `L` | \|V\| | 24 B raw | once per layout version |
| C2 to storage | `VK` sorted by key | \|V\| | 25 to 27 B per row (Parquet) | once per version |
| C2 to storage | `EK` sorted by `src_key`, both directions | 2\|E\| | 11.7 to 14.6 B per row (Parquet) | once per version |
| C2 to storage | `LEVELS`, levels 0..L_h | at most sum min(4^l, \|V\|), adaptive head far fewer (section 2) | 64 B per row in Arrow | once per version |
| C2 to storage | `PE_l`, l = 0..L_p+1 | at most min(16^l, 2\|E\|) each | 1.8 to 2.3 B per row (Parquet, sorted) | once per version |
| storage to C3, at start | the head of `LEVELS` | about (16/3)\|V\|/T | 34 MiB at 1e9, T = 1e4 | at start, per version |
| Sail to C3, one expand | 4 children + pseudo-edges of the children to the frontier | at most 4 + 4K | measured 3 to 599 KiB (section 7) | per click |
| Sail to C3, one leaf | the vertices of a cell and their edge rows | mass, mass x degree | measured 0.3 MiB + 3.0 to 17.7 MiB for about 1e4 vertices | per click on a small cell |
| C3 to C6 | the same, plus mapping | same | same | per click |
| C6 to C3 | request: cell id + frontier (sorted i64 cell ids) | at most K | 8 B per frontier cell: 80 KiB at K = 1e4 | per click |

### 1.3 Two deployment shapes

| | In-process on the driver | Remote |
|---|---|---|
| Where C3 runs | in the Sail driver process, as a driver-placed extension like Nutmeg ("native Nutmeg algorithms execute on the driver", `examples/extensions/WRITING-AN-EXTENSION.md:30-31`; per-session resident store with a prepaid quota, default 256 MiB, `examples/extensions/nutmeg/README.md:9-12`) **[code]** | its own process on any host |
| How C3 reads | DataFusion scans inside the driver, no RPC | Spark Connect (`sail spark server`) or Arrow Flight SQL (`sail flight server`) |
| What C3 can hold | the head and an LRU within the extension's quota | anything the host has |
| Browser access | still needs a gateway: Spark Connect is gRPC and an extension exposes relations, not an HTTP port **[inf]** | the service is the gateway |
| Lifetime | tied to a session; a recycled session gets a new store (`nutmeg/README.md:12-13`) **[code]** | independent of Sail sessions |
| Fixed cost per request | none for transport | measured 1.1 to 1.3 ms for a trivial Spark Connect query, 3 to 10 ms for the smallest Parquet range read (section 7) **[run]** |

The fixed cost of the remote shape is small against a one-second budget. The in-process shape saves
milliseconds, not seconds, and ties the service to a session. **Recommendation: remote first.** Revisit
in-process only if a driver-resident head is needed to share memory with a layout kernel.

**Arrow Flight SQL in this tree** [code]. `crates/sail-flight` is a Flight SQL server started by
`sail flight server` (`crates/sail-cli/src/runner.rs:22-31`, `183-192`). It is a separate process with its
own session manager (`crates/sail-flight/src/session.rs:72-86`). All clients share one session id,
`flight-default` (`service.rs:55-66`). It accepts SQL text only: `get_flight_info_statement` parses one
statement, executes it, and parks the stream under a UUID ticket (`service.rs:90-176`). `do_get_statement`
streams it once (`service.rs:178-207`). Commands are drained eagerly into memory (`service.rs:134-147`).
Idle sessions expire after 3600 s (`application.yaml:952-958`, marked experimental). There are no
prepared statements, no authentication handler beyond an empty handshake (`service.rs:73-88`), and no
DataFrame plans. So it cannot share a Spark Connect session's temporary views or checkpoints. It can
read tables created in its own session (section 7.6 uses `CREATE TABLE ... USING parquet LOCATION`).
For a remote cell server it is a usable low-overhead SQL path. Spark Connect is the path that shares
catalogs and code with the batch jobs.

## 2. The level table, precisely

### 2.1 Keys

All ids are i64.

- **Quantize.** Take the bounding box of the layout, padded to a square of side `D` at `(x0, y0)`. Let
  `qx = clamp(floor((x - x0) * 2^Lmax / D), 0, 2^Lmax - 1)`, and the same for `qy`. `Lmax = 31` gives a
  62-bit key that is non-negative in i64. The prototype uses exactly this ([`quadsql.py`](quadsql.py)).
- **Morton key.** `key = spread(qx) | spread(qy) << 1`, where `spread` inserts a zero bit between bits
  (five shift-or-mask steps). In Sail it is a chain of projections with `shiftleft`, `|` and `&`. Each step
  is its own `withColumn`, so no subexpression is duplicated.
- **Cell at level l.** `cell_l = key >> 2(Lmax - l)`. The children of `c` are `4c .. 4c+3`. The vertices of
  `c` are `key in [c << 2(Lmax-l), (c+1) << 2(Lmax-l))`, one contiguous range. This is the quadkey prefix
  property of the Bing Maps tile system ("the quadkey of any tile starts with the quadkey of its parent
  tile") **[lit]**.
- **One id for a cell of any level (for the API).** Use S2's convention: a trailing marker bit,
  `cid = (cell << (2(Lmax-l)+1)) | (1 << 2(Lmax-l))`. The level is the position of the lowest set bit, and
  the descendants of `cid` are the contiguous range `[cid - lsb + 1, cid + lsb - 1]`. S2 documents both
  properties for its 64-bit cell ids **[lit]**. With `Lmax = 31` the top bit used is 62, so `cid` is a
  non-negative i64. A frontier of mixed levels is then a sorted list of disjoint ranges. Mapping any key to
  its visible cell is a binary search.
- **3D.** Interleave three axes. 21 bits per axis fit 63 bits. A cell has 8 children and `cell_l = key >> 3(Lmax-l)`.

### 2.2 Schemas

| Table | Columns | Sort | Rows |
|---|---|---|---|
| `VK` | `vid i64, key i64, x f64, y f64` | `key` | \|V\| |
| `EK` | `src_key i64, dst_key i64, src i64, dst i64` (each undirected edge twice; self loops dropped; optional `w f32`) | `src_key` | 2\|E\| |
| `LEVELS` | `level i8, cell i64, mass i64, sx f64, sy f64, xmin f64, xmax f64, ymin f64, ymax f64, deg_sum i64` | `(level, cell)` | section 2.3 |
| `PE_l` | `src_cell i64, dst_cell i64, w i64` (both directions; `src_cell = dst_cell` is the cell's internal edge count) | `src_cell` | at most min(16^l, 2\|E\|) |

The centroid is `(sx/mass, sy/mass)`. `deg_sum` is the number of `EK` rows whose `src_key` falls in the
cell, which is the cost of an on-demand expand (section 3). The prototype stores everything except
`deg_sum`.

### 2.3 Store all levels, or compute a level on demand

- **One level on demand** is one `GROUP BY cell_l(key)` over `VK`: |V| rows in, at most min(4^l, |V|) out.
  Measured on cit-Patents: 36 to 59 ms for level 6, 97 to 135 ms for level 8 (65,536 rows) **[run]**.
  Restricted to one cell, it is a key-range scan plus a group-by. With `VK` sorted: 8 to 31 ms **[run]**.
- **All levels** are built from the finest one: one `GROUP BY` over `VK` at level `L_c`, then each coarser
  level is aggregated from the one below (at most 4^(l+1) rows in). Measured on cit-Patents, levels 0..12
  in 0.81 s **[run]**.

Rows per level are at most min(4^l, |V|). Measured on cit-Patents **[run]** (`levels-rows` records):

| Level | 3 | 5 | 7 | 8 | 10 | 12 |
|---|---|---|---|---|---|---|
| random layout: cells | 64 | 1,024 | 16,384 | 65,536 | 1,020,076 | 3,379,483 |
| random: largest mass | 59,600 | 3,903 | 294 | 90 | 17 | 6 |
| hierarchical layout: cells | 63 | 927 | 12,648 | 45,503 | 439,170 | 2,099,108 |
| hierarchical: largest mass | 661,668 | 48,708 | 3,154 | 840 | 73 | 13 |

Storage **[calc]** (`estimates.out` section 1). Store every level down to `L*`, where the mean mass is still
at least 16. That is `L* = floor(log4(|V|/16))`. At 64 B per row:

| \|V\| | L* | rows in levels 0..L* | bytes | all levels 0..31 |
|---|---|---|---|---|
| 1e6 | 7 | 21,845 | 1.3 MiB | 2.2e7 rows, 1.3 GiB |
| 1e8 | 11 | 5.6e6 | 341 MiB | 1.9e9 rows, 113 GiB |
| 1e9 | 12 | 2.2e7 | 1.3 GiB | 1.7e10 rows, 1.0 TiB |

Storing all 32 levels costs about |V| rows per level below `log4 |V|`. That is the "|V| times levels" worst
case of the task. It is never needed.

### 2.4 The head: the part worth materializing

The service only needs a cell as an aggregate while its parent is too heavy to show as real nodes. So
the useful tree is the set of cells whose parent holds more than T vertices. In a uniform layout its
internal cells number about (4/3)|V|/T' with T' in [T, 4T). Their children are four times that, which
gives the bound (16/3)|V|/T. Skewed layouts add at most |V|/T cells per extra level of depth **[calc]**.

| \|V\| | T = 1e3 | T = 1e4 | T = 1e5 | bytes at T = 1e4 |
|---|---|---|---|---|
| 1e6 | 5,333 | 533 | 53 | 34 KiB |
| 1e8 | 533,333 | 53,333 | 5,333 | 3.3 MiB |
| 1e9 | 5.3e6 | 533,333 | 53,333 | 33 MiB |

Measured on cit-Patents **[run]** (`adaptive-tree-cells`): random 5,509 / 1,365 / 85 cells for
T = 1e3 / 1e4 / 1e5. Hierarchical: 10,156 / 1,177 / 129. The bound is 20,132 / 2,013 / 201. So the head
fits in the cell server's memory at every size considered. It answers "children of c" without touching
storage. This is the draft's "maybe the head of the tree can be materialized", with a size.

## 3. Pseudo-edges

### 3.1 Cost and size

`PE_l = GROUP BY (cell_l(src_key), cell_l(dst_key)) count(*)` over `EK`. Building `EK` costs two joins of
`E` with `VK` (one per endpoint) and a sort. After that, every level is one aggregate over 2|E| rows, or
a rollup of the level below.

Rows: at most min(2|E|, 16^l). A layout with no locality is the worst case. Expected rows are
`16^l (1 - exp(-2|E|/16^l))`, and that predicts the measured counts to 0.2% **[run]** **[calc]**:

| Level | 2 | 4 | 6 | 8 | 10 | 12 |
|---|---|---|---|---|---|---|
| random layout, measured | 256 | 65,536 | 14,412,661 | 32,900,343 | 33,036,666 | 33,037,845 |
| formula | 256 | 65,536 | 14,435,667 | 32,911,103 | 33,037,349 | 33,037,843 |
| hierarchical layout, measured | 256 | 33,908 | 1,802,799 | 24,683,670 | 32,962,279 | 33,036,041 |

Reading:

- With no locality, a level saturates at 16^l pairs as soon as 16^l is well below 2|E|. Below that it
  holds nearly one row per edge. At cit-Patents size, level 8 and below already hold one row per edge.
  Pseudo-edges then compress nothing.
- The hierarchical placeholder has locality down to about 1/32 of the side (section 7.1). It cuts level 6
  by a factor of 8 and level 4 by 2. Below its smallest scale it behaves like the random layout. A real
  force layout has locality down to the edge length, so its curve should stay lower to deeper levels
  **[inf]**.
- So a full level is never a thing to send to a browser below level 5 or so. Measured: the full level-7
  view is 31M pseudo-edges (712 MiB, 11 s) for random and 7.8M (179 MiB, 2.1 s) for hierarchical
  **[run]**. Views must be frontier-bounded, and each cell's pseudo-edges capped at the top k by weight.
  Cornac does the same: it sorts a tile's edges by count and sends the top n **[lit]**.

Worst case at scale (random layout, |E| = 16|V|) **[calc]**:

| \|V\| | 2\|E\| | l = 4 | l = 6 | l = 8 | l = 10 |
|---|---|---|---|---|---|
| 1e6 | 3.2e7 | 6.6e4 | 1.4e7 | 3.2e7 | 3.2e7 |
| 1e8 | 3.2e9 | 6.6e4 | 1.7e7 | 2.3e9 | 3.2e9 |
| 1e9 | 3.2e10 | 6.6e4 | 1.7e7 | 4.3e9 | 3.2e10 |

### 3.2 Options

| Option | Precompute | Per expand | Storage | Verdict |
|---|---|---|---|---|
| A. Precompute every level | `PE_0 .. PE_Lc` | read `PE_(l+1)` rows of 4 children | sum of section 3.1, up to \|levels\| x 2\|E\| | Cornac's choice; about 20 times the raw size **[lit]** |
| B. Precompute none | nothing | scan `EK` rows of the cell: mass(c) x degree | none | fine at 1e6, fails for coarse cells at 1e8 and 1e9 |
| C. **Precompute coarse levels only** (recommended) | `PE_0 .. PE_(Lp+1)` | `PE` block if `deg_sum(c) > R`, else `EK` range | at most sum of min(16^l, 2\|E\|) for l up to Lp+1 | bounded both ways |
| D. Per viewport, on demand, filtered on visible cells | nothing | `EK` rows with `src_key` in any visible cell | none | same as B summed over the viewport; never cheaper than B for an expand |

The rule for C **[calc]** (`estimates.out` section 4): `L_p` is the smallest l with 32|V|/4^l <= R, where R is
the edge-row budget of one on-demand expand.

| \|V\| | R = 1e6 | R = 1e7 | R = 1e8 |
|---|---|---|---|
| 1e6 | L_p = 3, 7e4 rows | L_p = 1 | L_p = 0 |
| 1e8 | L_p = 6, at most 2.9e8 rows (628 MiB) | L_p = 5, at most 1.8e7 rows (39 MiB) | L_p = 3 |
| 1e9 | L_p = 8, at most 3.7e10 rows (78 GiB) | L_p = 6, at most 2.9e8 rows (628 MiB) | L_p = 5, at most 1.8e7 rows (39 MiB) |

Bytes at the measured 2.3 B per stored row. These are worst-case (random layout) sizes. With `deg_sum` per cell the rule becomes per cell: dense
cells deeper than `L_p` get precomputed blocks too, and sparse coarse regions need none.

### 3.3 The visible-window query

"Expand c" (frontier level l, children at level l+1) returns:

1. the 4 children of c: from the head in memory, or one range read of `LEVELS` (`cell between 4c and 4c+3`);
2. pseudo-edges between each child and every visible cell (the other children included):
   - precomputed: read `PE_(l+1)` rows with `src_cell between 4c and 4c+3`, then map `dst_cell` to the
     visible cell that contains it, then sum.
   - on demand: read `EK` rows with `src_key` in the key range of c, take `cell_(l+1)(src_key)`, map
     `dst_key` to its visible cell, then count.

Both are bounded reads only because `PE_l` and `EK` are sorted by the source key. Then the range
predicate prunes row groups and pages. Pseudo-edges among the visible cells that are not c do not
change, so the client keeps them.

Mapping to the frontier. The visible cells are disjoint key ranges. A destination key maps to the one
range containing it, by binary search over at most K ranges. With `PE_(l+1)` the destination is a cell at
level l+1. That only resolves frontier cells at level l+1 or coarser. Where the user has expanded deeper
elsewhere, either read a finer `PE` (cost: more rows), or report the edge to that region's ancestor at
level l+1 and draw it to the ancestor's centroid. The on-demand path is exact at any depth, because it
maps vertex keys. That choice is an open decision (section 9, D2).

### 3.4 What Sail can and cannot do here today

| Need | Today | Evidence | Upstream issue |
|---|---|---|---|
| Sorted files from a sort before a Parquet write | **yes, in the default save mode only**. `mode("overwrite")` drops the sort: 4 of 4 files unsorted, against 4 of 4 sorted with the same frame in the default mode | [run] `raw/probe-sorted-write.txt` ([`probe_sorted_write.py`](probe_sorted_write.py)). Mechanism [code]: overwrite wraps the sink in `BarrierExec` with a `FileDeleteExec` (`crates/sail-data-source/src/listing/planner.rs:253-258`, `source.rs:315`). `BarrierExec` does not override `maintains_input_order` (`crates/sail-physical-plan/src/barrier.rs:64-80`), so the sort below it is removed as unneeded **[inf]**, the same way as for Delta in `delta-order-plans` section 1. Same code in upstream `99ee46f69` (`planner.rs:258`). New; not in the earlier studies, which wrote in the default mode | [lakehq/sail#2741](https://github.com/lakehq/sail/issues/2741) |
| Pruning on a key range over sorted Parquet | **yes**: row-group statistics and the page index | [run] `raw/explain-analyze-cit-Patents-random-ek-sorted.txt`: row groups 32 total, 4 matched; pages 152 total, 4 matched; 98.3K rows and 3.22 MB scanned. Unsorted: 33.04M rows, 219.7 MB (`...-ek-plain.txt`) | none needed |
| Delta tables clustered by key | **no**: `CLUSTER BY` and `OPTIMIZE ... ZORDER BY` are refused, and a sort before a Delta write is dropped | `delta-order-plans` section 1 | [lakehq/sail#2726](https://github.com/lakehq/sail/issues/2726) (the dropped sort). `CLUSTER BY` and `ZORDER` are missing features; no issue filed |
| Delta file pruning by min/max | works, if files are clustered, which Sail cannot produce | `delta-order-plans` section 2 | none needed |
| Range partitioning for disjoint files | **no**: `repartitionByRange` plans a hash repartition | `delta-order-plans` section 5 | [lakehq/sail#2728](https://github.com/lakehq/sail/issues/2728) |
| Global sort for a write | `orderBy` then write merges all partitions into one stream (`SortPreservingMerge`) before the sink | `delta-order-plans` section 1 (write plan); time in section 7.4 **[run]** | none: works as designed |
| A sort that a later query can trust | checkpoint after sort returns **wrong results**; never sort before `checkpoint()` | `delta-order-plans` section 4 | [lakehq/sail#2722](https://github.com/lakehq/sail/issues/2722) |
| Session-independent caching | none: `persist` is a no-op, checkpoints are per session and removed at shutdown | section 1.1; `delta-order-plans` section 4 | none filed |
| Dense ids | not needed: the key comes from coordinates, and `vid` stays the user's i64. If a renderer wants 0..n-1 buffer indexes, the client numbers the rows of each response. Never use `monotonically_increasing_id()` before writing it | `dense-ids` summary item 3 and line 917 | [lakehq/sail#2732](https://github.com/lakehq/sail/issues/2732) (a sort under `monotonically_increasing_id()` is removed) |
| A declared order Sail would trust without a sort | **no**: the sort order recorded in Parquet footers (`sorting_columns`) is never used, and `DataFrameWriter.sortBy` fails to resolve its column | `delta-order-plans` section 1 and 3 | [lakehq/sail#2730](https://github.com/lakehq/sail/issues/2730), [lakehq/sail#2727](https://github.com/lakehq/sail/issues/2727) |

For the scales where one sorted stream is too slow, the alternative is
`repartition(T, cell_b(src_key)).sortWithinPartitions(src_key)`, written in the default mode. Each file is
then sorted, so pages are narrow, but every file spans the whole key range, and a query reads one page
run in each of T files. Parquet keeps that sort (`delta-order-plans` section 1, `parquet-hash-sorted`,
point query 73.7K rows of 2M) **[run, earlier study]**. With bucket split points chosen from `LEVELS`, files
could instead hold disjoint ranges via `partitionBy(bucket)`. That needs the slow `partitionBy` write ([lakehq/sail#2731](https://github.com/lakehq/sail/issues/2731)) and
is not tested here **[inf]**.

## 4. Interaction latency budget

Target: an expand in under 1 s at the 95th percentile, the first view in under 2 s **[inf]**, in line with
interactive tile viewers (Cornac reports 10 to 100 ms per tile transfer **[lit]**). Budget:

| Step | Budget | Basis |
|---|---|---|
| browser to service round trip | 50 to 150 ms | WAN, assumption |
| service: find children, plan the range read | under 5 ms | head in memory; trivial Sail query 1.1 to 1.3 ms **[run]** |
| Sail: range read and aggregate | 10 to 500 ms | depends on rows and storage (below) |
| Arrow to the browser, decode, render | 50 to 200 ms | 0.1 to 1 MB per response **[run]**; render is the client's |

What the read costs. Measured on local SSD, warm footer cache, 10 cores **[run]**: a pruned range read of
1e5 to 6e5 edge rows takes 8 to 150 ms end to end. Unpruned scans take 50 to 120 ms for 33M edge rows and
about 0.5 s for 521M. That is a scan rate of about 3e8 to 1e9 rows/s on this laptop. On object storage the bytes dominate.
Assume about 200 MB/s for one reader and 20 to 100 ms per request **[inf]**, with 2 to 3 round trips
(footer and page index cached by Sail after the first time).

| Design | 1e8 vertices | 1e9 vertices |
|---|---|---|
| On-demand expand, frontier level 5, uniform cell | 3.1e6 rows, 43 MiB: about 0.2 s from object storage | 3.1e7 rows, 432 MiB: about 2 s. **Misses the budget** |
| On-demand expand, frontier level 3 | 5e7 rows, 691 MiB: about 3.5 s. **Misses** | 5e8 rows, 6.8 GiB. **Misses** |
| Precomputed `PE_(l+1)` block, any l up to L_p | at most 4 x 4^(l+1) rows (16k at l = 5) and less than 1 MiB | the same bound, independent of \|V\| |
| Leaf (real nodes) at T = 1e4 | 1e4 vertex rows + 3.2e5 edge rows, about 5 MiB | the same |
| Children of c | from the head, under 1 ms | the same |
| Full level as a first view | only up to level 4 or 5 (section 3.1) | the same |

**[calc]** from `estimates.out` section 5. So precomputed coarse blocks plus pruned reads meet the budget at
1e8 and 1e9. On-demand aggregation meets it only for cells under about 1e5 vertices (`deg_sum` up to about
3e6 rows).

Where the cache sits:

| Cache | Holds | Key | Size |
|---|---|---|---|
| C3 head | `LEVELS` rows of the head | `(version, cid)` | 33 MiB at 1e9, T = 1e4 |
| C3 block LRU | raw `PE_(l+1)` blocks of 4 children, unmapped; leaf blocks | `(version, cid, level of PE)` | a byte budget, for example 1 GiB; one block is under 1 MiB **[run]** |
| C6 browser | responses already mapped to its frontier; deck.gl's `TileLayer` defaults to 5 times the visible tiles (`maxCacheSize`) **[lit]** | `(version, cid)` | tens of MiB |

Blocks are cached unmapped, so users with different frontiers share them. The mapping to one frontier is a
cheap per-request step. Everything is keyed by `layout_version`, so a new layout never serves stale cells.

## 5. Prior art

Every item was checked on the web on 2026-10-03 (title, authors or vendor, year, link). "Read" says how
much.

| Work | Trick | Transfers? | Read |
|---|---|---|---|
| Perrot, Auber. "Cornac: Tackling Huge Graph Visualization with Big Data Infrastructure". IEEE Trans. Big Data, 2018 early access, [doi:10.1109/TBDATA.2018.2869165](https://doi.org/10.1109/TBDATA.2018.2869165), [HAL hal-01872712](https://hal.science/hal-01872712) | Spark/GraphX batch over a precomputed layout. It merges nodes geometrically, level by level (unit-disk clustering, d_i = d0/2^i), merges edges between merged nodes with a count, and keeps at most S long edges per node by direction. Each level is cut into 4^i map tiles stored in HBase. The browser fetches tiles by viewport and clears off-screen tiles when its cache is full. OSM-Europe: 174M nodes, 348M edges, 22 levels, 11.5 GB raw, 202 GB in HBase ("The ratio of aggregated data to raw data is around 20", Table 1). | **Yes, the closest system.** Differences here: Morton keys instead of (l, i, j); fixed quadtree cells via GROUP BY instead of representative election; a head plus on-demand blocks instead of the full pyramid, which avoids the 20x | Full text (accepted manuscript) |
| Abello, van Ham, Krishnan. "ASK-GraphView: A Large Scale Graph Visualization System". IEEE TVCG 12(5):669-676, 2006, [doi:10.1109/TVCG.2006.120](https://doi.org/10.1109/TVCG.2006.120) | A cluster hierarchy, viewed through a cut of the tree. "Macro edges" between cut nodes carry the summed weights of the edges below. At most 64 children per expansion. "up to 16 million edges"; the RAM bound is the stated limit (32 B per edge, 2 GB) | Macro edge = pseudo-edge. The per-expansion bound matches the frontier bound. Its hierarchy is clustering, not space | Full text |
| Archambault, Munzner, Auber. "Grouse: Feature-Based, Steerable Graph Hierarchy Exploration". EuroVis 2007, [EG DL](https://diglib.eg.org/items/22b91b7b-af8f-4dfa-8c17-ef1cb687314b) | Opens metanodes of a given hierarchy on demand and lays out only the opened subgraph | The expand interaction without global relayout. Small scale (7,640 nodes in its example) | Abstract, parts of full text |
| Archambault, Munzner, Auber. "GrouseFlocks: Steerable Exploration of Graph Hierarchy Space". IEEE TVCG 14(4):900-913, 2008, [doi:10.1109/TVCG.2008.34](https://doi.org/10.1109/TVCG.2008.34) | Users build several alternative hierarchies over one graph | Argues that the spatial quadtree should not be the only hierarchy (open decision D8) | Abstract, dataset section |
| Archambault, Munzner, Auber. "TopoLayout: Multilevel Graph Layout by Topological Features". IEEE TVCG 13(2):305-317, 2007, [doi:10.1109/TVCG.2007.46](https://doi.org/10.1109/TVCG.2007.46) | Detects trees, biconnected components and clusters, collapses them, and lays out each with a suitable algorithm | Layout stage only (section 6) | Abstract, result tables |
| Elmqvist, Fekete. "Hierarchical Aggregation for Information Visualization: Overview, Techniques, and Design Guidelines". IEEE TVCG 16(3):439-454, 2010, [doi:10.1109/TVCG.2009.84](https://doi.org/10.1109/TVCG.2009.84) | Each aggregate summarizes its subtree by count or sum, extents, average and distribution. Navigation is drill-down and roll-up | The `LEVELS` row is exactly count, sum and extents | Abstract, aggregate section |
| Elmqvist, Do, Goodell, Henry, Fekete. "ZAME: Interactive Large-Scale Graph Visualization". IEEE PacificVis 2008, [doi:10.1109/PACIFICVIS.2008.4475479](https://doi.org/10.1109/PACIFICVIS.2008.4475479) | An adjacency matrix aggregated into a pyramid and paged on demand; French Wikipedia, 500k articles and 6M links | `PE_l` is a level of that pyramid in Morton order. A matrix view comes free | Abstract |
| Nachmanson, Prutkin, Lee, Riche, Holroyd, Chen. "GraphMaps: Browsing Large Graphs as Interactive Maps". GD 2015, [doi:10.1007/978-3-319-27261-0_1](https://doi.org/10.1007/978-3-319-27261-0_1) | Nodes ranked into zoom layers by tile quotas: "the number of entities rendered at each view does not exceed a predefined threshold" | The quota is the mass threshold T as a rendering budget. Small graphs | Method section |
| Zinsmaier, Brandes, Deussen, Strobelt. "Interactive Level-of-Detail Rendering of Large Graphs". IEEE TVCG 18(12):2486-2495, 2012, [doi:10.1109/TVCG.2012.238](https://doi.org/10.1109/TVCG.2012.238) | Density-field node aggregation and edge cumulation per frame on the GPU, no precomputed hierarchy | A client-side alternative, bounded by GPU memory (Cornac reports it ran out of 16 GB on OSM-Europe) | Abstract, introduction |
| Datashader (HoloViz, Anaconda). [Networks guide](https://datashader.org/user_guide/Networks.html) | Rasterizes points and edge segments into a fixed pixel grid with reductions such as count, then shades. `hammer_bundle` bundles edges | Fallback when a view has too many pseudo-edges: rasterize `(cell, cell)` counts on the server as an image | Docs pages |
| Graphistry (vendor). [Release 2.53.0 blog](https://www.graphistry.com/blog/graphistry-2-53-0-large-graph-visualization-at-10-million-edges), 2026-09-03 | GPU server layout and analytics, WebGL client, rendering split between server and client GPUs. "a 10-million-edge graph ... now needs 537 MB" in the browser | The opposite design: ship the whole graph. It shows where that ends (about 1e7 edges) | Blog, README |
| Neo4j Bloom. [Settings drawer](https://neo4j.com/docs/bloom-user-guide/current/bloom-visual-tour/settings-drawer/) | "Node query limit - can be adjusted within a range of 100-10000"; expansion obeys the same limit | Commercial explorers cap the working set near 1e4 nodes. That supports T near 1e4 | Docs pages. No per-scene maximum found |
| cosmos.gl (formerly Cosmograph's cosmos), N. Rokotyan and O. Stukova. [Repository](https://github.com/cosmosgl/graph), [OpenJS announcement](https://openjsf.org/blog/introducing-cosmos-gl), 2025 | Force simulation and rendering in WebGL shaders, positions kept in GPU textures. "over one million nodes and links" (OpenJS) | A renderer for the leaf level, and a client-side layout for subgraphs under about 1e6 | Docs, README |
| deck.gl `TileLayer` and `MVTLayer`, [docs](https://deck.gl/docs/api-reference/geo-layers/tile-layer); kepler.gl [release notes](https://docs.kepler.gl/release-notes) | Tiles indexed by (x, y, z) are fetched for the viewport and cached (`maxCacheSize` defaults to 5 times the visible tiles). Works in a non-geographic `OrthographicView`. Custom indexing via `Tileset2D` | Directly usable for a map-style client: `getTileData(x, y, z)` maps to a key range | Docs |
| Schwartz. "Bing Maps Tile System". Microsoft Learn, [article](https://learn.microsoft.com/en-us/bingmaps/articles/bing-maps-tile-system) | Quadkeys interleave the tile's x and y bits; key length = level; a child's quadkey extends its parent's; nearby tiles have nearby quadkeys | This is the key of section 2.1 | Full page |
| Mapbox. "Vector Tile Specification" 2.1, [spec](https://github.com/mapbox/vector-tile-spec/blob/master/2.1/README.md) | Per-tile protobuf with integer coordinates in a per-tile extent (often 4096); the z/x/y scheme is a convention outside the tile | A possible wire format for a map client. Arrow IPC is simpler here | Spec text |
| Google S2 geometry. "S2 Cell Hierarchy", [devguide](http://s2geometry.io/devguide/s2cell_hierarchy.html) | 64-bit cell ids with a trailing 1 bit; "the subdivision level of a cell can easily be determined from the position of its lowest-numbered 1 bit"; `range_min` and `range_max` give the contiguous id range of the descendants | The single-i64 cell id of section 2.1 | Docs page |
| Jacomy, Venturini, Heymann, Bastian. ForceAtlas2, PLoS ONE 9(6):e98679, 2014, [doi:10.1371/journal.pone.0098679](https://doi.org/10.1371/journal.pone.0098679); Gephi [README](https://github.com/gephi/gephi) | "ForceAtlas2 is not adapted to networks bigger than 100,000 nodes, unless allowed to work over several hours". Gephi's README claims "up to a million elements" | The draft's "Gephi cannot handle more than 100k nodes" is the ForceAtlas2 limit; Gephi itself claims about 1e6 elements | Article, README |

Also verified, not used above: Holten, "Hierarchical Edge Bundles", IEEE TVCG 12(5), 2006,
[doi:10.1109/TVCG.2006.147](https://doi.org/10.1109/TVCG.2006.147). Its idea, bending edges along the
hierarchy path, suits pseudo-edges drawn through the quadtree. Also Liu, Jiang, Heer, "imMens", CGF 32(3),
2013, [doi:10.1111/cgf.12129](https://doi.org/10.1111/cgf.12129): precomputed binned data tiles as the unit
of transfer.

Not verified, so not used: a stated scene limit for Bloom; Graphistry's client limits; a Gephi node limit
in its own documentation (only "more than 10,000 nodes" for the desktop in its FAQ).

## 6. The layout question, briefly

The service consumes `L(vid, x, y)` and `layout_version`, nothing else. So the layout is a separate,
swappable job. From the ForceAtlas2 study:

| \|V\| | Route | Why |
|---|---|---|
| 1e6 | Driver-native ForceAtlas2 with Barnes-Hut (FA2 study 7.2): relational attraction, native repulsion | Tree of 28 MiB; minutes. A GPU kernel (cuGraph, Brinkmann et al.) or cosmos.gl would also do |
| 1e8 | Multilevel: coarsen relationally (Pregel-shaped merges), lay out the coarsest graph natively, refine with tens of iterations per level. Driver kernel at the coarse levels; negative sampling or the driver kernel (with a large driver, 2.7 GiB tree) for the finest | 500 full-size iterations would be 14 hours on 16 cores at 1e8 (FA2 study 3.4); multilevel cuts full-size iterations |
| 1e9 | Multilevel with negative sampling for the fine levels (relational, M rows per vertex per iteration, no broadcast), or Morton-range partitions with local trees (research-grade) | The tree alone is 27 GiB; repulsion must leave the driver |

Does the hierarchical layout argue for coupling? A multilevel layout produces coarse supernodes with
positions, much like `LEVELS`. But its supernodes are graph clusters (matchings, solar systems,
communities), and the quadtree cells are regions of the plane. Each level of the quadtree is one
GROUP BY on the final positions, which is cheap (0.8 s for all levels at 3.8M vertices **[run]**). Reusing
the layout's hierarchy would save that GROUP BY and would make cells follow communities, as in
ASK-GraphView. The price is a second key scheme and a service that depends on one layout algorithm.
**Recommendation: do not couple.** Optionally carry the layout's cluster path as extra columns of `VK`,
for a second, community-based hierarchy (GrouseFlocks' point), served by the same machinery with a
different key.

A slowly changing graph keeps its layout version for a long time. An incremental layout that moves few
vertices invalidates few blocks, but blocks are immutable per version. Rebuilding C2 is one pass over `E`
(section 7.4). Diffing versions is not worth its complexity before C2's rebuild time is a problem **[inf]**.

## 7. Prototype and measurements

### 7.1 Setup

- Machine: Apple M1 Max, 10 cores, 64 GiB, macOS 26.2. **Shared**: another agent ran Sail and Rust jobs at
  the same time. Load average 10 to 30 during the cit-Patents runs and up to 147 during the graph500-24
  runs (`load_average` in each `start` record). **These numbers are shape only.**
- Sail: release binary above, `SAIL_MODE=local`, `SAIL_EXECUTION__DEFAULT_PARALLELISM=10`, every other
  `SAIL_*` variable removed, `RUST_LOG=warn` ([`vizserver.py`](vizserver.py)). Parquet defaults:
  `parquet.pruning=true`, `parquet.enable_page_index=true`, `parquet.pushdown_filters=false`,
  `parquet.max_row_group_size=1048576`, `parquet.data_page_row_count_limit=20000`
  (`application.yaml:472-530`, `633-660`) **[code]**. PySpark Connect 4.0.1, pyarrow 25.0.1, Python 3.12.8.
  One server at a time, on an ephemeral port, stopped at the end of each script.
- Data: LDBC `cit-Patents` (3,774,768 vertices, 16,518,947 edges; 33,037,845 edge rows in both directions
  without self loops) and `graph500-24` (8,870,942 vertices, 260,379,520 edges).
- Timing: wall time in the client, from the call to an Arrow table (`toArrow()`) or to the end of a write.
  Interaction queries get one untimed warm-up (recorded as `first`) and then 3 timed runs. Builds get 3
  timed runs. Median and range.

**Placeholder layouts** ([`layout.py`](layout.py), not layout algorithms):

- `random`: `x, y` = two independent hashes of the id. No locality: the worst case for pseudo-edges.
- `hierarchical`: min-priority label propagation over the undirected edges, priority `xxhash64(id)`. After
  r rounds a vertex's label is the lowest priority within r hops. Each coordinate is
  `0.5 + 0.5 u(p8) + 0.25 u(p4) + 0.125 u(p2) + 0.0625 u(p1) + 0.03125 u(id)`, each u an independent hash
  centred on 0. Vertices that share labels share boxes, so edges are short at the scales of side 1/2
  down to 1/32. On cit-Patents the 8-round label covers 3,063,027 vertices (81%): a dense core. On
  graph500-24 it covers 8,865,133 (99.9%) after 5 rounds, because the graph's diameter is small
  (`raw/layout-*.jsonl`).

**Measured with** [`bench.py`](bench.py). Raw lines: `raw/bench-<graph>-<layout>.jsonl`. Tables:
[`summarize.py`](summarize.py) gives `raw/summary.txt`. File facts: [`file_layouts.py`](file_layouts.py)
gives `raw/file-layouts.json`.

### 7.2 Building the tables (seconds, median and range of 3)

Seconds, median (range) of 3 runs. Each write is followed by nothing else; the `PE` cells also read the
row count back. Source: `raw/bench-<graph>-<layout>.jsonl`, `raw/summary.txt` **[run]**.

| Step | cit-Patents, random | cit-Patents, hierarchical | graph500-24, random |
|---|---|---|---|
| bounding box (one aggregate) | 0.027 (0.026-0.032) | 0.028 (0.026-0.032) | 0.056 (0.048-0.060) |
| `VK`, unsorted write | 0.083 (0.081-0.084) | 0.092 (0.085-0.093) | 0.272 (0.266-0.280) |
| `VK`, sorted write | 0.188 (0.183-0.223) | 0.183 (0.183-0.191) | 0.626 (0.604-0.646) |
| `EK` (2 joins, both directions), unsorted write | 1.00 (1.00-1.06) | 1.13 (1.13-1.18) | 21.9 (21.5-24.8) |
| `EK`, sorted write | 1.61 (1.60-1.65) | 1.76 (1.69-2.34) | 52.5 (51.0-55.4) |
| `LEVELS`, all levels 0..12 (finest, then rollups) | 0.81 (0.81-0.86) | 0.82 (0.81-0.85) | 2.25 (2.12-2.30) |
| one level on demand, l = 6, to Arrow | 0.036 (0.036-0.039), 4,096 rows | 0.059 (0.050-0.064), 3,441 rows | 0.075 (0.065-0.101), 4,096 rows |
| one level on demand, l = 8, to Arrow | 0.135 (0.135-0.153), 65,536 rows | 0.097 (0.093-0.135), 45,503 rows | 0.251 (0.235-0.260), 65,536 rows |
| `PE_4` from `EK`, sorted write | 0.165 (0.163-0.172), 65,536 rows | 0.139 (0.138-0.141), 33,908 rows | 4.03 (3.68-4.21), 65,536 rows |
| `PE_6` | 0.662 (0.662-0.664), 14.4M rows | 0.390 (0.380-0.401), 1.80M rows | 11.1 (10.6-11.2), 16.8M rows |
| `PE_8` | 1.05 (1.05-1.06), 32.9M rows | 0.942 (0.937-0.958), 24.7M rows | 74.0 (69.3-75.5), 454M rows |
| `PE_10` | 1.21 (1.19-1.23), 33.0M rows | 1.22 (1.20-1.24), 33.0M rows | 68.5 (67.9-88.2), 517M rows |
| `PE_12` | 1.40 (1.37-1.43), 33.0M rows | 1.32 (1.28-1.46), 33.0M rows | not run |
| `PE_8` from raw `E` with both joins, count only (no write) | 1.03 (0.95-1.04) | 1.10 (1.10-1.11) | 31.8 (27.3-32.1) |
| all `PE` levels by rollup from the finest (12, or 10 for graph500) | 6.42 (6.42-6.87) | 4.58 (4.55-4.75) | 105 (85-121) |
| peak server RSS during the builds (ps, 50 ms samples) | 6.2 GiB | about 6 GiB | 25.7 GiB |

Stored sizes (`raw/file-layouts.json`) **[run]**: `VK` 25 to 27 B per row; `EK` sorted 14.3 to 14.6 B per row on
cit-Patents and 11.7 on graph500-24 (unsorted 18.4 to 19.1 and 12.4); `PE_l` sorted 1.8 to 2.3 B per row
(unsorted 3.3 to 4.5); `LEVELS` 57 to 60 B per row. All tables written sorted have every file sorted by its
key (`files_sorted_by_key`).

Extrapolated to 1e8 and 1e9 vertices, linear in edge rows (`estimates.out` section 6) **[calc]**: the sorted `EK`
build is about 0.9 and 9 core-hours, `PE_8` about 1.3 and 12.6 core-hours, all `PE` levels by rollup about 1.8
and 18 core-hours. That is the same order as one or two Pregel rounds on the same graph, done once per
layout version. Linear scaling is an assumption: a sort is n log n, and a cluster adds network shuffles.

### 7.3 Interaction queries on cit-Patents (seconds, median and range of 3, after one warm-up)

Frontier = all non-empty cells of level l. "heaviest" and "median" pick the cell of that mass rank.
"sorted": tables written after `orderBy(key)`, default save mode. "plain": the same rows in arrival order
(`VK`, `EK`) or scrambled by a hash (`PE`).

| Query (frontier level l, the cell with the most vertices) | cit-Patents random, l = 5 | cit-Patents hierarchical, l = 5 | cit-Patents hierarchical, l = 7 | graph500-24 random, l = 5 | graph500-24 random, l = 7 |
|---|---|---|---|---|---|
| cell mass | 3,903 | 48,708 | 3,154 | 8,938 | 638 |
| children from `LEVELS` (stands in for the in-memory head) | 0.003 (0.003-0.003) | 0.003 (0.003-0.003) | 0.033 (0.014-0.069) | 0.003 (0.003-0.003) | 0.005 (0.005-0.006) |
| children on demand from `VK`, sorted | 0.010 (0.009-0.010) | 0.010 (0.010-0.011) | 0.024 (0.018-0.036) | 0.010 (0.010-0.011) | 0.011 (0.010-0.014) |
| children on demand from `VK`, plain | 0.028 (0.027-0.028) | 0.026 (0.025-0.030) | 0.040 (0.036-0.079) | 0.040 (0.038-0.040) | 0.038 (0.037-0.040) |
| expand: pseudo-edges from precomputed `PE_(l+1)`, sorted | 0.008 (0.008-0.011) | 0.007 (0.007-0.007) | 0.043 (0.040-0.060) | 0.008 (0.008-0.009) | 0.011 (0.011-0.012) |
| expand: pseudo-edges on demand from `EK`, sorted | 0.009 (0.009-0.009) | 0.014 (0.014-0.017) | 0.035 (0.026-0.036) | 0.013 (0.012-0.014) | 0.013 (0.011-0.014) |
| expand: precomputed `PE_(l+1)`, plain | 0.021 (0.019-0.023) | 0.010 (0.010-0.013) | 0.072 (0.070-0.079) | 0.020 (0.019-0.023) | **0.456 (0.446-0.462)** |
| expand: on demand from `EK`, plain | 0.055 (0.049-0.058) | 0.070 (0.069-0.079) | 0.102 (0.099-0.106) | **0.539 (0.505-0.585)** | **0.530 (0.494-0.539)** |
| rows returned by the expand (Arrow bytes) | 4,107 (112 KiB) | 2,473 (68 KiB) | 8,979 (246 KiB) | 4,108 (112 KiB) | 21,911 (599 KiB) |

The median-mass cell of each frontier gives the same picture (`raw/summary.txt`). The precomputed and the
on-demand path return identical rows in every case, which cross-checks the two.

First view, a whole level of cells and all its pseudo-edges, to Arrow (median, range):

| | cit-Patents random | cit-Patents hierarchical | graph500-24 random |
|---|---|---|---|
| level 5 | 0.332 (0.331-0.333): 1,024 cells, 1,048,576 pseudo-edges, 24 MiB | 0.076 (0.076-0.080): 927 cells, 304,066 pseudo-edges, 7 MiB | 0.219 (0.188-0.228): 1,024 cells, 1,048,576 pseudo-edges, 24 MiB |
| level 7 | 11.1 (11.0-11.1): 16,384 cells, 31.0M pseudo-edges, 712 MiB | 2.10 (2.08-2.21): 12,648 cells, 7.8M pseudo-edges, 179 MiB | skipped: 211M pseudo-edges |

Real nodes of one cell (the cell nearest 10,000 vertices), vertices and their edge rows:

| | cit-Patents random (level 4, 14,365 vertices) | cit-Patents hierarchical (level 6, 9,969) | graph500-24 random (level 5, 8,938) |
|---|---|---|---|
| vertices, sorted / plain | 0.019 (0.019-0.042) / 0.039 (0.038-0.040) | 0.027 (0.024-0.027) / 0.071 (0.054-0.075) | 0.016 (0.016-0.016) / 0.056 (0.047-0.057) |
| edge rows, sorted / plain | 0.078 (0.077-0.080) / 0.149 (0.139-0.188); 126,762 rows, 3.9 MiB | 0.079 (0.078-0.094) / 0.281 (0.217-0.333); 99,800 rows, 3.0 MiB | 0.153 (0.153-0.154) / 1.53 (1.50-1.61); 581,532 rows, 17.7 MiB |

Pruning, from `EXPLAIN ANALYZE` of the on-demand expand's scan (`raw/explain-analyze-*-ek-*.txt`) **[run]**:

| | rows out of the scan | row groups matched by statistics | rows kept by the page index | bytes scanned | scan time |
|---|---|---|---|---|---|
| cit-Patents random, `EK` sorted | 98.3K | 4 of 32 | 98.3K of 3.68M | 3.22 MB | 5.2 ms |
| cit-Patents random, `EK` plain | 33.04M | 32 of 32 | all | 219.7 MB | 187 ms |
| graph500-24 random, `EK` sorted | 688.1K | 4 of 192 | 688.1K of 4.19M | 0.59 MB | 5.5 ms |
| graph500-24 random, `EK` plain | 520.8M | 500 of 500 | all | 2.18 GB | 3.19 s (summed over partitions) |

Reading:

- Every interactive query on sorted tables took 3 to 43 ms, on both graphs. The floor of about 3 ms is
  Sail's cost of a tiny Parquet range read through Spark Connect. A trivial query costs 1.1 to 1.3 ms.
- Sorting decides the cost once the table is large. On cit-Patents (33M edge rows) plain tables cost 2 to
  7 times more. On graph500-24 (521M edge rows) they cost 40 times more for an expand (0.53 s against
  0.013 s) and 10 times more for a leaf (1.53 s against 0.15 s). With sorting, the time did not grow from
  cit-Patents to graph500-24, although the edge table grew 16 times. That is the property the design needs
  at 1e9.
- Precomputed and on-demand pseudo-edges cost the same here, because the heaviest level-5 cell has at most
  about 5e5 edge rows. The case for precomputing is the arithmetic of sections 3.2 and 4, where a level-5
  cell at 1e9 vertices has 3e7 edge rows. This prototype does not reach it.
- A whole level as the first view is interactive only at level 5 or coarser. At level 7 it is 2 to 11 s and
  179 to 712 MiB, which confirms the need for top-k pseudo-edges per cell.
- Wider ranges in the hierarchical level-7 column coincide with load average above 100 on the shared
  machine.

### 7.4 What the graph500-24 runs add

- Build times grow roughly with edge rows: 16 times the rows gave 22 times (unsorted `EK`) and 33 times
  (sorted `EK`) the time. The sorted write is 2.4 times the unsorted one, and its peak server RSS was 20.9
  GiB (5.8 GiB for cit-Patents). The extra cost is the sort plus the single merged stream of the write
  plan **[inf]**. At 1e9 this would need `sortWithinPartitions` per hash bucket instead (section 3.4).
- `PE_8` holds 454M rows for 521M edge rows: with no locality, one row per edge. That is the worst case of
  section 3.1. It costs as much to build as `EK` itself.
- Pruning works at this size: 4 of 192 row groups, 0.59 MB scanned (table above).
- The hierarchical layout was not benchmarked on graph500-24: its labels collapse to one by round 5, so it
  adds nothing beyond the random layout at coarse scales (`raw/layout-graph500-24.jsonl`).

### 7.5 A superseded run

The first random-layout run wrote with `mode("overwrite")`. Its "sorted" tables were not sorted, and sorted
and plain timed the same. It is kept as `raw/superseded-overwrite-mode-*`. It led to the probe in section
3.4. Also, the `layout-vk-*` lines in `bench-*.jsonl` read the statistics of column `id`, not `key`.
`raw/file-layouts.json` replaces them.

### 7.6 The same expand over Arrow Flight SQL

[`flight_probe.py`](flight_probe.py) starts `sail flight server` (local mode, no other settings), registers
the cit-Patents random tables with `CREATE TABLE ... USING parquet LOCATION`, and runs the frontier-5
expand of the heaviest cell (cell 980) as SQL text. It uses `pyarrow.flight` with hand-encoded Flight SQL
messages. Raw: `raw/flight-cit-Patents-random.jsonl` **[run]**. Seconds, median (range) of 3, after one warm-up.

| Query | Flight SQL | Spark Connect (section 7.3) |
|---|---|---|
| trivial (`SELECT 1` / `spark.range(1)`) | 0.0006 (0.0006-0.0009) | 0.0013 (0.0012-0.0014) |
| children from `LEVELS` | 0.0027 (0.0021-0.0044) | 0.003 (0.003-0.003) |
| expand, precomputed `PE_6`, sorted | 0.0035 (0.0032-0.0037) | 0.008 (0.008-0.011) |
| expand, on demand from `EK`, sorted | 0.0054 (0.0052-0.0067) | 0.009 (0.009-0.009) |

Both paths return the same 4,107 rows. Flight SQL saves a few milliseconds per request, partly the PySpark
client's own work **[inf]**. Against a one-second budget the transport choice is not the deciding factor. Its
limits (one shared session, SQL text only, no authentication) are the deciding factor (section 1.3).

## 8. Proposed design with contracts

### 8.1 Tables

One immutable directory per `(graph, layout_version)`. Parquet, written in the default save mode after a
sort (section 3.4). All ids i64.

| Table | Schema | Sort | Built by | When |
|---|---|---|---|---|
| `L` | `vid i64, x f64, y f64` | none | layout job (C1) | per layout version |
| `META` | `version, lmax, x0, y0, side, n_vertices, n_edge_rows, T, L_p, R` | | C2 | per version |
| `VK` | `vid i64, key i64, x f64, y f64` | `key` | C2 | per version |
| `EK` | `src_key i64, dst_key i64, src i64, dst i64 [, w f32]` both directions | `src_key` | C2 | per version |
| `LEVELS` | `cid i64, level i8, mass i64, sx f64, sy f64, xmin f64, xmax f64, ymin f64, ymax f64, deg_sum i64, internal_w i64` | `cid` | C2 | per version; levels 0..L*, or only the head plus levels up to L_p+1 |
| `PE_l` | `src_cell i64, dst_cell i64, w i64` | `src_cell` | C2 | l = 0..L_p+1, plus blocks for dense cells deeper (`deg_sum > R`) |

### 8.2 Service API (C3 and C5)

Requests are small JSON or protobuf. Responses are one Arrow IPC stream with named record batches.

| Request | Response batches | Computed | Bound |
|---|---|---|---|
| `open(graph, version)` | `meta`; `cells(cid, level, mass, cx, cy, xmin, xmax, ymin, ymax)` for the top `K0` cells of the head (for example level 4 or 5); `edges(src_cid, dst_cid, w)` top k per cell from `PE_l` | from the head and one `PE_l` read | K0 at most 1,024 cells, k x K0 edges |
| `expand(version, cid, frontier: [cid])` | `cells` for the 4 children; `edges(child_cid, frontier_cid, w)` top k per child and an "other" total | precomputed block if `deg_sum(cid) > R`, else an `EK` range; map to the frontier; top k | at most 4 + 4k rows; 1 to 2 range reads |
| `collapse(version, cid, frontier)` | `edges` of `cid` to the frontier | `PE` of `cid`'s level, or the sum of its children's rows already on the client | client-side when possible |
| `leaf(version, cid, frontier)`, allowed when `mass(cid) <= T` | `nodes(vid, x, y)`; `edges(src_vid, dst_vid)` inside the cell; `edges(src_vid, frontier_cid, w)` to the rest | `VK` range, `EK` range, map `dst_key` to the frontier | T node rows, T x degree edge rows |
| `tile(version, z, x, y)` (map-style option) | `cells` at level z+d inside tile (x, y) at level z; `edges` inside the tile and to its 8 neighbours | key range of the tile, `LEVELS` and `PE` reads | 4^d cells |
| `nodes(version, [vid])` | attributes joined from the graph | join through Sail | as asked |

### 8.3 Precomputed versus per request

| Precomputed (C2, per version) | Per request (C3) |
|---|---|
| `VK`, `EK` (two joins and a sort of 2\|E\| rows) | children: from the head in memory |
| `LEVELS` up to L* (or the head) with `deg_sum` | pseudo-edges of a dense cell: one `PE` block (range read) |
| `PE_l` for l up to L_p+1, and blocks for dense deep cells | pseudo-edges of a sparse cell: `EK` range, aggregate |
| | leaf nodes and edges: `VK` and `EK` ranges |
| | mapping to the frontier, top k, "other" totals |

### 8.4 Memory and latency bounds per component

| Component | Memory | Latency target | Basis |
|---|---|---|---|
| C2 index build | Sail shuffle and sort of 2\|E\| rows; no resident state | minutes to hours, offline | section 7.4 |
| C3 head | (16/3)\|V\|/T x 64 B: 33 MiB at 1e9, T = 1e4 | under 1 ms per lookup | section 2.4 |
| C3 block cache | configured, for example 1 GiB: about 1e3 to 1e4 blocks | hit: under 10 ms | section 4 |
| C3 per request | one block or one leaf: at most R edge rows streamed, at most 4 + 4k rows held | under 0.5 s at R = 1e7 from object storage **[inf]** | sections 3.2, 4 |
| C6 browser | K cells + k K edges + at most 1e5 leaf nodes: about 10 to 50 MiB | render under 100 ms with WebGL | Cornac's client: "our cache never uses more than 1GB"; cosmos.gl at 1e6 elements **[lit]** |

## 9. Open decisions for Sem

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | Interaction model | (a) frontier expand and collapse, as in the draft; (b) map-style zoom and pan over tiles; (c) both | (c) on the same tables. A tile view is a frontier of one level inside the viewport; deck.gl's `TileLayer` gives the client side |
| D2 | Pseudo-edges to visible cells finer than the precomputed level | (a) read a finer `PE` level; (b) report to the ancestor at the block's level and draw to its centroid; (c) always on demand for those | (b), marked in the response. It keeps every read bounded; exactness returns as soon as the user expands there |
| D3 | How much to precompute | the R rule of section 3.2 (L_p), per cell with `deg_sum` | R = 1e7 edge rows: L_p = 5 at 1e8, 6 at 1e9 |
| D4 | Threshold T for real nodes | 1e3 to 1e5 (the draft says 3e4 to 1e5) | T = 1e4 per leaf, total visible nodes at most 1e5: Bloom caps at 1e4, Cornac's renderer at 1e5 elements at 60 fps **[lit]** |
| D5 | Cell id at the API | (a) `(level, cell)` pairs; (b) one i64 with S2's trailing bit | (b) at the API, both columns in storage |
| D6 | Storage | (a) Parquet, immutable per version; (b) Delta; (c) checkpoints | (a). Sail cannot cluster Delta (section 3.4), and checkpoints die with the session |
| D7 | Where per-request reads run | (a) through Sail (Spark Connect); (b) Flight SQL; (c) the service reads Parquet itself with DataFusion | (a) first: the same catalogs, object stores and code as C2. (c) is the fallback if Sail's per-query overhead grows on a cluster. It never needs to be the only path |
| D8 | Hierarchy | (a) spatial quadtree only; (b) also a community hierarchy from the layout or from WCC/Louvain | (a) now. Keep the key scheme generic so (b) is another key column |
| D9 | Deployment | in-process extension versus remote | remote (section 1.3) |
| D10 | Edge cap per view | top k per cell plus an "other" total; or a raster (Datashader) above a density | top k = 16 to 32, raster later |
| D11 | Layout coupling | coupled multilevel versus separate job | separate (section 6) |
| D12 | 2D or 3D | quadtree or octree | 2D first. 3D only changes the key (3 x 21 bits) and the fan-out (8) |

## 10. Limits

- **A shared laptop.** Another agent ran Sail and Rust jobs throughout. Load averages ranged from 10 to 147.
  The timings show shape only, not a result to quote.
- **Local SSD, warm OS cache, local mode.** No object store, no cluster, no `local-cluster` mode. Every
  latency figure for object storage in section 4 is an assumption, not a measurement.
- **Placeholder layouts.** The hierarchical one has locality only from 1/2 down to 1/32 of the side. A real
  force layout should produce fewer pseudo-edges at deep levels than measured here. That is not shown.
- **Only up to 8.9M vertices and 521M edge rows were run.** Every 1e8 and 1e9 figure is arithmetic in
  `estimates.py`, and the build extrapolation is linear by assumption.
- **What the prototype does not implement.** It has no mixed-level frontier: the frontier is always one
  whole level, so the binary search over S2-style ids is not exercised. It has no top-k, no `deg_sum`
  column, no in-memory head (a `LEVELS` range read stands in), no service, no gateway, no browser and no
  render timing.
- **The overwrite finding** (section 3.4) was run on the fork binary only. The mechanism (`BarrierExec`
  without `maintains_input_order`) is read from code, not confirmed from a write plan. The same code in
  upstream `99ee46f69` was read, not run. Only `orderBy` was tested in the default mode;
  `sortWithinPartitions` in the default mode rests on the earlier study.
- **The Flight probe** ran one query shape, with no concurrency and no authentication.
- **The adaptive-head bound** (16/3)|V|/T is for a uniform layout. Measured counts fall within it on both
  layouts, but a pathologically deep layout can exceed it by up to |V|/T cells per extra level.
- **Peak RSS** is sampled with `ps` every 50 ms and includes Sail's caches.
- **The smoke run.** In an untimed smoke run (not kept), the first query of the session took 62 s. It did
  not recur in any recorded run: every `first` value of a trivial query is about 0.1 s.
- **"Plain" tables.** `VK` and `EK` keep arrival order, which is random with respect to the key. `PE` is
  scrambled by a hash.
- **Prior art.** Each item was read to the extent stated in section 5. Not verified: the Datashader timings,
  Graphistry's client limits, a Bloom per-scene maximum, the Cornac issue number (vol. 6, 2020 per
  Semantic Scholar), and Frishman and Tal's page range. Those are not cited as facts.
- **The binary** predates its tree's HEAD (built 00:19, HEAD committed 05:43 on 2026-10-02).

## Files

All in this directory. Tables were written to the session scratch directory and are not kept.

| File | Contents |
|---|---|
| `README.md` | this report |
| [`vizserver.py`](vizserver.py) | starts and stops one Sail server (Spark Connect or Flight) on an ephemeral port, records settings and host facts |
| [`quadsql.py`](quadsql.py) | the key, cell and aggregate expressions (section 2) |
| [`layout.py`](layout.py) | the two placeholder layouts |
| [`bench.py`](bench.py) | the table builds and interaction queries |
| [`probe_sorted_write.py`](probe_sorted_write.py) | the overwrite-mode probe |
| [`flight_probe.py`](flight_probe.py) | the Flight SQL comparison |
| [`file_layouts.py`](file_layouts.py) | file facts of every table written |
| [`summarize.py`](summarize.py) | tables from the raw records |
| [`estimates.py`](estimates.py), [`estimates.out`](estimates.out) | the arithmetic |
| `raw/bench-<graph>-<layout>.jsonl` | one JSON line per measurement, with settings, host facts and load average in the `start` line |
| `raw/layout-<graph>.jsonl` | layout generation, propagation rounds |
| `raw/flight-cit-Patents-random.jsonl` | Flight SQL timings |
| `raw/explain-analyze-<graph>-<layout>-ek-{sorted,plain}.txt` | `EXPLAIN ANALYZE` of the on-demand expand scan |
| `raw/probe-sorted-write.txt` | the overwrite probe's output and plan |
| `raw/file-layouts.json` | rows, files, bytes, sortedness, row-group spans |
| `raw/summary.txt` | all medians and ranges in one table |
| `raw/superseded-overwrite-mode-*` | the first run, whose sorted tables were not sorted (section 7.5) |

## Checked independently

Added by the reviewer of this study. The new Sail finding, a sort dropped by
`mode("overwrite")`, was reproduced with a separate script on unmodified
upstream `99ee46f69`: `orderBy(k)` then a default write gave 4 of 4 sorted
files; the same with `mode("overwrite")` gave 0 of 4; the same for
`sortWithinPartitions`. It is written up as standalone upstream report 12 in
[`../../sail-upstream-reports-2026-10-02/12-overwrite-write-drops-sort/`](../../sail-upstream-reports-2026-10-02/12-overwrite-write-drops-sort/README.md),
filed as [lakehq/sail#2741](https://github.com/lakehq/sail/issues/2741). The cited code (`barrier.rs`, `listing/planner.rs:253-258`) reads
as the study says.
