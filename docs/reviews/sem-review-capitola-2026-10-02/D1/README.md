# D1: what a sorted checkpoint write costs on Sail, and what it could buy

Item D1 of [`SEM-REVIEW-2.md`](../../../SEM-REVIEW-2.md), section 9. Measured
on Capitola on 2026-10-02 with a release Sail host (`querygraph/sail`
`0d1ef2ca3`) in local mode, parallelism 10.

## The question

graphframes-rs writes its vertex state hash-partitioned and sorted by key,
and reads it back declaring that layout, so the join against the edges needs
no shuffle and no sort. Sem's argument (remarks 12 and 23b): the sorted write
may cost three times a plain one, but it is a write of V rows, and it removes
work over E rows, and V is much smaller than E. He asked how the write-cost
gap scales. The only earlier number was one point at 16M rows.

## What was measured

1. The cost of writing the same frame six ways, at 16M, 64M and 268M rows.
2. The cost of one relational round today at the same sizes, split into the
   join and the rest.

Two frames per size. A state: a unique-looking BIGINT id and a DOUBLE. An
edge table: `src` and `dst` over rows/16 vertices. Both incompressible by
construction. Every write reads its input from Parquet, as a round does.

## Result 1: write cost

Median seconds. Four samples for the first four modes (order reversed within
each block), two for the bucketed modes. The ranges are within 20% of the
median. In parentheses: times the plain write.

| Rows | Shape | Plain | Round-robin | Hash | Hash, sorted | Bucketed (`partitionBy`) | Bucketed, sorted |
|---|---|---|---|---|---|---|---|
| 16M | state | 0.13 | 0.18 (1.4x) | 0.14 (1.1x) | 0.76 (6.0x) | 1.14 (8.9x) | 1.74 (13.7x) |
| 16M | edges | 0.11 | 0.16 (1.5x) | 0.13 (1.2x) | 0.40 (3.7x) | 1.12 (10.3x) | 1.47 (13.5x) |
| 64M | state | 0.56 | 0.76 (1.4x) | 0.58 (1.0x) | 3.11 (5.5x) | 4.45 (7.9x) | 7.08 (12.6x) |
| 64M | edges | 0.48 | 0.66 (1.4x) | 0.52 (1.1x) | 1.62 (3.4x) | 4.42 (9.2x) | 5.90 (12.3x) |
| 268M | state | 2.04 | 2.88 (1.4x) | 2.20 (1.1x) | 12.89 (6.3x) | 19.84 (9.7x) | 30.04 (14.7x) |
| 268M | edges | 1.62 | 2.42 (1.5x) | 1.86 (1.2x) | 7.67 (4.7x) | 18.60 (11.5x) | 25.41 (15.7x) |

The modes:

- **Plain**: `frame.write.parquet`.
- **Round-robin**: `frame.repartition(P)`. This is what Pecan does before
  every checkpoint today (B1's toggle turns it off).
- **Hash**: `frame.repartition(P, key)`.
- **Hash, sorted**: `frame.repartition(P, key).sortWithinPartitions(key)`.
- **Bucketed**: a bucket column `pmod(xxhash64(key), P)` and
  `write.partitionBy("bucket")`. One directory and one file per bucket. This
  is the layout a reader can declare.
- **Bucketed, sorted**: the same, sorted by key inside each bucket.

## Result 2: one round today

A Pregel-style step: join the state to the edges on `src`, sum a message by
`dst`, write. Median of three.

| Edges | Vertices | Round, hash join | Round, sort-merge preferred | Aggregate and write, no join | Join's share |
|---|---|---|---|---|---|
| 16M | 1.00M | 0.17 | 0.30 | 0.09 | 0.08 (48%) |
| 64M | 4.00M | 0.92 | 1.51 | 0.49 | 0.44 (47%) |
| 268M | 16.75M | 4.49 | 8.00 | 2.45 | 2.04 (45%) |

## Reading

- **The gap is a constant ratio.** From 16M to 268M rows every mode scales
  linearly. A sorted write costs 3.4 to 6.3 times a plain one. That answers
  the scaling question: no cliff, no convergence.
- **The sort is not the expensive part. The bucketing is.** Sail's
  `partitionBy` write alone costs 8 to 11 times a plain write, about 70 ns a
  row against 7. Sorting adds a third to a half as much again.
- **A plain sorted write does not give the layout.** Sail's writer merges the
  partitions into one stream and rolls files by size: 4 files at 16M and 64M
  rows, 8 at 268M, whatever the partitioning. Each file is sorted, but the
  files are not the hash partitions. Only the bucketed write gives one file
  per partition.
- **Sem's argument holds for the sort and fails on today's writer.** At 268M
  edges the join is 2.0 s of a 4.5 s round. That is the most a declared
  layout can remove. The state write it needs costs, per round, for 16.75M
  vertices:

  | State write | Seconds | Over plain | Most a round can gain | Edges written once |
  |---|---|---|---|---|
  | Plain (today) | 0.14 | | | 1.6 s |
  | Hash, sorted (not a declarable layout today) | 0.80 | +0.66 | 1.4 s of 4.5 (31%) | 7.7 s |
  | Bucketed, sorted (declarable) | 1.82 | +1.68 | 0.4 s of 4.5 (8%) | 25.4 s |

  With a bucketed writer as cheap as the sorted one, the layout is worth up
  to a third of a round and repays the edge sort in five rounds. With the
  writer as it is, it is worth under a tenth and repays the edge write in
  about 65 rounds.
- **The ceiling is under 2x.** The join is 45 to 48% of a round at every
  size. Removing all of it would not make a round twice as fast.
- **Preferring sort-merge joins without the layout is a loss**: 1.6 to 1.8
  times the hash-join round, because the edges are sorted every round.

## For upstream, at the user's decision

Two observations about Sail itself, both reproducible with the scripts here.

1. `write.partitionBy` costs 8 to 11 times a plain write of the same rows.
2. With `SAIL_OPTIMIZER__PREFER_HASH_JOIN=false`, `explain` of a join fails
   (`SortMergeJoinExec requires children [0, 1] to be co-partitioned`) while
   the same query executes and returns the right rows.

## Limits

- An M1 Max laptop, macOS, a fast internal SSD, a warm page cache. The gate
  was not used. Ratios should carry over better than seconds.
- Local mode. In cluster mode a shuffle crosses processes, and removing it
  may be worth more. That is D2, on the gate.
- The round with a declared layout was not measured: the reader is on
  another branch (`work/declared-layout`). "Most a round can gain" assumes
  the merge join costs nothing, so it is an upper bound.
- Synthetic frames with uniform keys, not a graph's degree distribution.
- The earlier write numbers in `GRAPHFRAMES-RS-PARITY.md` (1.5 to 5.8 s
  plain, 11.6 to 12.5 s partitioned, at 16M rows) are 10 times these. They
  came from an x86 build under Rosetta whose cargo profile was not recorded.

## Files

`d1_write_cost.py`, `d1_bucketed_write.py`, `d1_round_cost.py`,
`d1_aggregate_only.py`, and their raw results: `d1-write-cost.json`,
`d1-bucketed-write.json`, `d1-round-cost.json`, `d1-aggregate-only.json`.
The servers are started with `../A2-local/serve.sh` (port 50178 default,
port 50179 with `SAIL_OPTIMIZER__PREFER_HASH_JOIN=false`).
