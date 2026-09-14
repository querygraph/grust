# Automatic Cypher execution with DataFusion 55

Status: active implementation goal, explicitly requested 2026-09-14. This extends the active
[performance and compatibility goal](arrow-performance-parity.md). Isopod 0.17.0 provides explicit SQL and typed Cypher execution over Arrow;
it does not yet select DataFusion automatically for ordinary Cypher queries.

## Goal and completion evidence

Deliver a fast, automatic Cypher-to-DataFusion 55 execution upgrade as part of
the existing broader Grust engineering goal. Preserve that goal's backend,
Arrow/ADBC, algorithm, benchmark and release obligations.

Completion requires automatic execution selection through ordinary Cypher
entrypoints, composable typed plans and native Arrow providers, preserved
language and resource-policy contracts, and measured end-to-end improvements
for the qualified workload classes. Retain efficient indexed/native/kernel
routes where they are appropriate. Publish the upgrade with full workspace,
package, documentation, book and registry verification. Neither explicit SQL
execution nor the released explicit Cypher bridge establishes completion.

Current implementation admits scalar predicates and parameters, inline property
maps, single-node scans, projection, DISTINCT, count aggregation and grouping,
projected-expression ordering, integer/string extrema, node identity and pagination
through explicit lowering APIs. `GraphSnapshot::execute` now connects Cypher
text parsing, typed planning and output-bounded portable result collection;
unsupported queries remain distinct from errors. Scalar binding resolution now supports multiple
caller-defined bindings. Parsed fixed-length relationship patterns now
share the RETURN compiler with scans.
Planner decisions distinguish unsupported shapes from semantic errors. Broader joins,
broader aggregates, route selection, resource mapping and comparative performance
qualification remain outstanding. The explicit bridge shipped in Isopod 0.17.0.

The completed [typed scan profile](../../benchmarks/arrow-pipelines/evidence/cypher-scan-771cb89)
passed all 42 oracle checks. Prepared execution improved on the larger tested
fixtures, while the indexed route was faster on the small fixture. Conversion
costs and differing admission boundaries are reported separately; these results
do not establish an automatic routing threshold.

## Integration boundaries

Reuse `grust-cypher::parser`, the public typed AST and semantic analysis. Lower
analyzed expressions into upstream DataFusion 55 logical expressions and plans;
do not generate SQL text or introduce another parser. Keep the optional bridge
above both crates so ordinary Cypher and graph kernels do not require DataFusion.
The existing indexed count plans remain eligible execution choices.

Admission returns a supported plan or a structured reason for selecting the
existing executor. Invalid Cypher remains an error. Execution errors after a
plan starts must propagate; they must not silently rerun against another
snapshot. Explain must report the chosen route, rejected alternatives and
capture/conversion requirements. Selection is automatic only for qualified
semantics and measured cost boundaries, with an explicit route override for
qualification.

## Data contract before lowering

Use native Arrow 59 providers and upstream projection/filter pushdown. Record
snapshot identity, schema and provider capabilities with the prepared plan.
Typed property columns need explicit null, missing-property, numeric-conversion
and heterogeneous-value behavior. Do not silently discard unsupported values.

The current interchange schema has optional external `edge_id`. Trail matching
requires stable physical relationship identity independent of external IDs;
providers must expose a unique snapshot-scoped relationship ordinal or decline
that plan. The released `cypher::GraphSnapshot` now supplies this ordinal for
validated native Arrow graph tables and retains an immutable provider pair.
Backend transaction/authorization identity and resource admission still need
integration. A lazy directed endpoint-join operator now retains these ordinals
and shared typed bindings. Parsed fixed-length incoming/outgoing/undirected paths and repeated nodes are
implemented; optional and variable-length patterns
remain outstanding. Parallel edges, repeated external IDs and loops must retain their
multiplicity. Node identity and endpoint integrity need equivalent validation.
Provider statistics must have an unknown state; guessed cardinalities cannot
justify a claimed cost improvement.

## First implementation and expansion

Start with read-only node scans, property filters, projections and aggregates,
then fixed-length relationship joins, grouping, DISTINCT, ordering and limits.
Qualify null propagation, integer overflow, mixed numeric comparisons, empty SUM,
all-null groups, repeated edges and trail exclusions before automatic selection.
OPTIONAL MATCH, subqueries, variable-length paths, writes and procedures retain
existing execution until their own mappings are qualified. This sequence is an
implementation order, not a reduction of the broader compatibility goal.

Plan caching must bind schema, snapshot/capability identity and parameter types
without caching answers. Prefer native providers to full graph export. Measure
whether capture and conversion erase kernel gains before selecting DataFusion.
Graph algorithms continue through the shared procedure/kernel architecture;
relational joins are not a substitute for specialized traversal kernels.

## Resources and proof

