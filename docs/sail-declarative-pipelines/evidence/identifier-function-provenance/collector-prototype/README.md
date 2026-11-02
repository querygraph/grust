# Scalar identifier function provenance

The source unit records non-foldability that Sail can erase while lowering a
function to a literal. One scalar IDENTIFIER argument gets an optional boolean
collector in PlanResolverState. It lives outside ConfigScope, because normal
function configuration restoration must not erase a child's provenance. A small
RAII scope restores its exact parent on success, error or cancellation; ordinary
query analysis has no collector. FunctionContextInput passes an optional mutable
borrow to synchronous builders, without a new registry, dependency, atomics,
serialized plan field, provider export or output metadata.

ScalarFunctionBuilder::non_foldable records the annotation before lowering, while
preserving the existing eager require_foldable contract. Registered functions and
higher-order functions record their non-foldability without preempting argument
semantic errors. The scalar helper finishes expression analysis, checks recorded
provenance, then performs the existing constant validation/evaluation. The ordinary
DataFusion-expression check still catches volatile functions retained in the tree.

Spark TypeOf overrides foldable=true and reads its child's resolved datatype; it
is not itself a RuntimeReplaceable subclass. Earlier design prose used "runtime
replacement" as shorthand for Sail's literal lowering. The implementation discards
only builtin typeof's argument observations and restores any already-false parent.
A raw-spec volatile-descendant walk would reject valid type-only expressions.
Table and catalog constant contexts retain their existing distinct policies.

The public oracle grew from16 to18 and20 cases; initial inputs and observations
remain. The20-case baseline matched11 behaviors. The candidate matches19 behaviors
and11 complete structured metadata sets. Eight false admissions are corrected;
typeof, nested parent restoration, bound parameters, missing columns and scalar
subquery error precedence are observed independently against Spark4.2.1.

The remaining case exposes a separate generic catalog issue: with
spark.sql.functionResolution.sessionOrder=second reported by both engines, Spark
chooses builtin typeof despite a registered Python UDF of the same name, while
Sail chooses that UDF. FunctionResolution.scala documents the default builtin-first
SQL path. This unit preserves Sail's function selection and records the mismatch;
it does not implement SQL PATH or silently change function precedence. The native
UDF fixture uses a unique name to isolate foldability; the colliding typeof case
stays in the public oracle as a required failure.

Three native tests cover real catalog-backed resolution, state/parameter restoration,
and rejecting an immutable registered function without invoking it. Four independent
mutations keep the test blob unchanged: erase the builder annotation, stop suspending
typeof children, stop marking registered functions, or reset a false parent to true.
The expected failing counts are retained per control. No production concurrency
mechanism is added; this is a mutable request-local resolver state.

attempt-01 retains the Clippy collapsible-if failure. baseline-setup-failure records
the baseline runner refusing a detached checkout still at that terminal failed
candidate; it never started a server. The checkout was restored to15fd and the
baseline rerun into a fresh directory. Native/RPC results are kept separate from
those infrastructure failures. All source and CLI receipts pin an immutable commit.

Fresh validation passes100 plan +177 Connect tests, formatting/strict Clippy,
300 selected public cases,67 upstream Python executions and4 existing parameter
tests. Prior dynamic13/13, namespace3/3 and SDP helper2/2 remain matching. The wider
34-case validator improves28→29 behaviors, with11 complete metadata sets; the7-case
replacement oracle remains6/7. Complete identifier metadata, unbound positional
origins, division-by-zero classification, catalog nondeterminism, function SQL PATH,
frozen SQL parameters, generic WithRelations and full Scala acceptance remain open.
