//! Multi-batch native-property graph interchange.
use super::{ArrowTable, array::RecordBatch, graph::validate_tables};
use grust_core::Result;

/// Validated native-property graph tables, without concatenating batches or
/// constructing a row-oriented Graph. Cloning shares Arrow buffers.
///
/// Node IDs are globally unique and every edge endpoint occurs in the node
/// tables. Parallel edges and isolates are preserved. Property rules match
/// `ArrowGraph`; arbitrary non-graph Arrow types belong in `ArrowTable`.
#[derive(Clone, Debug)]
pub struct ArrowGraphTables {
    nodes: ArrowTable,
    edges: ArrowTable,
}
impl ArrowGraphTables {
    /// Validate native scalar-property tables across batch boundaries.
    /// Validation borrows identity strings and retains a temporary O(nodes)
    /// identity set. No edge adjacency or property row maps are built.
    pub fn try_new(nodes: ArrowTable, edges: ArrowTable) -> Result<Self> {
        // Check schema-only tables too: zero batches must not bypass the
        // structural column and property-pair contract.
        let empty_nodes = RecordBatch::new_empty(nodes.schema());
        let empty_edges = RecordBatch::new_empty(edges.schema());
        validate_tables(
            std::slice::from_ref(&empty_nodes),
            std::slice::from_ref(&empty_edges),
        )?;
        validate_tables(nodes.batches(), edges.batches())?;
        Ok(Self { nodes, edges })
    }
    /// Borrow node batches in their original order.
    pub fn nodes(&self) -> &ArrowTable {
        &self.nodes
    }
    /// Borrow edge batches in their original order.
    pub fn edges(&self) -> &ArrowTable {
        &self.edges
    }
    /// Transfer the validated tables into independent standard-reader pipelines.
    pub fn into_tables(self) -> (ArrowTable, ArrowTable) {
        (self.nodes, self.edges)
    }
}
