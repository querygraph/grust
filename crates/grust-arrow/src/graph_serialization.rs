//! Borrowed projection of native tables onto the existing Graph serde contract.
//! Per-batch descriptors borrow columns and property keys. Rows, strings and
//! property maps are not materialized. The serializer owns output/error policy.
use super::{
    ArrowGraphTables, ArrowTable,
    array::{Array, ArrayRef, BooleanArray, Float64Array, Int64Array, RecordBatch, StringArray},
    schema::DataType,
};
use serde::{
    Serialize, Serializer,
    ser::{Error, SerializeMap, SerializeSeq, SerializeStruct},
};

impl ArrowGraphTables {
    /// Borrow the ordinary Grust `Graph` serialization surface without building
    /// a row graph or copying string/property values. Native scalar tags, missing
    /// versus null properties, identity, batch order and parallel edges survive.
    ///
    /// Serializing allocates only property-column descriptors for one batch at
    /// a time. The caller's serializer/writer owns output allocation and limits;
    /// writer failures stop immediately and may leave an output prefix.
    pub fn as_serializable_graph(&self) -> impl Serialize + '_ {
        GraphView(self)
    }
}

struct GraphView<'a>(&'a ArrowGraphTables);
impl Serialize for GraphView<'_> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let mut graph = serializer.serialize_struct("Graph", 2)?;
        graph.serialize_field(
            "nodes",
            &Rows {
                table: self.0.nodes(),
                kind: Kind::Nodes,
            },
        )?;
        graph.serialize_field(
            "edges",
            &Rows {
                table: self.0.edges(),
                kind: Kind::Edges,
            },
        )?;
        graph.end()
    }
}

#[derive(Clone, Copy)]
enum Kind {
    Nodes,
    Edges,
}
struct Rows<'a> {
    table: &'a ArrowTable,
    kind: Kind,
}
impl Serialize for Rows<'_> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let mut rows = serializer.serialize_seq(Some(self.table.num_rows()))?;
        for batch in self.table.batches() {
            let columns = Columns::new::<S::Error>(batch, self.kind)?;
            let properties = properties::<S::Error>(batch)?;
            for row in 0..batch.num_rows() {
                rows.serialize_element(&Row {
                    columns: &columns,
                    properties: &properties,
                    row,
                })?;
            }
        }
        rows.end()
    }
}

enum Columns<'a> {
    Nodes {
        ids: &'a StringArray,
        labels: &'a StringArray,
    },
    Edges {
        ids: &'a StringArray,
        from: &'a StringArray,
        to: &'a StringArray,
        labels: &'a StringArray,
    },
}
impl<'a> Columns<'a> {
    fn new<E: Error>(batch: &'a RecordBatch, kind: Kind) -> Result<Self, E> {
        let strings = |name| column::<StringArray, E>(batch, name);
        Ok(match kind {
            Kind::Nodes => Self::Nodes {
                ids: strings("node_id")?,
                labels: strings("label")?,
            },
            Kind::Edges => Self::Edges {
                ids: strings("edge_id")?,
                from: strings("source")?,
                to: strings("target")?,
                labels: strings("label")?,
            },
        })
    }
}

struct Row<'a, 'b> {
    columns: &'b Columns<'a>,
    properties: &'b [Property<'a>],
    row: usize,
}
impl Serialize for Row<'_, '_> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let props = Properties {
            columns: self.properties,
            row: self.row,
        };
        match self.columns {
            Columns::Nodes { ids, labels } => {
                let mut row = serializer.serialize_struct("Node", 3)?;
                row.serialize_field("id", ids.value(self.row))?;
                row.serialize_field("label", labels.value(self.row))?;
                row.serialize_field("props", &props)?;
                row.end()
            }
            Columns::Edges {
                ids,
                from,
                to,
                labels,
            } => {
                let mut row = serializer.serialize_struct("Edge", 5)?;
                row.serialize_field("id", &(!ids.is_null(self.row)).then(|| ids.value(self.row)))?;
                row.serialize_field("from", from.value(self.row))?;
                row.serialize_field("to", to.value(self.row))?;
                row.serialize_field("label", labels.value(self.row))?;
                row.serialize_field("props", &props)?;
                row.end()
            }
        }
    }
}

