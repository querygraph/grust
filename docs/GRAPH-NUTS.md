# Graph Nuts master plan

Graph Nuts is the umbrella for graph algorithms executed through Sail and
validated with independent graph benchmarks. It covers the algorithm kernels,
Sail extension wiring, large-graph qualification, and the published evidence.
The name describes the benchmark family; it does not create a new execution
engine or imply a combined leaderboard.

## Objectives

1. Provide correct PageRank, WCC, BFS and shortest-path implementations with
   both reference and advanced variants.
2. Run the algorithms through Sail in local and distributed modes with small,
   focused extension changes.
3. Qualify native and relational/DataFusion execution separately, including
   staging, memory, disk and file-descriptor behavior.
4. Validate on synthetic fixtures and real large graphs such as cit-Patents,
   Graph500 and other openly documented datasets.
5. Preserve neutral, reproducible evidence for every result, including
   failures, admission refusals, unavailable samples and timeouts.
6. Publish concise tutorials and summaries while retaining the detailed raw
   matrices and audit records.

## Project map

### Sail implementation and integration

| Directory | Role | Status and source of truth |
|---|---|---|
| `src/sail` | Upstream Sail checkout | Use for clean upstream comparisons and maintainer-facing changes. |
| `src/sail-extensions-poc` | Main extension proof of concept | Current reference for Pecan, Nutmeg integration, protocol examples, staged graph execution, and the small Sail-side API surface. Design plans and scaling notes live in `grust/docs`, not here; this repository holds code, tutorials and evidence. |
| `src/sail-large-graphs` | Large-graph execution, Argentea and traversal qualification work; branch `work/extensions-traversal-bench` | Use for real-graph ingestion, staging pressure, `ulimit`, spill behavior and distributed capacity experiments. Results must be copied into the evidence archive and summarized in the master plan. **The remote branch is the authority**: on 2026-09-28 the local checkout (`9c9ea46c8`) was 76 commits behind `querygraph/work/extensions-traversal-bench` (`b87fb27ac`) and carried five uncommitted host-file edits under `crates/sail-common-datafusion` and `crates/sail-execution`. Everything Argentea-related listed below lives on the remote tip. |
| `src/sail-querygraph-alignment` | Sail alignment and upstream compatibility checkout; branch `agent/sail-performance-alignment` | Use to compare extension assumptions with current Sail/DataFusion APIs and to stage maintainer-compatible changes. |
| `src/sail-grust-performance-alignment` | Performance-oriented Sail/Grust alignment; branch `agent/grust-performance-alignment` | Use for cross-checking execution and accounting behavior; do not treat it as the canonical published extension source unless explicitly promoted. |
| `src/sail-traversal-controls` | External traversal reference implementations: `gapbs`, `graph500`, `parallel-sssp` | A plain directory, not a git repository, holding upstream checkouts used as independent controls for BFS and SSSP. The build and pinning scripts that consume them are tracked under `sail-large-graphs/examples/extensions/benchmarks/traversal-controls`. |
| `src/sail-upstream-pr.*` | Temporary upstream PR worktrees | Ephemeral review checkouts. Never use them as a source of truth. |

The canonical extension implementation is `sail-extensions-poc`. Large-graph
work may diverge while experiments run, but every promoted change must be
reapplied to the canonical branch and recorded with its source commit.

**Where documents go.** Plans, reviews, handoffs and this map live in
`grust/docs`. The Sail fork receives only small, limited edits after careful
review; its `docs/development/extensions` tree holds the evidence reports and
design records that were written beside the code, and nothing new is added
there without that review.

Astra's gate and work checkouts live under `/private/tmp/sail-*` (about 60
detached worktrees of the same clone plus logs and receipts: 1,054 entries,
64 GB on 2026-09-28, oldest from 2026-09-16). They are Astra's to prune;
`git worktree list` in `~/src/sail` shows which are still registered.

All Sail checkouts under `~/src` are worktrees of one clone whose remotes are `origin`
(lakehq/sail, upstream), `querygraph` (the querygraph/sail fork where all
graph branches live) and `fork` (alexy/sail, a true GitHub fork, used only to
open upstream pull requests because `querygraph/sail` is not registered as a
fork).

### Execution paths

Four paths compute graph results through Sail. The names describe where the
work runs, not different definitions of the algorithms.

| Path | Entry point | Where the graph work runs | State on 2026-09-28 |
|---|---|---|---|
| **Pecan** | `pyspark_pecan.GraphAlgorithms` in `sail-extensions-poc/examples/extensions/graph-algorithms` | Python controls rounds; Sail/DataFusion executes joins and aggregates on workers; Parquet checkpoints between rounds | PageRank and WCC in reference, delta/frontier and fused-contraction forms. Ran Graph500-24 (260 M edges) in Sem's 24 GB single-host envelope and all four Graph Kernels inputs in the Morrobay campaign. No checkpoint purge, no declared layout, builtin reducers only. |
| **Nutmeg Banda** | `sail_nutmeg.Nutmeg.stage/run/drop` over `sail-extensions-poc/examples/extensions/vendor/nutmeg-graph` | Staging, CSR and Grust 0.23.0 kernels inside Sail's driver process; one machine | All 36 Grust kernels plus `pagerankDelta`, `wccRandomized`, `wccRandomizedFused`. Ran the 4 M-vertex inputs under a 32 GiB native allowance; refused them at 8 GiB; has never run Graph500-24. Limit is string identity in staging and projection, not the kernels. |
| **Nutmeg Grenada** | Nutmeg `GraphTables` adapted to `GraphAlgorithms` | Same as Pecan; no native staging | Same coverage and results as Pecan. |
| **Argentea** | `sail-large-graphs/examples/extensions/argentea` (Rust core, worker adapters, Python client) | Native CSR partitions on Sail workers for the lifetime of one Sail job; ordinary Flight shuffles carry messages; rounds unrolled as native stages in one job | Reference and residual PageRank (32-phase), BFS in reference, frontier and direction-switching forms (128-stage in process clusters), WCC (min-label and seeded star) and weighted SSSP pass process-cluster qualification; PageRank and BFS pass physical two-host (Capitola/Morrobay) qualification. Bounded rounds per job; one attempt for native regions; no capacity or performance evidence. |

The scaling review and improvement sequence for all four is
`grust/docs/FABLE-ON-ASTRA.md`; its diagnosis input is
`grust/docs/SCALING-NUTS.md`.

### Algorithm libraries and native paths

| Directory | Role |
|---|---|
| `src/nutmeg` | Nutmeg development checkout. Use for upstream Nutmeg work that has not yet been signed or frozen for Sail integration. |
| `src/nutmeg-signed` | Signed Nutmeg source used for reproducible integration and native-kernel qualification. |
| `src/grust-pagerank-fused` | Grust worktree, branch `work/pagerank-fused` (`2985fac`): one fused pull pass per PageRank iteration, bit-identical to the reference. Kernel research, not a release branch. |
| `src/grust-narrow-u32` | Grust worktree, branch `work/narrow-targets` (`48598b4`): the four-byte CSR arc targets that shipped in Grust 0.23.0. Index width is `u32` for nodes and arcs, with an explicit refusal at 2^32. |
| `src/grust-pagerank-f32` | Grust worktree, branch `work/pagerank-f32` (`ead3568`): `f32` scores behind the `precision` option. Scores default to `f64`; `f32` is opt-in and can stall against an absolute tolerance on very large N. |
| `src/grust-fastrp-f64` | Grust worktree, branch `work/fastrp-f64-accumulator` (`0e498f9`): accumulator precision for FastRP embeddings. |
| `src/grust` | This repository: shared algorithm contracts, backend-neutral documentation, release evidence and the Graph Nuts master plan. Grust 0.23.0 "Langoustine" is the released kernel set (twenty crates on crates.io, tag `v0.23.0` at `6504c0c`). `HANDOFF.md`, `GRUST-SAIL.md` and `LAKESAIL-AWS-QUERYGRAPH.md` at the repository root record the release state, the Sail changes Nutmeg needed, and where the AWS hosts' work went. |
| `src/grustframes` | Compatibility and GraphFrames-style API experiments. Use for API comparison, not as the authority for Sail staging behavior. |
| `src/graph-book` | General graph documentation and explanatory material. Link to Graph Nuts where Sail-specific execution is discussed. |

The native PageRank delta/frontier kernel is qualified only when its staging
path has also succeeded. Kernel correctness and staging scalability are
separate claims.

