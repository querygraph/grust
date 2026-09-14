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

/// Exact counts from the captured native tables, not optimizer estimates.
/// Original batch counts describe input layout, not execution parallelism.
/// Selectivity, join cardinality, retained input memory and total process memory
/// are not inferred. Serialized size is explicitly unknown unless measured.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct SnapshotStatistics {
    pub node_rows: usize,
    pub edge_rows: usize,
    pub node_batches: usize,
    pub edge_batches: usize,
    /// Logical UInt64 identity payload added during capture. Allocator capacity
    /// and array/schema metadata are not included.
    pub edge_ordinal_bytes: usize,
    /// Exact core Graph JSON size when measured by input-policy capture. `None`
    /// means unmeasured, including for empty tables; it never means zero bytes.
    pub serialized_graph_bytes: Option<usize>,
}

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
    statistics: SnapshotStatistics,
}
impl GraphSnapshot {
    /// Capture validated native Arrow tables without copying property buffers.
    /// Row-order ordinals preserve parallel relationships, loops and missing or
    /// repeated external IDs. Re-capturing a graph creates a separate identity
    /// domain, even when its rows happen to receive the same ordinal numbers.
    pub fn try_new(engine: &DataFusionEngine, graph: ArrowGraphTables) -> Result<Self> {
        let (nodes, edges) = graph.into_tables();
        let statistics = SnapshotStatistics {
            node_rows: nodes.num_rows(),
            edge_rows: edges.num_rows(),
            node_batches: nodes.batches().len(),
            edge_batches: edges.batches().len(),
            edge_ordinal_bytes: edges
                .num_rows()
                .checked_mul(size_of::<u64>())
                .ok_or_else(|| DataFusionError::Plan("edge ordinal byte size overflow".into()))?,
            serialized_graph_bytes: None,
        };
        Ok(Self {
            identity: Arc::new(()),
            nodes: engine.table_provider(nodes)?,
            edges: engine.table_provider(with_ordinals(edges)?)?,
            statistics,
        })
    }

    /// Admit exact graph rows and serialized bytes under the prepared request's
    /// original deadline, then capture native providers. The borrowed Arrow view
    /// avoids a row graph and encoded JSON allocation; measurement is cached.
    ///
    /// This checks input size only. Backend authority, existing input-buffer
    /// admission, ordinal allocation and execution work/intermediates remain
    /// separate obligations. It does not establish a complete bounded executor.
    pub fn try_new_with_input_policy(
        engine: &DataFusionEngine,
        graph: ArrowGraphTables,
        request: &grust_cypher::PreparedReadRequest<'_>,
    ) -> Result<Self> {
        let bytes = request
            .check_serializable_graph(
                graph.nodes().num_rows(),
                graph.edges().num_rows(),
                &graph.as_serializable_graph(),
            )
            .map_err(|error| DataFusionError::External(Box::new(error)))?;
        let mut snapshot = Self::try_new(engine, graph)?;
        snapshot.statistics.serialized_graph_bytes = Some(bytes);
        request
            .check_measured_graph(
                snapshot.statistics.node_rows,
                snapshot.statistics.edge_rows,
                bytes,
            )
            .map_err(|error| DataFusionError::External(Box::new(error)))?;
        Ok(snapshot)
    }

    /// Read exact capture metadata in constant time without scanning providers,
    /// exporting the graph or planning a query. Clones retain the same counts;
    /// session catalog replacement cannot change this snapshot's statistics.
    pub fn statistics(&self) -> SnapshotStatistics {
        self.statistics
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
