//! Native columnar ingestion, with batch-local validation and upsert semantics.
use super::{LanceDbGraphStore, edges_schema, nodes_schema};
use arrow::array::{RecordBatch, RecordBatchIterator, RecordBatchReader};
use grust_arrow::v58::{BatchReader, edges_from_batch, nodes_from_batch, project_batch};
use grust_core::prelude::*;
use std::num::NonZeroUsize;

impl LanceDbGraphStore {
    /// Upsert native Arrow readers in the shared `grust-arrow` storage layout.
    ///
    /// Nodes use `id,label,props`; edges use `key,id,from_id,to_id,label,props`.
    /// `props` is Grust's serialized property map. Required columns are checked,
    /// properties and identities validated per batch, and typed mirrors kept
    /// in sync. Existing identity/property buffers go directly to LanceDB.
    ///
    /// Nodes precede edges. Each merge is an independent commit; an error or
    /// cancellation may leave prior batches (or a generic table before its typed
    /// mirror) written, as with `put_graph`. Stream order determines upserts.
    /// This does not assert that all endpoints occur in these input readers.
    /// The byte limit applies to each decoded input batch, before row slicing.
    pub async fn load_arrow(
        &self,
        nodes: impl RecordBatchReader + Send,
        edges: impl RecordBatchReader + Send,
        max_batch_bytes: NonZeroUsize,
    ) -> Result<LoadReport> {
        let max_rows = NonZeroUsize::new(self.config.bulk_batch_size.max(1))
            .expect("batch size is at least one");
        let nodes = BatchReader::new(nodes, max_rows, max_batch_bytes);
        let edges = BatchReader::new(edges, max_rows, max_batch_bytes);
        let schema = self
            .schema
            .read()
            .map_err(|_| GrustError::Backend("LanceDB schema lock poisoned".into()))?
            .clone();
        let node_table = self.open_nodes().await?;
        let edge_table = self.open_edges().await?;
        let typed_nodes = self.open_typed_node_tables().await?;
        let typed_edges = self.open_typed_edge_tables().await?;
        let mut report = LoadReport::default();
        for batch in nodes {
            let batch = batch.map_err(arrow_error)?;
            let batch = project_batch(&batch, nodes_schema(), &["id", "label", "props"])
                .map_err(arrow_error)?;
            let rows = nodes_from_batch(&batch)?;
            if let Some(schema) = &schema {
                for node in &rows {
                    schema.validate_node(node)?;
                }
            }
            merge_batch(&node_table, batch, "id").await?;
            for (node_type, table) in &typed_nodes {
                let selected = rows
                    .iter()
                    .filter(|node| node.label == node_type.label)
                    .collect::<Vec<_>>();
                Self::merge_typed_nodes_into(table, node_type, &selected).await?;
            }
            report.nodes += rows.len();
        }
        for batch in edges {
            let batch = batch.map_err(arrow_error)?;
            let batch = project_batch(
                &batch,
                edges_schema(),
                &["key", "id", "from_id", "to_id", "label", "props"],
            )
            .map_err(arrow_error)?;
            let rows = edges_from_batch(&batch)?;
            if let Some(schema) = &schema {
                for edge in &rows {
                    schema.validate_edge_props(edge)?;
                }
            }
            merge_batch(&edge_table, batch, "key").await?;
            for (edge_type, table) in &typed_edges {
                let selected = rows
                    .iter()
                    .filter(|edge| edge.label == edge_type.label)
                    .collect::<Vec<_>>();
                Self::merge_typed_edges_into(table, edge_type, &selected).await?;
            }
            report.edges += rows.len();
        }
        Self::compact(&node_table).await?;
        Self::compact(&edge_table).await?;
        for (_, table) in &typed_nodes {
            Self::compact(table).await?;
        }
        for (_, table) in &typed_edges {
            Self::compact(table).await?;
        }
        Ok(report)
    }
}

async fn merge_batch(table: &lancedb::Table, batch: RecordBatch, key: &str) -> Result<()> {
    let schema = batch.schema();
    let source = Box::new(RecordBatchIterator::new(std::iter::once(Ok(batch)), schema));
    let mut merge = table.merge_insert(&[key]);
    merge
        .when_matched_update_all(None)
        .when_not_matched_insert_all();
    merge
        .execute(source)
        .await
        .map_err(|e| GrustError::Backend(format!("LanceDB Arrow merge failed: {e}")))?;
    Ok(())
}
fn arrow_error(error: arrow::error::ArrowError) -> GrustError {
    grust_arrow::v58::into_grust_error(error)
}
