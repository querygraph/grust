# Automatic routing: partition fix and warm route profile

Capitola (aarch64 macOS, 10 cores, 64 GiB), stable Rust 1.97.1, run
2026-09-14 23:19–23:22 UTC. The host was an interactive workstation during the
run (Chrome, WindowServer, Spotlight, Docker Desktop); load averages were about
27 at start and end, recorded in `host-start.txt` and `host-end.txt`. Exact
binary hashes are in `hashes.txt`:

- `before_cypher_end_to_end` is the retained `6544dc4` binary that produced the
  [original failure](../cypher-conversion-6544dc4) (same SHA-256).
- `after_cypher_end_to_end` and `cypher_route` are built from branch
  `claude/auto-datafusion-route` (base `a134e05`) with the zero-copy partition
  split and the router. `cypher_route` forces each route, so the threshold
  constant later set from these results does not affect them.

## Partition fix, one million nodes

Ten process pairs, alternating order, each running three trials per route with
the unchanged 256 MiB pool, spill disabled and four target partitions:

| Binary | DataFusion trials | Memory exhaustion | Median DataFusion total (s) |
| --- | ---: | ---: | ---: |
| before | 30 | 2 | 0.798 |
| after | 30 | 0 | 0.797 |

Both before-binary failures are the retained `Memory Exhausted while SpillPool
(DiskManager is disabled)` error; all 60 indexed trials passed. Two of thirty
against none of thirty is not statistically decisive by itself (two-sided
Fisher p ≈ 0.49). The structural evidence is stronger: the fixed physical plan
contains no `RoundRobinBatch` repartition (regression
`single_large_batches_are_split_without_round_robin`), and DataFusion 55.1
`repartition/mod.rs` is where each queued slice was charged its shared parent
buffers. The fix did not change measured DataFusion time.

## Warm route profile

`cypher_route 5 1000 3000 10000 30000 100000 300000 1000000`: one `RoutedGraph`
per size, then the complete bounded-read entrypoint on each forced route, five
alternating trials. All trials passed with identical results on both routes.
Median seconds per query (q0 filtered count, q1 top-7 ids by ORDER BY, q2
group-by with ORDER BY):

| Nodes | q0 reference | q0 DataFusion | q1 reference | q1 DataFusion | q2 reference | q2 DataFusion |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1,000 | 0.00087 | 0.00098 | 0.00088 | 0.00055 | 0.00172 | 0.00090 |
| 3,000 | 0.00223 | 0.00058 | 0.00227 | 0.00051 | 0.00449 | 0.00090 |
| 10,000 | 0.00809 | 0.00072 | 0.00828 | 0.00096 | 0.01746 | 0.00106 |
| 30,000 | 0.02698 | 0.00086 | 0.02802 | 0.00099 | 0.05764 | 0.00109 |
| 100,000 | 0.09058 | 0.00096 | 0.09583 | 0.00109 | 0.19741 | 0.00119 |
| 300,000 | 0.28274 | 0.00141 | 0.30139 | 0.00143 | 0.60173 | 0.00144 |
| 1,000,000 | 0.97369 | 0.00224 | 1.07067 | 0.00304 | 1.99825 | 0.00228 |

One-time capture (index plus Arrow snapshot) took 0.0012 s at 1,000 nodes,
0.057 s at 100,000 and 1.055 s at 1,000,000, and is excluded from trials. The
reference route was faster only for q0 at 1,000 nodes, so
`DEFAULT_MIN_DATAFUSION_NODES` is 3,000. These are single-node scans on one
loaded host; they do not qualify joins, other shapes, other hosts or backends.
