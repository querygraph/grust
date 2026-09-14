# Grust DataFusion

An optional shared **DataFusion 55** foundation for native Arrow 59 pipelines.
The facade exposes it with `features = ["datafusion"]`. It shares Arrow tables
with `grust-arrow` and uses upstream DataFrames, providers and result streams.

`DataFusionEngine` provides:

- Explicit working-memory, parallelism, batch-size and spill settings.
- Native `ArrowTable` registration without IPC or payload copies.
- Validated graph registration as `<catalog>.graph.nodes` and `.edges`.
- Upstream table-provider registration preserving backend pushdown hooks.
- Read-only SQL planning and streaming results, plus direct context access for
  native functions, catalogs, object stores and expression extensions.
- `BlockingReader`, an explicit demand-driven bridge for synchronous Arrow/ADBC
  consumers on an ordinary or blocking thread. It needs a caller-owned live
  Tokio runtime; it introduces no hidden worker or prefetch queue.

The optional Cypher bridge lowers the existing AST into typed plans. Its admitted
scalar domains preserve null, identity, multiplicity, ordering and exact Int64
semantics. SDKs using older DataFusion/Arrow versions keep their native
execution paths until a separately verified compatible adapter is available.

Working-memory pools are not RSS caps and upstream does not account for every
allocation. Input tables and caller-retained results require caller admission.
Spill is disabled unless a directory and limit are explicitly configured.
Read-only SQL options do not sandbox caller-installed providers or functions.

See [Arrow architecture](../../docs/arrow-pipelines.md) and the
[active engineering goal](../../docs/goals/arrow-performance-parity.md).

## Example

With facade features `datafusion` and a Tokio runtime, a native table can be
queried without an IPC round trip:

```rust
use grust::{arrow::ArrowTable, datafusion::{DataFusionEngine, ExecutionOptions, SpillPolicy}};
use grust::datafusion::datafusion::arrow::array::{ArrayRef, Int64Array, RecordBatch};
use std::{num::NonZeroUsize, sync::Arc};

async fn query() -> Result<(), Box<dyn std::error::Error>> {
    let engine = DataFusionEngine::new(ExecutionOptions {
        working_memory_bytes: NonZeroUsize::new(64 << 20).unwrap(),
        target_partitions: NonZeroUsize::new(2).unwrap(),
        batch_rows: NonZeroUsize::new(4096).unwrap(),
        spill: SpillPolicy::Disabled,
    })?;
    let batch = RecordBatch::try_from_iter([
        ("weight", Arc::new(Int64Array::from(vec![3, 5, 8])) as ArrayRef),
    ])?;
    engine.register_table("input", ArrowTable::from(batch))?;
    let stream = engine.execute_stream("SELECT SUM(weight) FROM input").await?;
    // Consume this native stream asynchronously, or pass it to BlockingReader
    // on an ordinary/blocking thread using a live caller-owned runtime.
    drop(stream);
    Ok(())
}
```

## Explicit Cypher execution

The optional `cypher` feature exposes typed expression and single-node scan
lowering through `cypher::lower_node_scan_with_parameters`. Supply the existing
parsed Cypher AST, an immutable native node-table DataFrame, and parameters.
The planner performs semantic analysis and returns `None` for unsupported query
shapes. It constructs DataFusion expressions directly without SQL serialization.

Current lowering covers scalar Bool/Int/String/null predicates, inline property
maps, projections, DISTINCT, count variants and grouping, integer/string MIN/MAX, projected-alias
ordering, and literal/parameter pagination. Output names reuse the portable
Cypher contract. Duplicate output names remain unsupported pending result
remapping. Floats, mixed types, arithmetic, joins and other query forms remain
outside this initial lowering surface.

This is not automatic routing and does not enforce `ReadQueryPolicy`. Provider
snapshot/schema validity and caller resource admission are prerequisites.
DataFusion runtime limits alone do not implement Cypher's candidate-work,
intermediate-copy and serialized-output budgets. The automatic execution goal
requires these boundaries to be integrated and qualified before route selection.

`ExpressionBindings` resolves graph variables to typed physical expressions.
`lower_expression_with_bindings` and `lower_aggregate_with_bindings` share this
contract so caller-prepared inputs with multiple bindings reuse scalar, count
and extrema semantics.

`cypher::GraphSnapshot` captures a validated `ArrowGraphTables` provider pair.
Node and edge plans retain that pair independently of catalog replacement.
Its edge provider adds `__grust_edge_ordinal`, a non-null UInt64 identity unique
within the captured snapshot, preserving parallel edges and optional/repeated
external IDs. Ordinal storage costs eight bytes per edge; existing buffers are
shared. Backend transaction identity and authorization remain caller contracts.

`GraphSnapshot::directed_relationships` constructs lazy typed endpoint joins
for node/relationship/node bindings. `RelationshipPlan` retains
a `GraphBindings` resolver for scalar/aggregate composition and physical edge
identity. This operator preserves loops and parallel relationships.
`plan_relationship_scan` lowers parsed fixed-length MATCH/WHERE/RETURN
patterns with named or anonymous elements, node labels and relationship types.
Undirected patterns are also admitted: both orientations preserve the same
physical edge identity, and self-loops occur once.
It shares projection, grouping, count/extrema, DISTINCT, ordering and pagination
with the node planner. Optional
matching, variable-length traversal and automatic routing remain unsupported.

