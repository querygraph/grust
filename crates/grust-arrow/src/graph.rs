//! Native Arrow scalar properties and two-table IPC interchange.
//!
//! Node identity is UTF-8 `node_id`; edges use UTF-8 `source` and `target`.
//! `label` and nullable `edge_id` preserve property-graph identity. Properties
//! use `property.<key>` plus Boolean `present.<key>` to distinguish missing
//! values from explicit null. Unsupported property types fail explicitly.
use super::{array as arrow_array, ipc as arrow_ipc, schema as arrow_schema};
use arrow_array::{
    Array, ArrayRef, BooleanArray, Float64Array, Int64Array, RecordBatch, StringArray,
};
use arrow_schema::{DataType, Field, Schema};
use grust_core::{Edge, Graph, GraphIndex, GrustError, Node, Props, Result, Value};
use std::{
    collections::BTreeSet,
    io::{Read, Seek, Write},
    sync::Arc,
};

fn error(e: impl std::fmt::Display) -> GrustError {
    GrustError::Serialization(e.to_string())
}

/// An immutable pair of Arrow tables. Cloning shares Arrow buffers.
#[derive(Clone, Debug)]
pub struct ArrowGraph {
    nodes: RecordBatch,
    edges: RecordBatch,
}
impl ArrowGraph {
    /// Validate tables, including unique node IDs and existing endpoints.
    pub fn try_new(nodes: RecordBatch, edges: RecordBatch) -> Result<Self> {
        let result = Self { nodes, edges };
        validate_tables(
            std::slice::from_ref(&result.nodes),
            std::slice::from_ref(&result.edges),
        )?;
        Ok(result)
    }
    pub fn nodes(&self) -> &RecordBatch {
        &self.nodes
    }
    pub fn edges(&self) -> &RecordBatch {
        &self.edges
    }
    /// Transfer the two batches into general Arrow tables. Buffers remain shared;
    /// each resulting table can be bound directly to an ADBC statement reader.
    pub fn into_tables(self) -> (super::ArrowTable, super::ArrowTable) {
        // Each table has exactly one batch whose own schema defines the table.
        (
            super::ArrowTable::from(self.nodes),
            super::ArrowTable::from(self.edges),
        )
    }

