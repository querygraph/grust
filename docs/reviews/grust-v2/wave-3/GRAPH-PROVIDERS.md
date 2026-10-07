# Wave 3: graph operator providers

This draft extends the executable relational compiler on PR #42. Production
crates remain unchanged. The implementation lives in the standalone, unpublished
`wave-3/sketch` workspace.

## Executable surface

- A single path segment with an explicit finite hop range, up to eight hops.
  Zero-hop paths contain one vertex and no edges. Expansion preserves parallel
  edges and path multiplicity.
- WALK, TRAIL, SIMPLE and ACYCLIC reuse the qualified fixed-hop predicates.
- ALL returns the path bag. SHORTEST chooses one minimum-hop path per pair of
  endpoints; ALL SHORTEST retains every minimum-hop tie. ANY uses that same
  minimum-hop choice, which is a valid arbitrary path. Ties in the one-path
  selectors are deliberately unspecified.
- Endpoint identities include graph group tags. A draft materialized path has
  `length`, `vertices` and `edges`; each identity is `{group, identity}`. The
  ranged edge binding is a list of edge identities, not a scalar edge entity.
  This is an internal draft encoding, not a finalized GQL or LEX representation.
- Endpoint and repeated edge predicates run before path selection. OPTIONAL
  MATCH keeps unmatched vertices and yields NULL for the missing path/list.
- Registered relation extensions lower through `RelationProviders` to ordinary
  unresolved relations, then pass through the full resolver. Providers cannot
  inject SQL or unchecked resolved slots. Missing registrations, invalid scopes
  and cyclic lowering produce typed errors; lowering depth is capped at 32.

`QueryResolver.resolve_with_providers` selects a registry. Existing `resolve`
uses `NoProviders`, preserving the explicit refusal for unregistered extensions.

## Sail and optimizer boundaries

`path_capability` distinguishes the finite SQL provider from shapes requiring a
separate execution adapter. The finite provider expands fixed-hop joins and
unions, then emits `rank` or `row_number` partitioned by endpoint identities and
ordered by length. Path selection is an optimizer boundary: costed inner joins
may be reordered inside it, but selection is never flattened into a join region.
Typed empty arrays are cast explicitly, preserving the element schema at zero
hops. A materialized path uses a physical slot so OPTIONAL nullability propagates.

Unbounded traversal is **not implemented**. Neither are multi-segment ranged
patterns or weighted shortest paths. An unbounded query is refused rather than
silently assigned a finite bound. Adding an iterative execution adapter and its
memory/cancellation contract is the next graph execution step. The eight-hop
limit is an admission cap for this SQL provider, not a claim about graph diameter.

## Qualification

The fixtures run on the existing native optimized macOS Sail host at
`9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3`, with fresh Parquet inputs and two
workers. Every case checks bag multiplicity and output types, both before and
after optimization. The evidence includes the earlier development receipts and
the detached source gate. No timings or performance claims are made.

New fixtures cover finite-range bags, shortest ties, one-path selection,
zero-hop typed identity lists, OPTIONAL shortest paths, TRAIL edge reuse and a
registered relation plugin with a bound parameter. Rust controls cover unknown
providers, provider cycles, unresolved references, invalid hop ranges, the cap
and incompatible path bindings.

## Source verdict

`PASSED graph-provider native source gate b193d2382ea1840dfe4434ac993694650a352d37`

The detached checkout remained clean and its HEAD unchanged. Rust formatting and
release Clippy passed; all 28 Rust tests passed with default features and again
with all features. All 92 native Sail cells passed (46 cases, resolved and
optimized), including output data types.

Evidence: [source gate](evidence/graph-providers/source-gate.json),
[native gate log](evidence/graph-providers/native-gate.log),
[query manifest](evidence/graph-providers/queries.json), and
[Sail receipt](evidence/graph-providers/native-sail-receipt.json).
The two earlier development receipts are retained separately; they cover earlier
fixture sets and do not substitute for the exact-source verdict.

## Iterative follow-up

The separate iterative adapter is now implemented and qualified on this branch;
see [ITERATIVE-SAIL.md](ITERATIVE-SAIL.md). The finite SQL implementation and its
source verdict above remain the record of PR #43.
