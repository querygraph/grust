# Grust Cumacean: Cypher writes planned from the typed AST

Grust gives Rust applications one property-graph API across memory, embedded databases, SQL systems and remote graph services. Nodes, edges, typed identities, traversals, mutations, schema and graph algorithms are written once against that API; Memory, Sail/Spark, PostgreSQL, pgGraph, PostgreSQL SQL/PGQ, Turso, SurrealDB, FalkorDB, LanceDB and CocoIndex sit behind it, and each adapter states which operations it pushes down, runs natively, answers through the portable reference, or does not support. `grust-cypher` is the portable GQL/Cypher layer over the same model. Tadpole 0.21.0 completes a missing part of that language and makes its reference executor considerably cheaper to run.

See the [repository and API guide](https://github.com/querygraph/grust), the [Grust book](https://firstpair.org/read/grust/), the [GQL profile statement](https://github.com/querygraph/grust/blob/main/docs/GQL_PROFILE_STATEMENT.md) and the full [`CHANGELOG.md`](https://github.com/querygraph/grust/blob/main/CHANGELOG.md).

## Write statements are planned from the typed AST

Grust's Cypher has had two planners. Reads were parsed by a typed parser into an AST and planned from it. Writes, `CREATE`, `MERGE`, `MATCH ... SET`, `DELETE` and their `RETURN` forms, were planned by a scanner that found keywords in the statement text, split it at commas and cut it at parentheses. The scanner was older than the parser, and it had corners: a `;` inside a backtick-quoted label split the statement, a keyword inside a quoted property name chose the wrong planner, a quoted label kept its backticks when stored, `{v: 'x' + 'y'}` stored the string `x' + 'y`, and `CREATE(n ...)` without a space was a syntax error.

Cumacean removes the scanner. `cypher_mutation_plan` and its option-taking and `sail_` forms now parse each `;`-separated statement with the typed parser and read the clauses, patterns, `WHERE` expression, `SET` and `REMOVE` items and `DELETE` targets from the AST. The lowering beneath is unchanged: an id-resolved single-identity operation stays one, a row-producing match stays one, and node, relationship and path variables bind across statements as before.

The switch was measured before it was made. Both planners ran on 1,638 write statements, every write-like string literal in the workspace's Rust sources, the crate's JSON corpora and a list of edge cases, under five option sets and, where a statement takes parameters, three parameter bindings. The 18,930 comparisons gave identical plans and bindings, or the same error variant, except where the scanner was wrong. The golden write plans did not change.

What changes is the handling of those corners, and the full list is in the changelog. Backtick-quoted names are read as names: labels, relationship types and property keys lose their quotes, doubled backticks collapse, and a malformed quoted name is a syntax error. Literals and escapes are read as the parser reads them, so `- 5`, `1e3`, `True`, `Null` and `\u{41}` mean what they say. Keywords need no surrounding spaces. Two things the scanner accepted silently are now rejected as unsupported, because they never meant what a reader would assume: a node pattern with several labels, or a relationship with type alternatives or a variable length, was stored or matched as one label or type (`A:B`, `R|S`, `R*2`); and an operator expression as a value was stored as its text. Rejected statements keep their error variant; some messages now quote the whole statement or name the construct instead of a fragment the scanner had cut.

## Arrow 59.2 as the floor

`grust-arrow`, `grust-algorithms` and `grust-algorithm-procedures` required Arrow 59.3; they now require 59.2. Nothing in them uses anything newer than 59.2, and a host that pins Arrow 59.2 and DataFusion 55.2, which is what Sail does, could not resolve them before. The workspace's own lockfile still takes the newest 59.x.

## Turso 0.8.1

The embedded Turso engine moves from 0.7.2 to its stable 0.8.1, with the `turso_*` crates and `antithesis_sdk` alongside. `grust-turso` needed no source change; it builds with all features, and its tests, `querygraph-memory`'s and the facade's with `turso` and `turso-sync` pass. The Turso measurements already published, in the strain chapter of the book and the 0.20.0 post, were taken on 0.7.2 and have not been rerun, so they stand as measurements of that engine.

## Why a patch release

Cumacean is 0.24.1 because no public type or signature changes and no golden plan moves; the planner beneath a public function is replaced and its corners are corrected. It is published now because the Sail extensions pin Grust from crates.io, and they need a published Grust that carries the typed write planner and accepts their Arrow.

## Upgrading

Cumacean is a lockstep release: move every direct Grust crate dependency to 0.24.1 together. Code that relied on a scanner corner listed above, multi-label write patterns, relationship type alternatives or variable lengths in a write, or operator expressions as stored values, now receives an unsupported error where it used to receive a wrong answer; everything else plans as before.
