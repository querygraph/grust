# F0: the floor of a CSR build from Parquet

Item F0 of [`SEM-REVIEW-2.md`](../../../SEM-REVIEW-2.md), section 9. Measured
on Capitola on 2026-10-02.

## The question

Sem's objection to Banda is that the conversion to a CSR eats the run. Before
changing Banda, the plan asks what the conversion costs when nothing else is
in the way: Parquet in, i64 ids, no Sail tables, no FFI crossing, no canonical
sort. That number is the floor. The gap between it and Banda's ingest is what
F1 has to close.

## The program

[`csr-floor/`](csr-floor/) is one Rust file, about 200 lines, built on the
`parquet` and `rayon` crates. It does four things.

1. Read `id` from the vertex file and the two endpoint columns from the edge
   file, one task per row group.
2. Map the i64 ids to dense indices. A direct table when the ids span at most
   16 slots per vertex; a binary search over the sorted ids otherwise.
3. Count degrees, take the prefix sum, fill the targets. Parallel, with
   atomic cursors.
4. Check that the sum of all targets equals the sum over the edge list.

Vertex ids stay i64 in the id array. Arc offsets are u64. Dense targets are
u32 under a checked bound, or u64 with `--wide`. The graph is taken as valid.
Neighbour order within a row is arrival order.

## Inputs

The LDBC Graphalytics Parquet files, as downloaded from
`datasets.ldbcouncil.org/graphalytics-parquet/`.

| File | Rows | SHA-256 |
|---|---|---|
| `cit-Patents-v.parquet` | 3,774,768 | `0969ea9ede0969e18e76a2c70191ed7ccecaecb9f1da6d954093dbefbc8958aa` |
| `cit-Patents-e.parquet` | 16,518,947 | `70bcba17b5a7762ef5a0c3d16c1dc37a352461b83e338f550ae897d844f0268f` |
| `graph500-24-v.parquet` | 8,870,942 | `f186f0fac502106454ceae29a57c7f350ae60699b5a5087b3001cfd054983428` |
| `graph500-24-e.parquet` | 260,379,520 | `da4f324e619c97d68190c0eba4e2f9e59ebcd492d84c3e1bafe7624fdc7e2453` |

## Result

Median of five runs, wall seconds inside the process, from the first file
open to the finished adjacency. The undirected form stores both directions
(the form WCC and an undirected BFS need).

| Graph | Form | Arcs | Threads | Read | Map ids | Build | Total | Range of total | Peak RSS |
|---|---|---|---|---|---|---|---|---|---|
| cit-Patents | directed | 16.5M | 4 | 0.10 | 0.07 | 0.04 | 0.22 | 0.20 to 0.25 | 0.7 GiB |
| cit-Patents | undirected | 33.0M | 4 | 0.14 | 0.07 | 0.19 | 0.42 | 0.37 to 0.57 | 0.6 GiB |
| cit-Patents | undirected | 33.0M | 10 | 0.09 | 0.05 | 0.18 | 0.32 | 0.29 to 0.33 | 0.7 GiB |
| graph500-24 | directed | 260M | 4 | 1.65 | 1.38 | 0.99 | 4.08 | 3.43 to 4.31 | 8.0 GiB |
| graph500-24 | undirected | 521M | 4 | 1.83 | 1.40 | 4.38 | 7.66 | 7.10 to 9.00 | 7.3 GiB |
| graph500-24 | undirected | 521M | 10 | 1.20 | 0.82 | 2.60 | 4.67 | 4.42 to 5.02 | 8.1 GiB |

Both graphs have compact ids, so the direct table applies. With the table
turned off (`--no-table`), the binary search is the fallback for sparse i64
ids. Three runs, graph500-24, undirected:

| Threads | Read | Map ids | Build | Total |
|---|---|---|---|---|
| 4 | 1.84 | 13.41 | 4.04 | 19.24 |
| 10 | 1.21 | 7.87 | 2.96 | 12.18 |

The raw records are [`runs.jsonl`](runs.jsonl) and
[`runs-binary-search.jsonl`](runs-binary-search.jsonl).

## Beside the other numbers

These are different machines and different boundaries. The table states an
order of magnitude, not a ratio.

| Path | Graph | Ingest to a usable CSR | Where |
|---|---|---|---|
| This floor | cit-Patents | 0.4 s | Capitola, 4 threads |
| Banda, staging and projection | cit-Patents | about 28 s | gate, September campaign |
| This floor | graph500-24 | 8 s (19 s with binary search) | Capitola, 4 threads |
| icebug, CSR build | graph500-24 | 179 to 186 s | Sem's receipts, 4 cores, DuckDB with a 12 GB limit |
| Banda, staging and projection | graph500-24 | about 650 s | gate, 32 cores, scale-24 BFS cell |

## What it says

- The conversion itself is small. On graph500-24 it is seconds, and about a
  quarter of that is reading Parquet.
- So Banda's 28 s and 650 s are our conversion, not the conversion. The
  candidates are the ones already named: ids as Utf8 with a string map (S1),
  the canonical sort (S2), the projection's target width and passes (S3),
  and the FFI crossing between Sail and the extension.
- Sparse ids cost real time: the binary search takes the map phase from 1.4
  to 13.4 s on 4 threads. A hash map or a sort-based join would be the next
  thing to try there. It is still about 10 times under icebug's build.
- The floor's memory is not tuned. It holds the endpoints twice (i64, then
  dense u64) beside the adjacency: 8 GiB for a 2.1 GiB CSR. An out-of-core
  build, which is what icebug does under a 12 GB limit, pays for that in
  time. The floor does not show how much.

## Limits

- One machine, an Apple M1 Max laptop (8 performance and 2 efficiency cores),
  macOS, warm page cache, other applications running. The gate is x86 and
  was not used. Rerunning this binary on the gate is one command and should
  be done before any number here is put beside a gate number as a ratio.
- No neighbour sorting, no deduplication, no edge properties, no weights.
- The fill order is not deterministic across threads. `--threads 1` makes it
  arrival order.
- Rust 1.97.1, `parquet` 59.3, `--release` with thin LTO.

## Reproduce

```sh
cd docs/reviews/sem-review-capitola-2026-10-02/F0/csr-floor
cargo build --release
target/release/csr-floor --vertices graph500-24-v.parquet \
  --edges graph500-24-e.parquet --src source --dst target \
  --undirected --threads 4
```
