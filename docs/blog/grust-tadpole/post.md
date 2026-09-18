# Grust Tadpole: Cypher learns to fold a list

Grust gives Rust applications one property-graph API across memory, embedded databases, SQL systems and remote graph services. Nodes, edges, typed identities, traversals, mutations, schema and graph algorithms are written once against that API; Memory, Sail/Spark, PostgreSQL, pgGraph, PostgreSQL SQL/PGQ, Turso, SurrealDB, FalkorDB, LanceDB and CocoIndex sit behind it, and each adapter states which operations it pushes down, runs natively, answers through the portable reference, or does not support. `grust-cypher` is the portable GQL/Cypher layer over the same model. Tadpole 0.21.0 completes a missing part of that language and makes its reference executor considerably cheaper to run.

See the [repository and API guide](https://github.com/querygraph/grust), the [Grust book](https://firstpair.org/read/grust/), the [GQL profile statement](https://github.com/querygraph/grust/blob/main/docs/GQL_PROFILE_STATEMENT.md) and the full [`CHANGELOG.md`](https://github.com/querygraph/grust/blob/main/CHANGELOG.md).

## Binding forms: `reduce`, comprehensions and general quantifiers

Until this release Grust's Cypher could not fold a list. `reduce(s = 0, x IN xs | s + x)` was a parse error, list comprehensions did not exist, and `any`/`all`/`none`/`single` were accepted in exactly one hard-coded shape in a write statement's `RETURN`. None of this was refused on principle; it had not been built.

Tadpole adds all three forms anywhere an expression is allowed:

```cypher
MATCH (p:Person)
WITH p, [x IN p.scores WHERE x > 0 | x * p.weight] AS weighted
WHERE any(x IN weighted WHERE x > 10)
RETURN p.name, sum(reduce(total = 0, x IN weighted | total + x)) AS total
```

The interesting part is how they were added. The read executor already evaluated a general expression tree, while write `RETURN` classified each projection into a fixed catalog of shapes, each with its own string-slicing parser. Adding a seventeenth shape for `reduce` would have meant reimplementing expression evaluation inside it. Instead there is now one evaluator and one scope rule: a binding form pushes an immutable lexical scope over the row and never modifies the row, read `RETURN`/`WHERE`/`WITH` and write `RETURN` share it, and the old quantifier parser is deleted.

The semantics are pinned by tests rather than prose. An empty list folds to its seed and a `NULL` list yields `NULL`. A `NULL` element is passed to the body, which decides. Quantifiers follow three-valued logic. Binding a name that already exists in the row is a semantic error rather than something precedence resolves. Every element charges one unit of work, so a budget, a cancellation or a deadline stops a long fold between elements, not after it.

Two limits are stated plainly. No SQL lowering exists for these forms yet: every read pushdown planner declines a query that contains one, and the store answers from the reference executor. The embedded Turso differential oracle checks that fallback returns reference-identical rows. And the write shape that was admitted before keeps its earlier exact-equality results, which differ from ordinary three-valued comparison; that compatibility rule applies only to the formerly admitted shape. The feature catalog grows to 72 supported entries of 77; the other five remain intentional strict-write rejections. `Full39075` is still the name of Grust's widest internal profile, not a claim of ISO/IEC 39075 certification.

This is a breaking change for code that matched on `CypherReturnTarget::PropertyListPredicate`, which is replaced by `CypherReturnTarget::Expression`.

## A cheaper reference executor

Memory defines Grust's reference behaviour, and several backends answer through it, so its cost matters. Profiling it found costs that had nothing to do with the queries being asked.

**Clock reads.** Bounded reads measure a graph's serialized size for admission, and the writer that did the counting read the clock once per JSON token. The thread-local read budget read it on every charge and every expression checkpoint, and per-row memory charges read it exactly each time. These now sample the deadline, as work charges already did; an observed expiry stays observed. Work limits, byte limits and cancellation are never sampled. An execution with no deadline pays for neither the counter nor the clock.

**Copies.** A matched start node was deep-copied, property map and strings included, into the candidate list and again into the row. Matched neighbours, bound relationships, variable-length trails and their endpoints, shortest-path reconstruction and path accumulators were deep-copied as well; a variable-length trail was copied in full for every result. Rows now hold an owned graph's elements by reference, and share elements a typed index builds on demand. The logical copy is still charged in full, so budgets admit and reject exactly the same queries.

**Rows and aggregates.** A row was a B-tree map, which allocates a full leaf for a single binding; it is now a key-sorted vector with the same iteration order. `COUNT`, `SUM` and `AVG` fold their arguments as they are evaluated instead of collecting them first.

**Counting bytes.** `grust-core` gains a serializer that adds up compact-JSON lengths without formatting any JSON. It mirrors `serde_json`'s encoding, delegates floats to `serde_json` itself, reports anything it does not model so the caller falls back to the writer, and is pinned to `serde_json` byte for byte by a differential test.

On one macOS laptop, over a 200,000-node ring in release mode, single runs rather than a benchmark suite: an unbounded filtered scan went from 282 ms to 101 ms, the same scan under a bounded policy from 937 ms to 237 ms, a one-hop match from 510 ms to 189 ms, `[:KNOWS*1..3]` from 1.1 s to 0.55 s, and an eight-element `UNWIND` with `sum` from 1.3 s to 0.51 s. Results are identical before and after. A clock read is cheap on that host; where the clock source is paravirtualised the sampling changes matter more, and an earlier measurement of per-unit deadline reads on such a host attributed about 83% of a full-path Cypher query to them. None of this makes the reference executor streaming, and the remaining gap between bounded and unbounded reads is the accounting itself.

## Automatic Cypher routing through DataFusion

`grust_datafusion::cypher::RoutedGraph` captures one graph as a typed index and an Arrow snapshot, admits each query once, and executes single-node scan plans through DataFusion with every physical operator charging candidate work and intermediate bytes against the caller's `ReadQueryPolicy`. Relationship joins, unsupported shapes, small graphs and plans over a limit stay on the reference executor, and explain reports which route was chosen and why DataFusion was declined. A declined route keeps its original admission and deadline through `run_prepared_read_query_indexed`. Large single-batch Arrow tables are split into contiguous zero-copy partitions, because round-robin repartitioning charged every queued slice the full size of its shared parent buffers.

## Full paths from procedures

An independent run of the algorithms benchmark against this work found ordinary Cypher 88 to 97% faster on its Dijkstra and PageRank cells, and one cell that did not move: full-path Dijkstra on a chain, where the cost is materialising millions of path entries rather than per-row overhead. That report led to three changes. A streaming `CALL` no longer deep-copies each yielded list into the row; it borrows the value from the procedure batch. The path output cursor admits work once per path instead of once per entry. And the streaming `SUM` state folds directly. On a 1024-node chain with 524,800 path entries the `UNWIND range(...)` aggregate went from 88 ms to 58 ms locally. The same report measured `reduce` at about 4.7 times the `UNWIND` form on this query. It is now about four times: a fold still pays general expression evaluation and byte accounting per element, and the benchmark rightly keeps the `UNWIND` shape for now.

## Execution accounting without the lock

Cooperative work units and cancellation no longer take the execution mutex. `ExecutionContext` holds both as atomics and admits each charge through a compare-exchange that recomputes the budget against the value it replaces, so enforcement stays exact at per-unit granularity. Memory reservations, peak accounting and wakers still hold the lock.

## Ladybug bulk loads

`grust-ladybug`, an internal adapter that is not published to crates.io, now bulk-loads through `COPY` from a temporary CSV. A caller loading one fresh graph in disjoint chunks can opt out of the per-chunk scan of stored keys, which was quadratic in the chunk count. The mode is off by default, and a key the store already held is then the caller's error.

## Upgrading

Tadpole is a lockstep release: move every direct Grust crate dependency to 0.21.0 together. Code that matched on the removed write-`RETURN` quantifier target needs the one change described above. Live-service backends were not re-qualified for this release, because binding forms never reach a backend planner; the embedded Turso store is the only store exercised against them.
