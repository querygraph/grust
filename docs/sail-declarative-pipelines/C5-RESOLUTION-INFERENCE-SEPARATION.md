# C5: separating flow resolution from schema inference (proposal)

Status: proposal for Codex's decision (CF-0058), no Sail edit. Pinned Spark
`617618396`; Sail base `779cb136d`; Fable head `33a883091`.

## What Spark does, read from source

- `DataflowGraph.validationFailure` runs `validateSuccessfulFlowAnalysis`
  first and `inferredSchema` last (`DataflowGraph.scala:198–207`).
- During analysis a flow reads an upstream dataset through
  `FlowAnalysis.readGraphInput` → `ctx.availableInput(id).load(asStreaming)`
  (`FlowAnalysis.scala:216–240`). For a table that input is a
  `VirtualTableInput`, whose `load` returns an empty DataFrame with the
  declared schema or, failing that, `SchemaInferenceUtils.inferSchemaFromFlows`
  over the flows resolved **so far** (`elements.scala:165–201`). So Spark
  also merges upstream flow schemas during analysis; the difference from
  Sail is where a merge failure lands:
  - with a downstream reader, the merge runs inside the reader's analysis
    and the reader is a **direct** failure attributed to the reader;
  - without a reader, the table's merge runs only in `inferredSchema`, last.
- `validateSuccessfulFlowAnalysis` (`GraphValidations.scala:288–329`)
  collects every failed flow, partitions them into direct failures and
  failures caused by a failed upstream, detects cycles among the failed
  subgraph, and throws one `UnresolvedPipelineException` naming both sets;
  the per-flow causes are logged, not carried in the exception's class.

Sail today (`analysis.rs`): one loop resolves each output's flows and
immediately calls `schema::infer` (merge of the flows' schemas plus the
declared-schema check), returning the **first** error it meets, whether a
resolution error or a merge error, in declaration order. That is the
divergence fixtured in `test_schema_merge_inside_resolution_runs_in_declaration_order`.

## Smallest change that preserves downstream binding

Keep the single loop and the eager per-output merge, because downstream
flows bind to the merged schema exactly as Spark's `VirtualTableInput.load`
does. Change only what happens on failure:

1. **Record instead of return.** A resolution error that is not
   `UnresolvedRelation` becomes `direct_failures[flow] = error` and marks the
   output failed; a `schema::infer` error becomes
   `inference_failures[output] = error` and marks the output failed. The loop
   continues with the other outputs.
2. **Failed upstream propagates as pending.** A flow whose read hits a failed
   output stays `UnresolvedRelation` → pending, as now. When a pass makes no
   progress, the pending outputs are classified: if a pending output reads a
   failed or pending output it is a **downstream failure**; otherwise the
   existing cycle detection runs (`topology::order`) and
   `PIPELINE_CIRCULAR_DEPENDENCY` stays as it is.
3. **Report in Spark's order.** After the loop:
   - if `direct_failures` is non-empty: raise the **first direct failure in
     declaration order** with its own condition and parameters unchanged
     (so `TABLE_OR_VIEW_NOT_FOUND` for an undefined dataset keeps its
     identity, which the existing Sail and upstream Python tests assert),
     and append to its message the two sorted lists Spark prints, "Flows
     with errors" and "Flows that failed due to upstream errors";
   - else if `inference_failures` is non-empty: raise the first one
     (`UNABLE_TO_INFER_PIPELINE_TABLE_SCHEMA` or
     `USER_SPECIFIED_AND_INFERRED_SCHEMA_NOT_COMPATIBLE`), likewise with the
     downstream list appended;
   - else continue to the post-resolution validations exactly as in
     `769914891`.

Effect on the fixtured divergence: with the merge output declared first and
the unresolved-source output second, Sail now records the merge failure,
keeps going, records the unresolved source as a direct failure, and reports
the unresolved source, as Spark does. The fixture becomes a reference-aligned
regression in both orders; until the change lands it stays as evidence.

What this does **not** change: `PlanResolver`, `GraphScope`, the session, the
error conditions of any individual failure, the post-resolution phase order,
or the cycle error. It touches `analysis.rs` only (about forty lines) plus
tests.

## Collection versus first error, stated explicitly

Spark raises one exception that names every failed flow; Sail will keep the
first direct failure as the error identity and name the rest in the message.
Reasons: Spark's `UnresolvedPipelineException` has no error class of its own,
so there is no condition to match; the pinned upstream Python tests and
Sail's own tests assert the specific underlying condition of the failing
flow; and wrapping would weaken those expected errors. The collected lists
are evidence, not identity. If Codex prefers a structured
`UNRESOLVED_PIPELINE`-style wrapper, that is a separate decision that
changes expected errors and must be taken against the pinned suites.

One attribution difference remains and is recorded rather than hidden: a
merge failure of output A that has a downstream reader B is, in Spark, a
direct failure of B (the merge runs inside B's analysis); in this proposal it
is an inference failure of A with B listed downstream. Both report after any
independent direct failure, and both name A and B; only the primary
attribution differs. A reference fixture (A with incompatible flows, B
reading A, C with an undefined source) will assert the reported identity in
both orders.

## Tests to add with the implementation

- the existing fixture, now asserting the unresolved source in both orders;
- A incompatible + B reads A + C undefined, both orders: C's condition first;
- A incompatible + B reads A, no other failure: inference failure named,
  B listed downstream;
- two independent undefined sources: the first in declaration order is the
  identity, both named;
- a cycle plus an undefined source: the undefined source first (Spark checks
  cycles only within the failed subgraph);
- the post-resolution phases unchanged when nothing fails.
