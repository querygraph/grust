# Pecan: official LDBC tiny-fixture semantics

Recorded UTC: 2026-10-01T19:11:10.610118+00:00.

**Run02 passed all 16 supported algorithm cases**, comparing every returned row with the current official archive references. These cover eight directed/undirected `test-*` fixtures and BFS, PageRank, WCC and weighted SSSP on both example graphs. The outputs contain 234 rows across the sixteen cases, with exact unique vertex coverage and zero semantic mismatches. Independent decoded-output review is retained in [independent-audit.json](independent-audit.json).

This is qualification for these fixtures, algorithms, method choices and input domain. CDLP and LCC are **unsupported**, recorded explicitly. Pecan accepts signed BIGINT IDs; this suite's positive IDs do not qualify the specification's complete unsigned-64-bit domain. It is not an official six-algorithm LDBC Benchmark Result. No performance comparison is made by this correctness suite.

## Source and execution

- Controller: `6ae2e43a903c2cee02da170465c922c72b76198e`, unchanged and clean before/after.
- Runtime: `56194b170155301ba91077f0ba3df31fe2c78b6b`; binary SHA-256 `5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec`.
- Native source: `ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73`; native library SHA-256 `eb0be839de652e059799dea3bba22cc0908998bd97cfa2f4cf04c67817e2ee50`.
- Existing Linux image `f3518d652fbea8b9b9f9ebf9849277ca3bd39d0c21bb2c6e36fbaeaa2dc2678e`; no runtime rebuild.
- Morrobay, Docker context `colima-sail-gate`, one local Sail server, two threads/partitions, 1 GiB Sail pool; two CPUs, 4 GiB container limit, no swap.
- Methods: BFS `frontier`, PageRank `power`, WCC `randomized_fused` seed 42, SSSP `delta_star` width 1.
- Run02 exited 0, without OOM, transport error or timeout; server cleanup completed, container removed and execution lock released.

Pins, all source/package hashes, raw case metadata, recorded input hashes and before/after source checks: [receipt.json](receipt.json). The helper verifies the same input hashes again after execution. Host closure: [host-result.json](host-result.json). Plan: [plan.json](plan.json).

## Official references and explicit adapters

