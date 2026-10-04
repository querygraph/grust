# How to parse Cypher and GQL in Grust v2

Wave 1 report for Sem Sinchenko, following the plan agreed on pull request #36.
Date: 2026-10-03. Code read: `grust-cypher` at tag `v0.24.0`, commit `d2668ec7`
(worktree `~/src/grust-f1`). All line references below are to that commit.

## Summary

1. The Cypher parser is not regex-based, and Grust has no regex dependency. It is a hand-written lexer plus a recursive-descent parser with a Pratt loop for expressions. Older hand-written string scanning (also not regex) still builds write plans and parses DDL. That is probably the code you saw, and it has real bugs.
2. Today's parser reads Cypher only. It rejected all 17 GQL syntax probes and 6 of 7 newer Cypher probes. ISO GQL is about 574 grammar rules against about 94 for Cypher, so GQL is new work whatever tool we choose.
3. Recommendation: hand-written recursive descent with Pratt expressions for both languages. Use two front-end crates on one shared lexer and syntax crate, each lowering to the unresolved plan. The tested Cypher parser moves there; it is not rewritten. Not `nom`, and not ANTLR as the runtime parser.
4. Measured speed per query (10 test queries): today 2.0 µs, winnow 5.3 µs, chumsky 7.9 µs, ANTLR Cypher 26 µs, ANTLR GQL 1,800 µs. Only the ANTLR GQL number matters in practice. Compile time and error quality separate the options more than speed does.
5. Two things would change this: a hard need for several errors per query in one pass (then chumsky, as Sail's SQL parser uses), or a hard need to share one grammar file with other languages (then the ANTLR GQL grammar, but as a test oracle, not as the Rust runtime).

Evidence tags used below: **[code]** read from Grust source, **[measured]** produced by the spike or a probe in this folder (raw record cited), **[docs]** read from a crate, repository or grammar page (version and date given), **[inferred]** my judgement from the evidence.

## 1. What exists today

### 1.1 Two parsing layers, not one

`grust-cypher` has two layers. The typed layer is the grammar authority. The legacy layer still produces write plans and DDL.

| Layer                                | Files (non-test lines)                                                                                                                                                                                                                                                                     | Used by                                                                                                                                                                                                                                                                                                                                                                                          |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Typed: lexer, parser, AST, semantics | `src/lexer.rs` (785), `src/parser.rs` (1,261) + `src/parser/binding_forms.rs` (67), `src/ast.rs` (531), `src/semantics.rs` (691)                                                                                                                                                           | The whole read path: `read.rs:337,350`, `pushdown.rs:657,1588,2464,4399`, `read_policy.rs:106`, `read/indexed.rs:50`, `read/prepared_procedures.rs:43`. `RETURN` expressions on writes: `returning/expression.rs:81`. An accept-gate for every write statement: `planner.rs:29-36`. Session and transaction commands read lexer tokens: `session.rs:95-106`, `transaction.rs:64-100`. **[code]** |
| Legacy: hand-written string scanning | `src/parse.rs` (703), `src/primitives.rs` (723), `src/where_clause.rs` (2,805), `src/returning.rs` (3,114), `src/planner.rs` (1,809), `src/ddl.rs` (524), `src/graph_type_ddl.rs` (188). These files mix scanning with plan building and evaluation, so not all ~9,900 lines are scanning. | Write plan construction (`planner.rs:180-192`, `planner.rs:272-291`), write-with-`RETURN` splitting (`returning.rs:113`), comment stripping and statement splitting for writes and DDL (`planner.rs:43-44,89-90`, `ddl.rs:483-484`), all DDL (`parse.rs:65-105`, `graph_type_ddl.rs:29-44`). **[code]**                                                                                          |

`crates/grust-cypher/Cargo.toml` lists no regex crate, and `grep -rn regex` over `src` finds nothing. **[code]** So the correction given on #36 stands: the parser is not regex-based. The precise statement is: the typed parser is recursive descent, and the write planner and DDL still use hand-written keyword scanning on strings.

Two doc comments are out of date. `parser.rs:9-12`, `lexer.rs:9-12` and `ast.rs:8-12` still say the typed path is "additive" and does not yet replace the `cypher_*` entrypoints. The read path has fully moved; the write path only uses it as a gate (`planner.rs:26-28` says so). **[code]**

### 1.2 The typed parser

| Aspect     | What the code does                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | Where                                                                   |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| Kind       | Hand-written recursive descent over a token vector, 89 functions. Expressions use a Pratt loop (`parse_expr_bp`) with binding powers OR 1, XOR 2, AND 3, comparisons 4, `+ -` 5, `* / %` 6, `^` 7. `IS [NOT] NULL` is a postfix in the loop.                                                                                                                                                                                                                                                                  | `parser.rs:115-130`, `parser.rs:954-990`, `ast.rs:479-498` **[code]**   |
| Lexer      | Byte-level, hand-written. Case-insensitive keywords (50 `Keyword` variants), backtick identifiers, `$` parameters, numeric and string literal families, `//` and `/* */` comments, arrows and `..`. `STARTS`/`ENDS` stay identifiers and the parser pairs them with `WITH`. `Keyword::StartsWith` and `Keyword::EndsWith` exist but nothing produces them. No `--` comments, which GQL allows.                                                                                                                | `lexer.rs:89-199`, `lexer.rs:322`, `lexer.rs:415-450` **[code]**        |
| Spans      | Every token has a byte span. 18 AST nodes carry a span (query, clauses, patterns). `Expr` variants carry none, so a semantic error inside an expression can only point at its clause.                                                                                                                                                                                                                                                                                                                         | `lexer.rs:24-52`, `ast.rs:354-428` **[code]**                           |
| Errors     | `ParseError { kind: Syntax \| Unsupported(GqlFeature), span, message }`. `render` gives line and column. `into_grust` maps to the structured `GrustError` channel and keeps the feature tag. One error per query: every rule returns `Result` and propagates with `?`; there is no recovery. Messages print tokens with `Debug`, for example `found Keyword(Return)`.                                                                                                                                         | `parser.rs:23-80`, `parser.rs:178-186` **[code]**                       |
| Statements | `parse_query` (one statement), `parse_statements` (`;`-separated), `parse_expression`. Clauses: `USE`, `MATCH`, `OPTIONAL MATCH`, `CREATE`, `MERGE`, `DELETE`, `DETACH DELETE`, `SET`, `REMOVE`, `WITH`, `UNWIND`, `RETURN`, `CALL` (procedures with `YIELD`, and `CALL { }` subqueries), `UNION [ALL]`. Patterns: node and relationship patterns, `*min..max`, `p = ...`, `shortestPath(...)` and `allShortestPaths(...)`. Expressions include `CASE`, list comprehensions, `reduce`, `any/all/none/single`. | `parser.rs:85-113`, `parser.rs:287-350`, `parser.rs:703-900` **[code]** |
| Semantics  | `semantics::analyze` checks scope, variable kinds and the `WITH` horizon, and records `GqlFeature` gates with spans.                                                                                                                                                                                                                                                                                                                                                                                          | `semantics.rs:117`, `semantics.rs:60-80` **[code]**                     |

### 1.3 How "GQL" and "Cypher" are distinguished today

They are not distinguished at the grammar level. There is one lexer and one parser, and they read a Cypher dialect. "GQL" in the code names the conformance catalog: `GqlFeature` (77 entries, 72 `Supported`, 5 intentional rejections), the profiles `StrictWrite`, `PortableGql` and `Full39075`, and the error channel. **[code]** `gql.rs:179`, `docs/GQL_PROFILE_STATEMENT.md:38,53`.

Catalog names can mislead. `quantified-path-pattern` is described as "Variable-length relationships (*min..max)" (`gql.rs:763-769`). That is Cypher syntax. GQL's quantifier `->{1,3}` is rejected (probe below). **[code]** **[measured]** The profile statement does disclaim full ISO conformance; I flag this only so the v2 GQL crate does not inherit the name.

GQL-shaped statements that exist today are outside the parser: `START TRANSACTION`, `COMMIT`, `ROLLBACK` in `transaction.rs:64-100`, session `SET`/`RESET`/`USE` in `session.rs:95-140`, both over lexer tokens. Graph-type DDL uses Grust's own syntax (`CREATE GRAPH TYPE g AS NODE Person (...)`), scanned as strings in `graph_type_ddl.rs`. GQL's own graph-type syntax is rejected. **[code]** **[measured]**

### 1.4 What today's parser accepts: probes

Raw record: `raw/probes.txt`. **[measured]**

| Probe                                                                                          | Result                            |
| ---------------------------------------------------------------------------------------------- | --------------------------------- |
| GQL `-[:KNOWS]->{1,3}`, `->+`, `((a)-[:R]->(b)){1,3}`                                          | rejected                          |
| GQL label expressions `:Person\|Robot`, `:Person&!Robot`, `IS Person`                          | rejected (`&` is a lexical error) |
| GQL element `WHERE` inside `( )`, abbreviated edge `(a)->(b)`                                  | rejected                          |
| GQL `ANY SHORTEST`, `TRAIL`, `DIFFERENT EDGES`                                                 | rejected                          |
| GQL `YIELD` after a graph pattern, `INSERT`, `FILTER`, `LET`, `NEXT`, `OFFSET`                 | rejected                          |
| GQL `CREATE GRAPH TYPE t AS { ... }`                                                           | rejected                          |
| Cypher `UNWIND`                                                                                | accepted                          |
| Cypher `EXISTS { }`, `COUNT { }`, map projection, list slice, pattern comprehension, `FOREACH` | rejected                          |

17 of 17 GQL probes and 6 of 7 newer Cypher probes are rejected. Each rejection has a correct span. The parser covers the Cypher subset Grust executes, not openCypher in full, and none of GQL's own syntax.

### 1.5 The string-scanning paths and two bugs they cause

The scanners skip single- and double-quoted strings but not backtick identifiers (`primitives.rs:587-600`, `parse.rs:410-452`). **[code]** Two probes show the effect. Raw record: `raw/probes.txt`. **[measured]**

| Statement                                              | Typed parser | Write planner                                                                                                                                                         |
| ------------------------------------------------------ | ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ``CREATE (n:`A;B` {id: 'x'})``                         | accepts      | fails: `split_cypher_statements` cuts at the `;` inside backticks, then the lexer sees an unterminated identifier                                                     |
| ``MATCH (n:Person {id: 'p1'}) SET n.`x CREATE y` = 1`` | accepts      | fails: `find_unquoted_keyword(statement, "CREATE")` finds `CREATE` inside the backticks and routes the statement to the `MATCH ... CREATE` planner (`planner.rs:279`) |
| `MATCH (n:Person {id: 'p1'}) SET n.x = 1` (control)    | accepts      | plans 1 operation                                                                                                                                                     |

Other scanning paths: `classify_statement` picks the statement kind by leading keyword (`parse.rs:28-51`). DDL is parsed by keyword stripping (`parse.rs:65-105`, `graph_type_ddl.rs`). There are two statement splitters: the legacy one (`parse.rs:410`) and a token-based one (`lexer.rs:331`, used by `transaction.rs:236`). The token-based one is correct for backticks because it splits tokens.

### 1.6 Tests that protect the parser

**[code]** Static counts (I did not run the suite; see Limits).

- `#[test]` functions: 831 in `src`, 66 in `tests`. Directly on the typed front end: lexer 22, parser 31, AST 5, semantics 17, GQL catalog 18.
- Corpora: `tests/gql/portable_read.json` (36 cases), `tests/gql/strict_write.json` (17), `tests/golden/write_corpus.json` (181 scripts), `tests/golden/write_golden.json` (20 byte-identical write plans).
- `parse_statements` accepts 224 of the 234 corpus sources. All 10 rejections are intended: non-standard `DELETE (:pattern)` forms, DDL (handled by `cypher_ddl`), an unterminated comment, and three expected-rejection cases. **[measured]** `raw/corpus.txt`.

### 1.7 Speed today

Apple M1 Max, rustc 1.97.1, release build, load average about 5 during the run. Raw record: `raw/bench.txt`. **[measured]**

| Input                                                        | Median                     |
| ------------------------------------------------------------ | -------------------------- |
| 10 `MATCH` queries from the tests, mean 63 bytes, lexer only | 0.89 µs per query          |
| Same, `parse_query` (lex and parse)                          | 2.0 µs per query           |
| 224 accepted corpus sources, `parse_statements`              | 2.9 µs per source, 35 MB/s |

The lexer is about 45% of the time. A read on the Memory reference costs milliseconds, so parsing is not a bottleneck. **[inferred]**

## 2. The grammars

### 2.1 Size

Counted with `raw/count_grammars.py` (a regex count, so approximate). Raw record: `raw/grammars.txt`. **[measured]** **[docs]**

| Grammar                 | Source, version                                                                                                                                                                                                                            | Parser rules        | Lexer rules            | Keywords                                       |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------- | ---------------------- | ---------------------------------------------- |
| ISO GQL, ANTLR          | `opengql/grammar` `GQL.g4`, version 1.9.0, commit `16ea71bd` (2025-06-17), Apache-2.0. Byte-identical to `antlr/grammars-v4` `gql/GQL.g4` at `7df52be9` (2026-10-03). Generated from the ISO BNF XML, then hand-tuned to remove ambiguity. | 574                 | 390 (+44 fragments)    | 218 reserved, 39 pre-reserved, 77 non-reserved |
| openCypher, ISO WG3 BNF | `opencypher/openCypher` `grammar/openCypher.bnf`, commit `677cbafa` (2026-03-20), Apache-2.0                                                                                                                                               | 377 productions     | in the BNF             | 63 distinct terminal words                     |
| Cypher, ANTLR           | `antlr/grammars-v4` `cypher/*.g4` at `7df52be9`, BSD                                                                                                                                                                                       | 94                  | 98 (59 keyword tokens) | 59                                             |
| Neo4j Cypher 25, ANTLR  | `neo4j/neo4j` branch `2026.09`, `Cypher25Parser.g4` / `Cypher25Lexer.g4`, GPL-3.0                                                                                                                                                          | 430                 | 377                    |                                                |
| Grust today             | `lexer.rs`, `parser.rs`                                                                                                                                                                                                                    | 89 parser functions | hand-written           | 50                                             |

The Neo4j grammar is the most complete Cypher grammar, but it is GPL-3.0 and Grust is `MIT OR Apache-2.0`, so it can only be read, not reused. **[docs]** The grammars-v4 Cypher grammar has five tokens defined implicitly in the parser (ANTLR warning 125 on `MANDATORY`, `SCALAR`, `OF`, `ADD`, `DROP`). **[measured]**

### 2.2 Where Cypher and GQL overlap and differ

openCypher's current grammar says it follows GQL's non-terminal names where possible (`grammar/README.adoc`). **[docs]** The pattern and expression sublanguages now largely coincide. The statement level does not.

| Construct                                                     | openCypher BNF (2026-03)                     | GQL.g4                                                                   | Grust today                        |
| ------------------------------------------------------------- | -------------------------------------------- | ------------------------------------------------------------------------ | ---------------------------------- |
| Node and edge patterns, direction                             | yes                                          | yes, plus abbreviated edges `->`, `<-`, `-`                              | yes, no abbreviated edges          |
| Quantifiers `*`, `+`, `{m}`, `{m,n}`                          | yes (`<graph pattern quantifier>`)           | yes (`graphPatternQuantifier`)                                           | only `*min..max`                   |
| Parenthesized path patterns with `WHERE`                      | yes                                          | yes                                                                      | no                                 |
| Label expressions `\| & ! %`                                  | yes                                          | yes                                                                      | only `:A:B` and `:T1\|T2` on edges |
| Path search prefix `ALL`, `ANY`, `ANY SHORTEST`, `SHORTEST k` | yes                                          | yes                                                                      | `shortestPath()` functions only    |
| Path modes `WALK`, `TRAIL`, `SIMPLE`, `ACYCLIC`               | no                                           | yes                                                                      | no                                 |
| Match modes `DIFFERENT EDGES`, `REPEATABLE ELEMENTS`          | no                                           | yes                                                                      | no                                 |
| `YIELD`                                                       | `CALL ... YIELD` only                        | also after a graph pattern                                               | `CALL ... YIELD`                   |
| Query composition                                             | `WITH`, `UNWIND`, `UNION`                    | `NEXT`, `LET`, `FOR`, `FILTER`, `UNION`/`EXCEPT`/`INTERSECT`/`OTHERWISE` | `WITH`, `UNWIND`, `UNION`          |
| Writes                                                        | `CREATE`, `MERGE`, `SET`, `REMOVE`, `DELETE` | `INSERT`, `SET`, `REMOVE`, `DELETE`; no `MERGE`                          | Cypher set                         |
| `x IN list` predicate                                         | yes                                          | no (`IN` only in `FOR` and `LET`)                                        | yes                                |
| Paging                                                        | `SKIP`/`OFFSET`, `LIMIT`                     | `OFFSET`/`SKIP`, `LIMIT`                                                 | `SKIP`, `LIMIT`                    |
| Graph types, catalog, sessions, transactions                  | no                                           | yes (large part of the 574 rules)                                        | separate hand-written paths        |

### 2.3 Can one lexer and one AST serve both?

**[inferred]**, from the tables above.

- **One lexer: yes**, if it emits words, not keywords. GQL reserves 218 words; Cypher reserves far fewer and allows many keywords as names. Today's lexer already leaves `STARTS` and `ENDS` as identifiers. A shared lexer with a small dialect switch (GQL's `--` comments, byte-string and temporal literal forms) and per-dialect keyword sets fits both.
- **One expression and pattern AST: yes.** Both grammars now name the same constructs (quantifiers, path search prefixes, label expressions). Dialect-only forms (`*min..max`, `shortestPath()`, path modes, match modes) become variants of the same nodes.
- **One statement AST: no.** Cypher's `WITH`/`UNWIND`/`MERGE` and GQL's `NEXT`/`LET`/`FOR`/`FILTER`/`INSERT` differ in structure. Each front end should have its own statement tree and lower it into the shared unresolved plan. That matches "two separate" parsers with one plan.

