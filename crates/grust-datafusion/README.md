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
