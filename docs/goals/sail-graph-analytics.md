# Graph analytics on Sail: replicating and exceeding Neo4j's Spark Connector and Graph Analytics

Status: proposal, 2026-09-19. Nothing here is built; every claim about Neo4j
is from its own documentation and press material (sources at the end), and
every claim about Grust is from the repository at `2bf244e` and the
published benchmarks.

## 1. What Neo4j positions, exactly

Neo4j sells two things around Spark and analytics, and they are positioned
differently.

### 1a. The Neo4j Connector for Apache Spark

A bridge. Apache 2.0, "process and transfer data between Neo4j and other
platforms"; connector 6.0 targets Spark 4.0–4.1 / Scala 2.13 / Java 17 and
Databricks 17.3 LTS (5.x for Spark 3.4–3.5). The database stays the system
of record; Spark is the ETL and ML side.

- **Read**, three ways: `labels` (nodes with properties), `relationship`
  (with `relationship.source.labels` / `relationship.target.labels`, the
  source and target nodes flattened into the row), or `query` (any Cypher
  `MATCH`). Schema comes from sampling unless the caller declares one;
  the docs call sampling "potentially an expensive operation".
- **Write**: `Append` builds `CREATE`; `Overwrite` builds `MERGE` and
  requires `node.keys` (and `relationship.source.node.keys` /
  `relationship.target.node.keys`); `query` mode takes user Cypher. "A write
  is not a single transaction": one transaction per `batch.size` rows per
  partition.
- **Streaming** (Structured Streaming): reads detect new rows through a
  user-maintained "unique, monotonically increasing" property
  (`streaming.property.name`, `streaming.from` = `NOW` | `ALL`); writes need
  `checkpointLocation` and `save.mode`. Documented limit: two writes in the
  same millisecond can lose one.
- **GDS from Spark**: the `gds` option names a procedure
  (`gds.graph.project`, `gds.pageRank.stream`, `…estimate`) and `gds.*`
  carries its configuration; results come back as a DataFrame. Only
  `stream` mode is supported, and "GDS reads also support a single
  partition only" — the algorithm runs on the Neo4j server and its
  result is drained through one partition.

The connector's job, then, is to move rows in and out of a database that
does the graph work. Its ceilings are the database's: one MERGE
transaction per batch, sampling for schema, a single partition for
algorithm results, a hand-rolled monotonic property for change capture.

### 1b. Neo4j Graph Analytics (Aura Graph Analytics; the GDS library)

The other half is the detachment of the algorithm engine from the database.
Announced 2025-05-07 as "the industry's first graph analytics offering for
any data platform": a "serverless offering with 65+ ready-to-use
algorithms", "Zero ETL", works "with any data source" — AuraDB,
self-managed Neo4j, pandas, Databricks, Snowflake, BigQuery, OneLake —
"requires no infrastructure setup and no prior experience with graph
technology or Cypher", "pay-as-you-use", and the marketing numbers: "2X
greater insight precision", "up to 80% model accuracy", "75% less code",
"insights twice as fast as open-source alternatives".

The mechanics, from the docs:

- A **session** "runs as an isolated Aura instance, with no memory or
  compute resources shared with your data store": a provisioned in-memory
  box sized 2 GB (free) to 512 GB, TTL up to 7 days, billed per use with a
  10-minute minimum, up to 100 concurrent sessions.
- The Python client (`graphdatascience`) is the interface: `GdsSessions`,
  `get_or_create(session_name, memory=SessionMemory.m_4GB, ttl,
  db_connection | cloud_location)`. A session is *attached* to an AuraDB
  or self-managed instance, or *standalone* (no database).
- **Projection** copies a graph into the session: `gds.graph.project.native`
  from a database, `gds.graph.project.cypher` (with
  `gds.graph.project.remote()` inside the query for the remote case),
  `gds.graph.construct` from pandas DataFrames, and platform integrations
  that ship the data to the session.
