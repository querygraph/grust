# Wave 3: Cypher source text to native Sail

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
operators, comprehensions, quantifiers and indexing are refused. Multipart USE
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
Twenty-four refusal fixtures stop before engine execution.

Run `live/gate-cypher.sh` from a clean detached checkout with external
`CARGO_TARGET_DIR`, `GATE_OUTPUT`, `SAIL_BINARY` and `GATE_PYTHON`. It checks Rust
formatting, Clippy, tests in default/serde/release modes, all existing relational
and iterative native fixtures, the source-text fixtures, refusal diagnostics and
runtime controls. The final verdict is only printed if HEAD and the checkout
remain unchanged. Source-specific receipts will be linked after the gate.
