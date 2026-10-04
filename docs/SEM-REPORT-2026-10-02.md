# Report to Sem: yesterday's questions, answered

2026-10-02. This is the short form. The long form, with every remark, the
plan and the status board, is [`SEM-REVIEW-2.md`](SEM-REVIEW-2.md). Each
line below names where its evidence is. Numbers from Capitola (an M1 Max
laptop) and from Morrobay (a shared 18-core Xeon, bare macOS) are ratios
and shapes, not publishable absolutes.

## The headline

1. **Pecan is in graphframes-rs's single-node class.** Same inputs read in
   place, same algorithm contracts, full oracle on every output, two hosts.
2. **The old 3.8x gap was the benchmark VM, not the code.** The same cell
   took 51.8 s in the VM and 8.9 s natively on the same machine.
3. **Banda's ingest was our conversion, as you said.** With integer ids
   kept as integers (Grust 0.24.0, released today) one WCC call on
   graph500-24 goes from 139 s to 7 to 8 s, launch to exit.

## Pecan against graphframes-rs

Pecan time over graphframes-rs time, launch to exit, Parquet in and
Parquet out, inputs in place. Below 1, Pecan took less.

| Graph | Algorithm | Capitola | Morrobay, native |
|---|---|---|---|
| cit-Patents | WCC, randomized contraction | 1.17 | 1.42 |
| cit-Patents | PageRank, delta Pregel, 10 steps | 1.14 | 1.16 |
| cit-Patents | BFS (your `shortest-path`, one landmark) | 0.65 | 0.71 |
| graph500-24 | WCC | 0.80 | 0.80 |
| graph500-24 | PageRank | 0.95 | 0.86 |
| graph500-24 | BFS | 0.87 | 0.86 |

Pecan `9f0aa7d2a`, graphframes-rs `b4da56d`, release builds with LTO.
Morrobay: 48 of 48 calls qualified, two G/P/P/G blocks, medians.
Evidence: `reviews/sem-review-capitola-2026-10-02/A2-local/README.md`,
`reviews/sem-review-morrobay-2026-10-01/A5/FableExact/README.md`.

What remains behind: WCC on the small sparse graph. Its first three rounds
are 65% of the call. Today's note on the per-partition union-find is about
exactly that.

## Your remarks, by group