## 3. The options

### 3.1 Versions and maintenance (checked 2026-10-03)

**[docs]** From the crates.io API and the GitHub API on 2026-10-03.

| Option                  | Crate, latest version, release date                                                                                                                                                       | Repository activity                                                                                                                                                 | Prior art for graph languages                                                                                                                                                 |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Hand-written RD + Pratt | none                                                                                                                                                                                      |                                                                                                                                                                     | Grust today; `sqlparser` 0.63.0 (2026-09-13, `apache/datafusion-sqlparser-rs`), whose README describes a hand-written recursive-descent parser with a Pratt expression parser |
| `nom`                   | 8.0.0, 2025-01-26                                                                                                                                                                         | `rust-bakery/nom`, last push 2025-08-26, 292 open issues                                                                                                            | `graphlite` 0.0.1 (ISO GQL) depends on nom                                                                                                                                    |
| `winnow`                | 1.0.4, 2026-07-13                                                                                                                                                                         | `winnow-rs/winnow`, push 2026-10-01; README credits it as the successor work to nom                                                                                 |                                                                                                                                                                               |
| `chumsky`               | 0.13.0, 2026-05-06                                                                                                                                                                        | moved to Codeberg `zesterer/chumsky` (GitHub archived), updated 2026-10-03                                                                                          | Sail's `sail-sql-parser` (chumsky 0.12, derive macros)                                                                                                                        |
| `pest` (PEG)            | 2.9.2, 2026-09-21                                                                                                                                                                         | `pest-parser/pest`, push 2026-10-03                                                                                                                                 | `cypher-rs-zk` 1.1.0 depends on pest                                                                                                                                          |
| `peg` (PEG macro)       | 0.8.6, 2026-05-04                                                                                                                                                                         | `kevinmehall/rust-peg`                                                                                                                                              | Drasi (`drasi-project/drasi-core`): `drasi-query-gql` and `drasi-query-cypher` 0.3.6, both on `peg` and one shared `drasi-query-ast`                                          |
| `lalrpop` (LR(1))       | 0.23.1, 2026-03-11                                                                                                                                                                        | `lalrpop/lalrpop`, push 2026-09-22                                                                                                                                  |                                                                                                                                                                               |
| ANTLR 4, Rust target    | old `antlr-rust` 0.2.2 (2022-07-22), repo `rrevenantt/antlr4rust` last push 2023-02-14. Maintained fork `antlr4rust` 0.6.0 (2026-09-27), tool jar from `antlr4rust/antlr4` release v0.6.0 | fork of `antlr/antlr4`, 32 stars, 14 open issues. Its README: "work in progress and I'm mostly trying to solve my problem as of now". Not an official ANTLR target. | Neo4j's Cypher 25 parser is ANTLR (Java): `Cypher25Parser.g4` in `neo4j/neo4j`                                                                                                |
| `tree-sitter`           | 0.27.0, 2026-08-30                                                                                                                                                                        | `tree-sitter/tree-sitter`, push 2026-10-03                                                                                                                          | `tree-sitter-cypher` 0.2.6 (2026-05-10); no GQL grammar crate found                                                                                                           |