    /// Materialize scalar property columns from a Grust graph.
    pub fn from_graph(graph: &Graph) -> Result<Self> {
        GraphIndex::new(graph)?;
        let nodes = table(
            vec![
                (
                    "node_id",
                    Arc::new(StringArray::from_iter_values(
                        graph.nodes.iter().map(|n| n.id.as_str()),
                    )) as ArrayRef,
                ),
                (
                    "label",
                    Arc::new(StringArray::from_iter_values(
                        graph.nodes.iter().map(|n| n.label.as_str()),
                    )),
                ),
            ],
            graph.nodes.iter().map(|n| &n.props).collect(),
        )?;
        let edges = table(
            vec![
                (
                    "source",
                    Arc::new(StringArray::from_iter_values(
                        graph.edges.iter().map(|e| e.from.as_str()),
                    )) as ArrayRef,
                ),
                (
                    "target",
                    Arc::new(StringArray::from_iter_values(
                        graph.edges.iter().map(|e| e.to.as_str()),
                    )),
                ),
                (
                    "label",
                    Arc::new(StringArray::from_iter_values(
                        graph.edges.iter().map(|e| e.label.as_str()),
                    )),
                ),
                (
                    "edge_id",
                    Arc::new(StringArray::from_iter(
                        graph
                            .edges
                            .iter()
                            .map(|e| e.id.as_ref().map(|id| id.as_str())),
                    )),
                ),
            ],
            graph.edges.iter().map(|e| &e.props).collect(),
        )?;
        Ok(Self { nodes, edges })
    }
    /// Materialize the Grust model. Table row order and parallel edges survive.
    pub fn to_graph(&self) -> Result<Graph> {
        let ids = strings(&self.nodes, "node_id", false)?;
        let nl = strings(&self.nodes, "label", false)?;
        let src = strings(&self.edges, "source", false)?;
        let dst = strings(&self.edges, "target", false)?;
        let el = strings(&self.edges, "label", false)?;
        let ei = strings(&self.edges, "edge_id", true)?;
        let np = properties(&self.nodes, &["node_id", "label"])?;
        let ep = properties(&self.edges, &["source", "target", "label", "edge_id"])?;
        let graph = Graph::new(
            np.into_iter()
                .enumerate()
                .map(|(i, props)| Node {
                    id: ids.value(i).into(),
                    label: nl.value(i).into(),
                    props,
                })
                .collect(),
            ep.into_iter()
                .enumerate()
                .map(|(i, props)| Edge {
                    id: (!ei.is_null(i)).then(|| ei.value(i).into()),
                    from: src.value(i).into(),
                    to: dst.value(i).into(),
                    label: el.value(i).into(),
                    props,
                })
                .collect(),
        );
        Ok(graph)
    }
    /// Write two Arrow IPC files to caller-owned sinks; no path is overwritten here.
    pub fn write_ipc(&self, nodes: impl Write, edges: impl Write) -> Result<()> {
        write_batch(nodes, &self.nodes)?;
        write_batch(edges, &self.edges)
    }
    /// Read one record batch per IPC file and validate the graph.
    pub fn read_ipc(nodes: impl Read + Seek, edges: impl Read + Seek) -> Result<Self> {
        Self::try_new(read_batch(nodes)?, read_batch(edges)?)
    }
}
fn write_batch(out: impl Write, batch: &RecordBatch) -> Result<()> {
    let mut writer = arrow_ipc::writer::FileWriter::try_new(out, &batch.schema()).map_err(error)?;
    writer.write(batch).map_err(error)?;
    writer.finish().map_err(error)
}
fn read_batch(input: impl Read + Seek) -> Result<RecordBatch> {
    let mut reader = arrow_ipc::reader::FileReader::try_new(input, None).map_err(error)?;
    let batch = reader
        .next()
        .ok_or_else(|| error("missing record batch"))?
        .map_err(error)?;
    if reader.next().is_some() {
        return Err(error("expected exactly one record batch"));
    }
    Ok(batch)
}
fn strings<'a>(b: &'a RecordBatch, name: &str, nullable: bool) -> Result<&'a StringArray> {
    let a = b
        .column_by_name(name)
        .and_then(|a| a.as_any().downcast_ref::<StringArray>())
        .ok_or_else(|| error(format!("{name} must be Utf8")))?;
    if !nullable && a.null_count() != 0 {
        return Err(error(format!("{name} contains nulls")));
    }
    Ok(a)
}
fn kind(v: &Value) -> Result<DataType> {
    Ok(match v {
        Value::Null => DataType::Null,
        Value::Bool(_) => DataType::Boolean,
        Value::Int(_) => DataType::Int64,
        Value::Float(_) => DataType::Float64,
        Value::String(_) => DataType::Utf8,
        _ => {
            return Err(error(
                "Arrow scalar interchange supports Null, Bool, Int, Float, String only",
            ));
        }
    })
}
fn table(base: Vec<(&str, ArrayRef)>, props: Vec<&Props>) -> Result<RecordBatch> {
    let mut fields: Vec<Field> = base
        .iter()
        .map(|(name, a)| Field::new(*name, a.data_type().clone(), *name == "edge_id"))
        .collect();
    let mut arrays: Vec<ArrayRef> = base.into_iter().map(|(_, a)| a).collect();
    let keys: BTreeSet<&String> = props.iter().flat_map(|p| p.keys()).collect();
    for key in keys {
        let vals: Vec<Option<&Value>> = props.iter().map(|p| p.get(key)).collect();
        let mut ty = DataType::Null;
        for v in vals.iter().flatten() {
            let t = kind(v)?;
            if t == DataType::Null {
                continue;
            }
            if ty != DataType::Null && ty != t {
                return Err(error(format!("mixed types for property {key}")));
            }
            ty = t;
        }
        macro_rules! col {
            ($array:ident, $variant:ident) => {
                Arc::new($array::from_iter(vals.iter().map(|v| match v {
                    Some(Value::$variant(x)) => Some(x.clone()),
                    _ => None,
                }))) as ArrayRef
            };
        }
        let a = match ty {
            DataType::Boolean => col!(BooleanArray, Bool),
            DataType::Int64 => col!(Int64Array, Int),
            DataType::Float64 => col!(Float64Array, Float),
            DataType::Utf8 => col!(StringArray, String),
            _ => Arc::new(arrow_array::NullArray::new(props.len())) as ArrayRef,
        };
        fields.push(Field::new(format!("property.{key}"), ty, true));
        arrays.push(a);
        fields.push(Field::new(
            format!("present.{key}"),
            DataType::Boolean,
            false,
        ));
        arrays.push(Arc::new(BooleanArray::from_iter(
            vals.iter().map(|v| Some(v.is_some())),
        )));
    }
    RecordBatch::try_new(Arc::new(Schema::new(fields)), arrays).map_err(error)
}
struct PropertyColumn<'a> {
    key: String,
    values: &'a ArrayRef,
    presence: &'a BooleanArray,
}
fn property_columns<'a>(b: &'a RecordBatch, base: &[&str]) -> Result<Vec<PropertyColumn<'a>>> {
    let mut result = Vec::new();
    let mut seen = BTreeSet::new();
    for f in b.schema().fields() {
        if !seen.insert(f.name().clone()) {
            return Err(error("duplicate column name"));
        }
        if base.contains(&f.name().as_str()) {
            continue;
        }
        if let Some(key) = f.name().strip_prefix("present.") {
            if b.column_by_name(&format!("property.{key}")).is_none() {
                return Err(error("orphan presence column"));
            }
            continue;
        }
        let key = f
            .name()
            .strip_prefix("property.")
            .ok_or_else(|| error(format!("unknown column {}", f.name())))?;
        let presence = b
            .column_by_name(&format!("present.{key}"))
            .and_then(|a| a.as_any().downcast_ref::<BooleanArray>())
            .ok_or_else(|| error("missing Boolean presence column"))?;
        if presence.null_count() != 0 {
            return Err(error("null presence marker"));
        }
        let a = b
            .column_by_name(f.name())
            .ok_or_else(|| error("missing property column"))?;
        if !matches!(
            a.data_type(),
            DataType::Null
                | DataType::Boolean
                | DataType::Int64
                | DataType::Float64
                | DataType::Utf8
        ) {
            return Err(error("unsupported property column type"));
        }
        for i in 0..b.num_rows() {
            if !presence.value(i) && a.data_type() != &DataType::Null && !a.is_null(i) {
                return Err(error("absent property has a value"));
            }
        }
        result.push(PropertyColumn {
            key: key.to_owned(),
            values: a,
            presence,
        });
    }
    Ok(result)
}
fn properties(b: &RecordBatch, base: &[&str]) -> Result<Vec<Props>> {
    let mut result = vec![Props::new(); b.num_rows()];
    for column in property_columns(b, base)? {
        let PropertyColumn {
            key,
            values: a,
            presence,
        } = column;
        for (i, p) in result.iter_mut().enumerate() {
            if !presence.value(i) {
                continue;
            }
            macro_rules! val {
                ($array:ident, $variant:ident) => {
                    Value::$variant(
                        a.as_any()
                            .downcast_ref::<$array>()
                            .ok_or_else(|| error("unsupported Arrow array representation"))?
                            .value(i)
                            .into(),
                    )
                };
            }
            let value = if a.data_type() == &DataType::Null || a.is_null(i) {
                Value::Null
            } else {
                match a.data_type() {
                    DataType::Boolean => val!(BooleanArray, Bool),
                    DataType::Int64 => val!(Int64Array, Int),
                    DataType::Float64 => val!(Float64Array, Float),
                    DataType::Utf8 => val!(StringArray, String),
                    _ => return Err(error("unsupported property column type")),
                }
            };
            p.insert(key.to_owned(), value);
        }
    }
    Ok(result)
}

pub(super) fn validate_tables(nodes: &[RecordBatch], edges: &[RecordBatch]) -> Result<()> {
    let mut ids = std::collections::HashSet::new();
    for batch in nodes {
        let values = strings(batch, "node_id", false)?;
        strings(batch, "label", false)?;
        property_columns(batch, &["node_id", "label"])?;
        for id in values.iter().flatten() {
            if !ids.insert(id) {
                return Err(GrustError::Schema(format!("duplicate vertex id '{id}'")));
            }
        }
    }
    for batch in edges {
        let source = strings(batch, "source", false)?;
        let target = strings(batch, "target", false)?;
        strings(batch, "label", false)?;
        strings(batch, "edge_id", true)?;
        property_columns(batch, &["source", "target", "label", "edge_id"])?;
        for row in 0..batch.num_rows() {
            if !ids.contains(source.value(row)) || !ids.contains(target.value(row)) {
                return Err(GrustError::Schema(
                    "edge endpoint is not present in vertices".into(),
                ));
            }
        }
    }
    Ok(())
}
