# Sem research and PR status

Observed 2026-10-08T04:57:27.056172+00:00. Consolidated report on
`work/grust-v2-cypher-semantics`; the exact source verdict and qualification
boundaries are in [Cypher semantics and SNB](../grust-v2/wave-3/CYPHER-SEMANTICS.md).
[GitHub states](../grust-v2/wave-3/evidence/cypher-semantics/github-states.json) were inspected separately; a draft PR is not a production release.

## Research and implementation

| Area                                    | Status                                          | Evidence and qualification limits                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| --------------------------------------- | ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| LDBC correctness and native comparisons | Complete within the requested contracts         | A0: 16/16 supported official LDBC fixtures. A6: 48 audited native calls: six reference preparations and forty-two numerical comparisons with complete output checks. [Native results](../sem-review-morrobay-2026-10-01/A5/FableExact/README.md).                                                                                                                                                                                                                                                                                                                             |
| Pecan changes                           | Implemented in the Sail fork                    | Snapshot bypass, signed-isolate WCC correction, GraphX delta PageRank contract, redundant edge-copy removal and typed API. Fork implementation is distinct from upstream publication.                                                                                                                                                                                                                                                                                                                                                                                         |
| Grust F1 ingest                         | Released as 0.24.0 Tanaid                       | Int64 identity and compact columnar projection. Tag `v0.24.0` at `d2668ec7`; board records twenty published crates and passing macOS/arm64 Linux gates. [Registry core](https://crates.io/crates/grust-core/0.24.0), [facade](https://crates.io/crates/grust-graph/0.24.0). Nutmeg integer-ID integration is on `work/nutmeg-int64-identity`.                                                                                                                                                                                                                                 |
| C2/C3/C4/D2/E0                          | Requested native controls complete              | Observer scopes, actual reservation admission/refusal/release, aggregate allocation controls, unsorted checkpoint layout and Pregel programs retain source gates and answers. [Completion report](../sem-completion-2026-10-03/README.md). Complete exclusive attribution and a general process RSS envelope are not qualified by these controls.                                                                                                                                                                                                                             |
| X1/X2 streams                           | Current replay and diagnostic controls complete | Original scale-24 two-host BFS passes all 16,777,216 rows against the original edge relation, including owned closure. Historical initiating causes and twelve earlier X2 stream losses remain unexplained.                                                                                                                                                                                                                                                                                                                                                                   |
| B8 union/explode                        | Protocol completed with failures retained       | Forty qualified rows, forty-four attempted calls, four OOM warmups and sixteen policy skips. Missing Graph500 contrast ratios remain withheld.                                                                                                                                                                                                                                                                                                                                                                                                                                |
| F0/F2 and Vortex                        | Measured controls complete                      | Checksum-guarded ingest diagnostics, one/three-call resident-CSR controls and separate four-phase profile retained. Vortex reader works in the bounded control; writer unavailable.                                                                                                                                                                                                                                                                                                                                                                                           |
| Sem research designs                    | Delivered                                       | Five October 2 studies and two October 3 design responses. [Research](../sem-research-2026-10-02/README.md), [October 3 designs](../sem-research-2026-10-03/README.md). [Cosmograph architecture](https://github.com/querygraph/grust/blob/work/cosmolang-proposal/docs/reviews/sem-research-2026-10-03/visualization/COSMOGRAPH-ARCHITECTURE.md) and [Cosmolang](https://github.com/querygraph/grust/blob/work/cosmolang-proposal/docs/reviews/sem-research-2026-10-03/visualization/COSMOLANG.md) remain proposals; the protocol schemas/examples are qualified separately. |
| Grust v2                                | Waves 1–3 drafts implemented and qualified      | [Wave 1](../grust-v2/wave-1/README.md) supplies LPG/kernel contracts; [Wave 2](../grust-v2/wave-2/README.md) supplies unresolved IR and the programmatic API. [Wave 3](../grust-v2/wave-3/EXECUTION.md) adds executable resolution, costed inner joins and native Sail SQL; subsequent drafts add providers, iterative execution and [Cypher semantics/SNB qualification](../grust-v2/wave-3/CYPHER-SEMANTICS.md). These standalone unpublished crates have not replaced the production workspace.                                                                            |
| Additional experiments                  | Intentionally paused or parked                  | Additional F2a paused following Fable’s October 3 handoff. B2/B3/B5/B6, partition union-find and attraction-only ForceAtlas2 implementations remain parked. CDLP, K-Core and additional Pregel programs are deferred.                                                                                                                                                                                                                                                                                                                                                         |
| Second String                           | Implemented and qualified in the fork           | [Draft PR #34](https://github.com/querygraph/sail/pull/34) at `f31c33ae`; all sixteen defaults and configurable variants. Forty-one release Rust tests and 112 checks in each native Sail mode pass; all 7,296 compiled Scala answers match through FFI, local mode and process workers.                                                                                                                                                                                                                                                                                      |

## Latest Cypher and LDBC work

All four requested draft semantics are implemented: MATCH-wide relationship
uniqueness; correlated CALL/subqueries with stable outer-row identity; full
path and relationship-list values; and ordering/numeric behavior through
WITH/RETURN. The native semantics set has 104 exact returned-result checks and
eight explicitly expected arithmetic errors. The five unchanged official SNB
v1 short queries (IS1, IS3–IS6) have thirteen parameter bindings and 130
resolved/optimized cells, including warmups and ABBA twice, against an
independent CSV oracle. Query hashes, parameter values, output types,
optimizer estimates, rewrite traces and failed development controls are retained.

This qualifies the disclosed local-mode read subset on SNB's development
dataset. It is not an audited full SNB benchmark, a full Cypher/GQL
implementation, process-cluster qualification or production integration.
Ranged-path WHERE, updates, comprehensions and unsupported function/provider
contracts still return explicit diagnostics. Unknown optimizer cost remains
unknown, including iterative work; an estimate is not an elapsed-time prediction.

Cosmolang C0, on the separate `work/cosmolang-proposal` branch, passed 11
schemas, 29 example exchanges and 16 rejection controls. It specifies graph
follow, nearest neighbors, degree filters, WCC, hierarchy expansion/collapse,
layouts and bounded speculative prefetch. It does not implement the browser,
MCP gateway, Nutmeg runtime or a multibillion-node hierarchy. See its
[qualification](https://github.com/querygraph/grust/blob/25e4c0ad597c4e9132b4cd6af938c631527ec8fc/docs/reviews/sem-research-2026-10-03/visualization/cosmolang/VALIDATION.md).

## Native comparison findings

The exact Fable-script protocol has four calls per engine and algorithm in two
G/P/P/G blocks. The primary statistic is Pecan median elapsed time divided by
graphframes-rs median elapsed time; values below one favor Pecan on this workload.

| Algorithm | cit-Patents | graph500-24 |
| --------- | ----------: | ----------: |
| WCC       |       1.415 |       0.795 |
| PageRank  |       1.159 |       0.861 |
| BFS       |       0.713 |       0.862 |

These are shared-host native macOS x86-64 results with snapshot inputs disabled,
sixteen configured software workers and 30-GiB engine pools. They are not a
32-GiB operating-system cap or a universal engine ranking. BFS/PageRank use the
stored directed arcs; that comparison does not qualify Graph500's official
undirected ground truth. The [full native report](../sem-review-morrobay-2026-10-01/A5/FableExact/README.md)
records timing boundaries, all forty-eight calls, physical output audits and
source identities. Benchmarking moved to native optimized binaries; VMs are
reserved for Linux build testing.

## Pull requests and upstream issues

| Item                                                                                                         | Observed state                          | What that state covers                                                                                                                                                                  |
| ------------------------------------------------------------------------------------------------------------ | --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [Grust #35](https://github.com/querygraph/grust/pull/35), [#36](https://github.com/querygraph/grust/pull/36) | Merged into `work/proposal-v5`          | Design drafts and work sequence; Grust v2 implementation is separate.                                                                                                                   |
| [Sail fork #32](https://github.com/querygraph/sail/pull/32)                                                  | Open draft, head `f2b297fc`             | Weighted SSSP and landmark Pregel programs; source gate and eleven full native controls.                                                                                                |
| [Sail fork #33](https://github.com/querygraph/sail/pull/33)                                                  | Open draft, head `98de82ab`             | Default-off C2 observations; forty-three scopes and bounded native/fault controls.                                                                                                      |
| [Sail fork #34](https://github.com/querygraph/sail/pull/34)                                                  | Open draft, head `f31c33ae`             | Native Second String extension; source and local/process-worker qualification completed.                                                                                                |
| Grust [#40](https://github.com/querygraph/grust/pull/40)–[#45](https://github.com/querygraph/grust/pull/45)  | Open drafts, stacked                    | Wave 3 interface, executable resolution/optimization, provider registry, iterative adapter and Cypher frontend. Their individual source gates are not a verdict on a prospective merge. |
| [Grust #46](https://github.com/querygraph/grust/pull/46)                                                     | Open draft, source `6638d9b4` qualified | MATCH uniqueness, correlation, entity paths, ordering/numeric semantics and the five-query SNB qualification.                                                                           |
| Upstream Sail #2722–2732, #2741 and #2742                                                                    | Thirteen open issues                    | Bug reports, not PRs; no published fix qualification in our reports.                                                                                                                    |
| [Upstream Sail #2643](https://github.com/lakehq/sail/pull/2643)                                              | Open draft, head `7cca4095`             | A commenter proposes it fixes [CASE panic #2742](https://github.com/lakehq/sail/issues/2742#issuecomment-6003165699); it is unmerged.                                                   |

## Next work

1. Review the stacked Grust draft PRs and this semantics follow-up; production
   migration and a merged-source gate remain separate work.
2. Review the qualified Sail fork PRs #32–34 before merging them into Pecan.
3. Expand query qualification beyond the five short SNB queries, with declared
   language/function admission and independent answers for each additional query.
4. Implement Cosmolang's runtime/browser integration after reviewing the contract.
5. Track upstream wrong-result reports, especially sorted checkpoint
   [#2722](https://github.com/lakehq/sail/issues/2722) and sorted overwrite
   [#2741](https://github.com/lakehq/sail/issues/2741), qualifying each proposed fix.
   Keep additional F2a paused as requested.