### 3.2 Comparison on the same criteria

Ratings are **[inferred]** from the measurements in section 4 and the documentation cited above. Dependency weight and build time are **[measured]** in `raw/compile-and-deps.txt`: unique crates in the dependency tree, and a cold release build of the library alone, `-j 4`.

| Criterion                            | Hand-written RD + Pratt                                       | nom / winnow                                                             | chumsky                                            | pest / peg                                            | lalrpop                                                         | ANTLR 4 (antlr4rust)                                             | tree-sitter                                   |
| ------------------------------------ | ------------------------------------------------------------- | ------------------------------------------------------------------------ | -------------------------------------------------- | ----------------------------------------------------- | --------------------------------------------------------------- | ---------------------------------------------------------------- | --------------------------------------------- |
| Coverage effort, Cypher              | Done for Grust's subset (1,330 lines); extend in place        | Rewrite; about the same size                                             | Rewrite; somewhat smaller                          | Rewrite; grammar file plus a second pass to typed AST | Rewrite; LR conflicts to resolve                                | Reuse the 94-rule grammars-v4 grammar, then walk the tree        | Reuse `tree-sitter-cypher`, then walk the CST |
| Coverage effort, GQL                 | New; 574 rules for all of GQL, far fewer for the query subset | New, same                                                                | New, same                                          | New, same                                             | New; ISO BNF is not LR(1) and needed hand-tuning even for ANTLR | Grammar exists (574 rules); the AST mapping is still new work    | No grammar exists                             |
| Error messages and spans             | Full control; today one error with span                       | `winnow`: one error, offset and labels you add by hand. `nom`: one error | Rich errors with expected sets, labels and spans   | One error with expected rules (pest)                  | One error, plus error recovery with `!`                         | Line and column, "no viable alternative"; default recovery       | Error nodes in a tree, no messages            |
| Several errors per query             | Possible (sync on clause keywords), not built                 | nom: no. winnow: only behind its `unstable-recover` feature              | Yes, built in (`recover_with`); E4 below shows two | No                                                    | Yes (`!` token)                                                 | The default strategy recovers, but E4 below still gave one error | Yes (always gives a tree)                     |
| Speed (section 4)                    | 2.0 µs                                                        | 5.3 µs (winnow, untuned)                                                 | 7.9 µs (untuned)                                   | not measured                                          | not measured                                                    | 26 µs Cypher, 1,800 µs GQL                                       | not measured                                  |
| Dependencies, cold build             | 0 crates, 0 s                                                 | nom 2 crates 2.5 s; winnow 1 crate 1.0 s                                 | 17 crates 6.5 s                                    | pest_derive 10 crates 2.9 s; peg 6 crates 2.0 s       | generator 47 crates 21.6 s; runtime 6 crates 5.4 s              | runtime 16 crates 3.3 s, plus Java to generate                   | 18 crates 8.5 s plus a C compiler             |
| Grammar compile time                 | 1.3k lines, ordinary                                          | subset 1.1 s                                                             | subset 5.8 s; Sail's full SQL parser 15.2 s        | proc-macro expands the grammar                        | generated tables                                                | generated Cypher 14k lines: 8.8 s; GQL 82k lines: 55.9 s         | C code                                        |
| Maturity                             | No dependency to age                                          | nom slowing (last release 2025-01); winnow active, 1.0                   | Active; breaking API changes between 0.x releases  | Mature                                                | Mature                                                          | Rust target is a one-person fork                                 | Mature, but built for editors                 |
| Share a grammar with other languages | No                                                            | No                                                                       | No                                                 | No                                                    | No                                                              | Yes: the same `.g4` runs in Java, Python, Go and others          | Yes for editor tooling (JS grammar, C parser) |
| Typed AST that maps to a plan        | Direct: functions return AST types                            | Direct                                                                   | Direct                                             | Untyped `Pairs` tree (pest), typed actions (peg)      | Typed actions in the grammar                                    | Generic parse tree; a visitor builds the AST                     | Untyped CST; a walker builds the AST          |

