# Cypher semantics and LDBC qualification goal

Branch: `work/grust-v2-cypher-semantics`, based on PR #45.

| Required item                                       | State                                                       | Evidence                                                                                                 |
| --------------------------------------------------- | ----------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| MATCH-wide relationship uniqueness                  | Development checks pass; final gate pending                 | `sketch/resolution/src/query/uniqueness.rs`                                                              |
| Correlated CALL/subqueries through providers        | Development checks pass; final gate pending                 | Native lateral aggregation and LIMIT probes fail; retained for the report                                |
| Full paths/entity lists: length/nodes/relationships | Development checks pass; final gate pending                 | Ordered columnar lookup, complete properties, mixed segments, zero hops and null optional paths          |
| Ordering propagation and numeric semantics          | Development checks pass; final gate pending                 | Explicit truncating division and scope/order preservation                                                |
| Representative LDBC queries and cost qualification  | Development oracle and paired runs pass; final gate pending | Five unchanged SNB v1 short queries, thirteen bindings, 26 initial checks and 130 warmup/measured checks |
| Consolidated report and email to Sem                | Planned                                                     | After the goal passes, send from configured dick@hurz.net to ssinchenko@apache.org                       |

All runs use native release execution. Gates run in detached clean checkouts.
Failures and capability refusals remain distinct from passed result checks.
This is query qualification, not an audited complete LDBC benchmark result.

Development receipt `cypher-semantics-probes/semantics05/receipt.json` outside the repository records 52 native result checks (26 cases, resolved and optimized). These are not yet a detached source verdict. Historical frontend refusal tests are being updated for the newly admitted contracts.

## Implementation contracts

- One MATCH tests relationship identity `(group, identity)` across its TRAIL patterns; separate MATCH clauses may reuse an edge. Optional joins keep uniqueness predicates in their join condition.
- Correlated bodies lower through `Argument`/`Apply` and the provider registry. A stable materialized row token keeps duplicate outer rows separate. Aggregate empty-input states, UNION and per-row ordering/limits are explicit operations. Direct Sail LATERAL aggregate/limit failures are retained.
- Paths expose length, ordered nodes and ordered relationships. Entity lookup joins typed identity lists to canonical graph tables by group/id and ordinal, retaining properties, inherited labels and stored relationship source/target. No graph collection occurs in execution. `length(p)` does not hydrate unused entities. An explicit `[*1]` remains an entity list while a fixed relationship stays scalar. Mixed segments apply relationship uniqueness before whole-path selection.
- Projection carries presentation ordering through hidden slots and removes them from final output and UNION alignment. DISTINCT/aggregate boundaries reset order. WITH predicates precede ordering and slicing.
- Numeric lowering preserves exact mixed integer/float comparisons, integer division toward zero, negative remainder, null propagation, IEEE floating zero behavior, and checked integer binary arithmetic. Expected division-by-zero and overflow errors remain separate outcomes from returned results. The minimum-integer division by minus one follows the [Neo4j integral runtime](https://github.com/neo4j/neo4j/blob/2026.09/community/values/src/main/java/org/neo4j/values/storable/IntegralValue.java). Overflow and integral zero-divisor behavior follow [CypherMath](https://github.com/neo4j/neo4j/blob/2026.09/community/cypher/runtime-util/src/main/java/org/neo4j/cypher/operations/CypherMath.java); mixed comparisons retain the distinction described by [NumberValues](https://github.com/neo4j/neo4j/blob/2026.09/community/values/src/main/java/org/neo4j/values/storable/NumberValues.java).
- This remains an unpublished read-query draft, not complete Cypher/GQL or an audited full LDBC implementation. Existing refusals still name unsupported grammar/contracts; they are not counted as passing executions.

## SNB boundary

The official SNB v1 implementation checkout is pinned at `f9c394a92cd55e535893f6c9907b141d6533c817`. Its development CSV dataset has 10,629 admitted vertices and 18,136 admitted relationships across the selected schema groups. The query track uses unchanged IS1, IS3, IS4, IS5 and IS6 files and verifies their hashes. Dates remain the importer-defined epoch-millisecond integers; empty CSV values remain null; Person languages map to `speaks`.

The CSV oracle evaluates lookups/joins and follows reply ancestry independently of generated SQL and plan operators. Inputs are prepared as fresh Parquet outside the execution timer. Native calls include SQL planning, Parquet scans, all materialization/traversal phases, final result collection and scratch cleanup. The paired protocol is a warmup for each plan followed by ABBA twice; all cells, including empty-result controls, are retained. Shared-host results are reported as optimized/resolved ratios, not absolute benchmark results.

## Reproduce the full source gate

Run `live/gate-semantics.sh` in a clean detached checkout. Set owned external `CARGO_TARGET_DIR` and `GATE_OUTPUT`, the retained native release `SAIL_BINARY`, `GATE_PYTHON`, and `GATE_SNB_CHECKOUT` at the pinned clean commit. The gate covers Python typing/style, Rust default/all-features/release, the earlier native relational/iterative/frontend cases, the new semantics and expected-error cases, refusal/resource controls, and the paired SNB oracle run. A verdict requires unchanged HEAD and a clean checkout at exit.

Source verdict, complete evidence index and consolidated Sem report will be added after the detached gate. Email is authorized from `dick@hurz.net` to `ssinchenko@apache.org`; the Debian SSH address remains pending.
