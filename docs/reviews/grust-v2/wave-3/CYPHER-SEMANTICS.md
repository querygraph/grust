# Cypher semantics and LDBC qualification goal

Branch: `work/grust-v2-cypher-semantics`, based on PR #45.

[Draft PR #46](https://github.com/querygraph/grust/pull/46), stacked on #45.

| Required item                                       | State                                          | Evidence                                                                                                                                                                                                                        |
| --------------------------------------------------- | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| MATCH-wide relationship uniqueness                  | Implemented and source-qualified               | Fixed/ranged comma patterns, repeated variables, optional matches, self loops, parallel arcs and zero-hop cases                                                                                                                 |
| Correlated CALL/subqueries through providers        | Implemented and source-qualified               | Duplicate outer rows, nested bodies, empty aggregates, UNION, per-row LIMIT/order and qualified provider refusal                                                                                                                |
| Full paths/entity lists: length/nodes/relationships | Implemented and source-qualified               | Ordered columnar hydration, complete admitted properties, stored edge endpoints, mixed segments, zero hops and null optional paths                                                                                              |
| Ordering propagation and numeric semantics          | Implemented and source-qualified               | Hidden sort slots, WITH scope/filter/slicing, exact mixed comparisons and eight expected arithmetic errors                                                                                                                      |
| Representative LDBC queries and cost qualification  | Source-qualified in the disclosed subset       | Five unchanged SNB v1 short queries, thirteen bindings, independent CSV oracle, 130 cells including warmups and ABBA twice                                                                                                      |
| Consolidated report and email to Sem                | Report pushed; SMTP service accepted the email | [Sem status](https://github.com/querygraph/grust/blob/36eaf1edcfd80e1d968256522c3b46d6b6df5e5c/docs/reviews/second-string-extension-2026-10-06/SEM-STATUS.md); authorized sender dick@hurz.net, recipient ssinchenko@apache.org |

All runs use native release execution. Gates run in detached clean checkouts.
Failures and capability refusals remain distinct from passed result checks.
This is query qualification, not an audited complete LDBC benchmark result.

## Exact source verdict

Source `6638d9b4b4094f28593439e26f94a75e70264c79`, tree
`f24d1b6dca068f5e2c2b0c3182e49bf6fd1748e5`, passed on native Morrobay
macOS x86-64 with Rust 1.98.1. HEAD was unchanged and the detached checkout
clean at exit. Documentation added later does not extend this verdict to a
prospective merge.

> PASSED Cypher semantics and LDBC source 6638d9b4b4094f28593439e26f94a75e70264c79: Rust default/all-features/release; native relational/iterative/frontend/semantics; exact SNB oracle and ABBA twice

| Gate                                                | Result                                   |
| --------------------------------------------------- | ---------------------------------------- |
| Rust formatting; default/all-features Clippy        | Passed                                   |
| Rust tests, default / all-features / release        | 40 each, passed                          |
| Python Ruff lint/format and strict mypy             | Passed                                   |
| Existing relational / iterative / frontend results  | 92 / 22 / 40 passed                      |
| New semantics results                               | 104 passed; 8 expected arithmetic errors |
| SNB cells, including warmups                        | 130 passed                               |
| Unsupported-contract diagnostics                    | 18 refused before execution              |
| Resource/cancellation/quoting/managed-pool controls | 19 passed                                |

[Source receipt](evidence/cypher-semantics/source-gate.json) records the exact
command, source, environment and raw-artifact hashes. [Gate log](evidence/cypher-semantics/native-gate.log),
[semantics programs](evidence/cypher-semantics/semantics/queries.json) and
[results](evidence/cypher-semantics/semantics/receipt.json) retain the evidence.
Expected arithmetic errors are successful error-contract checks, not returned
results. Each owned native server was terminated with SIGTERM after session
closure; receipts retain exit `-15`, no session-shutdown error and unchanged
binary hashes.

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

## Cost observations on the shared native host

Two configured workers and a fair 256-MiB Sail-managed pool were used. There
was no 32-GiB operating-system cap. The pool governs managed allocations,
not whole-process RSS. The shared-host protocol is a warmup for each plan
then resolved/optimized/optimized/resolved twice, each cell in a fresh
execution scope. Four measured cells per variant form each median.

The ratio below is optimized median divided by resolved median. Values below
one mean less elapsed time for the optimized variant within this protocol.
The development dataset is small; these measurements do not establish
large-graph throughput or an engine comparison.

| Query | Binding/control | Optimized / resolved | Optimizer estimate |
| ----- | --------------- | -------------------: | -----------------: |
| IS1   | 8796093022220   |                0.876 |               5356 |
| IS1   | absent (-1)     |                0.890 |               5356 |
| IS3   | 8796093022220   |                0.987 |              21641 |
| IS3   | absent (-1)     |                0.973 |              21641 |
| IS4   | 343597383680    |                0.954 |              56996 |
| IS4   | 206158430246    |                0.954 |              56996 |
| IS4   | absent (-1)     |                0.992 |              56996 |
| IS5   | 343597383680    |                0.981 |             115322 |
| IS5   | 206158430246    |                0.978 |             115322 |
| IS5   | absent (-1)     |                0.993 |             115322 |
| IS6   | 343597383680    |                0.969 |            Unknown |
| IS6   | 206158430246    |                0.983 |            Unknown |
| IS6   | absent (-1)     |                0.997 |            Unknown |

The generic optimizer cost is an internal metadata-based estimate, not
seconds. NDV equality estimates and the conservative default selectivity are
disclosed in each rewrite trace. IS6's iterative work retains an unknown
cost; it is not reported as zero. Optimization remains optional and both
program variants must return the same exact oracle answer.

[All normalized cells](evidence/cypher-semantics/snb/receipt.json),
[ratios and ranges](evidence/cypher-semantics/snb/ratios.json),
[query text, parameters, output types, SQL/programs, estimates and traces](evidence/cypher-semantics/snb/queries.json),
and [pinned schema/table request](evidence/cypher-semantics/snb-request.json)
are published. Absolute execution and compiler times are omitted from the
public artifacts; all warmups and measured outcomes are retained. Verbose
explain dumps are replaced with hashes; full raw artifacts remain at the
external gate-output location in the source receipt and can be regenerated
from the pinned sources. No inference about whole-process RSS is made.

## Preserved failures and remaining admission

The [development failure index](evidence/cypher-semantics/development-failures/index.json)
retains failed SQL probes, wrong numeric results, hydration SQL/schema errors,
provider-depth stack overflow, iterative binding-shape panics and an input
loader failure. These were probes on unfrozen development source, not failed
verdicts on the final source commit. Two early compiler refusals have no
retained stdout log; the index identifies that limitation.

Native LATERAL aggregation and correlated LIMIT failed; the implementation
uses an explicit materialized outer-row domain and partitioned operations.
`from_json` of an empty struct caused a cancelled stream in its probe; the
implementation uses `struct()` instead. The cancellation's initiating cause
was not diagnosed. Raw integer overflow returned an incorrect wrapped value
in the probe; checked decimal arithmetic now raises the expected error.

[Refusal fixtures](evidence/cypher-semantics/refusals.json) preserve unsupported
contracts. Ranged/materialized-path WHERE, updates, comprehensions,
quantifiers/indexing, unknown function/provider overloads and multipart USE
remain outside the admitted frontend. A path is an explicit typed wire
Struct/list contract in this draft, not a claim to implement every Cypher
value operation. Source-level resolver span attribution, full language
conformance, a complete SNB workload, process-cluster query qualification and
production API migration remain further work. The required four features
were implemented; these limits are not substitutes for those implementations.

## Consolidated delivery

[Sem's consolidated progress report](https://github.com/querygraph/grust/blob/36eaf1edcfd80e1d968256522c3b46d6b6df5e5c/docs/reviews/second-string-extension-2026-10-06/SEM-STATUS.md)
covers the earlier research, native algorithm contrasts, fork PRs, Grust
release, all Wave 3 drafts, Cosmolang and this query qualification. Email
uses Debian's existing Resend SMTP configuration. The [submission receipt](evidence/cypher-semantics/email-submission.json) records
SMTP acceptance at 2026-10-08T05:05:11.115165+00:00, with both reports
attached. Recipient inbox delivery was not independently confirmed. The
[cleanup receipt](evidence/cypher-semantics/cleanup.json) records removal of
the two owned temporary targets and detached gate checkout.
