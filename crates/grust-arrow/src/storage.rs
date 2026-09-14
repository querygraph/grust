//! Shared universal graph-table layout used at database ingestion boundaries.
//!
//! Identity columns are Arrow UTF-8; `props` holds Grust's existing serialized
//! `Props` contract. This is distinct from `ArrowGraph`'s native property columns.
//! Conversion to rows is explicit and scoped to the caller's batch, never a
//! hidden whole-stream materialization. Adapters rename columns by projection.
use super::{array, schema};
use array::{Array, RecordBatch, StringArray};
use grust_core::{Edge, GrustError, Node, Props, Result, checked_edge_key};
use schema::{DataType, Field, Schema, SchemaRef};
use std::sync::Arc;

fn error(e: impl std::fmt::Display) -> GrustError {
    GrustError::Serialization(e.to_string())
}

/// Universal node storage schema: non-null `id`, `label`, and serialized `props`.
pub fn node_storage_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("id", DataType::Utf8, false),
        Field::new("label", DataType::Utf8, false),
        Field::new("props", DataType::Utf8, false),
    ]))
}
/// Universal edge storage schema: stable `key`, nullable explicit `id`,
/// `from_id`, `to_id`, `label`, and serialized `props`.
pub fn edge_storage_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("key", DataType::Utf8, false),
        Field::new("id", DataType::Utf8, true),
        Field::new("from_id", DataType::Utf8, false),
        Field::new("to_id", DataType::Utf8, false),
        Field::new("label", DataType::Utf8, false),
        Field::new("props", DataType::Utf8, false),
    ]))
}
/// Encode one node slice in the universal storage layout. Complex Grust values
/// use the same serialization as existing database adapters.
pub fn nodes_to_batch(nodes: &[Node]) -> Result<RecordBatch> {
    let props = nodes
        .iter()
        .map(|n| serde_json::to_string(&n.props).map_err(error))
        .collect::<Result<Vec<_>>>()?;
    RecordBatch::try_new(
        node_storage_schema(),
        vec![
            Arc::new(StringArray::from_iter_values(
                nodes.iter().map(|n| n.id.as_str()),
            )),
            Arc::new(StringArray::from_iter_values(
                nodes.iter().map(|n| n.label.as_str()),
            )),
            Arc::new(StringArray::from_iter_values(
                props.iter().map(String::as_str),
            )),
        ],
    )
    .map_err(error)
}
/// Encode one edge slice, validating every stable edge identity first.
pub fn edges_to_batch(edges: &[Edge]) -> Result<RecordBatch> {
    let keys = edges
        .iter()
        .map(checked_edge_key)
        .collect::<Result<Vec<_>>>()?;
    let props = edges
        .iter()
        .map(|e| serde_json::to_string(&e.props).map_err(error))
        .collect::<Result<Vec<_>>>()?;
    RecordBatch::try_new(
        edge_storage_schema(),
        vec![
            Arc::new(StringArray::from_iter_values(
                keys.iter().map(String::as_str),
            )),
            Arc::new(StringArray::from_iter(
                edges.iter().map(|e| e.id.as_ref().map(|id| id.as_str())),
            )),
            Arc::new(StringArray::from_iter_values(
                edges.iter().map(|e| e.from.as_str()),
            )),
            Arc::new(StringArray::from_iter_values(
                edges.iter().map(|e| e.to.as_str()),
            )),
            Arc::new(StringArray::from_iter_values(
                edges.iter().map(|e| e.label.as_str()),
            )),
            Arc::new(StringArray::from_iter_values(
                props.iter().map(String::as_str),
            )),
        ],
    )
    .map_err(error)
}
/// Borrow a uniquely named UTF-8 column, checking required values for null.
pub fn utf8_column<'a>(
    batch: &'a RecordBatch,
    name: &str,
    nullable: bool,
) -> Result<&'a StringArray> {
    let schema = batch.schema();
    let mut matches = schema
        .fields()
        .iter()
        .enumerate()
        .filter(|(_, field)| field.name() == name);
    let (index, _) = matches
        .next()
        .ok_or_else(|| error(format!("missing column {name}")))?;
    if matches.next().is_some() {
        return Err(error(format!("ambiguous column {name}")));
    }
    let column = batch
        .column(index)
        .as_any()
        .downcast_ref::<StringArray>()
        .ok_or_else(|| error(format!("column {name} is not UTF-8")))?;
    if !nullable && column.null_count() != 0 {
        return Err(error(format!("null in required column {name}")));
    }
    Ok(column)
}
/// Decode and validate one node batch. Duplicate IDs keep input order; the
/// destination decides upsert semantics. This does not validate graph closure.
pub fn nodes_from_batch(batch: &RecordBatch) -> Result<Vec<Node>> {
    let ids = utf8_column(batch, "id", false)?;
    let labels = utf8_column(batch, "label", false)?;
    let props = utf8_column(batch, "props", false)?;
    (0..batch.num_rows())
        .map(|i| {
            Ok(Node::new(
                labels.value(i),
                ids.value(i),
                serde_json::from_str::<Props>(props.value(i)).map_err(error)?,
            ))
        })
        .collect()
}
/// Decode and validate one edge batch, rejecting forged stable keys before a
/// caller writes this batch. Explicit empty IDs are preserved, distinct from null.
pub fn edges_from_batch(batch: &RecordBatch) -> Result<Vec<Edge>> {
    let keys = utf8_column(batch, "key", false)?;
    let ids = utf8_column(batch, "id", true)?;
    let from = utf8_column(batch, "from_id", false)?;
    let to = utf8_column(batch, "to_id", false)?;
    let labels = utf8_column(batch, "label", false)?;
    let props = utf8_column(batch, "props", false)?;
    (0..batch.num_rows())
        .map(|i| {
            let mut edge = Edge::new(
                labels.value(i),
                from.value(i),
                to.value(i),
                serde_json::from_str::<Props>(props.value(i)).map_err(error)?,
            );
            if !ids.is_null(i) {
                edge.id = Some(ids.value(i).into());
            }
            if checked_edge_key(&edge)? != keys.value(i) {
                return Err(error("edge key does not match its identity"));
            }
            Ok(edge)
        })
        .collect()
}

#[cfg(test)]
#[path = "storage_tests.rs"]
mod tests;
