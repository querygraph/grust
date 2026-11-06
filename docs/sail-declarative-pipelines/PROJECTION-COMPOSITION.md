# Preserve computation when projections reuse an alias

Two successive projections computing `v + 1 AS v` must add twice. Equal expression
text does not mean equal computation: each projection reads its immediate child's
output. An isolated DataFusion 55.2 projection-optimization probe turns inputs
`1, 2, 3, 4` into `2, 3, 4, 5` instead of `3, 4, 5, 6`. Direct analysis and
filter pushdown preserve the expected result; identity-projection controls pass.
The defect affects batch queries and streaming preparation.

Disabling projection optimization sacrifices column pruning. Renaming aliases
around the public rule adds scoping and metadata machinery while leaving internally
created projection pairs outside its control. Postprocessing cannot reconstruct a
discarded addition.

Recommend owning the narrowly scoped rule and private helpers inside Sail's
logical-optimizer crate. Estimated ownership is 1,142 existing production lines,
with no replacement optimizer framework. Register the same implementation in the
ordinary optimizer and streaming preparation. The existing equal-expression
shortcut is the source-derived candidate: it bypasses substitution into the child's
input. Test removing that shortcut while retaining ordinary composition.

Copy pinned DataFusion 55.2 source exactly before adapting it. Retain attribution
and comparison evidence. Preserve recursion protection explicitly; copying the
module does not inherit DataFusion's feature configuration. Its required dependency
version is already locked.

The unchanged owned copy must reproduce the stock failure. The correction must
pass the original arithmetic oracle, identity controls, qualifiers, metadata,
subqueries, column pruning and both compilation paths. Preserve volatile evaluation
counts and conditional guards; determinism alone does not authorize evaluating an
otherwise unused expression. Compare optimized plans and measured costs.

Spark 4.2.1 source confirms dependent projection composition; JVM parity was not
executed. Should Sail own this rule to correct composition while preserving its
optimizations? The controlled failure, exact ownership diff and regression checks
must settle that implementation decision before broader readiness claims.
