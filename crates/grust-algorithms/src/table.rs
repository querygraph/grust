//! Node-aligned result tables: one row per projected node, typed named columns.
//!
//! Most graph algorithms answer "a value per node" — a core number, a triangle
//! count, a centrality, a community. Each used to need its own result type and
//! its own arm in the Arrow and row adapters. A kernel now hands its buffers to
//! a `NodeTable`, and both adapters are written once. Buffers move in; nothing
//! is copied, and their memory admission travels with them.

use crate::{AlgorithmError, GraphProjection, Result, buffer::Buffer};
use grust_core::NodeId;

/// One value per projected node, in projection row order.
// The catalog's kernels arrive one at a time; some column kinds precede their first user.
#[allow(dead_code)]
pub(crate) enum NodeColumn {
    /// Signed integers; never null.
    Integer(Buffer<i64>),
    /// Finite doubles; never null.
    Number(Buffer<f64>),
    /// Doubles where NaN means "no value" and is emitted as null.
    OptionalNumber(Buffer<f64>),
    /// A projection row, emitted as that node's external id.
    Node(Buffer<usize>),
    /// Booleans; never null.
    Boolean(Buffer<bool>),
}

impl NodeColumn {
    fn len(&self) -> usize {
        match self {
            Self::Integer(values) => values.values.len(),
            Self::Number(values) | Self::OptionalNumber(values) => values.values.len(),
            Self::Node(values) => values.values.len(),
            Self::Boolean(values) => values.values.len(),
        }
    }
}

/// A whole-result value, repeated on every row the way `pagerank` repeats its
/// iteration count: tabular consumers have nowhere else to read it.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum TableScalar {
    /// Signed integer.
    Integer(i64),
    /// Double.
    Number(f64),
    /// Boolean.
    Boolean(bool),
}

/// One cell, borrowed from the table.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum TableValue<'a> {
    /// Signed integer.
    Integer(i64),
    /// Finite double.
    Number(f64),
    /// No value for this node.
    Null,
    /// Another projected node, by external id.
    Node(&'a NodeId),
    /// Boolean.
    Boolean(bool),
}

/// The declared type of a column, for adapters that build typed output.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TableType {
    /// Signed 64-bit integer.
    Integer,
    /// Double, possibly null.
    Number,
    /// External node id.
    Node,
    /// Boolean.
    Boolean,
}

/// Typed per-node results retaining projection identity and memory admission.
/// Columns come first, in the order the kernel declared them, then scalars.
pub struct NodeTable {
    graph: GraphProjection,
    columns: Vec<(&'static str, NodeColumn)>,
    scalars: Vec<(&'static str, TableScalar)>,
}

impl NodeTable {
    pub(crate) fn new(graph: &GraphProjection) -> Self {
        Self {
            graph: graph.clone(),
            columns: Vec::new(),
            scalars: Vec::new(),
        }
    }

    pub(crate) fn column(mut self, name: &'static str, column: NodeColumn) -> Result<Self> {
        let n = self.graph.node_count();
        if column.len() != n {
            return Err(AlgorithmError::OutputContract(format!(
                "column `{name}` has {} rows for {n} nodes",
                column.len()
            )));
        }
        if let NodeColumn::Node(rows) = &column
            && rows.values.iter().any(|&row| row >= n)
        {
            return Err(AlgorithmError::OutputContract(format!(
                "column `{name}` refers to a node outside the projection"
            )));
        }
        self.columns.push((name, column));
        Ok(self)
    }

    pub(crate) fn scalar(mut self, name: &'static str, value: TableScalar) -> Self {
        self.scalars.push((name, value));
        self
    }

    /// Projection supplying external ids and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        &self.graph
    }

    /// Rows: one per projected node.
    pub fn rows(&self) -> usize {
        self.graph.node_count()
    }

    /// Columns after `nodeId`, per-node columns first and then scalars.
    pub fn width(&self) -> usize {
        self.columns.len() + self.scalars.len()
    }

    /// Name and declared type of column `index`.
    pub fn field(&self, index: usize) -> (&'static str, TableType) {
        if let Some((name, column)) = self.columns.get(index) {
            let kind = match column {
                NodeColumn::Integer(_) => TableType::Integer,
                NodeColumn::Number(_) | NodeColumn::OptionalNumber(_) => TableType::Number,
                NodeColumn::Node(_) => TableType::Node,
                NodeColumn::Boolean(_) => TableType::Boolean,
            };
            return (name, kind);
        }
        let (name, scalar) = self.scalars[index - self.columns.len()];
        let kind = match scalar {
            TableScalar::Integer(_) => TableType::Integer,
            TableScalar::Number(_) => TableType::Number,
            TableScalar::Boolean(_) => TableType::Boolean,
        };
        (name, kind)
    }

    /// The cell at `column`, `row`.
    pub fn value(&self, column: usize, row: usize) -> TableValue<'_> {
        if let Some((_, values)) = self.columns.get(column) {
            return match values {
                NodeColumn::Integer(values) => TableValue::Integer(values.values[row]),
                NodeColumn::Number(values) => TableValue::Number(values.values[row]),
                NodeColumn::OptionalNumber(values) => {
                    let value = values.values[row];
                    if value.is_nan() {
                        TableValue::Null
                    } else {
                        TableValue::Number(value)
                    }
                }
                NodeColumn::Node(values) => {
                    TableValue::Node(&self.graph.node_ids()[values.values[row]])
                }
                NodeColumn::Boolean(values) => TableValue::Boolean(values.values[row]),
            };
        }
        match self.scalars[column - self.columns.len()].1 {
            TableScalar::Integer(value) => TableValue::Integer(value),
            TableScalar::Number(value) => TableValue::Number(value),
            TableScalar::Boolean(value) => TableValue::Boolean(value),
        }
    }

    /// An integer column by name.
    pub fn integers(&self, name: &str) -> Option<&[i64]> {
        self.columns.iter().find_map(|(n, c)| match c {
            NodeColumn::Integer(values) if *n == name => Some(values.values.as_slice()),
            _ => None,
        })
    }

    /// A double column by name; NaN marks a node without a value.
    pub fn numbers(&self, name: &str) -> Option<&[f64]> {
        self.columns.iter().find_map(|(n, c)| match c {
            NodeColumn::Number(values) | NodeColumn::OptionalNumber(values) if *n == name => {
                Some(values.values.as_slice())
            }
            _ => None,
        })
    }

    /// A node-reference column by name, as projection rows.
    pub fn nodes(&self, name: &str) -> Option<&[usize]> {
        self.columns.iter().find_map(|(n, c)| match c {
            NodeColumn::Node(values) if *n == name => Some(values.values.as_slice()),
            _ => None,
        })
    }

    /// A whole-result scalar by name.
    pub fn scalar_value(&self, name: &str) -> Option<TableScalar> {
        self.scalars
            .iter()
            .find_map(|(n, value)| (*n == name).then_some(*value))
    }
}
