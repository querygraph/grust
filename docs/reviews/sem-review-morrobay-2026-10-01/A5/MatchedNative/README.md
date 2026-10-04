# Native matched WCC, PageRank and BFS

## Findings

All 70 outcomes qualified: six separate GraphFrames references, twelve warmups, 48 measured calls in two ABBA blocks per dataset and algorithm, and four calls in two separate WCC snapshot pairs. References and warmups are excluded from ratios.

| Dataset | Algorithm, inputs in place | Four adjacent Pecan / GraphFrames ratios | Geometric mean |
| --- | --- | --- | ---: |
| cit-Patents | wcc | 1.923054, 1.902076, 1.971826, 1.947757 | 1.936001 |
| cit-Patents | pagerank | 1.618894, 1.761632, 1.736708, 1.662748 | 1.694032 |
| cit-Patents | bfs | 1.565044, 1.673701, 1.780290, 1.668648 | 1.670187 |
| graph500-24 | wcc | 0.869807, 0.881514, 0.884733, 0.908584 | 0.886048 |
| graph500-24 | pagerank | 1.006564, 0.975254, 0.954563, 1.009490 | 0.986203 |
| graph500-24 | bfs | 1.067621, 1.075130, 1.121952, 1.114551 | 1.094556 |

| Dataset | Separate WCC pair, Pecan snapshot on | Pecan / GraphFrames ratio |
| --- | --- | ---: |
| cit-Patents | One adjacent pair | 2.053981 |
| graph500-24 | One adjacent pair | 1.114015 |

These are ratios on shared Morrobay. Above one means Pecan's interval was longer in the adjacent pair. Each main contrast has four measured calls per engine; each separate snapshot contrast has one call per engine.

## Full outputs and contracts

Every call covers every original vertex exactly once: 3,774,768 Cit vertices and 8,870,942 Graph500 vertices. Raw schemas, complete retained inventories, zero mismatches, identity closure and independently observed process closure are retained.

WCC compares canonical minimum original labels and both directions of full partition equivalence. BFS compares exact hops along the stored source-to-target arcs, with Cit source 5795784 and Graph500 source 798169. Pecan exports only `id,hops`; GraphFrames exports its original `id,dist_SOURCE`. Pecan NULL and GraphFrames INT32_MAX are explicit unreachable adapters. Distance and predecessor fields are not exported or compared.

PageRank uses initial rank and delta .15, damping .85, first-step sends followed by delta > .01, ten fixed steps, no dangling redistribution, and final normalization. Pecan uses `pregel_delta` with voting disabled. Every score is compared to the separate GraphFrames reference at the predeclared absolute bound 1e-12. Reference preparation qualifies domain and physical values; it has no numerical self-comparison.

Agreement with the separately prepared GraphFrames outputs is the oracle contract. Stored directed BFS and PageRank do not qualify official Graph500 undirected ground truth or establish independent topology correctness.

## Timing, source and resources

The primary timer is parent Popen through waited child exit, including Python bootstrap and imports, engine startup, reads, actions, the complete projected raw Parquet export and cleanup. Oracle and retention checks follow outside it. Fable's timer starts after imports and its BFS exports four fields; this timer and two-field BFS projection do not reproduce those boundaries.

Pecan controller `d0e4e422a`; optimized native Sail `9f0aa7d2a`; GraphFrames `b4da56dabe`; frozen runtime/measurement helpers `6ae2e43a9`. The controller and compiled runtime have an observed empty diff over Rust crates, Cargo manifests, lockfile and toolchain. Source, build, client and original input admissions are retained.

Both engines are local with 16 configured threads and a 30 GiB software pool; Pecan has 16 partitions. GraphFrames uses FairSpillPool and Pecan uses a greedy pool. Main comparisons read inputs in place; the separate WCC pairs enable Pecan snapshots. The physical macOS host has 128 GiB. These settings are not OS CPU, memory or swap caps. There is no PSS, cgroup or steal observation. Periodic process RSS is a sampled observation and may include shared pages.

## Evidence

[report.json](report.json) retains all 70 outcomes and original timer values. [evidence.tar.gz](evidence.tar.gz) preserves exact small metadata, complete logs, helper sources and their source archives. [INPUTS.json](INPUTS.json) maps portable names to original paths and identities. [archive-verification.json](archive-verification.json) binds every physical archive member. Raw Parquet and binaries remain represented by root's independently checked inventories and are not embedded.
