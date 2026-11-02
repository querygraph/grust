# CTE and pipeline-default configuration reference

Twelve direct public Connect observations on installed Spark4.2.1, with local
source617618396 audited separately. These refine the first input-binding phase
in [the configuration design](../../FLOW-CONFIGURATION-DESIGN.md). They are not
Sail parity results or an execution of the original Scala suites.

| Case | Observed Spark result |
| --- | --- |
| CTE shadows graph output | Foo=1 from constant CTE, rather than graph's7 |
| differently cased CTE reference | same constant result under insensitive default |
| unused CTE reading true view, main query reading false view | duplicate flow SQL conf |
| used CTE reading true view, uppercase outer column | unresolved column |
| namespace-qualified read of bare temporary output despite CTE homonym | table/view not found |
| nested CTE shadows unused outer CTE reading true view | unresolved column |
| filter subquery over true view before false child | duplicate flow SQL conf |
| union left true then right false | duplicate flow SQL conf |
| reverse union order | unresolved column before conflict checking |
| graph true default explicitly overridden false on both flows | Foo=1 |
| graph false default, view explicitly true | duplicate flow SQL conf |
| graph true default inherited identically | foo=1 |

The qualified-read case does **not** demonstrate qualified graph-view binding:
the graph output in this fixture is a bare temporary view. Its TABLE_OR_VIEW_NOT_FOUND
outcome must be kept separate from persisted view creation namespaces.

The unused-definition cases refute reference-site-only CTE traversal for this
phase. FlowAnalysis invokes CTESubstitution before graph-input substitution. For
these pure queries CTESubstitution's forceInline is false: it retains WithCTE,
whose children are cteDefs followed by the main plan. Graph-input substitution
visits those definitions, even when the main query does not reference them.
Do not infer removal of unused definitions from the FlowAnalysis inlining comment.
Later optimizer inlining/pruning is a separate phase. Recursive CTE behavior and
legacy CTE policy settings are not qualified by this packet.

`reference.py` derives from the preceding common thirteen-case harness, replaces
its cases and records graph defaults explicitly. Every case uses a separate graph
and database, explicit parquet materialization, caseSensitive=false session base,
and verifies that setting remains false afterwards. Raw streamed events, complete
errors, input definitions and returned rows are in `observations.json`; runtime
jar hashes and source pin are recorded separately. The session stops with no15002
listener. `source-audit.json` preserves pinned source excerpts for CTESubstitution,
WithCTE.children and pre-order transformDownWithSubqueries. `verify.py` validates
the exact twelve outcomes, source/harness identities and teardown. SHA256.json
covers the complete packet. No product configuration fusion is activated.