## 4. The spike

Folder: `spike/` (a standalone cargo workspace) and `antlr-probe/`. Build with `CARGO_TARGET_DIR` under `~/src/reference/build/`. Run `parsing-spike agree|errors|bench|corpus|probes`.

**Design.** The same subset grammar is written twice. It covers `[OPTIONAL] MATCH` patterns (labels, property maps, typed and ranged relationships, path variables), `WHERE` with a full precedence ladder, and `RETURN` with `DISTINCT`, `AS`, `ORDER BY`, `SKIP` and `LIMIT`.

- `crates/subset-winnow`: winnow 1.0.4 over characters, the nom style Sem suggested. 313 lines, not counting blanks and comments.
- `crates/subset-chumsky`: chumsky 0.13.0 over **Grust's own lexer tokens** (`grust_cypher::lexer::tokenize`). This tests the "one shared lexer, separate parser" layout. Error recovery is on for node patterns and bracketed expressions. 205 lines on the same count, plus the reused lexer.
- Both produce one shared subset AST (`crates/subset-ast`, 97 lines).
- Today's parser is called through `grust_cypher::parser::parse_query`.

**Agreement.** On all ten queries, winnow and chumsky produce identical ASTs, and today's parser accepts every query. `raw/agree.txt`. **[measured]**