Inline scalar property maps on both endpoint nodes and relationships use the
same predicate compiler as node scans. Literal and parameter values are admitted;
correlated expressions remain unsupported. Missing properties and null equality
retain the portable executor's matching behavior.

Repeated endpoint variables constrain the pattern to self-loops. They use one
node join and endpoint equality; the undirected form needs no reverse branch.
Node and relationship variables must remain distinct.

Anonymous node and relationship elements receive private, collision-free
bindings after semantic analysis. Named bindings remain borrowed during name
resolution. Anonymous node scans retain label and inline-property constraints.

`GraphSnapshot::plan` provides one parsed-Cypher planning entrypoint. Its
`QueryPlan` records the selected `PlanKind` and either a typed DataFrame or an
explicit unsupported reason. Invalid queries remain errors. This chooses a
compiler from the query shape; cost-based executor selection and read-policy
admission are still required before ordinary Cypher can route automatically.

`decode_result_batch` converts supported native scalar batches into ordinary
`CypherResultTable` rows. It preserves column order/names, nulls and exact Int64
values, validates types before allocating rows, and resolves array types once
per column. Unsupported types fail without coercion. Owned rows and strings
require caller allocation/output admission; Arrow/ADBC consumers can keep the
native batches directly.

`collect_result` consumes a typed DataFrame incrementally into a portable table
with cumulative row and serialized JSON output limits. It checks rows before
decoding and counts encoding bytes without building a JSON buffer. The accounting
includes columns, delimiters, escaping and inter-row commas across batches.
Errors abort without returning partial output or retrying. One decoded batch,
input/working memory, candidate work and deadlines still need separate admission;
this is output enforcement, not the complete Cypher read policy.

`GraphSnapshot::execute` accepts Cypher text, parameters and explicit
`OutputLimits`, selects the typed compiler and returns an ordinary result table.
`CypherExecution` separates completed execution from unsupported queries that
never executed. Parse, semantic, execution and output-limit errors propagate
without fallback. This explicitly selects DataFusion; query/input admission,
candidate work, intermediate memory, deadlines and cost-based routing remain
separate integration requirements.

`RelationshipPlan::join_trail` composes plans through shared node bindings and
excludes physical edge reuse across all joined parts. Parallel edges remain
distinct. Plans must come from the same captured snapshot; cloned handles retain
that identity. Physical columns are renamed before composition to avoid alias
collisions. The parsed path planner composes these operators for fixed-length paths;
variable-length lowering and path-resource admission remain separate work.

Fixed-length paths reuse the shared RETURN and predicate compilers after trail
composition. Labels, relationship types, inline maps and repeated nodes constrain
the complete path, with physical edge uniqueness across all segments. Direction
may differ per segment. Variable-length bounds and named path values remain
unsupported; path execution costs still need measurement.

### Shared cancellation and deadlines (unreleased)

`ExecutionContext::cancelled()` is a runtime-independent notification shared by
procedures and relational execution. `grust_datafusion::run_cancellable` races
an operation with that notification and the context's absolute deadline.
`GraphSnapshot::execute_with_context` applies it through complete Cypher result
consumption. The operation and its owned streams are dropped on cancellation or
deadline; errors are never retried. Dropping one wrapper unregisters its waiter
without cancelling sibling work. A deadline needs Tokio's time driver.

Control is cooperative: synchronous work within one poll is not preempted, and
providers/kernels must checkpoint during computation. Wrapping stream creation
alone does not control later consumption. These methods do not charge candidate
work or intermediate allocations and do not establish complete read-policy
admission or automatic routing.

`control_stream` retains cancellation and deadline control for an Arrow stream's
whole lifetime. `DataFusionEngine::execute_stream_with_context` controls both
SQL preparation and the returned stream. Batches pass through without buffer
copies, queues or worker tasks. Completion or the first error immediately drops
the provider stream and timer; subsequent polls remain finished. The controlled
stream can feed `BlockingReader` and ADBC ingestion directly.

### Prepared read admission (unreleased)

`grust_cypher::PreparedReadRequest` owns the validated AST, policy and original
absolute deadline, borrows the admitted immutable parameters, and retains any
application registry generation. The bounded reference executor uses its
request, graph/index and output checks. Indexed graph checks reuse the cached
exact serialized size; parameter/output counting does not allocate encoded JSON.
Oversized parameters fail before graph inspection. Preparation does not authorize
or bind a backend snapshot, install execution budgets, or qualify a DataFusion
route. Route-specific candidate/intermediate accounting must still be enforced.

### Exact snapshot statistics (unreleased)

`GraphSnapshot::statistics()` returns exact node/edge row counts, original input
batch counts and the logical bytes added for UInt64 relationship ordinals. These
are cached during capture and read in constant time without a provider scan or
graph export. Cloned snapshots keep identical statistics; session catalog
replacement cannot change them. Batch counts do not claim execution parallelism.
Selectivity, join cardinalities, serialized graph size and total memory are not
inferred from these counts. Automatic routing still requires qualified costs and
complete resource admission.