### Alternative extensions and comparison implementations

| Directory | Role |
|---|---|
| `src/sedona-db-extension-poc` | Apache Sedona extension proof of concept and Sail integration experiments. Keep its protocol and build instructions separate from Nutmeg. |
| `src/pecan` | Not present as a checkout. Pecan is the relational implementation and benchmark harness in `sail-extensions-poc/examples/extensions/graph-algorithms`. |
| `src/cargraph` | A plain directory, not a git repository. Graph representation and algorithm experiments that may supply fixtures or comparative kernels. |
| `src/querygraph` | QueryGraph integration and graph product work. Use for protocol and product integration, not as the benchmark evidence archive. |
| Sem's `querygraph/sail` PR 30, branch `graphframes-rs-like` (`b772a112c8`, marked do-not-merge) | Pure-PySpark Pregel with GraphX-style delta messages (`gfrs-poc/pregel.py`, `pagerank.py` with `skip_dest_state`), a checkpointer without purge, and the `sem_benchmark` harness. Runs on any Spark Connect server without an extension. Retained results: Graph500-24 in 172 s at 8.0 GB peak RSS and 7.7 GB written over 19 iterations at tolerance 1e-5 on a c5d.4xlarge with a 24 GB pool; cit-Patents in 14.7 s at 1.3 GB. Nutmeg was run only on a ten-vertex example. Not yet compared with Pecan in one envelope; `FABLE-ON-ASTRA.md` S5 schedules that. |
| `SemyonSinchenko/graphframes-rs` (external) | Rust GraphFrames-style library on DataFusion whose execution model Sem's PR follows; the Sail-side integration plan is `graphframes-rs-plan.md` and its review. |

## Benchmark and publication map

| Directory | Role |
|---|---|
| `src/adversarial-graph` | Graph benchmark harness and evidence for graph stores and execution paths. Keep workload design and comparisons neutral. |
| `src/adversarial-graph-algorithms` | Algorithm benchmark workloads, result ledgers and large-graph runs. Use for PageRank, WCC, BFS and shortest-path campaign definitions. |
| `src/adversarial-site` | Published site (`master`, `40e23a6`). `/graph/graphnuts` is the Graph Nuts page with summary findings above expandable matrices, rendered by `scripts/render-graphnuts.mjs` and checked by `scripts/verify-graphnuts-evidence.mjs`; `/graph/kernels` is the Grust kernel benchmark page from campaign B9. Both render from evidence files; hand-typed numbers fail the renderer. |
| `src/adversarial-site-large-campaign` | Branch `work/graphframes-large-campaign` (`fad121d`): the independently audited large Sail graph campaign as a site publication. Promote only verified artifacts into the main site. |
| `src/adversarial-agents` | Agent and systems benchmark support. It is not an algorithm correctness authority. |

### Hosts

