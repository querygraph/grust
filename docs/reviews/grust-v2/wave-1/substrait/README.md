# Substrait, SQL text, or Spark Connect relations: what Grust should emit

Wave 1 research for the Grust v2 plan agreed on pull request #36. It answers
Sem's open question under "Substrait" in
`../../../sem-research-2026-10-02/grust-model/GRUST_STRUCTURE_PROPOSAL.md`.
Checked 2026-10-03.

## Summary

1. Yes, Grust can emit Substrait. A two-hop plan built from protobuf structs, with no SQL, ran on DataFusion 55.1.0 and on DuckDB 1.5.5 and gave the same rows as SQL (measured).
2. Substrait has no recursion. Variable-length and shortest paths cannot be expressed in it. The same holds for Spark Connect relations. Only SQL text with `WITH RECURSIVE` carries them today, on the engines that run it.
3. Substrait reaches DataFusion, DuckDB (community extension) and Acero. It does not reach Grust's own backends: PostgreSQL, Turso, SurrealDB, FalkorDB and LanceDB have no consumer, and Sail and Spark have none built in.
4. Spark Connect relations reach only Sail and Spark. Grust already reaches both with SQL text inside a Spark Connect `Sql` relation. So relations add no backend.
5. Recommendation: SQL text first, emitted from the new plan through one emitter trait. Substrait second, as an optional emitter written directly against the `substrait` crate, aimed at DataFusion-family engines. Spark Connect relations are not planned until a need appears that SQL text cannot meet.

Marks used below: **[measured]** means this experiment ran it. **[code]** means read from source at the cited line. **[docs]** means read from a specification, documentation or repository, with the date. **[inferred]** means reasoning not checked directly.

## 1. What Grust emits today

The source is `~/src/grust-f1` at tag `v0.24.0` (commit `d2668ec7`) [code].

### Structure

- `crates/grust-cypher/src/pushdown.rs` (5,679 lines) parses and analyzes a query.
  - It then tries ten shape-specific lowerings in a fixed order: node, segment, variable-length, optional, multi-pattern, procedure, subquery, correlated keys, shortest, and pipeline (`lower_single`, lines 4424-4457).
  - The first one that matches wins. If none matches, `plan_read` returns `Ok(None)` (lines 4394-4421), and the backend runs the in-memory reference executor instead.
- Each lowering renders a SQL string through `&dyn SqlDialect`.
- The `RETURN` projection runs in Rust over text rows, through the shared reference projection (`project_text_rows`, for example lines 2198-2211). This covers aggregates, `DISTINCT`, and `ORDER BY` when it is not pushed.
- `UNION` is not sent as SQL. Each arm runs separately, and `combine_union` merges the results in Rust (lines 4295-4300 and 4462).
- An opt-in `COUNT(*)` pushdown lives in `pushdown/scalar_count.rs` (lines 145-161).
- `SqlDialect` (lines 356-480) is pure string configuration:
  - table and column names, quoting and casts;
  - JSON property extraction;
  - string predicates and boolean literals;
  - capability flags: `orders_json_typed`, `recursive_cte_supported`, `shortest_walk_supported`, `json_props_keys_scan`, `integer_series_sql`, `lateral_json_keys_sql`;
  - recursive-walk tokens.
- There are four implementations:

| Dialect                  | Where                                    | JSON access                                | Recursive CTE                                                                                       |
| ------------------------ | ---------------------------------------- | ------------------------------------------ | --------------------------------------------------------------------------------------------------- |
| `SparkDialect` (Sail)    | `pushdown.rs:485-532`                    | `GET_JSON_OBJECT(props, '$.k')` (line 500) | disabled: "Sail 0.7.1 accepts the syntax but cannot resolve the recursive relation" (lines 488-492) |
| `SqliteDialect` (oracle) | `pushdown.rs:538-635`                    | `json_extract` (line 548)                  | yes, and shortest-path walk too (line 616)                                                          |
| `PostgresReadDialect`    | `grust-postgres-core/src/lib.rs:247-337` | `props #>> ARRAY[k,'value']` (line 263)    | yes; no shortest walk, because there is no `rowid`                                                  |
| `TursoReadDialect`       | `grust-turso/src/lib.rs:1609`            | SQLite family                              | yes                                                                                                 |

Other backends do not use this path:

- **Sail.** It sends the SQL as a Spark Connect `Sql` relation (`grust-sail/src/lib.rs:1682`).
- **SQL/PGQ.** Its crate writes its own `GRAPH_TABLE (... MATCH ...)` text (`grust-postgres-pgq/src/lib.rs:245`).
- **Other stores.** SurrealDB builds SurrealQL. FalkorDB sends Cypher through `GRAPH.QUERY`. LanceDB uses `query().only_if(filter)`. pgGraph calls `graph.build`. CocoIndex has no query path.
- **`grust-datafusion`.** It already lowers the Cypher AST straight to DataFusion `Expr` and `DataFrame` values, with no SQL text. It covers node scans and relationship scans, and is pinned to DataFusion 55.0.0 (`crates/grust-datafusion/Cargo.toml`, `src/cypher/mod.rs`). This matters below: it is the one existing "plan, not text" emitter.

