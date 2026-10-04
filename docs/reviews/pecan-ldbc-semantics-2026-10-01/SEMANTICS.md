# Pecan: LDBC tiny-graph semantic handoff

Prepared 2026-10-01 by an independent read-only reviewer. No Pecan run, container, or benchmark was launched for this inspection. Official archives were fetched and decoded in memory; no repository was modified.

## Priority and scope

Run the current LDBC `test-*` correctness fixtures before larger performance work. Pecan implements BFS, PageRank, WCC, and SSSP. Record CDLP and LCC as **unsupported**, including their official fixtures in the inventory; do not describe four-algorithm qualification as all-six Graphalytics conformance. Also run the two `example-*` graphs for supported algorithms: their two-step PageRank references expose finite-step and sink behavior.

## Official inputs and exact download links

[Official current catalog](https://ldbcouncil.org/benchmarks/graphalytics/datasets/) and [official test-set download script](https://ldbcouncil.org/scripts/download-graphalytics-data-sets-r2-test.sh). The catalog warns that older pre-March-2023 datasets had incorrect data or reference outputs. Use the currently served archives and retain their hashes.

Each archive below contains `<name>.v`, `<name>.e`, `<name>.properties`, and `<name>-<ALGORITHM>` reference output. The reference files are space-separated vertex/value records, not CSV-with-header files.

| Archive | Vertices / edges | Required settings |
|---|---:|---|
| [test-wcc-directed](https://datasets.ldbcouncil.org/graphalytics/test-wcc-directed.tar.zst) | 8 / 10 | WCC ignores direction |
| [test-wcc-undirected](https://datasets.ldbcouncil.org/graphalytics/test-wcc-undirected.tar.zst) | 8 / 7 | WCC ignores direction |
| [test-pr-directed](https://datasets.ldbcouncil.org/graphalytics/test-pr-directed.tar.zst) | 50 / 246 | damping 0.85; exactly 14 iterations |
| [test-pr-undirected](https://datasets.ldbcouncil.org/graphalytics/test-pr-undirected.tar.zst) | 50 / 113 | damping 0.85; exactly 26 iterations |
| [test-sssp-directed](https://datasets.ldbcouncil.org/graphalytics/test-sssp-directed.tar.zst) | 10 / 13 | source 1; DOUBLE `weight`; directed |
| [test-sssp-undirected](https://datasets.ldbcouncil.org/graphalytics/test-sssp-undirected.tar.zst) | 12 / 14 | source 1; DOUBLE `weight`; undirected |
| [test-bfs-directed](https://datasets.ldbcouncil.org/graphalytics/test-bfs-directed.tar.zst) | 10 / 17 | source 1; directed |
| [test-bfs-undirected](https://datasets.ldbcouncil.org/graphalytics/test-bfs-undirected.tar.zst) | 10 / 14 | source 1; undirected |
| [test-cdlp-directed](https://datasets.ldbcouncil.org/graphalytics/test-cdlp-directed.tar.zst) | 8 / 18 | 5 iterations; unsupported by Pecan |
| [test-cdlp-undirected](https://datasets.ldbcouncil.org/graphalytics/test-cdlp-undirected.tar.zst) | 8 / 13 | 5 iterations; unsupported by Pecan |
| [test-lcc-directed](https://datasets.ldbcouncil.org/graphalytics/test-lcc-directed.tar.zst) | 10 / 17 | unsupported by Pecan |
| [test-lcc-undirected](https://datasets.ldbcouncil.org/graphalytics/test-lcc-undirected.tar.zst) | 9 / 12 | unsupported by Pecan |

[example-directed](https://datasets.ldbcouncil.org/graphalytics/example-directed.tar.zst): 10 vertices, 17 edges, all six references; PR damping 0.85 and exactly 2 iterations, BFS/SSSP source 1. [example-undirected](https://datasets.ldbcouncil.org/graphalytics/example-undirected.tar.zst): 9 vertices, 12 edges, all six references; PR damping 0.85 and exactly 2 iterations, BFS/SSSP source 2. Both include real-valued edge weights.

### Archive SHA-256 observed during this inspection

| Archive | Bytes | SHA-256 |
|---|---:|---|
| test-wcc-directed.tar.zst | 433 | `14d5f462fa9e77823756fc87f4fc85c3d906a4ebaa0ebecac0758ac07819541b` |
| test-wcc-undirected.tar.zst | 428 | `c3d5f73b02a4a71db55ef0bedea9618dbb01f2429cf7068b1b7e741b00890d26` |
| test-pr-directed.tar.zst | 1635 | `25dbd25c1bf0d9dc55ebdeb4d45299ccacc27c91feccc3e1d448ea8b82342374` |
| test-pr-undirected.tar.zst | 1380 | `49a67b0c1978f47f552f593d7ccc0b2e1bac383e29736efeb43d7e9aba74a9a0` |
| test-sssp-directed.tar.zst | 603 | `97b6b72184e6137af271dd2f3088aa68452510e08b3cea98da860a378bfa9bb6` |
| test-sssp-undirected.tar.zst | 625 | `908f7b9c12c4a7b3fb0836547b3cd49543448999ed450c575ede88f1149d7306` |

**Malformed upstream properties:** `test-wcc-directed.properties` sets `graph.test-wcc-directed.edge-file = test-wcc-directed.v`; `test-sssp-undirected.properties` sets `graph.test-sssp-undirected.edge-file = test-sssp-undirected.v`. Actual edge members are the corresponding `.e` files. Retain original properties unchanged, resolve `.e` explicitly in the adapter, and record these two corrections in the input manifest. Otherwise a generic properties loader can read vertices as edges.

## Semantic contracts and adapters

Specification pin: [`ldbc/ldbc_graphalytics_docs@c0f8927d144aa0216949c444eca96f42905a576d`](https://github.com/ldbc/ldbc_graphalytics_docs/tree/c0f8927d144aa0216949c444eca96f42905a576d). [Formal definition](https://github.com/ldbc/ldbc_graphalytics_docs/blob/c0f8927d144aa0216949c444eca96f42905a576d/tex/definition.tex): graph representation lines 25–35; PR 244–265; WCC 268–270; SSSP 323–325; validation 465–467. [Reference pseudocode](https://github.com/ldbc/ldbc_graphalytics_docs/blob/c0f8927d144aa0216949c444eca96f42905a576d/tex/appendix_algorithms.tex): PR 29–49, WCC 55–74, SSSP 142–164.

- **PR:** uniform initial rank `1/N`; uniform redistribution of dangling mass; damping 0.85; exactly the properties-file iteration count; DOUBLE arithmetic. Use Pecan `method="power", reset_probability=0.15, tolerance=None, max_iterations=14/26` (or 2 for examples). Expected result metadata is `converged=None`, not `True`. A positive algorithm convergence tolerance is a different stopping contract.
- **Undirected edges:** official EVLP lists each undirected edge once. Pecan PR has a directed recurrence: explicitly append the reversed arcs once. BFS/SSSP should receive the original edge list and `directed=False`; their controller expands reversals itself. WCC always treats edges as undirected.
- **WCC:** official acceptance is partition equivalence. Canonical minimum original ID is an additional Pecan/reference check, not an official labeling restriction. Both test fixtures have `{1,2,3,4,9}->1` and `{6,7,8}->6`; vertex 5 does not exist. Check full membership, including false merges and splits.
- **SSSP:** traverse outgoing arcs for directed input; sum finite nonnegative DOUBLE weights, including zero; source distance zero; unreachable is positive infinity. Pecan emits null distance/parent/hops for unreachable rows: normalize only distance null to positive infinity in the explicit output adapter and retain the raw result. Directed test vertex 9 is unreachable; undirected test vertices 11 and 12 are unreachable.
- **Validation:** require exact complete vertex-ID coverage and unique rows, reject nonfinite PR values, and compare each finite PR/SSSP value with `abs(actual-reference) <= 0.0001*abs(reference)`. The threshold is relative 0.01%, not absolute 1e-4. Reference zero requires actual zero. Match positive infinity to positive infinity; reject finite/infinite mismatches and NaN. BFS uses exact depths with an explicit null-to-unreachable adapter.

Validator pin: [`ldbc/ldbc_graphalytics@7b8bde76cf7aab5e90b25ecd4b38829e2f98b292`](https://github.com/ldbc/ldbc_graphalytics/tree/7b8bde76cf7aab5e90b25ecd4b38829e2f98b292).

- [Algorithm.java lines 38–43](https://github.com/ldbc/ldbc_graphalytics/blob/7b8bde76cf7aab5e90b25ecd4b38829e2f98b292/graphalytics-core/src/main/java/science/atlarge/graphalytics/domain/algorithms/Algorithm.java#L38): PR/SSSP use epsilon; WCC uses equivalence.
- [EpsilonValidationRule.java lines 34–38](https://github.com/ldbc/ldbc_graphalytics/blob/7b8bde76cf7aab5e90b25ecd4b38829e2f98b292/graphalytics-core/src/main/java/science/atlarge/graphalytics/validation/rule/EpsilonValidationRule.java#L34): infinity handling and relative error.
- [EquivalenceValidationRule.java lines 30–48](https://github.com/ldbc/ldbc_graphalytics/blob/7b8bde76cf7aab5e90b25ecd4b38829e2f98b292/graphalytics-core/src/main/java/science/atlarge/graphalytics/validation/rule/EquivalenceValidationRule.java#L30): reject both false splits and false merges.

## Current source support and existing evidence

Inspected exact candidate controller `6ae2e43a903c2cee02da170465c922c72b76198e`, staged inside the `sail-extension-targets` volume at `/targets/pecan-typed-tests-20261001/candidate`. Guest host-filesystem prefix is `/var/lib/docker/volumes/sail-extension-targets/_data/pecan-typed-tests-20261001/candidate`.

- [Pecan algorithms.py lines 165–239](https://github.com/querygraph/sail/blob/6ae2e43a903c2cee02da170465c922c72b76198e/examples/extensions/graph-algorithms/src/pyspark_pecan/algorithms.py#L165): fixed-step power PR exists, initializes uniformly and redistributes sinks. The older Grust review's proposed finite-step API gap is stale for this source.
- [algorithms.py lines 243–289](https://github.com/querygraph/sail/blob/6ae2e43a903c2cee02da170465c922c72b76198e/examples/extensions/graph-algorithms/src/pyspark_pecan/algorithms.py#L243): WCC methods, canonical labels, convergence contract.
- [algorithms.py lines 293–329](https://github.com/querygraph/sail/blob/6ae2e43a903c2cee02da170465c922c72b76198e/examples/extensions/graph-algorithms/src/pyspark_pecan/algorithms.py#L293): BFS/SSSP source, direction, weights, nullable unreachable output.
- [traversal.py lines 30–43](https://github.com/querygraph/sail/blob/6ae2e43a903c2cee02da170465c922c72b76198e/examples/extensions/graph-algorithms/src/pyspark_pecan/traversal.py#L30): DOUBLE schema and undirected reverse-arc expansion.

Local Grust evidence:

- `/Users/alexy/src/grust/docs/reviews/pecan-validation-2026-10-01/README.md:4`: valid graph caller contract (unique non-null BIGINT IDs, valid endpoints/source, finite nonnegative DOUBLE weights and finite path sums).
- Same README lines 78–104: exact-source gates, source-first imports, runtime/tool versions. These are existing fixture gates, not an official test-* conformance verdict.
- `/Users/alexy/src/grust/docs/reviews/pecan-typed-experiments-2026-10-01/README.md:62`: existing controller/runtime/image pins; lines 80–90: signed sparse-ID compatibility smoke and full cit-Patents WCC oracle; lines 100–106: refresh admission before each cell.
- `/Users/alexy/src/grust/docs/reviews/sail-stream-experiments-2026-09-30/SEM-REVIEW-2-RESPONSE.md:21`: older PR recurrence comparison warning. Keep it for historical claims; use the current power API for official finite-step fixtures.

No retained official test-* conformance suite was found in the inspected Grust experiment/gate reports. A new harness must bind archive/member hashes, parsed properties and explicit adapters, controller/runtime origins, full raw output, oracle verdict, and certain process/container closure before advancing. Keep prior frozen benchmark helpers unchanged; use a new harness and report directory.

Passing these positive-ID tiny fixtures does not establish the full unsigned-64-bit Graphalytics ID domain: Pecan's stated schema is signed BIGINT. Report the tested domain and unsupported algorithms explicitly.
