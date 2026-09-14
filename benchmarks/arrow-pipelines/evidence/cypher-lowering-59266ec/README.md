# Initial Cypher lowering qualification

Clean source `59266ec`, Capitola, DataFusion 55.1.0. The focused all-feature
`grust-datafusion` suite passed 18 tests with zero failures/ignored tests;
all-targets Clippy passed with warnings denied. Raw logs retain the earlier
missing-trait build failure and reserved-keyword test-alias failure separately.
The integer-ordering regression passed at `cd5b8e8`; broader Cypher qualification
is still required after the shared helper and precision changes.

This is correctness evidence for an explicit typed node-scan lowering API.
There is no automatic routing or speedup claim. The tests cover scalar/null
predicates, native/reference fixtures, count aggregation, grouping, parameter
binding, ordering/pagination, implicit names and inline property maps. They do
not prove all Cypher expressions, graph joins, caller policy enforcement or
backend execution equivalence. These changes are not yet released.
