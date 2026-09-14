//! Immutable provider pairs for typed graph planning.
use crate::DataFusionEngine;
use datafusion::{
    arrow::{
        array::UInt64Array,
        datatypes::{DataType, Field, Schema},
        record_batch::RecordBatch,
    },
    common::{DataFusionError, Result},
    dataframe::DataFrame,
    datasource::TableProvider,
    execution::context::SessionContext,
};
use grust_arrow::{ArrowGraphTables, ArrowTable};
use std::sync::Arc;

/// Reserved physical relationship identity, distinct from optional `edge_id`.
/// Ordinals are unique only within one [`GraphSnapshot`] and survive partitioning.
pub const EDGE_ORDINAL: &str = "__grust_edge_ordinal";

/// Validated, immutable node/edge provider pair for one captured graph.
/// Clones share providers and Arrow buffers. Replacing a session catalog cannot
/// change either side of this pair. Construction allocates eight bytes per edge
/// for physical identity; callers must admit this storage and the input buffers.
/// This handle does not establish backend transaction or authorization identity.
#[derive(Clone)]
pub struct GraphSnapshot {
    pub(super) identity: Arc<()>,
    nodes: Arc<dyn TableProvider>,
    edges: Arc<dyn TableProvider>,
}
impl GraphSnapshot {
    /// Capture validated native Arrow tables without copying property buffers.
    /// Row-order ordinals preserve parallel relationships, loops and missing or
    /// repeated external IDs. Re-capturing a graph creates a separate identity
    /// domain, even when its rows happen to receive the same ordinal numbers.
    pub fn try_new(engine: &DataFusionEngine, graph: ArrowGraphTables) -> Result<Self> {
        let (nodes, edges) = graph.into_tables();
        Ok(Self {
            identity: Arc::new(()),
            nodes: engine.table_provider(nodes)?,
            edges: engine.table_provider(with_ordinals(edges)?)?,
        })
    }

    /// Build a plan directly from this snapshot's node provider.
    pub fn nodes(&self, context: &SessionContext) -> Result<DataFrame> {
        context.read_table(Arc::clone(&self.nodes))
    }

    /// Build a plan from this snapshot's edge provider, including [`EDGE_ORDINAL`].
    pub fn edges(&self, context: &SessionContext) -> Result<DataFrame> {
        context.read_table(Arc::clone(&self.edges))
    }
}

fn with_ordinals(table: ArrowTable) -> Result<ArrowTable> {
    let input_schema = table.schema();
    if input_schema.field_with_name(EDGE_ORDINAL).is_ok() {
        return Err(DataFusionError::Plan(format!(
            "reserved column {EDGE_ORDINAL}"
        )));
    }
    let mut fields = input_schema.fields().to_vec();
    fields.push(Arc::new(Field::new(EDGE_ORDINAL, DataType::UInt64, false)));
    let schema = Arc::new(Schema::new_with_metadata(
        fields,
        input_schema.metadata().clone(),
    ));
    let mut offset = 0_u64;
    let batches = table
        .into_batches()
        .into_iter()
        .map(|batch| {
            let count = u64::try_from(batch.num_rows())
                .map_err(|_| DataFusionError::Plan("edge count exceeds UInt64".into()))?;
            let end = offset
                .checked_add(count)
                .ok_or_else(|| DataFusionError::Plan("edge ordinal overflow".into()))?;
            let ordinals = UInt64Array::from_iter_values(offset..end);
            offset = end;
            let mut columns = batch.columns().to_vec();
            columns.push(Arc::new(ordinals));
            Ok(RecordBatch::try_new(Arc::clone(&schema), columns)?)
        })
        .collect::<Result<Vec<_>>>()?;
    ArrowTable::try_new(schema, batches).map_err(|error| DataFusionError::External(Box::new(error)))
}