**Speed.** `raw/bench.txt`, 20,000 iterations × 9 rounds, median. **[measured]**

| Parser                                            | ns per query |
| ------------------------------------------------- | ------------ |
| Grust lexer alone                                 | 891          |
| Today, `parse_query`, full grammar                | 2,001        |
| winnow subset                                     | 5,255        |
| chumsky subset (Grust lexer + chumsky)            | 7,906        |
| ANTLR, grammars-v4 Cypher (`raw/antlr-probe.txt`) | 26,120       |
| ANTLR, opengql GQL, same queries in GQL spelling  | 1,812,871    |

The combinator versions are not tuned. Their rich error types allocate on every backtrack. I would expect a tuned version to come close to today's, not to beat it. **[inferred]** The ANTLR GQL parser stays at 1.8 ms per query even with its DFA cache warm (the cache is a `lazy_static` shared across parsers). I did not profile it; ambiguity in the large grammar forcing full-context prediction is the likely cause. **[inferred]**

**Error quality on malformed queries.** `raw/errors.txt` and `raw/antlr-probe.txt`. **[measured]**

| Query                                  | Today                                                                           | winnow                                            | chumsky                                                                                                | ANTLR (Cypher grammar)                                     |
| -------------------------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------- |
| E1 `MATCH (n:Person RETURN n.name`     | "expected ')' to close a node pattern, found Keyword(Return)", span on `RETURN` | "invalid node pattern, expected `)`", offset      | "found Keyword(Return) expected Colon, LBrace, or RParen", span                                        | "no viable alternative at input 'MATCH (n:Person RETURN'"  |
| E2 `... WHERE a.age > RETURN b.name`   | "expected an expression, found Keyword(Return)"                                 | "invalid expression, expected `(`, an expression" | "found Keyword(Return) expected Keyword(Not), Minus, or expression"                                    | "no viable alternative at input '... a.age > RETURN'"      |
| E3 `MATCH (n:Person) RETRUN n.name`    | "unexpected trailing input: Identifier(\"RETRUN\")"                             | "expected `RETURN`"                               | "found Identifier(\"RETRUN\") expected relationship pattern, Comma, Where, Optional, Match, or Return" | "no viable alternative at input 'MATCH (n:Person) RETRUN'" |
| E4 two errors: `{name: }` and `(3 + )` | first error only                                                                | first error only                                  | **both errors**, each with its own span                                                                | first error only                                           |