### The operator set the SQL actually uses

This is what any output form must carry.

| Operator                                                                   | Where in today's SQL                                                                        | Notes                                                |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| Table scan of `nodes` and `edges`                                          | every leaf                                                                                  | fixed generic tables, not one table per label        |
| Filter: `AND`, `OR`, `NOT`, comparisons, `IS NULL`, `IN (list)`            | `render_predicate`, line 1300                                                               | label and type equality; lists of edge types         |
| Arithmetic `+ - * /` with casts to integer or float                        | `ArithExpr`, lines 141-169                                                                  | division rendered as float division                  |
| String predicates (starts, ends, contains)                                 | dialect `string_predicate`                                                                  | `STARTSWITH`, `instr`, `substr`, `position`, `right` |
| JSON property access                                                       | dialect `json_property`                                                                     | properties are one JSON text column (`props`)        |
| Inner join chain, equality and `OR` conditions                             | segment, lines 2119-2131; undirected uses `OR`, lines 2058-2063                             |                                                      |
| Comma joins with conditions in `WHERE`                                     | multi-pattern, line 3377                                                                    |                                                      |
| `LEFT JOIN` to a derived table                                             | optional, line 3042; subquery, lines 3817-3818                                              |                                                      |
| Correlated scalar subquery with `MIN`                                      | shortest, lines 4161-4167                                                                   |                                                      |
| Lateral table function                                                     | `json_each` / `jsonb_object_keys` (lines 603, 612; PG line 328)                             | key enumeration                                      |
| `SELECT DISTINCT`, `UNION` of two scans, `ORDER BY`                        | procedures, lines 3579-3596                                                                 |                                                      |
| `ORDER BY`, `LIMIT`, `OFFSET`                                              | lines 1278-1284 and 2354-2358                                                               | pushed only when the sort type is known              |
| `COUNT(*)`                                                                 | `scalar_count.rs:151-157`                                                                   | the only aggregate pushed                            |
| `CASE WHEN`                                                                | undirected walk step, lines 2625 and 4109                                                   |                                                      |
| `WITH RECURSIVE` with a string visited set (`instr`, `\|\|`, hex encoding) | variable-length, lines 2666-2673; shortest, lines 4148-4162; `integer_series_sql`, line 629 | uses `printf` and `rowid` on SQLite                  |
| `UNION ALL`                                                                | only inside recursive CTEs                                                                  | top-level `UNION` is combined in Rust                |
| `GROUP BY`                                                                 | not used                                                                                    | grouping runs in Rust                                |
| Window functions                                                           | not used                                                                                    |                                                      |

Wave 3's resolver and optimizer are meant to push more down (Sem: "lower filters to join conditions", join reordering). So the target set is the table above plus `GROUP BY` aggregates, top-level `UNION`, and window functions such as the `row_number()` dense-id step in `../../../sem-research-2026-10-03/grust-design/README.md`, section 4.2. Questions 14 and 10 of the experiment below cover these.

## 2. Substrait, for that operator set

The specification's latest release is **v0.104.0, published 2026-09-27**, and it is still pre-1.0 [docs: `github.com/substrait-io/substrait` releases; `site/docs/spec/versioning.md` at v0.104.0].

- The versioning page says: "Until then, we will remain in the 0.x.x version regime". Breaking changes bump x, and "we may remove previously deprecated fields".
- Releases are automated and weekly. v0.104.0 itself is marked breaking.

### Relations at v0.104.0

Source: `proto/substrait/algebra.proto` at v0.104.0 [docs]. The v0.85.0 copy shipped in the Rust crate was also read [code].

