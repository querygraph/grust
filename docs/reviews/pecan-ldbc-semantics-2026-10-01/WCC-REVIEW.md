# WCC representative selection and canonical labels

Read-only source review, 2026-10-01. Controller: `6ae2e43a903c2cee02da170465c922c72b76198e`; existing runtime: `56194b170155301ba91077f0ba3df31fe2c78b6b`. No source, frozen helper or runtime was changed, and no probe or benchmark was launched for this review.

## What `min_by` selects

[Pecan wcc_fused.py](https://github.com/querygraph/sail/blob/6ae2e43a903c2cee02da170465c922c72b76198e/examples/extensions/graph-algorithms/src/pyspark_pecan/wcc_fused.py#L20) projects forward and reverse neighbors, groups by vertex, and computes:

```text
min_by(neighbor, priority), min(priority)
```

Priority is the signed BIGINT representation of `gf_axpb(a, neighbor, b)`. A nonzero GF coefficient makes that transformation bijective, so equal priorities identify the same neighbor. The result is compared with the vertex's own priority to select its closed-neighborhood representative.

This operation runs during contraction and recovers the original neighbor ID associated with the minimum randomized priority. It is separate from minimum original component labeling. [wcc_randomized.py](https://github.com/querygraph/sail/blob/6ae2e43a903c2cee02da170465c922c72b76198e/examples/extensions/graph-algorithms/src/pyspark_pecan/wcc_randomized.py#L147) does canonical labeling only after reverse expansion: materialize `(id, component)`, group by component to compute `min(id)`, join those minima back, and materialize the result.

The current public contract promises canonical minimum IDs. Official LDBC WCC validation accepts partition equivalence, so an explicit arbitrary-label option could omit that final aggregate/join while preserving the existing default. That change would not remove the contraction-round `min_by`.

## Exact runtime route and accumulator state

Runtime 561's [registry](https://github.com/querygraph/sail/blob/56194b170155301ba91077f0ba3df31fe2c78b6b/crates/sail-plan/src/function/aggregate.rs#L320) selects Sail `MinByFunction`. Its [simplify hook](https://github.com/querygraph/sail/blob/56194b170155301ba91077f0ba3df31fe2c78b6b/crates/sail-function/src/aggregate/max_min_by.rs#L263) rewrites the expression to ordered LAST_VALUE with descending, nulls-first priority and a non-null-priority filter. The generic fallback accumulator itself retains just a winning value and ordering scalar; it is not an array of every neighbor.

For the rewritten Int64 expression, [DataFusion 55.1 grouped support](https://github.com/apache/datafusion/blob/55.1.0/datafusion/functions-aggregate/src/first_last.rs#L199), [factory](https://github.com/apache/datafusion/blob/55.1.0/datafusion/functions-aggregate/src/first_last.rs#L79) and [LAST_VALUE delegation](https://github.com/apache/datafusion/blob/55.1.0/datafusion/functions-aggregate/src/first_last.rs#L1143) select `FirstLastGroupsAccumulator<PrimitiveValueState<Int64Type>>`. State holds one typed winning value per group, one ordering scalar in a small per-group vector, validity/seen bitmaps and scratch storage. Its [growth](https://github.com/apache/datafusion/blob/55.1.0/datafusion/functions-aggregate/src/first_last.rs#L478) creates a small allocation per new group; its [batch processing](https://github.com/apache/datafusion/blob/55.1.0/datafusion/functions-aggregate/src/first_last.rs#L552) also inspects resident groups. Bounded state per group can therefore still be expensive at high cardinality. It does not grow with every edge belonging to that group.

The compact `min(struct(DOUBLE, BIGINT, BIGINT))` patch does not optimize this ordered LAST_VALUE or its companion ordinary BIGINT MIN.

### Existing evidence and its limits

- [min-by-probe/README.md](../sail-stream-experiments-2026-09-30/min-by-probe/README.md), [source receipt](../sail-stream-experiments-2026-09-30/min-by-probe/source-receipt.json) and [allocation receipt](../sail-stream-experiments-2026-09-30/min-by-probe/allocation-receipt.json): component probe on Sail source `b569e75de625885b3d919fa4196b2e0bed14c618`, DataFusion 55.1.0 and Arrow 59.3.0. At 100,000 groups, first retained requested bytes were 11,692,032. This excludes grouping/hash state, the companion MIN and surrounding operators; it is not WCC RSS or peak memory. Prefix-emission allocation findings apply only if that path executes.
- [wcc-fused-worker-plan/README.md](../sail-stream-experiments-2026-09-30/wcc-fused-worker-plan/README.md) and [actual audit](../sail-stream-experiments-2026-09-30/wcc-fused-worker-plan/actual-control-audit.json): earlier controller `3a9028057c6c6c5034492845926fc4bc18f9626f`, runtime `2894a962076d3cc404dd72ec736ebeb9239901f6`. Actual worker task logs show ordered LAST_VALUE in both **Partial** and **FinalPartitioned** aggregates, with matching successful task identities on both workers. The hypothesis that this controlled expression had no partial aggregate is contradicted by those receipts.
- Runtime 561 was checked during this review: `Cargo.lock` SHA-256 `46121478d56b0d911d4f295f428b2816bd4a976d22265994afc2a5378bb00546`; `max_min_by.rs` SHA-256 `9ba14aacf6f76afcb4806c6f4d5255d0ce8a0196cc9321c8d2d98b93a4dfd325`. Both match the earlier actual control's source bridge exactly. The lock uses the same registry DataFusion aggregate/common 55.1.0 and Arrow 59.3.0 dependencies, with no active Cargo patch override.

This establishes the exact source bridge. Today's runtime 561 timing cells used warning logs and did not capture Explain/task plans. Their precise aggregate modes, live group counts, spills and memory contribution remain unmeasured here.

## What the paper preserves

Primary paper: Bögeholz, Brand and Todor, **In-database connected component analysis**, ICDE 2020, [official PDF](https://conferences.computer.org/icde/2020/pdfs/ICDE2020-5acyuqhpJ6L9P042wmjY1p/290300b525/290300b525.pdf), also [arXiv 1802.09478v2](https://arxiv.org/pdf/1802.09478v2).

Section V-C, PDF page 4 / printed 1528, explains affine invertibility. Section V-D and **Figure 4, PDF page 5 / printed 1529**, replace arg-min by plain MIN over transformed IDs, retain each representative table `R_i`, and compose those tables in reverse with left joins. Coefficient composition supplies labels for vertices that disappeared from later edge tables. Affine inverses recover IDs from priorities; they do not invert a many-to-one contraction and therefore do not eliminate its vertex-to-representative mappings.

[Sem's pinned forward selector](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/src/algorithm/connectivity/connected_components.rs#L50) uses plain MIN over GF-transformed IDs. Its [forward/backward execution](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/src/algorithm/connectivity/connected_components.rs#L247) still saves representative tables and affine coefficients, then left joins those maps backward. Its optional canonical labeling is a final aggregate/join.

Pecan similarly retains contraction maps and expands them backward, but representatives stay in original-ID space. Its source documents that property as avoiding mixed round-hash and isolated-ID spaces. The historical reason for choosing it, or for not decoding an affine inverse after MIN, is not established by this review. The operator has requested Astra's account; no reply is assumed here.

## Minimal experimental variant

Use plain BIGINT MIN while keeping the existing original-ID representation and coefficient stream:

```text
h(x) = a*x + b in GF(2^64), a != 0
chosen = min(h(vertex), min(h(neighbor))) using existing signed BIGINT order
representative = h_inverse(chosen)
```

This should recover exactly the current representative, not merely an equivalent component partition. It removes ordered LAST_VALUE and leaves a single BIGINT MIN, while preserving contraction maps, backward expansion, isolate behavior and the default final canonical-label contract.

[Runtime 561 GF implementation](https://github.com/querygraph/sail/blob/56194b170155301ba91077f0ba3df31fe2c78b6b/crates/sail-session/src/extensions/graph_utils/functions.rs#L9) uses carry-less multiplication modulo `x^64+x^4+x^3+x+1`; addition is XOR. Compute `a_inverse` once per round using that exact bit arithmetic. Decode each chosen priority with `gf_axpb(a_inverse, chosen, multiply(a_inverse,b))`, converting coefficient bit patterns to signed BIGINT literals without floating-point conversion. Ordering stays signed, as in the existing selector; GF arithmetic treats every signed value as its full unsigned 64-bit pattern. The runtime currently exposes `gf_axpb`, not an inverse UDF.

Verify affine round trips, exact representative equality under identical coefficients, signed extremes, duplicate/reversed edges, self-loops, disconnected components and isolates. Retain actual plans, per-stage memory/spill and full membership/canonical output before drawing an execution claim. Per-group inverse decoding adds scalar work and must be measured.

An explicit arbitrary-label output option is a separate experiment. Labels must remain globally distinct across disconnected components, including isolates; replacing original IDs with hashes in only part of the output is insufficient. Maintaining original representative IDs avoids that collision problem naturally.

## Timing observation is not attribution

The retained [comparison summary](../pecan-typed-experiments-2026-10-01/morrobay-20261001/comparison-summary.json) reports first-three-round totals of 23.5163 s and 23.6951 s for the two measured local candidate cells: mean 23.6057 s, approximately 23.6 s. These intervals include representative planning/materialization, counts, endpoint relabeling, canonical edge reduction, checkpoint work and observer operations. They do not isolate `min_by`, prove it caused that time, or attribute a first-round memory peak. Capture that stage separately before changing the explanation.