The findings:

- Hand-written messages are already as precise as the combinators' messages. They name the construct ("to close a node pattern"). Two things are worth fixing: E3 says "trailing input" instead of "expected RETURN", and tokens print in `Debug` form.
- chumsky gives the best default messages and the only multi-error result. It took two `recover_with` lines.
- winnow needs a hand-written context label on every rule to say anything useful.
- The ANTLR messages are the weakest: no expected set, and the whole prefix is echoed back.

**Compile time** of the grammar crate alone, release: winnow subset 1.1 s, chumsky subset 5.8 s, generated ANTLR Cypher 8.8 s, generated ANTLR GQL 55.9 s. `raw/compile-and-deps.txt`. **[measured]** Scaled to a full grammar, chumsky's cost is real. Sail's chumsky SQL parser crate takes 15.2 s on the same machine. **[measured]**

**What the spike decided.** No tool improves on today's parser in speed or message quality for one error. chumsky wins on several errors per query and on default messages, at about 5× compile time and 4× run time. ANTLR's Rust runtime is too slow and too heavy for the GQL grammar to be the runtime parser. Sharing Grust's lexer with a different parser front end works without changes to the lexer.

## 5. Recommendation

### 5.1 Approach

| Question        | Answer                                                                                                                                                                                                                                                                                                                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Cypher          | Keep hand-written recursive descent with Pratt expressions. Move today's typed parser; do not rewrite it in `nom`.                                                                                                                                                                                                                                                                          |
| GQL             | Same technique, new crate. Write it rule by rule against `opengql/grammar` `GQL.g4` (Apache-2.0), using its rule names as function names so every function traces to the standard. Start with the query subset: linear statements, patterns with quantifiers, label expressions, path search prefixes and modes, `FILTER`, `LET`, `NEXT`. Catalog, session and graph-type rules come later. |
| Grammar sharing | Use the ANTLR GQL grammar as an offline **differential oracle**, not as the runtime. The generated parser (Java, or `antlr4rust` in a separate test crate) checks that Grust's GQL parser accepts and rejects the same sample inputs.                                                                                                                                                       |
| Shared lexer    | Yes. One lexer that emits words; each dialect classifies keywords. Shared `Span`, tokens and diagnostics.                                                                                                                                                                                                                                                                                   |
| Shared AST      | Share the pattern and expression nodes. Keep a separate statement tree per language. Each front end lowers into the unresolved plan's types.                                                                                                                                                                                                                                                |
| Errors          | Keep `ParseError` with spans and feature tags. Add expected sets and `Display` token names. Add statement-level recovery (skip to the next clause keyword) when a user needs several errors at once.                                                                                                                                                                                        |