| Host | Role | State on 2026-09-28 |
|---|---|---|
| morrobay | 18-core, 128 GB Intel Xeon Mac; Linux gate through Colima (`colima-sail-gate`, 24 CPUs, 64 GiB); ran the 180-trial large campaign and the 216-cell traversal campaign in 56 GiB containers | Traversal campaign `gk-traversal-release-538b` finished 2026-09-29 00:01 UTC, 216 of 216 passed (harness `538b94cbb`, host and wheel `038c9b9597`, image `f3518d652f`), evidence at `~/src/sail-extensions-gates/graph-kernels-traversal-1f18/campaign`. Its independent audit (`traversal-validation/independent-audit/audit_campaign.py` from `b87fb27ac`) passed all 216 cells; report `…/audit/audit-report.json` sha256 `9ae42253cede55e04b3125f8962d26515f7a1796c90960b6624f9c2ff8c20deb`; closing record `…/campaign/CLOSED-2026-09-29.md`, copied to `grust/docs/reviews/gk-traversal-release-538b-closed.md`. The Linux baseline was rebuilt from `b87fb27ac` on 2026-09-29 (`~/src/sail-extensions-gates/graph-nuts-b87fb27ac/rebuild.py`; receipt `/targets/graph-nuts-b87fb27ac/rebuild-receipt.json`; host `sail-linux-x86_64-b87fb27ac29b-release` sha256 `ce64f25b…`, wheel sha256 `125a6d3a…`), and qualified: 54 functional cells passed (`qualify.py`, `/targets/graph-nuts-b87fb27ac/qualification/summary.json`). The same day the gate VM was resized to 32 CPUs, 110 GiB and a 240 GB disk (default VM stopped), and the volume pruned of 63 GB of Astra's build caches (`/targets/PRUNED-2026-09-29.txt`; evidence, receipts, `repository.git`, venvs, campaign runs and large inputs kept; Sedona wheel copied to `/targets/linux-gates/wheels/`). Staged there: `gn-capacity-b87fb27a.json` (36 BFS/SSSP cells on Graph500 scale 24 and 25, tip harness) and `gn-ranking-b87fb27a.json` (30 PageRank/WCC/BFS/SSSP cells on cit-Patents, pinned `d2a11214…`, S0 harness checkout `/targets/graph-nuts-b87fb27ac/source-s0` at `7f00735ad`, certificate policy), with input preparation started 04:20 UTC (scale 24: 268,435,456 edges in 1024 files; scale 25: 536,870,912 edges in 2048 files, complete in the volume, but the harness's `docker cp` of the 7.4 GB to the host timed out, so `capacity/datasets/scale25/HOST-COPY-INCOMPLETE.txt` points at the volume copy and its pinned `manifest.json`; cit-Patents imported through the S0 SNAP importer). The capacity matrix was launched 04:36 UTC with `--skip-prepare` (`capacity-launch.json`, `capacity-run.log`) and stopped at 05:03 UTC after five cells (`capacity/STOPPED-2026-09-29.md`): its Graph500 datasets used `source: 0`, copied from the harness's `graph500-matrix.example.json`, and vertex 0 is isolated in these Kronecker graphs (the passed scale-24 Pecan cell reports `reached = 1` and one empty iteration), so every traversal cell would have measured loading plus one empty round. It was re-issued at 05:04 UTC as `gn-capacity-b87fb27a-hub` with the sampled highest-degree vertex 13507776 as the source for both scales (`graph-nuts-gate-next/pick_sources.py`; sampled degree 46,207 in 1/16 of the scale-24 edges), and the ranking matrix as `gn-ranking-b87fb27a-hub` with cit-Patents source 3569341 (the highest out-degree, 770 citations). The five kept cells: scale-24 Pecan BFS frontier 199.6 s and Grenada BFS push-pull 372.5 s (loading only, 21 GiB peak PSS each); scale-24 Banda refused staging in 64.8 s; and the two scale-25 blockers of the baseline: the Banda cell refused staging in 92 s because the canonical sort's admitted working space came to 404 GB (8.6 GB permutation, about 396 GB of sort keys at the 16x-buffer-plus-128-bytes-per-row bound, 141 GB sorted copy) against the 80 GiB quota, and the relational cell failed after 331 s, in the harness's certificate query rather than the traversal (the hub-source rerun showed the BFS completes and only the 33.5M-row certificate join hits it), with `decoded message length too large: found 8234561 bytes, the limit is: 4194304 bytes`, Tonic's 4 MiB client default that Sail's internal gRPC clients keep while its servers accept 128 MiB. Both fixes are on fork branches (`work/s2-stage-order`, `work/grpc-client-decode-limit`, merged in `work/gn-gate-next` at `ac000b6e8`, all pushed). A chain (`~/src/sail-extensions-gates/graph-nuts-gate-next/chain.sh`, v4 from 05:13 UTC after three aborted starts recorded in `chain.log`; `chain-launch.json`) first re-prepares the inputs, because the fixtures pin `traversal.source` in the dataset manifest and `graph_cell.py` asserts it (the source-0 datasets stay untouched under `/targets/gn-capacity-b87fb27a` and `/targets/gn-ranking-b87fb27a`; the hub-source copies go under `…-hub`), then ran the hub-source capacity matrix (29 of 36 cells before an orchestration stop; 3 passed, the rest refusals, memory failures and stream losses, see the record), then the hub-source cit-Patents ranking matrix (30 cells, 29 passed and one WCC label-convention mismatch, finished 17:57 UTC), then builds the gate: the first attempt from `666c619a6` (17:57 UTC) failed at `core-tests` on a stale vendored test, its records are under `graph-nuts-gate-next/failed-666c619a6/`; the second, by `chain-next.sh` from `work/gate-core-tests` at `2557feaf1` (18:08 to 18:44 UTC, all 17 steps passed; receipt `graph-nuts-gate-next/rebuild-receipt.json`; host `sail-linux-x86_64-2557feaf18e4-release` sha256 `ff33c08838…`, wheel sha256 `6fe0672a78…`, entry points sedona/nutmeg/argentea) into `/targets/graph-nuts-2557feaf1`, links the Graph500 inputs into `/targets/gn-capacity-ac000b6e/datasets`, and runs `gn-capacity-ac000b6e.json` (run id `gn-capacity-2557feaf`, started 18:44 UTC; the file and the `/targets/gn-capacity-ac000b6e` root keep their earlier names; source 13507776; 42 cells; every relational cell records its per-iteration plans; every server runs with a 120 s keepalive timeout): the 12 scale-25 relational cells with the client decode limit raised, 8 scale-24 relational reference/frontier cells that rerun the baseline's `h2 protocol error` failures, 12 Banda cells at scale 24 and 25 with `stage_order: asStaged`, and 10 Argentea cells at scale 24 and 25 (BFS reference/frontier/direction, SSSP reference/delta_star, 30-round cap, 32 partitions). Findings aggregate with `graph-nuts-gate-next/capacity_findings.py <host_output>`. The baseline capacity matrix stopped itself after 29 of 36 cells (an orchestration/cleanup error on the swapped host); `chain-scale26.sh` first resumes it (`--resume`, the 7 unrun cells), then reruns the 12 cit-Patents ranking-kernel cells on the new gate (`gn-ranking-next.json`, run id `gn-ranking-2557feaf`, host output `ranking/`, tiered stage receipts and the corrected WCC certificate), then prepares Graph500 scale 26 (67,108,864 vertices, 1,073,741,824 edges) with the new `max-degree` source policy and runs `gn-capacity-scale26.json` on the same gate: 12 relational, 6 Banda `asStaged` and 5 Argentea cells, host output `capacity-scale26/`. **Reordered 2026-09-29 23:10 UTC on two user directions: no more cell timeouts (4 h per cell now, 8 h at scale 26), and Argentea first.** The 42-cell matrix on gate 2 was stopped after 3 cells (kept under `capacity-attempt1-5400s/`: Pecan reference timed out at 5400 s past its baseline failure point, Pecan frontier passed, Grenada push-pull passed with its certificate, which verified the decode limit). Gate 3 is building from `work/s5-frontier-build-side` (`ffcfbd569`, started 23:08 UTC, `rebuild-gate3.py`/`launch-rebuild-gate3.py`, `source-gate3.bundle`, `harness-gate3/`) into `/targets/graph-nuts-ffcfbd569`, and `chain-argentea.sh` (log `chain-argentea.log`) then ran, on gate 3, `gn-argentea-gate3.json` (22 cells: the 12 Banda `asStaged` cells at scales 24 and 25 first, then the 10 Argentea cells, host output `argentea-gate3/`); **reordered again 2026-09-30 02:22 UTC** because that plan put Banda before Argentea: the chain was stopped in its fifth cell (Banda scale-25 frontier, its partial log kept as `argentea-gate3/interrupted-cell5-container.log`, the four recorded cells kept), and `chain-argentea2.sh` (same log) runs `gn-argentea-first-gate3.json` (run id `gn-argentea-first-ffcfbd56`, the 10 Argentea cells only, host output `argentea-first-gate3/`, container environment `SAIL_CLUSTER__TASK_STREAM_CREATION_TIMEOUT_SECS=900` through the new `environment` map, started 02:26 UTC with scale-24 BFS reference first), then the Banda remainder, then as before; **relaunched a third time at 04:16 UTC** as `chain-argentea3.sh` after the Argentea scale-24 frontier cell lost a worker to Sail's 60 s idle probe (see the record): `gn-argentea-first2-gate3.json` (run id `gn-argentea-first2-ffcfbd56`, host output `argentea-first2-gate3/`, the 10 Argentea cells), `gn-banda-rest-gate3.json` (the 8 unrecorded Banda `asStaged` cells, `banda-rest-gate3/`), then `gn-rest-gate3.json`, scale 26 and `gn-ranking-next.json`, every cell container now carrying `SAIL_CLUSTER__WORKER_MAX_IDLE_TIME_SECS=86400` and `SAIL_CLUSTER__TASK_STREAM_CREATION_TIMEOUT_SECS=900` through the `environment` map; the first Argentea matrix's records stay under `argentea-first-gate3/` (reference passed 1213 s, frontier lost its worker): **Stopped at 05:19 UTC on the user's direction** (the question is when to run Pecan, Banda, Grenada or Argentea; no long matrix without asking): `chain-decide.sh` runs the five-cell `gn-decide-gate3.json` (`decide-gate3/`: Argentea BFS scale 25; Banda, Argentea and Pecan SSSP delta-star at scale 24; Pecan BFS reference at scale 25) and stops; the relaunched Argentea matrix kept its reference repeat (1445 s) under `argentea-first2-gate3/`; the Banda remainder, relational rerun, scale 26, ranking rerun and baseline resume are parked pending the user. The earlier plan below is what was queued, not what runs: `gn-rest-gate3.json` (20 relational cells: scale 25 and the scale-24 reference/frontier reruns, `relational-gate3/`), scale-26 preparation and its 23 cells (`capacity-scale26/`), the 12-cell cit-Patents ranking rerun (`ranking/`), and the baseline's 7 unrun cells. The earlier `chain-next`, `chain-scale26` and `chain-gate3` scripts are superseded. `summarize.py` is the PageRank/WCC verifier and flags every traversal cell falsely; that output is kept under `summary-pagerank-verifier-not-applicable/`. Not a dedicated host, so its timings are observations, not publishable numbers; the host's Eigen Times nightly (`com.eigen.nightly` launch agent, `~/bin/eigen-nightly.sh`) starts the default Colima VM (48 GiB) beside the 110 GiB gate VM and runs its `eigen-runner` container at 01:00, 03:00, 13:00 and 15:00 UTC for up to an hour, pushing the 128 GB host into swap; the user keeps it running, so every campaign record marks which cells overlapped it (on 2026-09-29: the baseline capacity cells after the sixth and the first ranking cells). |
| capitola | Second physical host for Argentea two-host qualification with morrobay | Available for functional runs. |
| quegee, grust, eigen, lakecat (AWS) | quegee was the only dedicated host publishable timings came from; the others were the Linux gate and second-opinion hosts | Stopped 2026-09-23 and cleared for termination; everything unique was taken off (`grust/LAKESAIL-AWS-QUERYGRAPH.md`). No publishable timing can be produced until a dedicated host exists again. |
| c5d.4xlarge (Sem's) | Source of the cit-Patents and Graph500-24 results in PR 30 | Not ours; reproduce under our harness before citing. |

The publication pipeline is:

1. Define the workload and output contract in the benchmark repository.
2. Pin Sail, extension, native-wheel and controller commits.
3. Run local, worker and multi-host functional checks.
4. Run isolated Linux measurements with explicit memory, disk and file limits.
5. Keep every outcome and raw receipt; independently verify successful answers.
6. Promote only hash-verified summaries, figures and CSVs to
   `adversarial-site`.
7. Publish a short Graph Nuts explanation above expandable detailed matrices.

## Algorithm tracks

### PageRank

- **Reference:** full power iteration over the staged graph or relations.
- **Advanced:** delta/frontier PageRank with tolerance-scaled activation,
  reactivation, sparse message propagation and a final fixed-point certificate.
- **Native path:** Nutmeg/Grust kernel after graph staging.
- **Relational path:** Pecan/DataFusion tables with explicit intermediate
  materialization and caller-owned output.

The advanced kernel must never be credited with a staging failure. Record graph
load/staging metrics separately from iteration metrics.

### WCC

- **Reference:** minimum-label propagation for relational execution and
  union-find for native execution.
- **Advanced:** randomized contraction, with fused relational variants where
  the protocol and correctness checks remain identical.

Chain graphs are diagnostic fixtures, not representative scaling graphs:
minimum-label propagation can require a linear number of rounds there.

### BFS and shortest paths

- **Reference:** full reached-set relational relaxation, and Grust's native
  BFS and Dijkstra.
- **Advanced:** direction-optimizing push/pull BFS with compact frontier
  membership; all-edge delta-star stepping for nonnegative weighted SSSP, with
  classical delta-stepping and rho-stepping as controls.
- **Argentea:** reference, frontier and direction-switching BFS pass bounded
  worker-process and physical two-host tests; weighted SSSP passes
  process-cluster tests. The initial deployment bound was 14 levels in 32
  phases, since extended to 128 native stages in process clusters.
- **Inputs:** the Graph Kernels hub/uniform inputs reinterpreted as
  undirected with weights (`GRAPH-KERNELS-TRAVERSAL.md`), and Graph500
  Kronecker inputs streamed from the pinned upstream generator into
  partitioned Parquet (`GRAPH500.md`). Preparing an input is not a result;
  the manifest records `validation.status` until a scalable correctness check
  has run.

Exact output contracts and separate tests for disconnected, duplicate-edge and
dangling fixtures apply, as for the first two tracks.

### The other Grust kernels

Grust 0.23.0 registers 36 kernels and Nutmeg Banda exposes all of them. Only
PageRank, WCC, BFS and SSSP have relational or Argentea forms.
`grust/docs/FABLE-ON-ASTRA.md` section 6 classifies every kernel by shape (sweep,
frontier, Pregel, join, global) and says which path can carry it to what size
once the scaling sequence lands. Seven of them (closeness, harmonic,
betweenness, louvain, leiden, spanning tree, Tarjan SCC) scale only through a
variant that changes the algorithm; seven more (Yen's, all-pairs shortest
paths, DFS, articulation points, bridges, biconnected components, max-flow and
min-cut) are in-core Banda kernels and must not be described as distributed.

## Large-graph qualification

The first required real-graph campaign is:

- cit-Patents: approximately 3.7 million vertices and 16.5 million edges;
- Graph500-24 M-class: approximately 8.8 million vertices and 260 million
  edges;
- larger graphs only after staging, spill and descriptor behavior are bounded.

Nutmeg’s current failure mode is staging: sort keys, permutation buffers and a
sorted copy can exceed the configured native budget before the algorithm runs.
The qualification plan is therefore:

1. measure staging RSS, disk, temporary-file count and descriptors;
2. test deterministic no-sort/as-staged ingestion where valid;
3. add bounded partitioned staging and deterministic merges;
4. set and record `ulimit -n` for large runs;
5. rerun native PageRank/WCC and compare only like-for-like end-to-end paths.

### What has been measured at scale

The Morrobay campaign (`sail-large-graphs` remote tip,
`docs/development/extensions/pecan-nutmeg-large-benchmark.md`) is the only
place all three driver paths meet on the same inputs, envelope and timer:
180 planned trials on hub/uniform-2097152 and -4194304, 179 passes and one
timeout, all successful vectors independently audited. Its retained facts:

- At 8 GiB native / 16 GiB pool / 32 GiB container, Banda's staging of the
  33,554,395-edge uniform graph was refused: the sort requested
  23,511,075,308 bytes of workspace, about 700 bytes per edge. That record is
  an admission error, not an OOM kill. The 29 other trials of that attempt
  did not run.
- At 32 GiB native / 48 GiB pool / 56 GiB container, all paths pass. Banda's
  reference PageRank has the lowest median full-call time on all four inputs
  with higher sampled PSS. Delta/frontier is slower than reference for every
  path on every input. Relational WCC fusion cuts time 11 to 25 percent for
  6 to 24 percent more memory; native fusion does not show that.
- One Pecan reference-WCC cell timed out at 1,800 s; its two other
  repetitions and a later control passed in about 33 s. The cause is
  unexplained and the timeout stays in the evidence.

The earlier sparse campaign (`sail-extensions-poc`,
`pecan-nutmeg-benchmark.md`, 228 trials, 226 passes and two expected
convergence caps) covers the 15 path/method combinations on bounded-component
graphs up to one million vertices.

`grust/docs/FABLE-ON-ASTRA.md` reads these together with Sem's PR 30 numbers and orders
the work: separate staging from kernel measurement (S0); integer identity
through staging (S1); sort only for kernels that read order, with a spilling
sort when they do (S2); a dense integer projection without per-node strings or
a per-edge record (S3); a file-backed CSR for Banda beyond memory (S4); Pecan
purge, layout, tolerance and Sem's delta messaging as a Pecan method (S5);
Argentea continuation across jobs, then a session-scoped native-state request
to Sail (S6). Each step has a fixture and a gate.

## Checkouts and builds on Capitola

`~/src` is the operator's whole workspace; only the entries below belong to
this work, and every one of them must be listed here. On 2026-09-28 the
operator had every Cargo compile cache under `~/src` removed (467 GB across
24 `target` directories, among them `sail-extensions-poc/target/debug`,
`grust/target`, `nutmeg/target`, `grust-binding-forms/target`,
`grust/benchmarks/lsqb/target`); the disk went from 12 GB to 464 GB free.
Delivery records under `sail-extensions-poc/target/extensions-*` kept their
binaries, wheels, receipts and logs; only their `deps`, `build`,
`incremental` and `.fingerprint` caches went. Any `target/` named below as a
build is therefore gone and rebuilds on first use; a Sail host build is 40
to 50 GB.

### Sail worktrees (one clone, `~/src/sail`, remotes `origin`=lakehq, `querygraph`, `fork`=alexy)

| Directory | Branch | What is built there |
|---|---|---|
| `~/src/sail` | `lakecat` (`9f6f8065d`, 2026-08-28) | The clone itself; LakeCat work, 3 dirty files. Not a graph checkout. |
| `~/src/sail-extensions-poc` | `work/extensions-datafusion-graphs` | 12 GB after the cleanup (`target/debug`, whose arm64 binary did not start, is gone). Runnable: `target/extensions-datafusion-final/mac-x86-de8e67098/sail` (x86_64, links the uv Python `cpython-3.12.13-macos-x86_64-none`, runs under Rosetta) with its `wheels/`; `target/extensions-datafusion-development/mac-x86/sail` likewise. Wheels: `target/extensions-poc/wheels/` and `target/extensions-datafusion-development/nutmeg-wheels/` (arm64 `sail_nutmeg`). Python: `.venv` (arm64 3.12.8, PySpark 4.0.1, `sail_nutmeg` installed) and `.venvs/extensions-datafusion`, `.venvs/extensions-x86*`. Delivery records: `target/extensions-datafusion-final/README.md`, `target/extensions-distributed-poc/`, `target/pecan-benchmark/`. |
| `~/src/sail-large-graphs` | `work/s0-source-degree` (`c00a36434`: `work/s0-tiered-accounting` plus `work/s2-stage-order`, `work/grpc-client-decode-limit` and the max-degree source policy, all from `work/extensions-traversal-bench` at `b87fb27ac`) | No `target/`; its builds run on morrobay under `~/src/sail-extensions-gates/` (for example `graph-kernels-traversal-1f18/`, the running campaign) and in Colima. The stash `preserve pre-catchup sail-large-graphs worktree 2026-09-28` holds three files that differ from the tip; audited, nothing unique but a small scheduler test difference. |
| `~/src/sail-declared-layout` | `work/declared-layout` (from `b87fb27ac`; pushed) | The graphframes-rs parity work: the `checkpointed` relation and Pecan's `layout="declared"` (pushed), and the host wrapper restating a native relation's declared layout with host columns (`crates/sail-session/src/extensions/plan.rs`, tested). Builds (session scratchpad, not `~/src`): arm64 extension artifacts in `s0-target`, the host check/test build in `host-target`, an arm64 wheel in `arm64-wheel/` and an x86_64 wheel `sail_nutmeg-0.1.0-cp312-cp312-macosx_10_12_x86_64.whl` in scratchpad `x86-wheel/` with its x86 venv `x86venv/`, made for the delivered x86 host; that host predates Pecan's utils service, so the Pecan comparison must run on morrobay. |
| (removed 2026-09-28) `sail-querygraph-alignment`, `sail-grust-performance-alignment`, `sail-upstream-pr.7kGHU1` | `agent/sail-performance-alignment`, `agent/grust-performance-alignment`, `agent/sail-performance-hot-paths` | August alignment and PR worktrees, clean and fully pushed; the worktrees were removed, the branches remain in the clone. |
| `~/src/canonical-order/sail`, `~/src/bounded-staging/sail` (symlink to the former) | detached `f1cf1729b` (the Sail commit Nutmeg 0.1.0 pins) | Astra's experiment layout from 2026-09-21, see the Nutmeg row. |

### Nutmeg and Grust

| Directory | Branch | Notes |
|---|---|---|
| `~/src/nutmeg` | `main` (`f267b03`) | Pins Sail `f1cf1729b` and Grust `6504c0c`. `target/` removed 2026-09-28. |
| `~/src/nutmeg-signed` | `work/spark-signed-integers` (`2c0813c`) | Signed-integer column handling for Spark. |
| `~/src/canonical-order/nutmeg` | `work/canonical-order` (`1492ca2`, 2026-09-21) | Astra's canonical-order staging experiment; relevant to S2. |
| `~/src/bounded-staging/nutmeg` | `work/bounded-staging` (`5220db1`, 2026-09-21) | Astra's bounded-memory staging experiment; relevant to S1/S2. Both experiment directories also link `grust` to a Claude worktree at `fd4e3ec`. |
| `~/src/grust` | `work/proposal-v5` | Evidence and book material; `target/` and `benchmarks/lsqb/target` removed 2026-09-28. |
| `~/src/grust-narrow-u32`, `grust-pagerank-f32`, `grust-fastrp-f64`, `grust-pagerank-fused` | see the Grust rows above | Kernel experiment worktrees; their `target/` caches removed 2026-09-28. |
| `~/src/grust-binding-forms`, `grust-arrow-null`, `grust-benchmark-krill`, `grust-benchmark-helix-sdk3`, `grust-release-krill`, `grust-arrow-pipeline` (+ `grust-arrow-buffer-owner`, `grust-lancedb-cancellation`), `grust-acorn-*`, `grust-copepod-delivery`, `grust-gooseneck-delivery` | various | Earlier Grust release and backend worktrees, not Graph Nuts; listed so nobody rebuilds into them by accident. `grust-binding-forms/target` (27 GB) removed 2026-09-28. |
| `~/src/grustframes` | `agent/sail-triplet-integration` | `target/` removed 2026-09-28. |
| `~/src/sedona-db-extension-poc` | `work/sail-extension-poc` | The Sedona extension, 5 dirty files. |

### Benchmarks, site, references

`~/src/adversarial-graph` (36 GB, evidence), `~/src/adversarial-graph-algorithms`
with worktrees `aga-b6` (`work/bench-b6`) and `aga-b7`
(`work/simple-rust-algo-bench-b9`), `~/src/adversarial-site` (14 dirty files),
`~/src/adversarial-site-large-campaign`, `~/src/graph-book`,
`~/src/querygraph` (32 GB), `~/src/sail-traversal-controls` (plain: `gapbs`,
`graph500`, `parallel-sssp` upstream checkouts), `~/src/cargraph` (plain),
`~/src/target` (Sail's runtime scratch: `global-logging`, `task-temp-directory`,
empty). The graphframes-rs CLI built on 2026-09-28 at `b4da56d` lives in
the session scratchpad, not under `~/src`.

## Pull requests and branches

| Where | Ref | State | What |
|---|---|---|---|
| `querygraph/sail` | `work/extensions-datafusion-graphs` (`bd8ce9ae8`) | promoted branch | The extension host, Pecan, Nutmeg wheel, sparse campaign. `sail-extensions-poc` checks it out. The two plan commits that had landed here on 2026-09-28 were dropped by the user on 2026-09-29; the plan lives in `grust/docs`. |
| `querygraph/sail` | `sail-extensions` (`bd8ce9ae8`) | the current extensions branch | Created 2026-09-29 at the promoted head as the always-current reviewer branch: it moves with `work/extensions-datafusion-graphs` (fast-forward only) and receives the propagation pass after each verified gate. The sole review target: `REVIEW-EXTENSIONS.md` says `git clone --branch sail-extensions` and asks reviewers to cite the commit. |
| `querygraph/sail` | tag `sail-extensions-1` (`7c58aced5`, 2026-09-26) | first review's fixed point (history) | The commit Sem was given (`git clone --branch sail-extensions-1`); kept so his comments stay placeable. Since 2026-09-29 reviews use the `sail-extensions` branch only (`REVIEW-EXTENSIONS.md`); no new tags unless a review needs a frozen point. The promoted branch is 18 commits past it (the benchmark tutorial, fused WCC plans, two-host task capacity, 21 changed lines of the design review). |
| `querygraph/sail` | `work/extensions-traversal-bench` (`b87fb27ac`) | active branch | Argentea, traversal benchmark, Graph500 preparation, the large campaign. `sail-large-graphs` checks it out, 76 behind as of 2026-09-28. |
| `querygraph/sail` | PR 30 `graphframes-rs-like` (`b772a112c8`) | open, do-not-merge | Sem's pure-PySpark Pregel and benchmark results; base is `work/extensions-datafusion-graphs`. |
| `querygraph/sail` | `work/s0-tiered-accounting` (`7f00735ad`) | pushed | S0: tiered accounting, the SNAP importer (`snap-edge-list`), and the certificate policy for PageRank/WCC on inputs without reference vectors (see `grust/docs/proposals/s0-tiered-accounting/`). |
| `querygraph/sail` | `work/declared-layout` (`17f8461f1`) | pushed | The `checkpointed` relation and `checkpoint` writer (driver and distributed modes), `nutmeg_bucket` from a functions-only entry point, Pecan's declared layout, and the host wrapper restating a native relation's declared layout with host columns (first upstream PR candidate). Read side verified; write side measured slow on Sail, see `GRAPHFRAMES-RS-PARITY.md` §14. |
| `querygraph/sail` | `work/s2-stage-order` (`80a750067`, on `work/s0-tiered-accounting`) | pushed | The Spark client chooses the staging order: `Request.order`, `Nutmeg.stage(order=)`, `graph_cell.py --stage-order`, suite-level `stage_order`; `asStaged` skips the canonical sort the scale-25 refusal named. 48 extension and 196 harness tests pass. Reviewable copy: `grust/docs/proposals/s2-stage-order/`. |
| `querygraph/sail` | `work/grpc-client-decode-limit` (`9dc75bee8`, on `b87fb27ac`) | pushed; **verified**, ready for an upstream PR | One hunk in `crates/sail-execution/src/rpc.rs`: the internal gRPC clients decode up to `GRPC_MAX_MESSAGE_LENGTH_DEFAULT` like the servers, instead of Tonic's 4 MiB default that failed the scale-25 certificates. Verified 2026-09-29 22:55 UTC: the Grenada BFS push-pull cell at scale 25 passed its certificate on the `2557feaf1` gate where the baseline failed it. Reviewable copy and PR cover note: `grust/docs/proposals/sail-grpc-client-decode-limit/`. |
| `querygraph/sail` | `work/gn-gate-next` (`ac000b6e8`) | pushed integration branch | The two branches above merged; `work/s0-source-degree` continues it and is what the gate build uses. |
| `querygraph/sail` | `work/s0-source-degree` (`c00a36434`, on `work/gn-gate-next`) | pushed | Harness: `--source max-degree` in the Graph500 and SNAP fixtures (degrees counted as chunks stream; lowest id among ties), `source_degree`/`zero_degree_vertices` in every manifest, `"source": "max-degree"` in matrices, `graph_cell.py` resolves it from the manifest and records request, degree and policy; summaries carry `reached`; the policy lives in a stdlib-only `traversal_source.py` so the host-side runner imports without numpy. 200 harness tests pass. `work/s0-argentea-engine` continues it. |
| `querygraph/sail` | `work/s0-argentea-engine` (`63eaeb5fe`, on `work/s0-source-degree`) | pushed; smoke passed | Harness: `--engine argentea` for bfs (reference/frontier/direction) and sssp (reference/delta_star) cells through `ArgenteaBfs`/`ArgenteaSssp`, the server exporting `SAIL_ARGENTEA_MEMORY_BYTES` = the native quota, `--argentea-max-rounds` (phase budget 2·cap+4), never a default engine. 201 harness tests pass. Capitola smoke on a 2000-vertex, 16,665-edge directed fixture in process-cluster mode (arm64 host and wheel from `17f8461f1`): all five methods passed with reference validation, about 7 s each, reached 1999 of 2000; BFS 7 levels, SSSP 22 and 35 rounds; the unrolled plan runs every capped phase (128 with the default cap), so the matrices cap at 30. `work/s5-iteration-plans` continues it. |
| `querygraph/sail` | `work/s5-iteration-plans` (`edcf86824`, on `work/s0-argentea-engine`) | pushed; smoke passed | Pecan `GraphAlgorithms(record_plans=)` attaches the physical plan of the frame each iteration materializes to its `iteration_start` event (reference/frontier, push-pull, delta-star); harness `--record-plans`. Capitola smoke: three Pecan cells with a plan in every iteration. `work/h2-keepalive-timeout` continues it. |
| `querygraph/sail` | `work/h2-keepalive-timeout` (`1f762aa64`, on `work/s5-iteration-plans`) | pushed; verification pending | Fork-only experiment knob: `SAIL_EXPERIMENTAL_HTTP2_KEEPALIVE_TIMEOUT_SECS` / `_INTERVAL_SECS` override the 10 s / 60 s h2 keepalive defaults of every Sail gRPC server (`sail-common/src/server/builder.rs`); the harness sets 120 s (`graph_cell.py --http2-keepalive-timeout`). Candidate cause of the six `h2 protocol error` stream losses in the capacity campaign. If the reruns stop losing streams, the upstream form is a configuration option with a longer default. `work/s0-wcc-certificate` continues it. |
| `querygraph/sail` | `work/s0-wcc-certificate` (`666c619a6`, on `work/h2-keepalive-timeout`) | pushed | The S0 ranking certificate requires a WCC label to name a member of its component instead of the numeric minimum (Banda's min-label kernel uses canonical Utf8 order), reporting `non_minimal_labels` and the convention. Found by the cit-Patents ranking matrix. `work/gate-core-tests` continues it. |
| `querygraph/sail` | `work/gate-core-tests` (`2557feaf1`, on `work/s0-wcc-certificate`) | pushed | One-line fix in the vendored `nutmeg-graph` test (`graph_tables/tests.rs`: `finish()` returns a `StageReport`, read `.info.staged_nodes`) that the first gate build found; nutmeg-graph 85 tests and clippy clean, extension tests and controlled clippy pass on Capitola. The gate built from it (`2557feaf1`) runs the 42-cell matrix; `work/s5-frontier-build-side` continues it. |
| `querygraph/sail` | `work/s5-frontier-build-side` (`ffcfbd569`, on `work/gate-core-tests`) | pushed; gate 3 queued | Pecan writes the frontier (or the unvisited set) as the left input of every expansion join, so the partitioned hash join builds on the small side instead of the adjacency; results unchanged (inner joins commute). 47 Pecan and 202 harness tests pass; five local cells' recorded plans show the frontier as the join's first child. Verified at scale by `chain-gate3.sh`: gate 3 build plus 24 relational cells at scales 24 and 25 (`gn-relational-gate3.json`, host output `relational-gate3/`). |
| `querygraph/sail` | `work/argentea-two-host-env` (`837a8ecf5`, on `work/s5-frontier-build-side`) | pushed | `qualify.py` two-host exercises pass through `SAIL_QUALIFY_EXTRA_ENV` (a JSON map, `SAIL_*` names only, recorded in the receipt) so a distributed Argentea run can raise `SAIL_CLUSTER__TASK_STREAM_CREATION_TIMEOUT_SECS` above Sail's 60 s default; both two-host checkouts (Capitola `~/src/sail-large-graphs`, Morrobay `argentea/host-ffcfbd569`) run it. |
| `querygraph/sail` | `work/matrix-environment` (`ae3b08f4f`, on `work/argentea-two-host-env`) | pushed to the fork | `run_matrix.py` accepts an optional `environment` map (`SAIL_*` string settings only, validated at load, part of the recorded configuration and cell fingerprint) exported into every cell container; the Morrobay `harness-gate3` copy carries the same file (md5 `d6b84bed…`) and the Argentea-first matrix uses it for the 900 s task-stream timeout. It was first pushed to `origin` (lakehq/sail) by mistake; the fork push and `remote.pushDefault querygraph` are done, the stray upstream branch was deleted by the user at 02:45 UTC on 2026-09-30, so nothing of it reached lakehq/sail beyond a branch ref that lived about 20 minutes. |
| `querygraph/sail` | `work/pecan-typed` (`7145d107c`, on `work/argentea-two-host-env`) | pushed | Pecan rewritten typed throughout on Sem's review: Pydantic option models (`PageRankOptions`, `WccOptions`, `TraversalOptions`), `IterationEvent` and `ContractionStep` models for observer events and contraction rounds, `MassResidual`, a slotted `SplitMix64`; mypy and ruff clean. Input validation removed under the valid graph contract (`AGENTS.md`, "Valid Graph Assumptions"; Pecan README): no null, uniqueness, endpoint-membership, source, weight, overflow or row-count jobs; the free schema check stays. Harness observers read `event.as_dict()`. 104 Pecan tests pass against a local Sail host (the validation tests are gone with the checks), 202 harness tests pass. Component result; the integration row below supersedes its older-base source and harness compatibility status. |
| `querygraph/sail` | `work/pecan-typed-integrated` (`6ae2e43a9`, merge of `cab6bacc` and `7145d107c`) | pushed; exact-commit gate passed | Pydantic rewrite integrated with newer runtime, ownership and certificate fixes. Typed singleton traversal seed; no graph-audit jobs; unnecessary eager N omitted; module-scope imports; Argentea and harness callers updated. Candidate and exact-commit gates: strict mypy/Ruff, 1,196 offline cases and 286 endpoint-configured cases passed (183 Spark-fixture cases; 103 repeated offline checks). Exact three-round SSSP fixture: 12→0 count queries, 49→37 forwarded ExecutePlan requests. No timing, memory or scale claim. [Integration and retained gate evidence](reviews/pecan-validation-2026-10-01/README.md). |
| `querygraph/sail` | `pr-2522`, `session-factory-hook` | rescued from AWS | Tree-verified replays of the host branches (`grust/LAKESAIL-AWS-QUERYGRAPH.md` §3–4). |
| `alexy/sail` | `csv-nanos-followup` (`804f300f`) | merged upstream as lakehq/sail#2672 (2026-09-29) | Format-aware nanosecond widening for CSV schema inference; rebased onto merged #2522; the last push fixed the PyLint check (B018). james-willis's draft #2657 rewrites the same function and now has to rebase onto it. |
| `lakehq/sail` | #2630 | merged | The session factory hook: an embedder chooses the session factory. Nutmeg's only required Sail change (`nutmeg/docs/sail-prs.md`). |
| `lakehq/sail` | #2374 | merged | Delta MERGE constraints resolved by visible names. |
| `lakehq/sail` | #2400 | open | Object-store, SQL and Iceberg hot-path performance. |
| `lakehq/sail` | #2136 | closed | The earlier Sail Cypher graph query extension attempt; superseded by the extension protocol. |
| `querygraph/grust` | `work/proposal-v5` (`644e683`) | branch | The fifth revision of the Sail extension API proposal, rebuilt on the Spark Connect `Relation.extension` seam; superseded in practice by the PoC's `design-review.md` and `maintainer-request.md`. |
| `querygraph/grust` | `main` (`215cdf4` HANDOFF) | default | Grust 0.23.0 release state and handoff. |
| `querygraph/nutmeg` | `main` (`f267b03`), tag `v0.1.0` at `58a120e` | released | Nutmeg 0.1.0; pins Sail `f1cf1729b` and Grust `6504c0c`. Not on crates.io because Sail does not publish. |

## Branch and evidence discipline

Each experiment names its repository, branch and source commit. Temporary
worktrees are not evidence. A result is publishable only when the tested commit
matches the named commit, the fixture reaches the intended execution path, and
all outcomes are retained. Timing is reported with host, memory envelope,
steal, command and result boundaries. No benchmark text should describe a
system as a winner; it should state the measured conditions and limitations.

## Current document register

These are the current documents that define the design, implementation,
validation and scaling work. Paths are relative to the named repository.

### Sail extension design and implementation

- `grust/docs/REVIEW-EXTENSIONS.md` — the current reviewer instructions for the
  Sail extensions: which ref to clone (`sail-extensions` branch for the latest,
  `sail-extensions-1` tag for the fixed first review), what to read and run,
  what is on the branch and what is still to be propagated. Kept current with
  every move of the review target, in the same commit.

- `sail-extensions-poc/docs/development/extensions/design-review.md` —
  standalone extension architecture review.
- `sail-extensions-poc/docs/development/extensions/design-review.pdf` — PDF
  rendering of that review.
- `sail-extensions-poc/docs/development/extensions/implementation-plan.md` —
  implementation plan and work breakdown.
- `sail-extensions-poc/docs/development/extensions/implementation-review.md` —
  implementation review findings.
- `sail-extensions-poc/docs/development/extensions/implementation-review-resolution.md` —
  resolutions and qualified follow-up decisions.
- `sail-extensions-poc/docs/development/extensions/abi-review.md` — wheel and
  ABI compatibility review.
- `sail-extensions-poc/docs/development/extensions/linux-environment.md` —
  Linux, Colima, Docker and host test setup.
- `sail-extensions-poc/docs/development/extensions/maintainer-request.md` —
  focused maintainer-facing change request.

### Algorithm and DataFusion plans

- `sail-extensions-poc/docs/development/extensions/datafusion-graph-plan.md` —
  direct DataFusion execution plan for graph tables.
- `sail-extensions-poc/docs/development/extensions/portable-graph-plan.md` —
  Pecan portable graph algorithm plan.
- `sail-extensions-poc/docs/development/extensions/portable-graph-validation.md` —
  validation status for portable algorithms.
- `sail-extensions-poc/docs/development/extensions/graphframes-rs-plan.md` —
  graphframes-rs integration plan.
- `sail-extensions-poc/docs/development/extensions/graphframes-rs-plan-review.md` —
  review of that plan.
- `sail-extensions-poc/docs/development/extensions/pecan-nutmeg-benchmark.md` —
  benchmark protocol and comparison boundaries.
- `sail-extensions-poc/examples/extensions/vendor/nutmeg-graph/OPTIMIZED_ALGORITHMS.md` —
  native advanced algorithm behavior, including delta/frontier PageRank and
  randomized WCC.
- `sail-large-graphs/docs/three-kinds-of-nut-graphs.md` — the plain-language
  explanation of Pecan, Banda and Grenada.

### Argentea (on the `sail-large-graphs` remote tip)

- `docs/development/extensions/argentea-plan.md` — the distributed Banda
  plan.
- `docs/development/extensions/argentea-integration.md` — the smallest first
  Sail change, the focused host gaps, the unrolled-round design and why the
  client loop was not kept, the live integration findings, and the remaining
  gates.
- `docs/development/extensions/argentea-advanced-plan.md` — signed residual
  PageRank, its barriers and certificate, and the BFS work.
- `docs/development/extensions/argentea-remote-fault-qualification.md` —
  worker-loss and cancellation qualification across hosts.
- `docs/development/extensions/argentea-validation/README.md` — evidence
  index for every Argentea attempt, successful and failed.
- `examples/extensions/argentea/README.md`, `PYTHON.md`, `DELTA.md`,
  `BFS.md`, `WCC_ADAPTER.md`, `SSSP_ADAPTER.md`, `GRAPH_RESOURCES.md`,
  `FAULTS.md`, `coordination.md` and the `*_CORE.md` files — tutorials and
  contracts per algorithm and per concern.

### Traversal benchmark (on the `sail-large-graphs` remote tip)

- `examples/extensions/benchmarks/TRAVERSAL-PLAN.md` — algorithm choices,
  acceptance gates, capacity ladder.
- `examples/extensions/benchmarks/GRAPH-KERNELS-TRAVERSAL.md` — BFS and SSSP
  on the four Graph Kernels inputs.
- `examples/extensions/benchmarks/GRAPH500.md` — streaming the pinned
  Graph500 generator into Parquet; explicitly not a Graph500 submission.
- `examples/extensions/benchmarks/TRAVERSAL-TUTORIAL.md` — running the
  traversal matrix.
- `docs/development/extensions/traversal-validation.md` — exact-output
  certificates for traversal campaigns.

### Scaling and benchmark evidence

- [`EXTENSIONS-ONE-PAGER.md`](EXTENSIONS-ONE-PAGER.md): the extension design in eight modules for a thirty-minute read, written 2026-09-30 after the upstream request for a one-pager and a few hundred lines of sample code: purpose, minimum contract, alternatives and exclusions per module; the minimum contract as a list; a three-step roadmap; five review questions. Sample code is the branch's Sedona `lib.rs`, the Nutmeg manifest and the minimal client (about 260 lines). To be copied to `docs/development/extensions/` on `sail-extensions` in the propagation pass.
- [`SEM-REVIEW-2.md`](SEM-REVIEW-2.md): Sem's second review (2026-09-30): his graphframes-rs numbers (cit-Patents WCC 4.7 s on 16 cores) against ours (Pecan 312 to 500 s in cluster mode, Banda 30 to 39 s), seven factors marked measured, source or unmeasured, and a staged speedup plan for Astra's and Sem's review: A measure on his terms (local mode, his binary on our host), B one job per round in Pecan, C cheap jobs and real memory limits in Sail, D the declared layout's write side, E the loop inside the server, F Banda ingest; targets and questions. Builds on `GRAPHFRAMES-RS-PARITY.md`.
- [`STREAM-LOSS-STATUS.md`](STREAM-LOSS-STATUS.md): the status for the review with Astra of the relational stream loss (`h2 protocol error: error reading a body from connection`): the fifteen cells, what passes, eight established facts with their evidence, the same-text failures already explained, four ranked hypotheses, three ten-minute experiments, evidence and source locations. Written 2026-09-30.
- [`WHICH-PATH.md`](WHICH-PATH.md): **the decision guide**: when to run Pecan, Banda, Grenada or Argentea, from the recorded cells of the 2026-09-29/30 campaign (short-answer table, per-path evidence, ceilings by scale, what would change the answer, what was deliberately not run). Written 2026-09-30 on the user's direction that the runs exist to answer this question; kept in step with the campaign record.
- `grust/docs/reviews/gn-capacity-2026-09-29.md` — the running record of the
  2026-09-29 capacity campaign on morrobay: inputs and sources, the two scale-25
  blockers of the baseline, the hub-source matrices, the new gate and its
  matrices, findings so far. Filled in as the chain progresses.

- `grust/docs/SCALING-NUTS.md` — current large-graph diagnosis
  and bounded-memory staging plan.
- `grust/docs/FABLE-ON-ASTRA.md` — review of all four paths
  against the retained evidence and the ordered improvement sequence S0–S6
  with a per-kernel reach table.
- `grust/docs/GRAPHFRAMES-RS-PARITY.md` — where graphframes-rs's speed
  comes from (declared co-partitioned, sorted checkpoints), what the fork
  lacks, the ordered change to reach parity and the measurement that decides
  it; the distilled upstream candidates.
- `sail-large-graphs/docs/development/extensions/pecan-nutmeg-large-benchmark.md`
  and its `pecan-nutmeg-large-benchmark/README.md` — the 180-trial Morrobay
  campaign and its evidence index.
- `sail-large-graphs/examples/extensions/benchmarks/LARGE-GRAPHS.md` —
  reproduction guide for the large Graph Kernels inputs.
- `sail-extensions-poc/docs/development/extensions/pecan-nutmeg-benchmark/README.md` —
  reproducibility entry point for the published matrix.
- `sail-extensions-poc/docs/development/extensions/pecan-nutmeg-benchmark/primary/tables.md` —
  primary reference/advanced results.
- `sail-extensions-poc/docs/development/extensions/pecan-nutmeg-benchmark/fusion/tables.md` —
  matched fusion results.
- `sail-extensions-poc/docs/development/extensions/pecan-nutmeg-benchmark/audit/main-audit.md` —
  independent primary audit.
- `sail-extensions-poc/docs/development/extensions/pecan-nutmeg-benchmark/audit/fusion-audit.md` —
  independent fusion audit.
- `sail-extensions-poc/docs/development/extensions/pecan-nutmeg-benchmark/audit/constrained-audit.md` —
  constrained-resource outcomes.
- `adversarial-site/graph/graphnuts` — published Graph Nuts page, with summary
  findings above expandable detailed matrices.

### Announcements and posts

- `grust/docs/SAIL-JEV.md` — draft blog post (2026-09-29) announcing Sail 0.7.2
  as the first query engine with Jev (TypeSafe System One) built in: the five
  SQL functions, how they run asynchronously and bounded inside the plan, and
  why in-engine inference matters; the user publishes it through the site.

### Tutorials and operational entry points

- `sail-extensions-poc/examples/extensions/TUTORIAL.md` — build and run the
  extension examples.
- `sail-extensions-poc/examples/extensions/benchmarks/TUTORIAL.md` — run local,
  worker and multi-host benchmark modes.
- `sail-extensions-poc/examples/extensions/README.md` — extension protocol and
  quick-start overview.
- `sail-extensions-poc/examples/extensions/WRITING-AN-EXTENSION.md` — minimal
  implementation examples for extension authors.
- `sail-extensions-poc/examples/extensions/sedona/README.md` and `PORTING.md` —
  Sedona-specific deployment and porting notes.
- `sail-extensions-poc/examples/extensions/nutmeg/README.md` — Nutmeg client
  and deployment notes.

### Backend-neutral Grust references

- `grust/docs/proposals/pyspark_graph_algorithms.md` — API and algorithm
  proposal for PageRank, WCC, BFS and shortest paths.
- `grust/docs/proposals/sail-extension-api.md` — extension API proposal.
- `grust/docs/proposals/sail-extension-api-astra-review.md` — review of the API
  proposal.
- `grust/docs/GENERALIZED_ALGORITHMS.md` — backend-neutral algorithm contracts.
- `grust/docs/book/chapters/algorithms-under-measurement.md` — measurement
  context for the shared algorithm surface.
- `grust/HANDOFF.md` — release and in-flight state as of 2026-09-25.
- `grust/docs/GRAPH-NUTS-HANDOFF-FABLE.md` — Astra's handoff of the Graph
  Nuts plan on 2026-09-28: finish the running Morrobay campaign untouched,
  rebuild the baseline from the traversal-bench tip, implement S0, then
  Argentea.
- `grust/GRUST-SAIL.md` and `nutmeg/docs/sail-prs.md` — the Sail changes
  Nutmeg needed and their gate.
- `grust/LAKESAIL-AWS-QUERYGRAPH.md` — what the four AWS hosts held and where
  it went.
- `grust/docs/reviews/briefing-2026-09-22.md` — the briefing that preceded
  the fifth proposal revision.
- `sail-extensions-poc/docs/development/extensions/sail-extensions-v5-opus-5.5-review.md`
  — the review that found the fifth revision proposing what the PoC had
  already built, its amendment, and the wheel question stated in full.

The register intentionally omits archived Opus drafts, superseded branch
notes, raw generated CSVs and vendored upstream Sedona documentation. Those
remain useful historical or dependency material but are not current design
authority.

### Obsolete or historical documents

Keep these until their useful conclusions have been transferred to the current
documents, then remove them in a deliberate cleanup:

- `sail-extensions-poc/docs/development/extensions/sail-extensions-v5-opus-5.5-review.md` —
  external review of an earlier design revision; historical input only.
- `sail-extensions-poc/docs/development/extensions/review-follow-up.md` —
  historical follow-up log whose resolved decisions now belong in the design
  and implementation reviews.
- `sail-extensions-poc/docs/development/extensions/graphframes-rs-plan-review.md` —
  historical review; retain while the graphframes-rs plan remains useful, then
  fold any remaining decisions into `datafusion-graph-plan.md`.
- Any document under a deleted `src/sail-extensions-*` or temporary
  `work/` checkout — branch artifact, never a source of truth.
- Generated benchmark tables, figures and raw evidence that are not referenced
  by the current manifest — retain in the evidence archive only if their
  provenance is still needed; otherwise clean them with the corresponding
  obsolete experiment.

## Immediate work queue

The ordered sequence with gates is `grust/docs/FABLE-ON-ASTRA.md` section 5; this list
maps it onto repositories.

1. **S0, in `sail-large-graphs`:** done in `work/s0-tiered-accounting` and
   running on morrobay: the baseline capacity matrix (Graph500 24 and 25) and
   then the cit-Patents ranking matrix. The Banda refusal is reproduced (see
   the morrobay row). Next on morrobay, after both matrices: build
   `work/gn-gate-next` into the gate volume (a `rebuild.py` variant with the
   new source sha) and run the scale-25 relational cells with the client
   decode limit raised, the Banda cells with `stage_order: asStaged`, then
   scale 26 and Argentea on the new wheel. Every refusal and timeout is a
   result and is kept. The harness follow-up for the isolated default source
   is done in `work/s0-source-degree` (`max-degree` policy, degrees and
   `reached` recorded); the running matrices still use the explicit hub
   vertex from `pick_sources.py`, which the fixtures now record the degree of
   only from that branch onward.
2. **S1 and S2, in `sail-large-graphs/examples/extensions/vendor/nutmeg-graph`:**
   the client-side `order` passthrough is in `work/s2-stage-order`; still to
   do: keep `Int64` identity through `normalize_*`; stage `asStaged` by
   default with a stable ordinal; sort only for kernels that declare they read
   order, through DataFusion's spilling sort; and tighten the sort-key bound
   (`admission.rs` `sort_keys_bound`: 16x the key buffers plus 128 bytes per
   row per key, about 25x the Arrow row-format size for short Utf8 ids).
   Gate: Graph500-24 stages in 24 GB.
3. **S3, in `grust` on a new `work/` branch beside `work/narrow-targets`:**
   an `Int64` entry to `GraphProjection` with a dense `u32` remap and no
   per-edge record unless requested. Gate: projection below 16 bytes per
   edge; Graph500-24 PageRank, WCC, BFS and Dijkstra on Banda in 24 GB.
4. **S4, in `grust` then Nutmeg:** file-backed CSR. Gate: Graph500-25 on a
   16 GB pool.
5. **S5, in `sail-extensions-poc` Pecan:** first, from the 2026-09-29 campaign:
   Pecan's BFS reference and frontier variants fail in iteration 2 at scale 24
   (workers at 47 GiB each, OOM-killed at the 100 GiB container limit) while
   Grenada's push-pull passes at 25 GiB on the same adjacency; the recorded
   cluster-mode plans (2026-09-29, first rerun cell) show a `Partitioned`
   hash join built on the left input, which Pecan writes as the adjacency:
   the O(|E|) build side. `work/s5-frontier-build-side` puts the frontier on
   the left; verify with the recorded plans on the next gate
   (`docs/reviews/gn-capacity-2026-09-29.md`).
   Then: purge through a `Command.extension`
   verb now and a session temp-directory request to Sail later; a cached
   sorted edge view; mass-normalized tolerance; Sem's delta messaging as a
   third PageRank method; the four-way comparison with PR 30 on Graph500-24
   in one envelope. Ask for `AggregateUDF` in the loader.
6. **S6, in `sail-large-graphs` Argentea:** continuation across jobs through
   owner-local partition files; placement-stability measurement; the
   session-scoped native-state maintainer request in the form of
   `maintainer-request.md`.
7. **Parity thread, next:** report Sail's `partitionBy` write cost upstream
   with `partitionby_probe.py`; profile the FFI batch crossing in the
   driver checkpoint writer; rerun the shuffle-versus-declared comparison
   on morrobay with process workers once the campaign ends; then the
   four-way Graph500-24 measurement (`GRAPHFRAMES-RS-PARITY.md` §4 item 6).
8. Keep `sail-extensions-poc` as the promoted implementation branch and
   update the Graph Nuts page and its evidence manifest after each qualified
   campaign. **Propagation pass after the `63eaeb5fe` gate verifies:** the
   2026-09-29 branches (`work/s2-stage-order`, `work/grpc-client-decode-limit`,
   `work/s0-source-degree`, `work/s0-argentea-engine`) live on the
   traversal-bench line, which has diverged from `work/extensions-datafusion-graphs`
   (83 versus 2 commits apart, neither an ancestor). Cherry-pick them onto the
   promoted branch and, in the same commits, update `design-review.md` (client
   staging order and the sort-key bound under Nutmeg; the gRPC client decode
   limit as a host fix under evidence), `examples/extensions/TUTORIAL.md` step 7
   (`order="asStaged"`) and `benchmarks/TUTORIAL.md` (the `argentea` engine and
   the `max-degree` source; the combination count). Nothing in those documents
   was changed on 2026-09-29.
9. Keep this file current: every new repository, branch, document, pull
   request or host that touches graph work gets a row here in the same
   commit that creates it. Keep `REVIEW-EXTENSIONS.md` current the same way:
   any move of `sail-extensions`, any new review tag, and the propagation pass
   update it in the same commit.