struct Property<'a> {
    key: &'a str,
    present: &'a BooleanArray,
    values: Values<'a>,
}
fn properties<E: Error>(batch: &RecordBatch) -> Result<Vec<Property<'_>>, E> {
    let mut columns = Vec::new();
    for (index, field) in batch.schema_ref().fields().iter().enumerate() {
        let Some(key) = field.name().strip_prefix("property.") else {
            continue;
        };
        let presence = batch
            .schema_ref()
            .fields()
            .iter()
            .position(|field| field.name().strip_prefix("present.") == Some(key))
            .ok_or_else(|| E::custom("missing property presence column"))?;
        columns.push(Property {
            key,
            present: cast::<BooleanArray, E>(batch.column(presence))?,
            values: Values::new::<E>(batch.column(index))?,
        });
    }
    // Ordinary Props is a BTreeMap. Match its deterministic property order even
    // when an external Arrow producer orders schema fields differently.
    columns.sort_unstable_by_key(|column| column.key);
    Ok(columns)
}

fn column<'a, T: 'static, E: Error>(batch: &'a RecordBatch, name: &str) -> Result<&'a T, E> {
    let array = batch
        .column_by_name(name)
        .ok_or_else(|| E::custom(format!("missing graph column {name}")))?;
    cast::<T, E>(array)
}
fn cast<T: 'static, E: Error>(array: &ArrayRef) -> Result<&T, E> {
    array
        .as_any()
        .downcast_ref::<T>()
        .ok_or_else(|| E::custom("unsupported native graph array representation"))
}

enum Values<'a> {
    Null,
    Bool(&'a BooleanArray),
    Int(&'a Int64Array),
    Float(&'a Float64Array),
    String(&'a StringArray),
}
impl<'a> Values<'a> {
    fn new<E: Error>(array: &'a ArrayRef) -> Result<Self, E> {
        Ok(match array.data_type() {
            DataType::Null => Self::Null,
            DataType::Boolean => Self::Bool(cast::<BooleanArray, E>(array)?),
            DataType::Int64 => Self::Int(cast::<Int64Array, E>(array)?),
            DataType::Float64 => Self::Float(cast::<Float64Array, E>(array)?),
            DataType::Utf8 => Self::String(cast::<StringArray, E>(array)?),
            _ => return Err(E::custom("unsupported native graph property type")),
        })
    }
    fn value(&self, row: usize) -> Scalar<'_> {
        match self {
            Self::Bool(array) if !array.is_null(row) => Scalar::Bool(array.value(row)),
            Self::Int(array) if !array.is_null(row) => Scalar::Int(array.value(row)),
            Self::Float(array) if !array.is_null(row) => Scalar::Float(array.value(row)),
            Self::String(array) if !array.is_null(row) => Scalar::String(array.value(row)),
            Self::Null | Self::Bool(_) | Self::Int(_) | Self::Float(_) | Self::String(_) => {
                Scalar::Null
            }
        }
    }
}

/// Borrowed native subset of Value's tagged wire representation. Parity tests
/// compare complete bytes against core Graph/Value serialization on every major.
#[derive(Serialize)]
#[serde(tag = "type", content = "value", rename_all = "snake_case")]
enum Scalar<'a> {
    Null,
    Bool(bool),
    Int(i64),
    Float(f64),
    String(&'a str),
}
struct Properties<'a, 'b> {
    columns: &'b [Property<'a>],
    row: usize,
}
impl Serialize for Properties<'_, '_> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let count = self
            .columns
            .iter()
            .filter(|column| column.present.value(self.row))
            .count();
        let mut properties = serializer.serialize_map(Some(count))?;
        for column in self.columns {
            if column.present.value(self.row) {
                properties.serialize_entry(column.key, &column.values.value(self.row))?;
            }
        }
        properties.end()
    }
}

#[cfg(test)]
#[path = "graph_serialization_tests.rs"]
mod tests;