### 5.2 Crate layout

```text
grust-lpg                 LPG traits (wave 1, separate report)
grust-plan                unresolved logical plan types; no parsing (wave 2)
grust-query-syntax        Span, Token, Lexer (dialect switch), Diagnostic,
                          shared pattern and expression AST, Pratt expression parser
grust-cypher-parser       Cypher statements -> syntax tree -> grust-plan
grust-gql-parser          GQL statements    -> syntax tree -> grust-plan
```

The parser crates have no third-party dependencies. A user of the programmatic API depends on neither parser crate. A Cypher user does not compile GQL. This follows Sem's crate rule on #36.

### 5.3 Migration without losing coverage

1. **Freeze the behaviour.** At `v0.24.0`, dump the `Debug` AST for every statement in the four corpora and for every query string in the parser, lexer and semantics tests into a golden file. The 224 accepted and 10 rejected corpus sources become the floor.
2. **Move, do not rewrite.** Move `lexer.rs`, `parser.rs`, `parser/binding_forms.rs`, `ast.rs` and `semantics.rs` (about 3,300 non-test lines) with their 75 unit tests into `grust-query-syntax` and `grust-cypher-parser`. The golden file must match byte for byte.
3. **Put the writes on the AST.** Every write statement already goes through the typed parser (`planner.rs:29-36`). Build write plans from that AST instead of from strings, guarded by the existing byte-identical `tests/golden/write_golden.json`. Add the two backtick probes from section 1.5 as regression tests first; they fail today.
4. **Remove the scanners.** Put `CREATE/DROP CONSTRAINT`, `INDEX` and `GRAPH TYPE` into the grammar. Replace `split_cypher_statements` and `strip_cypher_comments` with the token-based `lexer::split_statements` (the lexer already skips comments). Then delete the scanning helpers in `parse.rs`, `primitives.rs`, `where_clause.rs` and `returning.rs`.
5. **Lower to the plan** once `grust-plan` exists (wave 2). The read path's tests (`tests/gql/portable_read.json`, `tests/read_conformance.rs`) check that lowering keeps results.
6. **Grow GQL by catalog entry.** Add GQL-syntax features to `GqlFeature` under GQL's names. Each gets an accept test, a reject test and oracle agreement. Keep `quantified-path-pattern` for the GQL form only, and give the Cypher `*min..max` form its own name.

