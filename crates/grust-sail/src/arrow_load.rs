//! Sail's native Arrow ingestion boundary. Standard readers compose with ADBC;
//! Spark Connect requires IPC only at the final transport boundary.
use super::{
    EDGE_STAGE_VIEW, NODE_STAGE_VIEW, SailGraphStore, merge_edges_from_view_sql,
    merge_nodes_from_view_sql, props_from_json, props_to_json, typed_edge_merge_from_view_sql,
    typed_node_merge_from_view_sql,
};
use arrow::{
    array::{Array, ArrayRef, RecordBatch, RecordBatchReader, StringArray},
    datatypes::{DataType, Field, Schema},
};
use grust_arrow::v58::{BatchReader, into_grust_error, project_batch, utf8_column};
use grust_core::prelude::*;
use std::{collections::BTreeMap, num::NonZeroUsize, sync::Arc};

impl SailGraphStore {
    /// Upsert standard Arrow readers into Sail without building a whole Graph.
    ///
    /// Node columns are `id,label,props`; edges use `src_id,dst_id,edge_type,props`
    /// and optionally `id`. Identity is UTF-8; properties use Sail's plain JSON
    /// (legacy tagged values are normalized). Null/empty props mean an empty map.
    /// Supplied auxiliary edge keys/endpoint labels are recomputed from identity
    /// and persisted nodes. Structural edge upserts retain Sail's existing policy.
    ///
    /// Batches are validated before staging, with schema/unique constraints and
    /// typed tables maintained. Node batches precede edge batches; prior batches
    /// can remain committed after an error or cancellation. No whole-input
    /// preflight or transaction is implied. Byte admission applies after decode.
    pub async fn load_arrow(
        &self,
        nodes: impl RecordBatchReader + Send,
        edges: impl RecordBatchReader + Send,
        max_batch_bytes: NonZeroUsize,
    ) -> Result<LoadReport> {
        self.bootstrap().await?;
        let rows =
            NonZeroUsize::new(self.config.batch_size.max(1)).expect("batch size is at least one");
        let schema = self.current_schema();
        let mut report = LoadReport::default();
        for batch in BatchReader::new(nodes, rows, max_batch_bytes) {
            let batch = batch.map_err(into_grust_error)?;
            let graph = Graph::new(nodes_from_batch(&batch)?, vec![]);
            let nodes = &graph.nodes;
            if let Some(schema) = &schema {
                schema.validate_graph(&graph)?;
                self.enforce_unique_node_constraints(&schema.constraints, nodes)
                    .await?;
            }
            let batch = node_stage_batch(&batch, nodes)?;
            self.stage_record_batch(NODE_STAGE_VIEW, batch).await?;
            self.run_command(&merge_nodes_from_view_sql(), vec![])
                .await?;
            if let Some(schema) = &schema {
                for node_type in &schema.nodes {
                    if nodes.iter().any(|node| node.label == node_type.label) {
                        self.run_command(&typed_node_merge_from_view_sql(node_type)?, vec![])
                            .await?;
                    }
                }
            }
            report.nodes += nodes.len();
        }
        for batch in BatchReader::new(edges, rows, max_batch_bytes) {
            let batch = batch.map_err(into_grust_error)?;
            let edges = edges_from_batch(&batch)?;
            for edge in &edges {
                validate_edge_key_components(edge)?;
            }
            let ids = edges
                .iter()
                .flat_map(|e| [&e.from, &e.to])
                .cloned()
                .collect::<Vec<_>>();
            let graph = Graph::new(self.get_nodes(&ids).await?, edges);
            let edges = &graph.edges;
            let endpoints = &graph.nodes;
            let labels = endpoints
                .iter()
                .map(|n| (&n.id, &n.label))
                .collect::<BTreeMap<_, _>>();
            if let Some(schema) = &schema {
                schema.validate_graph(&graph)?;
                self.enforce_unique_edge_constraints(&schema.constraints, edges)
                    .await?;
            }
            let batch = edge_stage_batch(&batch, edges, &labels)?;
            self.stage_record_batch(EDGE_STAGE_VIEW, batch).await?;
            self.run_command(&merge_edges_from_view_sql(), vec![])
                .await?;
            if let Some(schema) = &schema {
                for edge_type in &schema.edges {
                    if edges.iter().any(|edge| edge.label == edge_type.label) {
                        self.run_command(&typed_edge_merge_from_view_sql(edge_type)?, vec![])
                            .await?;
                    }
                }
            }
            report.edges += edges.len();
        }
        Ok(report)
    }

    /// Visit query result batches without collecting a full result or exposing
    /// Spark Connect payloads. A callback error stops consumption. The callback
    /// runs synchronously and should do bounded work; it must not block on I/O.
    pub async fn visit_arrow_batches(
        &self,
        sql: &str,
        mut consume: impl FnMut(RecordBatch) -> Result<()> + Send,
    ) -> Result<()> {
        self.run_plan(self.query_request(sql, vec![])?, |data| {
            for batch in
                grust_arrow::v58::read_ipc_stream(data.as_slice()).map_err(into_grust_error)?
            {
                consume(batch.map_err(into_grust_error)?)?;
            }
            Ok(())
        })
        .await
    }