| Need             | Substrait                                                                                                        | Note                                                                                                                                                                   |
| ---------------- | ---------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| scan             | `ReadRel` with a named table, virtual table, local files, extension table or Iceberg table                       | includes `filter`, `best_effort_filter` and a projection mask                                                                                                          |
| filter           | `FilterRel`                                                                                                      |                                                                                                                                                                        |
| project          | `ProjectRel` with an `Emit` output mapping in `RelCommon`                                                        |                                                                                                                                                                        |
| joins            | `JoinRel`: inner, outer, left, right, left and right semi, anti, single and mark; `post_join_filter`; `CrossRel` | `LateralJoinRel` was added in v0.96.0 (2026-07-05). Physical `HashJoinRel`, `MergeJoinRel` and `NestedLoopJoinRel` number their join types differently from `JoinRel`. |
| aggregate        | `AggregateRel` with grouping sets and measures that can carry a filter                                           |                                                                                                                                                                        |
| set              | `SetRel`: union distinct and all, intersection, minus variants                                                   |                                                                                                                                                                        |
| limit and offset | `FetchRel` with `offset_expr` and `count_expr`                                                                   | the integer fields are removed at v0.104.0 and deprecated at v0.85.0                                                                                                   |
| sort             | `SortRel`; `TopNRel` added in v0.88.0                                                                            |                                                                                                                                                                        |
| window           | `ConsistentPartitionWindowRel`                                                                                   | listed under "physical relations"                                                                                                                                      |
| extension points | `ExtensionLeafRel`, `ExtensionSingleRel`, `ExtensionMultiRel` (protobuf `Any` payloads)                          | where graph operators would go                                                                                                                                         |
| shared subplans  | `ReferenceRel` (`subtree_ordinal`)                                                                               | a DAG reference, not recursion                                                                                                                                         |
| subqueries       | scalar, `IN`, `EXISTS`/`UNIQUE`, `ANY`/`ALL` comparisons; outer references                                       |                                                                                                                                                                        |
| expressions      | `IfThen`, `Switch`, `Cast`, `SingularOrList`, lambdas, field references into struct, list and map                |                                                                                                                                                                        |

**Recursion.** No relation in `algebra.proto` at v0.104.0 is recursive, iterative or a fixpoint [docs].

- An issue search for "recursive", "recursive CTE" and "WITH RECURSIVE" found no proposal. GitHub Discussions were not searched.
- The only way to express a walk is an extension relation whose meaning the consumer has to know.

**Functions** are referenced through extension YAML files identified by URNs.

