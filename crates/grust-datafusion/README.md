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

This is relational SQL execution, not a second Cypher interpreter or a rewrite
of graph kernels as joins. Cypher lowering must separately preserve null,
identity, multiplicity, ordering and numeric semantics before selecting this
execution path. SDKs using older DataFusion/Arrow versions keep their native
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

## Cypher lowering under development

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
and extrema semantics. This does not yet lower relationship patterns into joins.

`cypher::GraphSnapshot` captures a validated `ArrowGraphTables` provider pair.
Node and edge plans retain that pair independently of catalog replacement.
Its edge provider adds `__grust_edge_ordinal`, a non-null UInt64 identity unique
within the captured snapshot, preserving parallel edges and optional/repeated
external IDs. Ordinal storage costs eight bytes per edge; existing buffers are
shared. Backend transaction identity and authorization remain caller contracts.
