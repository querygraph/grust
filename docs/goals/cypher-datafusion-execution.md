# Automatic Cypher execution with DataFusion 55

Status: active implementation goal, explicitly requested 2026-09-14. This extends the active
[performance and compatibility goal](arrow-performance-parity.md). The released
DataFusion foundation accepts explicit SQL; it does not yet select plans for
ordinary Cypher queries.

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
execution nor the current partial scan compiler establishes completion.

Current implementation admits scalar predicates and parameters, inline property
maps, single-node scans, projection, DISTINCT, count aggregation and grouping,
projected-expression ordering, integer/string extrema, node identity and pagination
through explicit lowering APIs. `GraphSnapshot::execute` now connects Cypher
text parsing, typed planning and output-bounded portable result collection;
unsupported queries remain distinct from errors. Scalar binding resolution now supports multiple
caller-defined bindings. Parsed directed single-hop relationship patterns now
share the RETURN compiler with scans.
Planner decisions distinguish unsupported shapes from semantic errors. Broader joins,
broader aggregates, route selection, resource mapping, comparative performance
qualification and release delivery remain outstanding.

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
that plan. The unreleased `cypher::GraphSnapshot` now supplies this ordinal for
validated native Arrow graph tables and retains an immutable provider pair.
Backend transaction/authorization identity and resource admission still need
integration. A lazy directed endpoint-join operator now retains these ordinals
and shared typed bindings. Parsed incoming/outgoing single-hop lowering is
implemented, as are undirected and repeated-endpoint one-hop matches; optional and variable-length patterns
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
and ignored tests are retained in `cypher-workspace-6c2bc0b` evidence. Packaging,
book delivery and registry release verification remain outstanding.

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
coverage, comparable end-to-end profiling and the named release remain open.