- The plan declares `extension_urns` (anchor and `extension:<owner>:<id>`). Each `ExtensionFunction` names a compound signature such as `equal:any_any` and points to a URN anchor.
- URNs were added in v0.75.0 (2025-09-14, PR #859). URI fields were deleted in v0.85.0 (2026-03-06, PR #971, breaking) [docs].
- Grust would publish its own YAML for anything non-standard, such as JSON property access. URNs are names, not fetchable locations, so every consumer must ship or register the definitions [inferred].

**Types** at v0.104.0 [docs, `type.proto`]:

- integers, floats, string, binary, decimal, temporals, uuid;
- `struct`, `list` and `map`;
- user-defined types.

There is **no JSON or variant type**. Issue #879, "introduce a standard JSON type", has been open since 2025-10-29. A property bag is therefore one of three things:

- a JSON string plus custom functions;
- a `map<string, T>` with one value type;
- a `struct` whose fields the resolved plan knows from the LPG schema.

**Stable and not stable.** The core relations above have been in place for years. Field-level changes still land under 0.x [docs, changelog]:

- the `FetchRel` integer fields were removed;
- URIs were removed;
- the time type was deprecated in v0.84.0.

### The Rust crate

| Crate                  | Version (date)                    | Spec                                                      | Source                                                                               |
| ---------------------- | --------------------------------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `substrait`            | 0.65.0 (2026-08-27) is the latest | v0.102.0, through the pinned `substrait-prost`            | crates.io [docs]                                                                     |
| `substrait`            | 0.63.0 (2026-03-11), used here    | v0.85.0 (`gen/version.in`: describe `v0.85.0-0-g2aaae7c`) | [code]                                                                               |
| `datafusion-substrait` | 55.1.0 (2026-09-11) is the latest | depends on `substrait ^0.63.0`, so spec v0.85.0           | crates.io [docs]; Dependabot PRs to move to 0.65.0 are open (#24255, #24842, #24861) |

So the newest DataFusion speaks a spec that is 19 minor versions behind the current release [docs].

## 3. Who consumes Substrait

The DataFusion row was read from the crate source. The others were read from their repositories on 2026-10-03 unless marked measured.

| Engine                                    | Consumes                                         | Produces                                   | Version                                                                                                                                      | Completeness and gaps                                                                                                                                                                                                                              |
| ----------------------------------------- | ------------------------------------------------ | ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **DataFusion** (`datafusion-substrait`)   | yes                                              | yes                                        | 55.1.0, spec v0.85.0                                                                                                                         | See the gap list after this table.                                                                                                                                                                                                                 |
| **DuckDB** substrait extension            | yes: `from_substrait`, `from_substrait_json`     | yes: `get_substrait`, `get_substrait_json` | community extension, not core; pinned ref `4ea63dd` for DuckDB 1.5.5; repo `substrait-io/duckdb-substrait-extension`, last commit 2026-10-01 | Its producer refuses recursive CTEs ("Not implemented Error: REC_CTE") **[measured]**. It writes a v0.78 version stamp with URNs **[measured]**. Its consumer rejects window functions and DataFusion's aggregate encoding **[measured, part 4]**. |
| **Arrow Acero**                           | yes (C++; PyArrow `pyarrow.substrait.run_query`) | expressions and schemas                    | Arrow 25.0.1 pins Substrait v0.44.0                                                                                                          | Maintenance only. Pre-URN, so likely incompatible with URN-only plans [inferred, not tested].                                                                                                                                                      |
| **Velox**                                 | no longer                                        |                                            | Substrait code deleted 2025-07-01 (#13938)                                                                                                   |                                                                                                                                                                                                                                                    |
| **Gluten** (Spark to Velox or ClickHouse) | yes, internally                                  | yes, from the Spark physical plan          | v1.7.0 (2026-08-26)                                                                                                                          | Uses its own fork of the protos, not wire-compatible with upstream (renumbered relations, custom `GenerateRel` and `WindowGroupLimitRel`). It is an engine-internal format, not an entry point for Grust.                                          |
| **Calcite / Isthmus** (substrait-java)    | Substrait to Calcite `RelNode`                   | SQL or `RelNode` to Substrait              | v0.104.0 (2026-09-27)                                                                                                                        | The readme claims TPC-H and most of TPC-DS. Not run here.                                                                                                                                                                                          |
| **Spark**                                 | not natively                                     |                                            | 4.0, 4.1; JIRA has no Substrait SPIP (only SPARK-47773, open)                                                                                | The substrait-java `spark` module translates between Substrait and Spark plans (Spark 3.4, 3.5, 4.0 builds). It is a JVM library and would need a Connect `RelationPlugin` to receive plans.                                                       |
| **PostgreSQL**                            | no maintained route                              |                                            | `PrimeDataConversion/substrait-postgres`, last commit 2025-06-19, 4 stars                                                                    | effectively none                                                                                                                                                                                                                                   |
| **Sail**                                  | no                                               | no                                         | builds on DataFusion 55.1.0 (`sail-upstream-main/Cargo.toml:173`)                                                                            | See the Sail notes below.                                                                                                                                                                                                                          |
| Arrow Flight SQL, ADBC                    | transport only                                   |                                            | `CommandStatementSubstraitPlan`; `AdbcStatementSetSubstraitPlan`                                                                             | They carry a plan to a server that must consume it.                                                                                                                                                                                                |
| Polars, Comet, Presto                     | no                                               |                                            | Polars #7404 closed as not planned; Comet uses its own protobuf                                                                              |                                                                                                                                                                                                                                                    |

Gaps in DataFusion's Substrait support, read from the 55.1.0 source and its open issues:

- **Producer.**
  - No `RecursiveQuery` (`producer/rel/mod.rs:74-75`; issue #16274, open since 2025-06-06).
  - No `Unnest` (line 73), no `USING` joins, no outer references.
  - The plan's `extension_urns` is always empty (`producer/plan.rs:47`).
  - Every function points to URN anchor `u32::MAX` ("We don't register proper extension URNs yet", `extensions.rs:120-144`).
  - Function names are DataFusion's own ("lt", not "lt:any_any").
- **Consumer.**
  - Resolves functions by name and ignores URNs.
  - Rejects `ReferenceRel`, `HashJoinRel`, `TopNRel`, `LateralJoinRel` and `post_join_filter`.
  - Open issues include #16248 (an epic of conversion issues), #25720, #25366, #25368, #25100, #25208, #14831 ("Substrait generated by Apache Calcite does not run in DataFusion") and #25603.

**Sail** has no Substrait code. A search of `sail-upstream-main` (99ee46f6, 2026-10-02) and `sail-pecan-integrated` (4b88c8fb, 2026-10-02) finds only the `DataFusionError::Substrait` error mapping (`crates/sail-common-datafusion/src/error.rs:158`) [code].

- Upstream rejects Spark Connect extension relations: `RelType::Extension(_) => Err(SparkError::unsupported("extension relation"))` (`crates/sail-spark-connect/src/proto/plan.rs:1339`).
- The fork branch `work/nutmeg-int64-identity` already accepts them. It decodes an `Any` with size limits (`proto/extension.rs:117`) and dispatches by type URL to a handler registry (`sail-plan/src/resolver/query/extension.rs:24`).

For Sail to accept Substrait, it would need one of the following [inferred]:

1. **A Connect extension handler** for a type URL such as `type.googleapis.com/substrait.Plan`. It would call `datafusion_substrait::logical_plan::consumer::from_substrait_plan` with the session state, and resolve named tables against Sail's catalog. Sail's tables live in its own catalog layer, so the consumer needs a `SubstraitConsumer` whose `resolve_table_ref` asks Sail.
   - Upstream would also have to accept extension relations at all. Today it rejects them.
   - This is a small reviewed PR in principle. It would also add `datafusion-substrait` to Sail's dependencies.
2. **Native support** next to the Spark Connect server. This would be a larger change, and a decision for the upstream maintainer.

## 4. The three forms compared

### Backend reach

| Backend                            | SQL text per dialect          | Substrait                                                                    | Spark Connect relations |
| ---------------------------------- | ----------------------------- | ---------------------------------------------------------------------------- | ----------------------- |
| Sail                               | yes, today (`Sql` relation)   | no; needs a Connect extension handler (section 3)                            | yes                     |
| Spark                              | yes (`Sql` relation)          | no; needs a JVM `RelationPlugin` around substrait-spark                      | yes                     |
| PostgreSQL                         | yes, today                    | no maintained consumer                                                       | no                      |
| PostgreSQL SQL/PGQ                 | yes (`GRAPH_TABLE` text)      | no                                                                           | no                      |
| Turso / SQLite                     | yes, today                    | no                                                                           | no                      |
| SurrealDB                          | SurrealQL is its own language | no                                                                           | no                      |
| FalkorDB                           | Cypher text                   | no                                                                           | no                      |
| LanceDB                            | filter strings                | no (Lance uses DataFusion inside, but exposes no Substrait entry) [inferred] | no                      |
| DataFusion (`grust-datafusion`)    | yes                           | yes **[measured]**                                                           | no                      |
| DuckDB (not a Grust backend today) | yes                           | yes, community extension **[measured]**                                      | no                      |

### The other criteria

| Criterion                                     | SQL text per dialect                                                                                                                                                                                     | Substrait                                                                                                                                                                                                                                                                      | Spark Connect relations                                                                                                                   |
| --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Fidelity for the operator set (section 1)     | complete where the dialect has the feature; JSON access per dialect                                                                                                                                      | Every non-recursive operator maps **[measured: hand-built plan; 18 of 18 DataFusion round trips]**. JSON access needs a Grust extension function **[measured: part 3]**.                                                                                                       | Read, Project, Filter, Join, Aggregate, SetOperation, Sort, Limit and Offset exist. JSON access needs `get_json_object` calls [inferred]. |
| Recursion (variable-length, shortest path)    | `WITH RECURSIVE` on SQLite, Turso, PostgreSQL and Spark 4.1 (SPARK-24497, in the [4.1.0 release notes](https://spark.apache.org/releases/spark-release-4.1.0.html)); not on Sail (`pushdown.rs:488-492`) | none in the spec; DataFusion's producer refuses it **[measured, Q19]**; DuckDB's producer refuses it **[measured]**                                                                                                                                                            | none as a relation; only through a `Sql` relation                                                                                         |
| Type fidelity                                 | weakest: everything returns as text (`project_text_rows`); casts per dialect                                                                                                                             | strong for scalars, struct, list and map; no JSON or variant type                                                                                                                                                                                                              | Spark types                                                                                                                               |
| Does the backend still optimize?              | yes, it plans from scratch                                                                                                                                                                               | Yes. DataFusion optimizes the consumed plan. Placement matters, though: with the filter on the `n0` read the plan ran in 155 ms, and with it above the joins (where SQL puts `WHERE`) it got SQL's transitive filter and ran in 46 ms, the same as SQL **[measured, part 1]**. | yes, it resolves and optimizes server side [inferred]                                                                                     |
| Debuggability                                 | readable, and can be pasted into a shell                                                                                                                                                                 | Binary or protobuf JSON. 493 lines of JSON for a two-hop plan (`raw/handbuilt-two-hop-rows.json`). Field references are positional. DataFusion's unparser back to SQL was wrong or failed for 8 of 18 shapes **[measured, part 2]**.                                           | protobuf, named columns, readable with `explain`                                                                                          |
| Dependency weight                             | none                                                                                                                                                                                                     | `substrait` 0.63.0: 41 crates normal, 90 with build dependencies (serde feature on) **[measured]**. `datafusion-substrait` pulls about 310 [measured].                                                                                                                         | Spark Connect protos (Sail's generated code or `spark-connect-rs`)                                                                        |
| Version churn                                 | per engine release                                                                                                                                                                                       | weekly 0.x spec with breaking field removals; DataFusion lags by 19 minors                                                                                                                                                                                                     | slow, tied to Spark releases                                                                                                              |
| Fits "Grust knows nothing about the backends" | Partly. The plan stays neutral, but each dialect is backend knowledge, kept in the emitter.                                                                                                              | Best fit for the format. It does not help reach, since none of Grust's current backends consumes it.                                                                                                                                                                           | Names the backend family (Spark)                                                                                                          |

## 5. The experiment

The experiment is in `experiment/`, a standalone cargo project with its own `[workspace]`. It was built with `CARGO_TARGET_DIR=~/src/reference/build/substrait-exp` and `-j 4`.

| Item                   | Version                                                              |
| ---------------------- | -------------------------------------------------------------------- |
| DataFusion             | `=55.1.0`, to match Sail                                             |
| `datafusion-substrait` | `=55.1.0`                                                            |
| `substrait`            | `=0.63.0`, spec v0.85.0                                              |
| DuckDB                 | v1.5.5, with the community substrait extension `4ea63dd`             |
| Rust                   | 1.97.1                                                               |
| Data                   | LDBC cit-Patents: 3,774,768 vertices, 16,518,947 edges, `bigint` ids |
| Machine                | this laptop, 4 partitions, shared with other agents                  |

The whole run took 25.5 s, with a peak resident set of 1.45 GB (`raw/stderr.txt`).

### Part 1: a hand-built Substrait plan

Source: `experiment/src/handbuilt.rs`.

- It builds Grust's fixed-segment shape `n0 ⋈ e0 ⋈ n1 ⋈ e1 ⋈ n2` from protobuf structs:
  - `ReadRel` with named tables;
  - `JoinRel` inner joins;
  - `FilterRel`;
  - `ProjectRel` with an `Emit` mapping;
  - `AggregateRel` with `count` and `sum`.
- Functions are declared properly, with URNs `extension:io.substrait:functions_comparison`, `functions_boolean`, `functions_aggregate_generic` and `functions_arithmetic`, and with compound names.
- No SQL or DataFusion planner is involved.

| Check                                      | SQL on DataFusion                                                               | Substrait on DataFusion                                       | Substrait on DuckDB |
| ------------------------------------------ | ------------------------------------------------------------------------------- | ------------------------------------------------------------- | ------------------- |
| Rows for `4000000 <= a < 4002000`          | 4,060, digest `35bb4e6daee6919e`                                                | 4,060, same digest                                            | 4,060               |
| Whole graph: count, sum(a), sum(b), sum(c) | 82,152,988 \| 440,634,906,497,932 \| 390,813,393,255,520 \| 321,991,011,040,247 | same                                                          | same                |
| Time, rows query, 5 runs                   | 44-63 ms                                                                        | filter on `n0` read: 154-161 ms; filter above joins: 45-49 ms | not timed           |

The plan is 852 bytes in binary (`raw/handbuilt-two-hop-rows.bin`). The physical plans are in `raw/handbuilt-two-hop-plans.txt` and `raw/handbuilt-two-hop-filter-on-top-physical.txt`.

- With the filter on top, the plan is the same as SQL's, including the inferred `FilterExec: source >= 4000000 AND source < 4002000` on `e0`.
- With the filter at the leaf, DataFusion does not infer it, and the joins become `Partitioned`.

This means an emitter must either leave predicate placement to the engine, or do the transitive inference itself, which is wave 3's "lower filters to join conditions".

### Part 2: Grust's SQL shapes through the DataFusion producer and consumer, and the unparser

Results are in `raw/coverage.jsonl` and `raw/experiment-log.txt`. The DuckDB column is from `raw/duckdb-check.txt`; it compares row counts only.

| Id  | Shape                                          | Rows      | Produce                                            | Consume = SQL | Unparse = SQL                                        | DuckDB runs DataFusion's plan      |
| --- | ---------------------------------------------- | --------- | -------------------------------------------------- | ------------- | ---------------------------------------------------- | ---------------------------------- |
| Q01 | scan, filter, `ORDER BY`, `LIMIT`/`OFFSET`     | 10        | ok                                                 | same          | **differs** (`LIMIT 12 OFFSET 2`)                    | ok                                 |
| Q02 | two-hop inner-join chain                       | 4,060     | ok                                                 | same          | same                                                 | ok                                 |
| Q03 | comma join (multi-pattern)                     | 5,853     | ok                                                 | same          | same                                                 | ok                                 |
| Q04 | `LEFT JOIN` to a subquery (optional)           | 899       | ok                                                 | same          | exec error                                           | ok                                 |
| Q05 | undirected `OR` join                           | 657       | ok                                                 | same          | exec error                                           | ok                                 |
| Q06 | `UNION`                                        | 1,695,137 | ok                                                 | same          | same                                                 | error (aggregate JSON)             |
| Q07 | `UNION ALL`                                    | 6,020,296 | ok                                                 | same          | same                                                 | ok                                 |
| Q08 | `COUNT(*)` over a join                         | 1         | ok                                                 | same          | exec error                                           | ok                                 |
| Q09 | `DISTINCT`                                     | 40,620    | ok                                                 | same          | same                                                 | error (aggregate JSON)             |
| Q10 | `GROUP BY` degree                              | 40,620    | ok                                                 | same          | same                                                 | error (aggregate JSON)             |
| Q11 | correlated `MIN` subquery (shortest tie-break) | 11,437    | ok, after DataFusion decorrelated it               | same          | same                                                 | error (aggregate JSON)             |
| Q12 | `EXISTS`                                       | 40,620    | ok                                                 | same          | **differs** (empty select list)                      | ok                                 |
| Q13 | `NOT IN`                                       | 3,803     | ok                                                 | same          | **differs** (became `NOT EXISTS`, empty select list) | ok                                 |
| Q14 | `row_number() OVER` (dense ids)                | 1,695,990 | ok                                                 | same          | same                                                 | error: window function unsupported |
| Q15 | `CASE` (undirected step)                       | 29        | ok                                                 | same          | same                                                 | ok                                 |
| Q16 | `starts_with`, `strpos`, `\|\|`, hex `encode`  | 2         | ok                                                 | same          | error (BinaryView)                                   | error (LIKE mapping)               |
| Q17 | JSON property access (a UDF)                   | 1         | ok                                                 | same          | same                                                 | error: no such function            |
| Q18 | map access `m['name']`                         | 2         | ok                                                 | same          | same                                                 | error: `get_field` unknown         |
| Q19 | `WITH RECURSIVE` bounded walk                  | 13        | **error: "Unsupported plan type: RecursiveQuery"** |               |                                                      |                                    |

Every produced plan declares zero URNs. All of its function references are dangling (`u32::MAX`). Both DataFusion and DuckDB resolved functions by name regardless.

### Part 3: a non-standard function

- DataFusion's producer wrote `json_get_str` with no URN.
- A consumer session without that UDF failed with "Unsupported function name: \"json_get_str\"" (`raw/experiment-log.txt`).
- DuckDB failed the same way.

So JSON property access in Substrait is only as portable as a Grust-published extension that each consumer implements.

### What the experiment decides

- **Emitting Substrait directly is small and works across two engines.** It took about 300 lines of struct building (`handbuilt.rs`).
- **The DataFusion producer is not a portable Substrait emitter.** It drops URNs and uses non-standard names, and DuckDB refuses 8 of 18 of its plans.
- **Recursion is out in every Substrait producer tried.**
- **Substrait to SQL through DataFusion's unparser is not reliable enough to be an SQL route.**

To repeat:

```sh
cd experiment
CARGO_TARGET_DIR=~/src/reference/build/substrait-exp cargo build --release -j 4
~/src/reference/build/substrait-exp/release/substrait-two-hop ~/src/reference/data/cit-Patents ../raw
python3 duckdb_check.py ~/src/reference/data/cit-Patents ../raw <scratch>/sub.duckdb
```

The second and third commands are run from the report folder, with `raw` as the second argument.

## 6. Recommendation

### Order

1. **SQL text first.** It reaches every SQL backend Grust has today: Sail and Spark (through the Connect `Sql` relation), PostgreSQL, SQL/PGQ, and Turso/SQLite. It is also the only form that carries recursion where the engine has it.
   - The change from today is the input: emit from the optimized plan through one emitter, instead of ten shape-specific lowerings that fall back to the reference.
   - `SqlDialect` stays as the dialect's configuration. Its capability flags become the emitter's capability descriptor.
2. **Substrait second, as an optional emitter.**
   - Behind a feature, written directly against the `substrait` crate, as in `handbuilt.rs`. Do not go through `datafusion-substrait`'s producer.
   - Pin one spec version per Grust release. Declare URNs.
   - Publish a small Grust extension YAML (`extension:io.querygraph:grust`) for property access, and for graph operators as `ExtensionSingleRel` and `ExtensionLeafRel` payloads.
   - Targets: `grust-datafusion` (replacing its direct `Expr` building, or kept next to it); DuckDB, if it becomes a backend; and Sail, once a Connect extension handler for Substrait exists upstream.
3. **Spark Connect relations: not planned.** Every engine they reach already takes Grust's SQL text through the same protocol. They add no recursion and no reach. They would bring back a typed builder only for the Spark family.
   - Reconsider if string building for Spark proves error-prone, or if Spark Connect plans are needed as values, for example to be composed by a DataFrame user.

### Shape of the emitter layer

The goal is that adding a form stays local to one module.

```rust
/// What a target can execute; the emitter consults it, never the backend.
pub struct EmitCapabilities {
    pub recursion: RecursionSupport,        // None | RecursiveCte | GraphOperator
    pub property_access: PropertyEncoding,  // JsonText | Map | Struct
    pub window_functions: bool,
    pub lateral: bool,
    // ...
}

pub trait PlanEmitter {
    type Output;                                   // String, substrait::proto::Plan, ...
    fn capabilities(&self) -> &EmitCapabilities;
    fn emit(&self, plan: &OptimizedPlan) -> Result<Self::Output, Unsupported>;
}
```

- **One plan.** It is the optimized plan of wave 3: relational nodes plus explicit graph-operator nodes, such as bounded expansion and shortest path, as the design note proposed.
- **Emitters.**
  - `SqlEmitter<D: SqlDialect>`: one emitter type, with per-dialect configuration.
  - `SubstraitEmitter`.
  - Later, perhaps `SparkConnectEmitter`.
- **Graph operators.** Each emitter either lowers a graph operator using its capabilities (a recursive CTE in SQL), emits it as an extension relation (Substrait), or returns `Unsupported` with the node. The backend then runs that node itself, relationally or by the local-projection path.
- **No shape list.** Nothing outside the emitters knows a dialect or a protobuf. The reference executor stays as the differential oracle for every emitter.
- **Predicate placement belongs to the optimizer, not the emitter** (part 1). The emitter should write filters where the plan has them. The engine's own rewrites then still apply.

### What remains open

- How property groups appear in the plan:
  - typed struct columns, from the LPG schema;
  - a map;
  - today's JSON text.

  Substrait favors the first. Today's storage is the third. This belongs to the LPG and resolution work.

- The exact Grust extension YAML, and whether graph operators should be Substrait extension relations at all, or stay above the plan.
- Whether the upstream maintainer would accept a Sail Connect extension handler for Substrait (section 3). No proposal has been made.
- Whether DataFusion will fix URN emission (`extensions.rs:120-144`; #11545 is referenced in the code).

## What would change this

- **A recursion construct in Substrait**, such as a fixpoint or recursive relation in the spec, implemented by DataFusion and DuckDB. This would remove SQL's only functional advantage on recursive patterns.
- **Sail accepting Substrait.** If Sail upstream accepted Substrait, by an extension handler or natively, Substrait would reach Sail without SQL strings. It would then be worth moving ahead of SQL for Sail.
- **A Substrait consumer for PostgreSQL, SQLite or Turso.** Today none is maintained. This would change reach completely.
- **SQL dialect maintenance outgrowing one Substrait emitter.** For example, if many more SQL engines were added and their dialect differences outgrew the cost of one Substrait emitter plus consumers.
- **A need for client-built Spark plans.** If Grust users need Spark Connect plans as values, to compose with their own DataFrames, Spark Connect relations would earn a place.
- **The DataFusion producer emitting standard URNs and names.** Going through `datafusion-substrait` would then become reasonable for `grust-datafusion`.

## Limits

- **One graph, one machine, single runs** (five for the timing), on a laptop shared with other agents. The times show shape only.
- **The DuckDB comparison for DataFusion-produced plans checks row counts, not row contents.** The hand-built plans were checked by count and by the four aggregates.
- **Only two consumers were run:** DataFusion and DuckDB. Acero, Isthmus, substrait-spark and Gluten were read about, not run. Acero's incompatibility with URN-only plans is inferred from its v0.44.0 pin.
- **The spec facts are from v0.104.0; the experiment used v0.85.0**, through the crate DataFusion 55.1.0 pins. The newest `substrait` crate, 0.65.0 (spec v0.102.0), was not built.
- **The recursion search covered issues, not GitHub Discussions.**
- **The Q01-Q19 queries are hand-written equivalents** of Grust's SQL shapes, over `v` and `e` tables. They are not the strings Grust renders over `grust_nodes` and `grust_edges` with JSON `props`.
- **Spark Connect relation coverage is from the design note and the protocol, not tested here.** That includes the Spark 4.1 recursive CTE claim, which comes from the release notes.
- **No file outside this folder was changed.** Nothing was committed.

## Files

| File                                                                                         | What                                    |
| -------------------------------------------------------------------------------------------- | --------------------------------------- |
| `experiment/Cargo.toml`, `Cargo.lock`                                                        | standalone project, pinned versions     |
| `experiment/src/handbuilt.rs`                                                                | the hand-built Substrait plans          |
| `experiment/src/main.rs`                                                                     | parts 1 to 3                            |
| `experiment/duckdb_check.py`                                                                 | runs the plans on DuckDB                |
| `raw/experiment-log.txt`, `raw/stdout.txt`, `raw/stderr.txt`                                 | run output, timings, peak memory        |
| `raw/coverage.jsonl`                                                                         | per-query results, errors, unparsed SQL |
| `raw/handbuilt-*.json`, `raw/handbuilt-*.bin`                                                | the hand-built plans                    |
| `raw/handbuilt-two-hop-plans.txt`, `raw/handbuilt-two-hop-filter-on-top-physical.txt`        | logical and physical plans              |
| `raw/df-produced/Q*.json`                                                                    | plans produced by DataFusion            |
| `raw/duckdb-check.txt`, `raw/duckdb-substrait-probe.txt`, `raw/duckdb-produced-two-hop.json` | DuckDB results                          |

## Checked independently

Added by the reviewer of this report. The experiment's DataFusion half was
rerun from the built binary into a scratch directory on 2026-10-03: SQL and
the hand-built Substrait plan returned the same 4,060 rows with the same
digest (`35bb4e6daee6919e`); the filter-above-joins variant matched too; the
`WITH RECURSIVE` shape (Q19) failed at the producer; a consumer without the
JSON function refused the plan. The two code citations checked
(`grust-sail/src/lib.rs:1682`, a Connect `Sql` relation; upstream
`sail-spark-connect/src/proto/plan.rs:1339`, extension relations
unsupported) read as stated.