- **Algorithms** run in three modes: `stream` (rows back), `mutate`
  (a property on the in-session graph), `write` (back to the database —
  "Attached/Self-managed only"). So "zero ETL" is precise in one
  direction: the data is *read* from anywhere, then copied into the
  session; writing results back lands in Neo4j, or comes out as rows.

The position: *your data can stay where it is; the graph engine is ours,
in-memory, serverless, and priced by the session.* GDS's 65+ algorithms
are the moat; the session is the product.

## 2. What Grust and Sail already have

Sail is a Spark Connect–compatible engine written in Rust on DataFusion:
PySpark clients speak to it unchanged, and it executes SQL and DataFrame
plans in process. Grust already meets it at that boundary:

- `grust-sail`: a `GraphStore` over Sail through Spark Connect (gRPC
  `ExecutePlan`), storing the universal graph shape in Delta tables
  (`grust_nodes`, `grust_edges`) plus typed per-label tables from a
  declared `GraphSchema`, staging Arrow batches as temp views before
  `MERGE`, and pushing filters and typed `ORDER BY` into Sail SQL. The
  Cypher layer (`grust-cypher`) plans reads and mutations for it
  (`sail_cypher_mutation_plan`, `run_read_query_on_named_graph`).
- `grust-datafusion`: DataFusion 55 providers over Grust's Arrow 59 tables,
  with explicit working-memory admission and optional spill; the
  automatic Cypher-to-DataFusion read routing goal is complete
  (`docs/goals/cypher-datafusion-execution.md`).
- `grust-algorithms` + `grust-algorithm-procedures`: native kernels over a
  CSR projection with Arrow in and Arrow out — `bfs`, `dfs`,
  `multiSourceBfs`, `dijkstra`, `shortestPaths`, `wcc`, `scc`, `pagerank`,
  `degree`, `topologicalSort`, `projectionStats`, `estimateCsr` — each with
  an independent oracle, callable from Rust, from Cypher as
  `grust.algorithms.*` through the procedure registry, and with per-unit
  work charging, exact budgets and cancellation (`grust-procedures`).
- `grust-arrow`: shared buffer ownership across Arrow 55/58/59 so a result
  retains its reservation without copying (Brine), and ADBC.
- Measurements, published: full-path Dijkstra on a 65,536-node chain,
  Grustcat 16.7 s against Neo4j Community + official GDS 194.1 s (11.6×;
  1.03 s against 11.9 s at 16,384), same container limits; in the strain
  benchmark grust-memory beats Neo4j over Bolt in every same-machine pair
  on loading (27× median), hub fan-out (85×), hot-node writes (111×), cold
  start and p99, matches its reach at com-Orkut (117 M edges) and sits at
  5.4 GB against Neo4j's 4.9 GB there.

What is missing is the packaging that Neo4j sells: a DataFrame-facing
connector, a projection-and-session surface, a Python client shaped like
the one analysts already know, and breadth of algorithms.

## 3. The proposal

Two products, mirroring Neo4j's two, on one engine.

### 3a. `grust` as a Sail data source: the connector, without the database

The Neo4j connector moves rows between Spark and a database. On Sail the
graph *is* lakehouse tables, so the connector collapses into a data source
that Sail executes in process:

| Neo4j connector | Sail + Grust | Same or better |
|---|---|---|
| `format("org.neo4j.spark.DataSource")`, `url`, credentials | `format("grust")` with a graph name; storage is Delta/Parquet/Iceberg the Sail session already reads | no second system, no credentials to a database |
| `labels` read | `grust.nodes` (label) → the typed node table; schema declared, never sampled | typed columns from `GraphSchema`, no sampling cost |
| `relationship` read with flattened endpoints | `grust.edges` (type) with source/target columns joined from the typed node tables in DataFusion | a join the engine plans and pushes, not a Cypher string |
| `query` (Cypher `MATCH`) | `grust.cypher(query)` → `grust-cypher` plans the read and lowers it to a DataFusion plan (the completed routing goal); anything not lowerable runs on the reference executor with a bounded-read budget | pushdown by construction: filters, projection, limit, top-N and aggregates stay in DataFusion |
| `Append` = `CREATE`, `Overwrite` = `MERGE` with `node.keys` | `mode("append")` inserts; `mode("overwrite")` is `MERGE` by declared keys, the path `grust-sail` already stages; one Delta commit per write, not one transaction per batch per partition | atomic writes, parallel edges kept by identity |
| streaming via a user-maintained monotonic property | Delta change data feed as the source; no property to maintain, no millisecond-collision limit | exactly-once by the table's own log |
| `gds` option: server-side procedure, stream only, one partition | §3b: the algorithm runs in the Sail process on a projection; results are a partitioned DataFrame | parallel result consumption; `mutate` and `write` exist |

Deliverable: a `grust-sail-source` crate registering with Sail's table
provider / table function extension points (to be confirmed against
Sail's current extension API; if Sail exposes DataFusion `TableProvider`
registration, `grust-datafusion` already produces those providers), a
PySpark-side `spark.read.format("grust")` / `df.write.format("grust")`
that needs no Python package, and Structured Streaming on Delta CDF.

### 3b. Graph Analytics in the query engine: the session, without the copy

Aura's design copies the graph into a separately billed in-memory
instance. In Sail the projection is built inside the engine that already
holds the DataFrame, from any table Sail can read, and the algorithm's
output is a DataFrame the same session can write anywhere Sail writes.

| Aura Graph Analytics | Sail + Grust | Same or better |
|---|---|---|
| session = isolated Aura instance, 2 GB–512 GB, TTL, 10-min minimum billing | session = the Spark Connect session, with the projection admitted against an explicit memory budget (`grust-procedures` reservations, `estimateCsr` for sizing) | no separate instance to provision or pay for; the budget is a number, refused before allocation |
| `gds.graph.project.native` / `.cypher` / `.remote` / `construct(pandas)` | `grust.graph.project(nodes_df, edges_df, orientation, weight)` from any DataFrame — a Delta table, a Parquet scan, a Snowflake/BigQuery read, a Cypher result — into the CSR projection | the "any data source" claim is literal: no remote copy into a second instance; a 117 M-edge graph projects into ~5 GB |
| 65+ algorithms, `stream` / `mutate` / `write` | 12 today (§2), each with an oracle; `stream` returns a DataFrame; `mutate` adds a column to the projection; `write` writes the DataFrame to any Sail sink (Delta, Iceberg, Snowflake, …) | `write` works standalone — in Aura it needs an attached Neo4j |
| Python client `graphdatascience`: `GdsSessions`, `gds.page_rank.mutate(G, …)` | a `grustanalytics` Python package with the same verbs over PySpark (`sessions.get_or_create`, `G = gds.graph.project(...)`, `gds.page_rank.stream(G)` → DataFrame) | familiar surface; runs on DataFrames at cluster scale, not pandas |
| "no Cypher" | SQL, DataFrames, or Cypher — the caller's choice; `grust.algorithms.*` is also a Cypher procedure | one kernel, three front ends |
| results per session, then deleted | results are tables; projections are cached per session with TTL | lineage stays in the lakehouse |

Deliverable: table functions `grust_project`, `grust_pagerank`, … over
DataFusion plans (the kernels take Arrow, return Arrow), the projection
cache keyed by session, and the Python package.

### 3c. Where "exceed" is already measured, and where it is not

Measured, publishable now: full-path Dijkstra 11.6× faster than GDS on the
same container limits; loading, fan-out and hot-node writes 27–111× faster
than Neo4j over Bolt in the strain harness; equal reach at 117 M edges;
memory within 10% of Neo4j's container at that scale, in process. Exact
budgets and cancellation at per-unit granularity, which GDS's `estimate`
procedures approximate.