| Your remark | What was done | Evidence |
|---|---|---|
| Remove data-touching checks; the graph and the arguments are assumed valid (3, 6) | Every validation job removed. The rule is in `AGENTS.md` in your words. | `querygraph/sail` `7145d107c` |
| Imports inside bodies; no type hints (4, 5) | Module-scope imports, enforced by a test. Everything typed; `mypy --strict` and `ruff` clean. | `6ae2e43a9` |
| WCC: why `min_by` and carried ids; follow the paper (14, 17) | Done as in Bögeholz et al. and your `connected_components.rs`: hashed ids as representatives, one union, one grouped `min`, inverse maps once at the end. The deviation was mine, not Astra's. Codex found a real defect in my first form (a hashed label could equal an isolated vertex's id); fixed, with its counterexample as a test. | `b522bf3a9` |
| PageRank: no dangling redistribution, no 1e-5 worry, delta as in GraphX (18 to 21) | `method="pregel"` is the paper's static form. `method="pregel_delta"` is your program column for column: ranks equal to yours to 1e-15, halting at the same step. The LDBC-contract form stays as a separately named method. | `f3b3ef8fc`, `0d1ef2ca3` |
| "As in X" must mean as in X (19) | Adopted as a rule in `AGENTS.md`. A deviation is a separate, named method. | |
| A proper Pregel; SSSP and PageRank on it (15, 22, 23c) | `GraphAlgorithms.pregel()` in the form of your `PregelBuilder`: vertex columns, messages either way, aggregates, participation, vote to halt, with or without destination state, one job per step. Your 13 unit tests are ported as its specification. PageRank runs on it. | `9f0aa7d2a` |
| Explode against `unionByName` on Sail, with numbers (11, 23a) | Measured, paired. Explode over union: 1.00 to 1.12. Union stays. Two graph500-24 shapes ran out of the 32 GiB container and are withheld. | `reviews/sem-review-morrobay-2026-10-01/B8/README.md` |
| The sorted write that lets the merge join skip sort and repartition, at scale (12, 23b) | Measured at 16M, 64M and 268M rows. A sorted write costs 3.4 to 6.3 times a plain one at every size. The bucketed write a reader could declare (`partitionBy`) costs 8 to 11 times, because of DataFusion's demultiplexer; written up for upstream with a reproducer. The join it would remove is 45% of a round. So your argument holds for the sort and fails on today's bucketed writer. Vortex was not looked at. | `reviews/sem-review-capitola-2026-10-02/D1/README.md`, `reviews/sail-partitionby-write-2026-10-02/README.md` |
| WCC: reach your single-node class or name the blocker (23d) | Reached; table above. The blocker for the earlier numbers was the VM. | above |
| Check against the LDBC `test-*` graphs (13) | 16 of 16 supported cases pass against the official references. | `reviews/pecan-ldbc-semantics-2026-10-01/README.md` |
| Why rewrite the inputs | `snapshot_inputs=False` reads them in place: graph500-24 WCC 30.4 to 20.3 s. Traversals no longer write a second copy of the edges. | `b522bf3a9`, `d0e4e422a` |
| 33 GiB for scale-24 SSSP; which memory pool (8, 9) | The number was a container peak over three processes, each with its own 96 GiB pool in a 100 GiB container. Not unbounded, but unbounded in sum. | `pecan-code-and-harness.md` |
| Banda should do graph500-24 in about 200 s on 4 cores; no strings and `HashMap<String, u32>` (24, 25) | You named the cause exactly. A plain CSR build from the Parquet file takes 7.7 s on 4 threads here. Banda's projection took 136 s through a string map on one thread. Grust 0.24.0 takes Int64 ids as integers and builds in parallel: 3.1 to 4.0 s, and 4.65 GiB where it held 13.4. | `reviews/sem-review-capitola-2026-10-02/F0/README.md`, `F1/README.md` |
| A CSR pays for itself at three calls; report end to end, Parquet in and out (26, 27) | On Capitola, with integer ids, it now pays from the first call on a graph that fits. Table below. | `F1/README.md` |

One WCC call, launch to exit, Capitola:

| Path | cit-Patents | graph500-24 |
|---|---|---|
| graphframes-rs | 3.5 to 3.7 s | 25.5 to 27.7 s |
| Pecan, inputs in place | 4.1 s | 20.3 s |
| Banda, Grust 0.23.0, text ids | 8.4 s | 139 s |
| Banda, Grust 0.24.0, integer ids, 8 build workers | 1.4 s | 7.3 to 8.2 s |
| Banda, each further call | 0.3 s | 1.2 to 2.0 s |

Your icebug reference for graph500-24 is about 200 s on 4 cores of an
i3.xlarge. The hosts and thread counts differ, so this is an order of
magnitude, not a ratio.

## What we got wrong

- **The benchmark host.** Every time we showed you before 2026-10-02 came
  from a VM that slowed Pecan 5.8 times on the same machine, and your
  binary by less. The first
  reading of the gap (too many controller actions per round) was wrong and
  is corrected in the plan. Benchmarks now run on bare macOS.
- **Improving on the fly.** `min_by` with carried ids, the dangling term,
  the certificates in the delta method: each was a deviation I added to an
  algorithm you had asked for "as in X". All three are undone or moved to
  separately named methods.
- **String identity in the CSR path.** Fixed at the door in 0.24.0. Your
  question today about `ProjectionData` shows it is not fixed in the model;
  see the report on Grust's model below.

## Still open from yesterday

- SSSP, your landmark shortest paths and the other programs on the Pregel
  loop; the kgs and wiki-Talk microbenchmarks.
- The declared layout in cluster mode (D2).
- Banda in your four-phase format natively on Morrobay (F2a).
- Vortex as a checkpoint format.
- An x86-64 Linux gate for the Grust release. The release was gated on
  macOS and on arm64 Linux.

## Today's tasks

Each has its own note under
[`reviews/sem-research-2026-10-02/`](reviews/sem-research-2026-10-02/README.md).
