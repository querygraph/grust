# Grust v2, wave 1: where each answer is

The plan of work agreed with Sem on
[querygraph/grust #36](https://github.com/querygraph/grust/pull/36): wave 1
is four independent items. All four are done. Each ends with open questions
for Sem.

| Item                          | Answer in brief                                                                                                                                                                                                                                                                                                                                                                                     | Folder                                      |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| LPG base traits and core APIs | Traits `VertexGroup`, `EdgeGroup`, `Lpg`; logical types, properties, directions, constraints; a checked in-memory schema with a builder. Pattern resolution returns every valid path through the schema graph (a backward feasibility pass, then a forward walk with no dead ends, capped and flagged). Sem's example resolves. A sketch crate with seven tests.                                    | [`lpg/`](lpg/README.md)                     |
| Kernel memory discipline      | Input is the host's and output the kernel's, each released once by the other side, as the Arrow C data interface prescribes. The CSR crosses as one Arrow `LargeList<UInt32>`. Every byte admitted before it is allocated; output bytes stay admitted until the host releases the output. A sketch crate with four tests through the C ABI.                                                         | [`kernel-memory/`](kernel-memory/README.md) |
| How to parse GQL and Cypher   | Hand-written recursive descent with Pratt expressions for both, moving today's parser into new crates rather than rewriting it: a shared syntax crate, plus a Cypher parser and a GQL parser that each lower to the unresolved plan. The GQL ANTLR grammar becomes a reference and a test oracle, not the runtime parser. GQL is new work with any tool: today's parser rejected all 17 GQL probes. | [`parsing/`](parsing/README.md)             |
| Substrait                     | Grust can emit it (a hand-built plan matched SQL on DataFusion and DuckDB), but it has no recursion, reaches none of Grust's own backends, and its specification is pre-1.0. SQL text first through one emitter trait; Substrait second as an optional emitter; Spark Connect relations not planned.                                                                                                | [`substrait/`](substrait/README.md)         |

The two sketch crates are in [`sketch/`](sketch/), a standalone cargo
workspace outside the release workspace.

## How the work was done

The LPG traits and the memory contract were written by Claude for Alexy.
The parsing report and the Substrait research were written by two separate
agents from written briefs, then checked: their central results were rerun
and their code citations read.

## Found on the way

Two bugs in today's Cypher write path, from the parsing report: the
string-scanning planner does not skip backtick identifiers, so
``CREATE (n:`A;B` {id: 'x'})`` fails and ``SET n.`x CREATE y` = 1`` is
misrouted, although the typed parser accepts both. Reproduced on the
published `grust-cypher` 0.24.0.

## Next

Wave 2, once Sem has reviewed these: the unresolved logical plan (traits and
the flow from Cypher, GQL and the programmatic API) and the programmatic API
draft.