Not measured, and the honest gap: **breadth**. GDS ships 65+ algorithms
across centrality, community detection, similarity, path finding, node
embeddings and ML pipelines; Grust ships 12, all in path finding,
components, centrality-lite and degree. The roadmap in
`docs/GENERALIZED_ALGORITHMS.md` already sequences the rest (P2: A*,
Bellman-Ford, betweenness, closeness, eigenvector, triangles, k-core; P3:
communities — Louvain, Leiden, label propagation — similarity, flow; P4:
embeddings). Parity in breadth is the long pole and cannot be claimed
early; the order should follow GDS usage — WCC and PageRank (done),
Louvain/Leiden, node similarity, betweenness, FastRP — each with the same
oracle discipline.

The performance claims Neo4j makes ("2X precision", "80% accuracy", "75%
less code") are about outcomes of using graph features in ML, not engine
speed; they are not ours to contest and should not be mirrored.

## 4. Phases

1. **Connector parity (Sail data source).** `grust.nodes` / `grust.edges` /
   `grust.cypher` reads with DataFusion pushdown; `append` / `overwrite`
   writes by declared keys; Delta CDF streaming. Acceptance: the strain
   harness's Sail lane and the queries benchmark run through
   `spark.read.format("grust")` with results identical to the Grust API
   path. Requires confirming Sail's extension points for a custom source.
2. **Analytics surface.** `grust.graph.project` from DataFrames, the twelve
   algorithms as table functions with `stream` / `mutate` / `write`, the
   projection cache and memory admission, the Python package mirroring
   `graphdatascience` verbs. Acceptance: the algorithms benchmark adds a
   "Grust on Sail" participant and reports it beside GDS.
3. **Breadth.** The P2/P3 algorithms in GDS-usage order, each with an oracle
   and an entry in the algorithms benchmark; sessions and TTLs; ADBC out.
4. **Positioning.** Publish the connector and analytics pages with the two
   comparison tables above, every cell measured, and the breadth gap
   stated with the roadmap — the same discipline as the strain page.

## 5. Risks and unknowns

- Sail's public extension API for custom data sources and table functions
  in Rust: to verify first; if absent, the interim path is SQL table
  functions over `grust-datafusion` providers registered at session start.
- Projection cost at scale: the in-process reference loads 1 M edges/s
  and holds com-Orkut in 5.4 GB; DataFrame → CSR needs the same measured,
  not assumed.
- Write-back semantics: Neo4j needs a database; our `write` is a table
  write, which is simpler but must define identity for `mutate` results
  joined back to source rows (node ids, not projection ordinals — the
  algorithms benchmark found exactly this defect once).
- Algorithm breadth and ML/embeddings: years of work if parity is the
  bar; the proposal claims parity on the engine and the surface, not on
  the catalog, until each entry is measured.

## Sources

- Neo4j Spark Connector docs: overview, reading, writing, streaming, GDS
  integration — https://neo4j.com/docs/spark/current/ ,
  https://neo4j.com/docs/spark/current/reading/ ,
  https://neo4j.com/docs/spark/current/writing/ ,
  https://neo4j.com/docs/spark/current/streaming/ ,
  https://neo4j.com/docs/spark/current/gds/
- Aura Graph Analytics docs — https://neo4j.com/docs/aura/graph-analytics/
- graphdatascience client, Graph Analytics Serverless —
  https://neo4j.com/docs/graph-data-science-client/current/graph-analytics-serverless/
- Press release, 2025-05-07 — https://neo4j.com/press-releases/aura-graph-analytics/
  (coverage: https://siliconangle.com/2025/05/07/neo4j-goes-serverless-bringing-graph-analytics-data-source/)
- Grust: `docs/GENERALIZED_ALGORITHMS.md`, `docs/arrow-pipelines.md`,
  `docs/goals/cypher-datafusion-execution.md`, `crates/grust-sail`,
  `crates/grust-datafusion`, `crates/grust-algorithms`
- Benchmarks: adversarial-graph-algorithms
  `docs/blog/graph-algorithms-full-paths/post.md`; adversari.al/graph/strain