The current bounded Cypher policy accounts candidate work, intermediate bytes,
result rows and output bytes. DataFusion's pool and spill limit alone do not
satisfy that policy. Add explicit mapping or decline execution when a requested
limit cannot be enforced; never silently weaken caller admission. Include
cancellation during scan, joins and output consumption, and release all retained
resources when the result stream is dropped. Caller-owned input and retained
output remain disclosed separately from tracked operator memory.

Run the same parsed-query fixtures through the reference executor and bridge,
with independent small-graph oracles and pinned external differential evidence.
Preserve unsupported, semantic mismatch, unavailable and resource failure as
distinct outcomes. Measure capture, conversion, preparation, execution and result
consumption separately, plus end-to-end time and process peak memory. Compare
identical datasets, protocols and envelopes; retain original benchmark pins.

Completion requires ordinary Cypher entrypoint integration, backend provider
coverage with declared limits, semantic and resource qualification, evidence for
execution selection, documentation/book updates and the named crate release.
A successful explicit SQL benchmark does not prove automatic execution.

## Integration inspection, 2026-09-14

`DataFusionEngine::context()` already exposes upstream typed logical plan
execution; no additional wrapper API is required. Regression `7d74e26` qualified
filter/projection execution and duplicate preservation across multiple batches
on DataFusion 55.1.0. Its receipt is under
`benchmarks/arrow-pipelines/evidence/typed-plan-7d74e26`.

Cypher's existing `pushdown` module has node, segment, variable-length and
optional read planning, but predicate descriptors are private and its public
rendering surface targets SQL dialects. Inspect extraction of a shared typed
relational descriptor before duplicating those eligibility rules. Existing
pushdown caveats, including arithmetic error behavior, are not automatic proof
of DataFusion semantic equivalence. The public AST remains the alternative
input if extracting those descriptors would entangle unrelated backend contracts.

## Current qualification and measurement boundary

The full Cypher suite passed 869 tests (zero failures, two ignored) after the
shared integer-ordering and column-name changes. The DataFusion suite passed
36 tests and locked warnings-denied Clippy at `95cb7c8`; its retained receipt is
`benchmarks/arrow-pipelines/evidence/cypher-execute-95cb7c8`. That includes the
text execution entrypoint, 28 relationship differential queries, anonymous node
scans, shared bindings, snapshot identity, result conversion and output limits.
The subsequent full workspace gate at `6c2bc0b` passed 1,597 tests, with zero
failures and 49 ignored, plus warnings-denied workspace Clippy. Linker warnings
and ignored tests are retained in `cypher-workspace-6c2bc0b` evidence. Final Isopod qualification and delivery supersede this preliminary release
status; see the release evidence below.

The optimized `cypher_scan` profile at `771cb89` completed on Capitola with all
42 oracle checks passing. It compares identical Cypher text through indexed
execution and typed lowering. At one million nodes, three-trial prepared-query
medians were 1.476991 seconds indexed and 0.004989 seconds typed DataFusion;
Arrow conversion/registration separately took 0.974918 seconds. The indexed
route was faster on the 17-node fixture. The raw receipt discloses differing
admission boundaries and co-resident inputs. These observations do not establish
an automatic threshold, backend parity or join throughput.

Output rows and exact serialized bytes are now enforced incrementally. Remaining
policy integration includes query/parameter/input admission, candidate work,
intermediate allocation, deadlines/cancellation and backend snapshot authority.
Automatic ordinary-entrypoint routing, broader language mappings, provider
coverage and comparable end-to-end profiling remain open. Isopod released
the explicit bridge; automatic routing will require its own qualified release.

The fixed-path profile at `100822f` completed with all 84 oracle checks passing.
At 100,000 nodes, prepared two-hop medians were 0.247736 s indexed and 0.018985 s
DataFusion; three-hop medians were 0.460961 s and 0.034407 s. Arrow preparation
was 0.0676–0.0691 s separately. Indexed execution was faster at 17 nodes. Raw
receipts and admission boundaries are retained under
`benchmarks/arrow-pipelines/evidence/cypher-paths-100822f`; this is a parallel-ring
profile, not a general cost threshold or backend/policy parity result.

## Isopod release completed, 2026-09-14

[Isopod evidence](../releases/isopod/README.md) records the final source
`044f4e9`: 1,599 tests passed, zero failed, 49 ignored; all eight native gates
passed; 24 archives matched independently; all 20 published registry archives
matched the qualified hashes. The book, hosted readers and TextPack are delivered.
This closes the explicit bridge milestone without closing this goal.

Next integration must preserve the complete `ReadQueryPolicy`. Its existing
execution budget is thread-local and synchronous; an async, multithreaded
DataFusion plan cannot inherit that budget by wrapping future construction.
Use an execution-owned admission/cancellation contract across planning, scans,
operators and result consumption. Keep cumulative candidate/intermediate-copy
accounting distinct from DataFusion's retained-memory pool. Route selection must
expose unsupported policy mappings and unknown costs, and must not retry errors
after execution begins. Capture/conversion and provider authority remain part
of the end-to-end decision.

