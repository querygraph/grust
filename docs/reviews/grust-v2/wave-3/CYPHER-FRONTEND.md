# Wave 3: Cypher source text to native Sail

**Later semantics follow-up:** [MATCH uniqueness, correlation, full paths, ordering/numeric semantics and native SNB qualification](CYPHER-SEMANTICS.md). The earlier scope and source verdict below are historical.

This follow-up to [iterative execution](ITERATIVE-SAIL.md) connects the existing
`grust-cypher` typed AST parser to the standalone, unpublished draft workspace.
It does not change the production parser, production crate APIs or Sail source.

## Architecture

```text
Cypher source → existing typed AST → Parser/Lowering contracts
             → unresolved plan → catalog/function resolution
             → costed join optimizer → SailProgram → native Sail + Parquet
```

`grust-cypher-frontend` implements `grust-syntax::Parser` and `Lowering`.
The parser consumes the whole single query. Syntax errors preserve original
UTF-8 byte spans. Unsupported lowering has a typed diagnostic and a clause or
pattern span. The resolver retains its typed schema, scope, function and
parameter errors; source-level resolver span attribution remains future work.

The frontend depends on the existing parser by path. It does not copy a grammar
or route through the legacy engine-specific planner. Function classification
comes from the supplied registry. A name registered as both scalar and aggregate
is refused rather than guessed.

## Admitted read surface

- Leading single-component `USE`; one path pattern per `MATCH` clause; repeated
  `MATCH` and `OPTIONAL MATCH`; node labels and property maps; edge type
  alternatives; incoming, outgoing and undirected edges.
- Cypher's relationship-unique TRAIL mode, including fixed multisegment paths.
  Single-segment bounded and unbounded ranges feed the existing program adapter.
  Shortest-path selectors retain the adapter's disclosed path semantics.
- Fixed-pattern `WHERE` is part of the match condition. An OPTIONAL filter does
  not remove the unmatched incoming row.
- `UNWIND`, `WITH`, terminal `RETURN`, `DISTINCT`, projected ordering, pagination,
  and left-associated `UNION` / `UNION ALL`.
- Registered scalar and aggregate calls, parameters, arithmetic and comparisons
  represented in the IR, lists/maps, CASE and null tests. `count(*)` lowers to
  counting a non-null constant; grouping preserves RETURN column order.
- Quoted bindings and aliases. Star projection follows visible binding order;
  complex output expressions require explicit `AS`.

## Refusals and remaining work

This is an explicitly admitted read subset, not full Cypher conformance.
Updates, procedures and subqueries are refused. Comma-separated patterns need
MATCH-wide relationship uniqueness. Named paths and ranged relationship
bindings need a full Cypher entity-path/list materialization contract; internal
identity arrays are not exposed as those values. Materialized/ranged path WHERE
needs correlated predicate lowering. WITH ordering needs propagation across
later clauses. Hidden ORDER BY keys, complex unaliased expressions, unsupported
operators (including division pending integer/float semantics), comprehensions, quantifiers and indexing are refused. Multipart USE
is refused because the current AST flattens quoted selector components.

The native runtime remains local-mode with a shared local filesystem, explicit
resource caps and cancellation checks. The pool limit governs Sail-managed
allocations, not total process RSS. This work adds no VM benchmark, performance
claim, process-cluster qualification or production release.

## Qualification

The new source-text manifest contains 20 queries with independent expected result
bags or sequences; both resolved and optimized programs execute. They cover
optional filtering, parallel edges, relationship reuse, count on an unmatched
optional row, projection order after grouping, CASE, UNION multiplicity, quoting,
parameter values, bounded traversal and eleven-hop unbounded traversal.
Twenty-six refusal fixtures stop before engine execution.

Run `live/gate-cypher.sh` from a clean detached checkout with external
`CARGO_TARGET_DIR`, `GATE_OUTPUT`, `SAIL_BINARY` and `GATE_PYTHON`. It checks Rust
formatting, Clippy, tests in default/all-features/release modes, all existing relational
and iterative native fixtures, the source-text fixtures, refusal diagnostics and
runtime controls. The final verdict is only printed if HEAD and the checkout
remain unchanged. Source-specific receipts are linked below.

## Observed verdict and evidence

Source `0e85df70dd2f7f6a37dd1aee1fc2fd36d7f9f3f0` passed from a clean detached
checkout on Morrobay, native macOS x86-64, Rust 1.98.1. The [source receipt](evidence/cypher-frontend/source-gate.json)
records the UTC observation, source tree, command, environment and artifact hashes.
The [full gate log](evidence/cypher-frontend/native-gate.log) retains the verdict.

| Check                                               | Result                 |
| --------------------------------------------------- | ---------------------- |
| Formatting and Clippy, default and all-features     | Passed                 |
| Rust tests, default / all-features / release        | 39 each                |
| Existing relational results, resolved / optimized   | 92 passed              |
| Existing iterative results, resolved / optimized    | 22 passed              |
| Cypher source results, resolved / optimized         | 40 passed              |
| Frontend and resolver refusals before execution     | 26 refused as expected |
| Runtime resource, cancellation and quoting controls | 13 passed              |

The [source-text manifest](evidence/cypher-frontend/cypher/queries.json) carries
query text, expected rows, emitted programs, output types and optimizer traces.
Its [native receipt](evidence/cypher-frontend/cypher/receipt.json) preserves actual
rows. The [refusal manifest](evidence/cypher-frontend/refusals.json) preserves
frontend diagnostic codes/spans and typed resolver errors. Earlier fixture
receipts are in the `relational/` and `iterative/` evidence directories; the
managed memory allocation refusal is in `memory/`.

The first gate [failed](evidence/cypher-frontend/attempts/gate01.json) on a
nonexistent feature flag. The second [failed](evidence/cypher-frontend/attempts/gate02.json)
on macOS Bash 3's handling of empty arrays under `nounset`, after passing Rust.
Both failed logs are retained beside their summaries; neither started native
cells. The third gate passed on the source named above.

The Sail release executable was reused without modification; its digest before
and after every run was
`ee80ac3cf9d028639561f3cf32435985192719d629807fcf6a368324fa84946e`.
Each owned Sail server was terminated and reaped. The final report commit changes
only documentation and evidence; executable source remains the gated source.

## Using the frontend

Call `grust_syntax::parse_and_lower` with `CypherParser` and
`CypherLowering { functions: registry }`, then supply the resulting plan to
`QueryResolver.resolve_iterative` with the caller's catalog, parameter types and
relation providers. Optimize that resolved plan and call `SailSql.emit_program`;
execute the resulting program inside the existing `Execution` context. Capability
refusals remain errors at their original layer.

For the fixture catalog, emit the reproducible source-text program manifest with:

```sh
cargo run --locked --release \
  --manifest-path docs/reviews/grust-v2/wave-3/sketch/Cargo.toml \
  -p grust-query-qualification -- --cypher
```

Replace the final flag with `--cypher-refusals` to inspect the refusal manifest.
Invoke the complete gate with `bash docs/reviews/grust-v2/wave-3/live/gate-cypher.sh`
and the four external paths described above.
