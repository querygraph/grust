# A2 source contracts before execution

This review compares Pecan `f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a`
with graphframes-rs `b4da56dabe20bba8e29563e06acc5179b2113ce3`.
The governing Grust revision read was
`c4ca01d3356460e350c200c1b997b0f76154dfcd`, including `AGENTS.md` and
`SEM-REVIEW-2.md` sections 8–9. Both inspected source checkouts were clean.
Observed UTC, complete tracked Git blob inventories, audited file SHA-256s,
the complete Pecan Python package inventory, equations, and scalar witnesses
are retained in [source-contract-audit.json](source-contract-audit.json).

The findings below are **source inferences and scalar arithmetic**, not
observations of these algorithms executing on the retained runtime. No engine,
container, build, benchmark, or graph-data scan was run for this review. A1
qualified the external build and CLI help; the previous A0 suite qualified
Pecan `6ae2e43a9`, not this new controller revision.

## PageRank: comparison deferred pending B11

The external CLI accepts a positive fixed iteration count. It keeps its
source participation filter `new_delta > tol` even then; the cap disables
early stopping by voting, not message pruning. Its default library threshold
is `0.01`; the CLI requires an explicit `--tol`.
[CLI arguments](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/src/main.rs#L160-L172),
[filter and cap](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/src/algorithm/centrality/pagerank.rs#L172-L207).

Setting `--tol 0` is accepted by the source, but still does not align the
finite iteration contract. Let `a` be reset probability, `d=1-a`, `N` the
vertex count, `1` the all-ones vector, and `P` the incoming transition operator
using out-degree, with zero columns for sinks and parallel edges counted
separately. Neither of the following methods redistributes dangling mass.

Pecan `method="pregel"` starts with `r_0=1/N` and executes
`r_(k+1)=(a/N)1+d P r_k`. Thus, after `K` steps:

```text
r_K = (a/N) sum(j=0..K-1) d^j P^j 1 + (d^K/N) P^K 1
```

Normalization is optional and defaults to false.
[Pecan initialization and update](https://github.com/querygraph/sail/blob/f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a/examples/extensions/graph-algorithms/src/pyspark_pecan/algorithms.py#L253-L289).

Graphframes uniformly seeds both rank and delta with `a`. At zero threshold,
its delta accumulation after `K` steps is:

```text
q_0 = a 1; delta_0 = a 1
delta_(k+1) = d P delta_k
q_(k+1) = q_k + delta_(k+1)
q_K = a sum(j=0..K) d^j P^j 1
```

It always divides the final ranks by their sum. The different coefficient of
the last term is not removed by final normalization.
[Graphframes initialization and vertex program](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/src/algorithm/centrality/pagerank.rs#L145-L188),
[normalization](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/src/algorithm/centrality/pagerank.rs#L210-L225).

A two-vertex directed graph `1 -> 2`, with `a=0.15`, `K=1`, and final
normalization on both sides, gives:

| Vertex | Pecan static Pregel | Graphframes zero-threshold delta |
|---|---:|---:|
| 1 | 0.1304347826 | 0.3508771930 |
| 2 | 0.8695652174 | 0.6491228070 |

These values were computed with scalar arithmetic, not measured from an
engine. The existing Pecan `power` method has LDBC dangling redistribution;
its `delta` method has uniform dangling redistribution, residual thresholds,
and a global certificate. Neither supplies the external thresholded delta
contract. Record **PageRank not comparable pending B11**. A fixed cap,
normalization, or a larger cap alone does not establish a shared contract.

## WCC: methods, coverage, and a signed-ID defect

Use explicit `canonical_labels=True` for the intended canonical comparison.
Pecan `min_label` propagates minimum original signed IDs to a fixed point and
always returns those labels. Its `canonical_labels=False` argument does not
change that path. Randomized WCC takes signed `MIN`/`least` of affine GF(2^64)
hashes, contracts edges, keeps forward history, and performs a reverse join
per earlier round. It then joins every declared vertex and, by default,
aggregates minimum original IDs per raw component. `randomized_fused` is an
alias of this implementation.
[Dispatch and min-label](https://github.com/querygraph/sail/blob/f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a/examples/extensions/graph-algorithms/src/pyspark_pecan/algorithms.py#L291-L343),
[representatives and unwind](https://github.com/querygraph/sail/blob/f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a/examples/extensions/graph-algorithms/src/pyspark_pecan/wcc_randomized.py#L100-L136),
[execution and final labeling](https://github.com/querygraph/sail/blob/f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a/examples/extensions/graph-algorithms/src/pyspark_pecan/wcc_randomized.py#L146-L212).

Graphframes uses the same signed minimum and affine field operations, and its
CLI keeps the builder default of canonical minimum original labels. The two
coefficient streams differ: Pecan uses explicit SplitMix64; graphframes uses
`rand::rngs::StdRng`. Seed 42 does not imply identical coefficients, traces,
or contraction counts.
[Graphframes representatives](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/src/algorithm/connectivity/connected_components.rs#L42-L67),
[seed and back pass](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/src/algorithm/connectivity/connected_components.rs#L247-L327),
[canonical labeling](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/src/algorithm/connectivity/connected_components.rs#L330-L384).

**B9 has a source-inferred namespace collision for a valid graph.** With
Pecan seed 42, the first coefficients are
`a=-4767286540954276203`, `b=2949826092126892291` and:

```text
f(1) = -7694170072594669674
f(2) =  5999225162152553522
z = f(1)
vertices = [1, 2, z]; edges = [(1, 2)]
expected canonical components = {1: 1, 2: 1, z: z}
source-predicted raw labels   = {1: z, 2: z, z: z}
source-predicted canonical    = {1: z, 2: z, z: z}
```

The connected pair contracts in one round to hashed label `z`; the isolated
vertex also gets `z` because the final left join coalesces a missing hashed
label to the original ID. Canonicalization then merges them. This affects
both randomized names and both canonical settings. `min_label` does not use
this hashed namespace. Graphframes has the same namespace pattern, although
its different coefficient stream means this particular seed-42 witness is
specific to Pecan.

The known cit-Patents admission records zero isolates. That dataset can still
receive a dataset-specific verdict through every cell's full independent
membership oracle. It cannot qualify generic signed-ID randomized WCC.
Run and retain the tiny witness before timing; preserve any mismatch as its
own outcome and do not patch algorithms through the comparison harness.

Require exactly one non-null `id: int64, component: int64` row per declared
vertex, no duplicates or missing/extra IDs, exact partition membership, and
exact minimum original IDs when canonical mode is selected. Arbitrary hashed
labels need partition equivalence, including rejection of false merges and
false splits; comparing only the number of components is insufficient.

## Native/runtime requirements and helper risks

The server graph-utils implementation and protobuf source are byte-identical
between Pecan `f3b3ef8fc` and the retained runtime source
`56194b170155301ba91077f0ba3df31fe2c78b6b`. This supports reusing that runtime
as a source inference; it does not replace an actual compatibility gate with
the new controller. `gf_axpb` uses three BIGINT arguments and returns BIGINT
bit patterns with reduction constant `0x1b`.
[Native scalar](https://github.com/querygraph/sail/blob/f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a/crates/sail-session/src/extensions/graph_utils/functions.rs#L9-L79).

Before execution, pin the complete new Python package, the actual runtime
binary, native wheel, image, helper bytes, and input/oracle hashes. Require
protocol 1, `fs`, `owned_runs_v1`, and `axpb`; verify `gf_axpb` signed-extreme
vectors on every worker execution path. Required package dependencies are
PySpark Connect 4.0.1, protobuf `>=7.36.1,<8`, and Pydantic `>=2.11,<3`.

New randomized WCC no longer needs `min_by` or a separate fused kernel. The
Pecan README's remaining fused-plan/min-by sentence is stale relative to
the inspected implementation. Do not copy that requirement into admission.
`min_label` does not populate `GraphResult.method`, seed, or contractions;
record the requested method separately. Randomized contraction records set
`active_vertices=0` as a placeholder, not an observed active-vertex count.

Both engines assume graph validity and freely check schema; do explicit
input validation in its own phase, bound to immutable bytes. Pecan still
snapshots inputs in its public call: B7 is open. Include and disclose that
cost in the selected timing boundary. Keep result validation after certain
child exit, and reject incomplete lifecycle closure before any timing ratio.

## BFS: proposed independent full-hop oracle

The prepared source `750000` was selected historically as 25% of a rounded catalog count;
it is not a verified vertex percentile. Membership was not checked during
this review. Admit it in the explicit input phase only if it appears exactly
once among the declared vertices; preserve a missing-source outcome.

Use original directed edge bytes, without symmetrizing or reversing. Pecan
uses `directed=True`; external shortest paths use `--landmarks 750000`
without `--to-landmarks`. Graphframes ignores weights for this algorithm.
Its output is `id: int64, dist_750000: int32`, with unreachable value
`2147483647`. Pecan emits distance/hops/parent and uses null for unreachable.
Compare hops only across engines, preserving the raw schemas and values.
[External initialization, direction, and messages](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/src/algorithm/connectivity/shortest_paths.rs#L95-L183),
[Pecan traversal contract](https://github.com/querygraph/sail/blob/f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a/examples/extensions/graph-algorithms/src/pyspark_pecan/algorithms.py#L345-L360).

Construct an independent array-based outgoing CSR over the complete sorted
declared ID set, then queue BFS from the admitted source until the queue is
empty. Preserve duplicate edges/self-loops in the input identity; they do not
change shortest hops. Persist the complete sorted oracle as Parquet
`id: int64, hops: nullable int64`, with a JSON manifest containing input
hashes, source, direction, row/reachable/unreachable counts, maximum hop,
level histogram, generator source hash, and oracle SHA-256. This is a
proposal; no BFS oracle was generated in this review.

Compare every vertex exactly, translating external INT32_MAX and Pecan null
only in the comparison adapter. Independently check source hop zero, the
shortest-path edge inequality, and a predecessor at hop minus one for each
reached non-source vertex. A separate Pecan parent check must require an
actual parent-to-child edge and hop increment; external output has no parent
to compare. An external finite cap can return partial output successfully;
only the complete oracle establishes full traversal. Pecan's cap includes
its final no-change certificate round.

Input SHA-256s below are inherited from the retained admission, not rehashed
by this source review:

| Artifact | SHA-256 |
|---|---|
| cit-Patents-v.parquet | `0969ea9ede0969e18e76a2c70191ed7ccecaecb9f1da6d954093dbefbc8958aa` |
| cit-Patents-e.parquet | `70bcba17b5a7762ef5a0c3d16c1dc37a352461b83e338f550ae897d844f0268f` |
| wcc-membership.i64le | `b07f8665c87f94286da7beb1ac5a9d13c4932fea31d8f1a382f9ecb1d3c0c8dc` |

## Actual preflight observations

Recorded 2026-10-01T22:42:56.310239+00:00. The prepared source 750000 was absent and the input
phase refused it. A pre-timing rule (maximum outgoing edge-row count, ties
by minimum raw ID) selected 5795784, with 770 outgoing rows. The independent
reference phase passed: 126298 reachable vertices, maximum hop count 13,
and zero isolates in the full 3774768-vertex domain. Both engines use the
same chosen source. The source proposal is preserved in plan-initial.json.

The release CLI’s actual tiny BFS Parquet schema was dist_1: int32 then
id: int64. All ten rows matched the official reference; the first
compatibility oracle had incorrectly required id first. The corrected
adapter requires exactly the two unique named columns and their exact types,
reads by name, and records the physical order without rewriting output.
WCC controls passed for graphframes and both Pecan methods before that
adapter stopped the sequence. Timed cells had not launched.

See preflight-evidence-index.json and preflight-evidence.tar.gz for the
closed attempts and unchanged raw tiny outputs.