## Shared asynchronous control, qualified increment

The unreleased shared `ExecutionContext` now exposes runtime-independent
cancellation notifications. DataFusion's `run_cancellable`, controlled Arrow
streams, SQL `execute_stream_with_context`, and Cypher `execute_with_context`
propagate cancellation and the absolute deadline through consumption. They
retain ordinary error outcomes and drop owned pending streams on termination.
The implementation uses no queue, worker task or Arrow buffer copy. Synchronous
work inside a poll remains cooperative. The five-crate consumer gate passed 976 tests, zero failures and two ignored,
plus warnings-denied Clippy. Qualification is recorded in
`benchmarks/arrow-pipelines/evidence/query-control-3139917`.

This is a prerequisite for automatic routing, not the routing implementation.
Shared query/parameter/input admission and candidate/intermediate accounting
remain necessary; none is inferred from cancellation or the memory-pool limit.

## Shared request admission, qualified increment

`PreparedReadRequest` now centralizes bounded query/parameter validation, graph
and index size checks, output checks and the original absolute deadline. It owns
the validated AST and policy, borrows immutable admitted parameters and retains
the application registry generation. The bounded reference executor now uses
these checks. Source `294baa8` passed 980 consumer tests with zero failures and
two ignored, plus warnings-denied Clippy; raw receipts are under
`benchmarks/arrow-pipelines/evidence/read-admission-294baa8`.

Preparation does not confer backend graph authority or install execution
budgets. Those route-specific obligations remain explicit and incomplete for
DataFusion. Automatic selection, exact provider statistics, native input
admission, candidate/intermediate accounting and release delivery remain open.

## Exact capture statistics, qualified increment

Source `7ab955f` adds constant-time `GraphSnapshot::statistics()` with exact
node/edge row counts, original batch counts and added ordinal payload bytes.
Clones and catalog replacement preserve these captured values. DataFusion's
47 tests and warnings-denied Clippy passed; receipts are under
`benchmarks/arrow-pipelines/evidence/snapshot-statistics-7ab955f`.

Next, exact serialized input admission can build on Arrow's existing paired
`property.<key>` and `present.<key>` columns: absence and explicit null survive
capture. A borrowed native serializer must preserve Grust's tagged scalar JSON,
identity fields, property keys, batch order and escaping, with independent
comparison against ordinary `Graph` serialization. Counting through a bounded
writer should avoid encoded JSON and row-graph allocation. This is not yet
implemented; row counts alone do not satisfy `max_graph_bytes`.

## Native serialized input admission, implemented and in qualification

`ArrowGraphTables::as_serializable_graph()` now borrows native Arrow 55/58/59
columns to reproduce the core graph serde representation. Source `7e337ad`
passed 52 all-feature tests and warnings-denied Clippy. The implementation keeps
property presence separate from null, orders property keys like core `Props`,
and exposes writer-controlled serialization without graph/JSON materialization.

`0e7abba` adds shared request checks for native serialization and trusted cached
measurements. `GraphSnapshot::try_new_with_input_policy` checks rows before
serialization, counts exact bytes under the original deadline, then captures
providers and retains the size. Ordinary capture keeps `serialized_graph_bytes`
explicitly unknown. Full workspace tests/Clippy are running on Capitola; a later
test-only change `cda270f` broadens typed-null coverage. Snapshot authority,
existing buffer/ordinal admission, candidate/intermediate accounting, automatic
routing, cost qualification and release delivery remain outstanding.

## Workspace integration passed; Ostracod release in qualification

The full `0e7abba` workspace gate passed 1,627 tests, zero failures and 49
ignored, plus warnings-denied all-target Clippy. Raw evidence is retained in
`benchmarks/arrow-pipelines/evidence/native-admission-workspace-0e7abba`.
Ostracod 0.18.0 prepares the accumulated shared control/admission changes for
release. Final source `28d2471` includes expanded typed-null tests and is running
the full native release gates on Capitola. Registry publication and book/blog
delivery are not yet complete. This release does not close automatic routing,
full execution-budget mapping, provider authority or performance qualification.

## Ostracod registry milestone, 2026-09-14

Final source `28d2471` passed all eight native release gates: 1,627 tests
passed, zero failed, 49 ignored. All 24 independently packaged archives matched;
all 20 published 0.18.0 registry archives matched those qualified hashes.
Tag `v0.18.0` identifies that source. The rebuilt book and TextPack are prepared;
canonical book deployment is in progress. Receipts are under
[Ostracod evidence](../releases/ostracod/README.md). Automatic routing, complete
work/intermediate-budget mapping, backend authority and comparable end-to-end
qualification remain incomplete and are the next engineering obligations.