    /// Stage any Arrow reader as one temporary Sail view. The transport must
    /// buffer one IPC payload, bounded by `max_ipc_bytes` including the schema;
    /// use graph loading for bounded repeated merges.
    /// The reader schema and all Arrow types supported by Sail are preserved.
    pub async fn stage_arrow_view(
        &self,
        name: &str,
        reader: impl RecordBatchReader + Send,
        max_ipc_bytes: NonZeroUsize,
    ) -> Result<()> {
        super::validate_arrow_view_name(name)?;
        let mut data = Vec::new();
        grust_arrow::v58::write_ipc_stream(
            grust_arrow::ByteLimitWriter::new(&mut data, max_ipc_bytes),
            reader,
        )
        .map_err(into_grust_error)?;
        self.run_plan(self.stage_view_request(name, data), |_| Ok(()))
            .await
    }
}

pub(super) fn nodes_from_batch(batch: &RecordBatch) -> Result<Vec<Node>> {
    let ids = utf8_column(batch, "id", false)?;
    let labels = utf8_column(batch, "label", false)?;
    let props = utf8_column(batch, "props", true)?;
    (0..batch.num_rows())
        .map(|i| {
            Ok(Node::new(
                labels.value(i),
                ids.value(i),
                read_props(props, i)?,
            ))
        })
        .collect()
}
pub(super) fn edges_from_batch(batch: &RecordBatch) -> Result<Vec<Edge>> {
    let from = utf8_column(batch, "src_id", false)?;
    let to = utf8_column(batch, "dst_id", false)?;
    let labels = utf8_column(batch, "edge_type", false)?;
    let props = utf8_column(batch, "props", true)?;
    let ids = if batch.column_by_name("id").is_some() {
        Some(utf8_column(batch, "id", true)?)
    } else {
        None
    };
    (0..batch.num_rows())
        .map(|i| {
            let mut edge = Edge::new(
                labels.value(i),
                from.value(i),
                to.value(i),
                read_props(props, i)?,
            );
            if let Some(ids) = ids
                && !ids.is_null(i)
            {
                edge.id = Some(ids.value(i).into());
            }
            Ok(edge)
        })
        .collect()
}
fn read_props(column: &StringArray, row: usize) -> Result<Props> {
    if column.is_null(row) || column.value(row).is_empty() {
        Ok(Props::new())
    } else {
        props_from_json(column.value(row))
    }
}
fn node_stage_batch(input: &RecordBatch, nodes: &[Node]) -> Result<RecordBatch> {
    let projected = project_batch(
        input,
        Arc::new(Schema::new(vec![
            Field::new("id", DataType::Utf8, false),
            Field::new("label", DataType::Utf8, false),
        ])),
        &["id", "label"],
    )
    .map_err(into_grust_error)?;
    let mut fields = projected
        .schema()
        .fields()
        .iter()
        .map(|f| f.as_ref().clone())
        .collect::<Vec<_>>();
    fields.push(Field::new("props", DataType::Utf8, true));
    let mut columns = projected.columns().to_vec();
    columns.push(props_column(input, nodes.iter().map(|n| &n.props))?);
    RecordBatch::try_new(Arc::new(Schema::new(fields)), columns).map_err(into_grust_error)
}
fn edge_stage_batch(
    input: &RecordBatch,
    edges: &[Edge],
    labels: &BTreeMap<&NodeId, &Label>,
) -> Result<RecordBatch> {
    // Reuse the established Sail shape while retaining input identity buffers.
    let columns = ["src_id", "dst_id", "edge_type"];
    let projected = project_batch(
        input,
        Arc::new(Schema::new(
            columns
                .iter()
                .map(|n| Field::new(*n, DataType::Utf8, false))
                .collect::<Vec<_>>(),
        )),
        &columns,
    )
    .map_err(into_grust_error)?;
    let mut fields = projected
        .schema()
        .fields()
        .iter()
        .map(|f| f.as_ref().clone())
        .collect::<Vec<_>>();
    fields.extend([
        Field::new("props", DataType::Utf8, true),
        Field::new("edge_key", DataType::Utf8, false),
        Field::new("id", DataType::Utf8, true),
        Field::new("src_label", DataType::Utf8, false),
        Field::new("dst_label", DataType::Utf8, false),
    ]);
    let keys = edges
        .iter()
        .map(checked_edge_key)
        .collect::<Result<Vec<_>>>()?;
    let mut arrays = projected.columns().to_vec();
    arrays.push(props_column(input, edges.iter().map(|e| &e.props))?);
    arrays.push(Arc::new(StringArray::from_iter_values(
        keys.iter().map(String::as_str),
    )));
    arrays.push(
        input
            .column_by_name("id")
            .cloned()
            .unwrap_or_else(|| Arc::new(StringArray::new_null(edges.len()))),
    );
    for source in [true, false] {
        arrays.push(Arc::new(StringArray::from_iter_values(edges.iter().map(
            |e| {
                let id = if source { &e.from } else { &e.to };
                labels.get(id).map(|label| label.as_str()).unwrap_or("")
            },
        ))));
    }
    RecordBatch::try_new(Arc::new(Schema::new(fields)), arrays).map_err(into_grust_error)
}
fn props_column<'a>(
    input: &RecordBatch,
    props: impl Iterator<Item = &'a Props>,
) -> Result<ArrayRef> {
    let encoded = props.map(props_to_json).collect::<Result<Vec<_>>>()?;
    let original = utf8_column(input, "props", true)?;
    if encoded
        .iter()
        .enumerate()
        .all(|(i, text)| !original.is_null(i) && text == original.value(i))
    {
        return input
            .column_by_name("props")
            .cloned()
            .ok_or_else(|| GrustError::Schema("missing props".into()));
    }
    Ok(Arc::new(StringArray::from_iter_values(
        encoded.iter().map(String::as_str),
    )))
}

#[cfg(test)]
#[path = "arrow_load_tests.rs"]
mod tests;
