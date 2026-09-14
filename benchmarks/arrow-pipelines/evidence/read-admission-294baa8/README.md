# Prepared read admission qualification

Source `294baa8`, Capitola, four nice Cargo jobs. Locked all-feature tests for
procedures, DataFusion, Cypher, algorithms and algorithm-procedures passed:
**980 passed, zero failed, two ignored**, across 26 result summaries.
Warnings-denied all-target Clippy passed for the same packages. Raw logs are
retained in `qualification-logs.tar.gz`, including ignored golden-regeneration
tests. This is focused integration evidence, not final workspace/release proof.

`PreparedReadRequest` binds the validated AST, immutable parameters, policy,
original deadline and any application registry generation. The existing bounded
reference executor now uses its input/output checks. New tests cover exact
parameter/graph/index/output byte boundaries, semantic rejection, deadline reuse
and retained registry ownership. Existing bounded reference/indexed and algorithm
resource tests passed. Parameter rejection precedes graph inspection.

The prepared request is not a graph-authorization or execution-budget witness.
Automatic routing, backend Arrow input admission, candidate/intermediate
accounting, end-to-end performance qualification and release delivery remain open.

The isolated facade check also passed: `cargo check --locked -p grust-graph
--no-default-features --features cypher,datafusion`. Its separate log avoids
relying on workspace feature unification for the public re-export.