## What would change this

- **Several errors per query become a requirement** (an editor, a language server, a notebook). Then chumsky becomes the better choice, especially if it can share infrastructure with Sail's `sail-sql-parser`. The price is about 5× grammar compile time and a run time still in microseconds. A hand-written parser can recover too (rust-analyzer does), but that is more work to build.
- **One grammar file must be shared with Java or Python** (for example GraphFrames). Then the ANTLR grammar becomes the source of truth. I would still keep a Rust runtime parser, unless a future `antlr4rust` and a disambiguated GQL grammar bring GQL parsing down from 1.8 ms. That needs a re-measurement.
- **The GQL target is "all of ISO GQL", not the query subset.** With 574 rules, a generator's head start counts for more. The ANTLR oracle would then matter more, and the hand-written estimate below would grow.
- **An existing Apache- or MIT-licensed Rust GQL parser reaches real coverage.** None I found does: `gql-parser` 0.1.1 and `graphlite` 0.0.1 are early. Drasi's `drasi-query-gql` is the most relevant, being two `peg` front ends on one shared AST.

## Limits

- The spike grammar is a small subset. Code-size comparisons between the tools are indicative only. For the full GQL query subset I estimate 2,500 to 4,000 hand-written lines, by analogy with today's 1,330 lines for Grust's Cypher. This is **[inferred]**, not measured.
- The combinator parsers were not tuned for speed (they use rich error types). pest, peg, lalrpop and tree-sitter were judged from documentation, versions, dependency trees and build times, not by writing a grammar.
- Measurements come from a shared laptop (Apple M1 Max) with another agent building. Load averages are in each raw file: 5 to 11 for the final runs, and up to 29 for an earlier run that gave the same ratios. Absolute numbers will move; the ratios were stable across runs.
- I did not run `grust-cypher`'s own test suite; the test counts are static. Only parse acceptance was run, on 234 corpus sources.
- Grammar sizes come from a regex count over the `.g4` and BNF files and are approximate.
- I did not profile why the ANTLR GQL parser is slow.
- The GQL probe spellings are mine, written from `GQL.g4`. A rejection by today's parser is certain. Whether each probe is valid GQL was checked only for the ten GQL-spelled spike queries, which the ANTLR GQL grammar accepted.
- The Neo4j and Sail facts come from reading their repositories (Sail read only, from a local checkout at `99ee46f6`). Nothing was pushed or posted anywhere.

## Files

- `README.md`: this report.
- `spike/`: standalone cargo workspace (`Cargo.toml` has its own `[workspace]`). It depends on the published `grust-cypher` `=0.24.0` from crates.io (the same source as tag `v0.24.0`).
- `antlr-probe/`: the ANTLR Rust-target probe. `generate.sh` downloads the pinned tool jar and grammars and generates about 4 MB of Rust into `src/` (git-ignored).
- `raw/`: `bench.txt`, `corpus.txt`, `agree.txt`, `errors.txt`, `probes.txt`, `antlr-probe.txt`, `compile-and-deps.txt`, `grammars.txt`, `count_grammars.py`.

## Checked independently

Added by the reviewer of this report, 2026-10-03. The spike's dependency was
switched from a local path to the published `grust-cypher` 0.24.0, and its
`probes` command rerun: both backtick probes reproduce (`CREATE (n:\`A;B\` ...)`
fails in the write planner with "unterminated quoted identifier";
``SET n.`x CREATE y` = 1`` is misrouted and fails), while the typed parser
accepts both and the plain-name control succeeds. The cited Pratt loop
(`parser.rs:954-990`) and the keyword routing (`planner.rs:279`) read as
stated.