The [official catalog](https://ldbcouncil.org/benchmarks/graphalytics/datasets/) supplies all fourteen retained archives, including the unsupported algorithms. [input-manifest.json](input-manifest.json) records exact download/member identities: fourteen compressed archives and 66 extracted members. The [semantic handoff](SEMANTICS.md) binds the formal specification and validator source pins.

- **PageRank:** damping 0.85, initial rank 1/N, uniform dangling redistribution, exactly 14 directed-test iterations, 26 undirected-test iterations and two example iterations. Pecan `tolerance=None` returns `converged=None` for this fixed-step contract.
- **Undirected inputs:** PR receives one added reverse arc per original edge. BFS/SSSP receive original edges with `directed=False`, because their controller expands reverse arcs. WCC ignores direction.
- **SSSP:** outgoing directed edges, archive DOUBLE weights, archive source, zero source distance. Raw unreachable distances remain null; the explicit comparison adapter maps them to the reference's positive infinity.
- **BFS:** compare exact hop distances; raw null unreachable distances map to the official integer sentinel `9223372036854775807`.
- **WCC:** official partition equivalence rejects false merges and splits. The additional Pecan canonical-minimum-ID check also passed every WCC fixture.
- **Numerical validation:** per-vertex relative 0.01% for finite PR/SSSP values; reference zero requires exact zero; infinity must match infinity and NaN is rejected. This does not replace fixed-step PR with a convergence threshold.
- **Upstream properties corrections:** `test-wcc-directed.edge-file` and `test-sssp-undirected.edge-file` mistakenly name `.v`. Their raw properties are unchanged; the adapter explicitly resolves the corresponding actual `.e`, with the correction recorded.

## Every supported case

| Fixture | Algorithm | Rows | Iterations | Outcome |
| --- | --- | ---: | ---: | --- |
| `test-bfs-directed` | bfs | 10 | 4 | passed |
| `test-bfs-undirected` | bfs | 10 | 4 | passed |
| `test-pr-directed` | pr | 50 | 14 | passed |
| `test-pr-undirected` | pr | 50 | 26 | passed |
| `test-wcc-directed` | wcc | 8 | 3 | passed |
| `test-wcc-undirected` | wcc | 8 | 3 | passed |
| `test-sssp-directed` | sssp | 10 | 9 | passed |
| `test-sssp-undirected` | sssp | 12 | 8 | passed |
| `example-directed` | bfs | 10 | 3 | passed |
| `example-directed` | pr | 10 | 2 | passed |
| `example-directed` | wcc | 10 | 2 | passed |
| `example-directed` | sssp | 10 | 4 | passed |
| `example-undirected` | bfs | 9 | 5 | passed |
| `example-undirected` | pr | 9 | 2 | passed |
| `example-undirected` | wcc | 9 | 3 | passed |
| `example-undirected` | sssp | 9 | 6 | passed |

[Classification index](classification-index.json) exposes outcomes, settings, schemas, corrections and evidence paths for subsequent queries. Its `archive` and `archive_prefix` fields locate each case directory within the portable tar. Complete original references and raw returned rows are in [evidence.tar.gz](evidence.tar.gz). The [evidence manifest](evidence-manifest.json) lists every archived file and its SHA-256; the gzip archive SHA-256 is `95529c91ac127262f318dc5faaab46309051602cd459eab35abe7dac8848a1aa`.

## Retained first attempt and helper correction

Run01 stopped after the first BFS case: its ten rows matched the official reference, but the harness incorrectly required every staging directory to disappear. Independent inspection found 13 directory entries and **zero** regular files, symlinks or special entries. The source's object-store removal deletes objects rather than filesystem directories. Run01 retains its failed producer/host verdict and fifteen unrun cases; it was not relabeled as a suite pass. [First-attempt audit](first-attempt-audit.json).

A new helper and fresh run02 namespace corrected that fixture contract, requiring zero non-directory entries and recording directory prefixes separately. All original semantic function ASTs remain unchanged. The new helper passed twelve oracle controls, nine cleanup controls, Ruff and mypy before launch. Actual run02 repeats those controls, checks each result/schema/metadata and hashes inputs/source before and after. The old helper and every original run01 artifact remain retained.

- Original helper: [run_ldbc.py](run_ldbc.py), SHA-256 `0badbeb3c6fbcae901b194d11295156819d805f5b019a5b6b372104e0db20734`.
- Corrected helper: [run_ldbc_v2.py](run_ldbc_v2.py), SHA-256 `3a661a82a014bf704a4ac24903f20bb029fa94164b4685cc91ddae555c7ba7c7`.
- Host wrappers: [run_host.py](run_host.py), [run_host_v2.py](run_host_v2.py). Their fixed paths are retained commands, not an invitation to reuse closed run IDs.

## Storage and follow-up

Full host-side evidence is under `/Volumes/Apo/graph-tests/results/pecan-ldbc-semantics-20261001-run02/`; the original failed-attempt archive is separately preserved under `/Volumes/Apo/graph-tests/results/pecan-ldbc-semantics-20261001/`. Standard gzip tar plus original text, JSON receipts, schemas and SHA-256 manifests preserve the fixtures and semantics. The guest results are retained too.

The [Pregel source review](PREGEL-REVIEW.md) addresses Sem's shared traversal proposal. The [WCC source review](WCC-REVIEW.md) records exact ordered-aggregate state, representative selection versus final canonical labels, the paper's retained contraction maps, and a proposed plain-MIN plus affine-inverse control. These reviews do not establish operator-level timing attribution or authorize another benchmark. The prior [typed Pecan comparison](../pecan-typed-experiments-2026-10-01/morrobay-20261001/COMPARISON.md) remains a separate, closed shared-host experiment. Further performance work should first match the external CLI/input/output/timer/envelope, then measure one change with retained physical plans and request counts.

The operator's priority request, semantic handoff, local execution-ownership note and WCC/Pregel questions were delivered to Capitola using Taildrop; original requests and delivery receipts are archived. Direct SSH authentication was rejected; no Capitola/Astra acknowledgement has been observed. The present execution and independent review occurred on Morrobay. The screenshot path supplied for Sem's proposal was unavailable on this host.
