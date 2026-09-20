//! Typed node property columns, row-aligned with a projection.
//!
//! A projection is topology: expensive to build, cached, the same for every
//! call over a graph. What a kernel needs per node varies per call — an
//! embedding for one, a seed community for the next — so properties are a
//! sibling of the projection rather than part of it. A `NodeProperties` is built
//! *against* a projection and holds it, which is what makes row alignment a fact
//! rather than a convention: it cannot be paired with the wrong projection,
//! because it carries the right one. Design: `docs/goals/node-properties-design.md`.

use std::collections::HashMap;

use grust_core::{Graph, Value};
use grust_procedures::MemoryAccount;

use crate::{AlgorithmError, GraphProjection, Result, buffer::Buffer};

/// What a property column holds.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PropertyKind {
    /// `f64`: coordinates, supplies, scalar features. Integers are accepted
    /// within the range `f64` represents exactly.
    Number,
    /// `i64`: community ids, seeds. Booleans are accepted as 0 and 1.
    Integer,
    /// A fixed number of `f32` per node: embeddings, feature vectors. The
    /// dimension is that of the first value present, and every other must match.
    Vector,
    /// A string, dictionary-encoded, for **equality filters only**: no order,
    /// no arithmetic. Codes are assigned in order of first appearance by row,
    /// so they do not depend on how the read was scheduled. A category has no
    /// default — there is no string to invent — so a missing one is rejected or
    /// kept as a null.
    Category,
}

/// What to do for a node that has no value.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum MissingProperty {
    /// An error naming the node and the key. The default: a silent zero inside a
    /// feature vector is a wrong answer that looks like a right one.
    Reject,
    /// Substitute this value; for a vector, every component. Not for categories.
    Default(f64),
    /// Keep the absence. Only the `optional_*` accessors read such a column, so
    /// a kernel that did not ask for nulls cannot forget to handle one.
    Null,
}

/// One column to read.
#[derive(Clone, Copy, Debug)]
pub struct PropertyRequest<'a> {
    /// The property's name on the node.
    pub key: &'a str,
    /// What it must hold.
    pub kind: PropertyKind,
    /// What to do where it is absent or null.
    pub missing: MissingProperty,
}

impl<'a> PropertyRequest<'a> {
    /// A column that must be present on every projected node.
    pub fn required(key: &'a str, kind: PropertyKind) -> Self {
        Self {
            key,
            kind,
            missing: MissingProperty::Reject,
        }
    }
}

/// One value as read from a source, before it is checked against the kind asked
/// for. Both constructors reduce their input to this, so the rules below are
/// written once.
#[derive(Clone, Copy)]
pub(crate) enum Cell<'a> {
    Float(f64),
    Int(i64),
    Bool(bool),
    Text(&'a str),
    Floats(&'a [f64]),
    /// Only Arrow produces single-precision lists; `Value` has no such array.
    #[cfg(feature = "arrow")]
    Singles(&'a [f32]),
    Ints(&'a [i64]),
    /// A value of a type no kind accepts.
    Other,
}

impl<'a> Cell<'a> {
    fn of(value: &'a Value) -> Self {
        match value {
            Value::Float(value) => Self::Float(*value),
            Value::Int(value) => Self::Int(*value),
            Value::Bool(value) => Self::Bool(*value),
            Value::String(value) => Self::Text(value),
            Value::FloatArray(values) => Self::Floats(values),
            Value::IntArray(values) => Self::Ints(values),
            _ => Self::Other,
        }
    }
}

enum Values {
    Number(Buffer<f64>),
    Integer(Buffer<i64>),
    Vector {
        values: Buffer<f32>,
        dimension: usize,
    },
    Category {
        codes: Buffer<u32>,
        dictionary: Vec<String>,
        /// Admission for the dictionary's strings.
        _strings: MemoryAccount,
    },
}

pub(crate) struct Column {
    key: String,
    values: Values,
    /// Present per row; `None` when every row has a value.
    valid: Option<Buffer<bool>>,
}

/// Property columns for the nodes of one projection, in its row order.
pub struct NodeProperties {
    pub(crate) graph: GraphProjection,
    pub(crate) columns: Vec<Column>,
}

/// A vector column: `dimension` values per row, row by row.
#[derive(Clone, Copy, Debug)]
pub struct Vectors<'a> {
    /// `rows * dimension` values.
    pub values: &'a [f32],
    /// Values per row; zero only when no projected node has a value.
    pub dimension: usize,
}

impl<'a> Vectors<'a> {
    /// The vector of one projection row.
    pub fn row(&self, row: usize) -> &'a [f32] {
        &self.values[row * self.dimension..(row + 1) * self.dimension]
    }
}

/// A category column: a code per row, and the string each code stands for.
#[derive(Clone, Copy, Debug)]
pub struct Categories<'a> {
    /// Index into `dictionary` per row.
    pub codes: &'a [u32],
    /// Distinct strings, in order of first appearance by row.
    pub dictionary: &'a [String],
}

impl Categories<'_> {
    /// The code of `value`, if any node has it. Compare codes, not strings.
    pub fn code_of(&self, value: &str) -> Option<u32> {
        self.dictionary
            .iter()
            .position(|entry| entry == value)
            .and_then(|index| u32::try_from(index).ok())
    }
}

impl NodeProperties {
    /// Read `wanted` from `graph` for the nodes `projection` selected.
    ///
    /// `graph` must be the graph the projection was built from: a projected node
    /// that `graph` does not contain is an error, as is a key requested twice. A
    /// node the projection's label selection left out contributes nothing, so
    /// rows stay aligned under any selection. Columns are admitted against the
    /// execution's memory limit before they are filled, and reading charges one
    /// work unit per node per column, plus one per vector component.
    pub fn from_graph(
        graph: &Graph,
        projection: &GraphProjection,
        wanted: &[PropertyRequest<'_>],
    ) -> Result<Self> {
        let context = projection.execution();
        context.checkpoint()?;
        let n = projection.node_count();
        validate_requests(wanted)?;

        // Projection row per snapshot node, once, for every column.
        let mut meter = context.work_meter();
        let mut rows = Buffer::capacity(graph.nodes.len(), context)?;
        let mut found = 0usize;
        for node in &graph.nodes {
            meter.charge(1)?;
            // `source` is the projection's own id lookup; a miss is a node the
            // label selection left out, not an error here.
            let row = projection.source(node.id.as_str()).ok();
            found += usize::from(row.is_some());
            rows.values.push(row);
        }
        if found != n {
            return Err(invalid(format!(
                "the graph has {found} of the projection's {n} nodes: properties must be read from the graph the projection was built from"
            )));
        }

        let mut columns = Vec::new();
        columns.try_reserve_exact(wanted.len())?;
        for request in wanted {
            let mut builder = Builder::new(request, n, projection)?;
            for (node, row) in graph.nodes.iter().zip(&rows.values) {
                let Some(row) = *row else { continue };
                meter.charge(1)?;
                match node.props.get(request.key) {
                    None | Some(Value::Null) => {
                        meter.charge(builder.absent(row, node.id.as_str())?)?
                    }
                    Some(value) => {
                        let extra = builder.present(row, node.id.as_str(), Cell::of(value))?;
                        meter.charge(extra)?;
                    }
                }
            }
            columns.push(builder.finish()?);
        }
        Ok(Self {
            graph: projection.clone(),
            columns,
        })
    }

    /// The projection these rows are aligned with.
    pub fn projection(&self) -> &GraphProjection {
        &self.graph
    }

    /// Keys, in the order requested.
    pub fn keys(&self) -> impl Iterator<Item = &str> {
        self.columns.iter().map(|column| column.key.as_str())
    }

    fn column(&self, key: &str) -> Result<&Column> {
        self.columns
            .iter()
            .find(|column| column.key == key)
            .ok_or_else(|| invalid(format!("node property {key} was not requested")))
    }

    /// A column read with `Reject` or `Default`: a value on every row.
    fn complete(&self, key: &str) -> Result<&Column> {
        let column = self.column(key)?;
        if column.valid.is_some() {
            return Err(invalid(format!(
                "node property {key} was read keeping nulls; use the optional accessor"
            )));
        }
        Ok(column)
    }

    /// A number per row. Errors if `key` was not requested as a number, or was
    /// requested keeping nulls.
    pub fn numbers(&self, key: &str) -> Result<&[f64]> {
        match &self.complete(key)?.values {
            Values::Number(values) => Ok(&values.values),
            _ => Err(wrong_kind(key, "a number")),
        }
    }

    /// An integer per row.
    pub fn integers(&self, key: &str) -> Result<&[i64]> {
        match &self.complete(key)?.values {
            Values::Integer(values) => Ok(&values.values),
            _ => Err(wrong_kind(key, "an integer")),
        }
    }

    /// A vector per row.
    pub fn vectors(&self, key: &str) -> Result<Vectors<'_>> {
        match &self.complete(key)?.values {
            Values::Vector { values, dimension } => Ok(Vectors {
                values: &values.values,
                dimension: *dimension,
            }),
            _ => Err(wrong_kind(key, "a vector")),
        }
    }

    /// A category per row.
    pub fn categories(&self, key: &str) -> Result<Categories<'_>> {
        match &self.complete(key)?.values {
            Values::Category {
                codes, dictionary, ..
            } => Ok(Categories {
                codes: &codes.values,
                dictionary,
            }),
            _ => Err(wrong_kind(key, "a category")),
        }
    }

    /// Integers where absence was kept: the values, and which rows have one. A
    /// row without a value holds zero, which means nothing; consult `present`.
    pub fn optional_integers(&self, key: &str) -> Result<(&[i64], &[bool])> {
        let column = self.column(key)?;
        match (&column.values, &column.valid) {
            (Values::Integer(values), Some(valid)) => Ok((&values.values, &valid.values)),
            (Values::Integer(_), None) => Err(invalid(format!(
                "node property {key} was not read keeping nulls"
            ))),
            _ => Err(wrong_kind(key, "an integer")),
        }
    }

    /// Categories where absence was kept; see [`Self::optional_integers`]. A
    /// row without a value holds code zero, which is a real code for some other
    /// row, so it means nothing here: consult `present`.
    pub fn optional_categories(&self, key: &str) -> Result<(Categories<'_>, &[bool])> {
        let column = self.column(key)?;
        match (&column.values, &column.valid) {
            (
                Values::Category {
                    codes, dictionary, ..
                },
                Some(valid),
            ) => Ok((
                Categories {
                    codes: &codes.values,
                    dictionary,
                },
                &valid.values,
            )),
            (Values::Category { .. }, None) => Err(invalid(format!(
                "node property {key} was not read keeping nulls"
            ))),
            _ => Err(wrong_kind(key, "a category")),
        }
    }

    /// Numbers where absence was kept; see [`Self::optional_integers`].
    pub fn optional_numbers(&self, key: &str) -> Result<(&[f64], &[bool])> {
        let column = self.column(key)?;
        match (&column.values, &column.valid) {
            (Values::Number(values), Some(valid)) => Ok((&values.values, &valid.values)),
            (Values::Number(_), None) => Err(invalid(format!(
                "node property {key} was not read keeping nulls"
            ))),
            _ => Err(wrong_kind(key, "a number")),
        }
    }
}

pub(crate) fn invalid(message: String) -> AlgorithmError {
    AlgorithmError::InvalidArguments(message)
}

fn wrong_kind(key: &str, wanted: &str) -> AlgorithmError {
    invalid(format!("node property {key} was not read as {wanted}"))
}

pub(crate) fn validate_requests(wanted: &[PropertyRequest<'_>]) -> Result<()> {
    for (index, request) in wanted.iter().enumerate() {
        validate(request)?;
        if wanted[..index].iter().any(|other| other.key == request.key) {
            return Err(invalid(format!(
                "node property {} is requested twice",
                request.key
            )));
        }
    }
    Ok(())
}

fn validate(request: &PropertyRequest<'_>) -> Result<()> {
    if request.key.is_empty() {
        return Err(invalid("node property key must be nonempty".into()));
    }
    match (request.kind, request.missing) {
        (PropertyKind::Category, MissingProperty::Default(_)) => Err(invalid(format!(
            "node property {}: a category has no default; reject or keep nulls",
            request.key
        ))),
        (PropertyKind::Vector, MissingProperty::Null) => Err(invalid(format!(
            "node property {}: vectors cannot keep nulls; reject or give a default",
            request.key
        ))),
        (_, MissingProperty::Default(value)) if !value.is_finite() => Err(invalid(format!(
            "node property {}: the default must be finite",
            request.key
        ))),
        (PropertyKind::Integer, MissingProperty::Default(value))
            if value.fract() != 0.0 || value.abs() > 9_007_199_254_740_992.0 =>
        {
            Err(invalid(format!(
                "node property {}: an integer default must be a whole number within 2^53",
                request.key
            )))
        }
        _ => Ok(()),
    }
}

/// Fills one column row by row. Rows arrive in snapshot order, which is
/// projection row order, so vectors are appended rather than indexed.
pub(crate) struct Builder<'a> {
    request: &'a PropertyRequest<'a>,
    values: Values,
    valid: Option<Buffer<bool>>,
    rows: usize,
    graph: &'a GraphProjection,
    codes: HashMap<String, u32>,
}

impl<'a> Builder<'a> {
    pub(crate) fn new(
        request: &'a PropertyRequest<'a>,
        rows: usize,
        graph: &'a GraphProjection,
    ) -> Result<Self> {
        let context = graph.execution();
        let values = match request.kind {
            PropertyKind::Number => Values::Number(Buffer::filled(rows, 0.0, context)?),
            PropertyKind::Integer => Values::Integer(Buffer::filled(rows, 0, context)?),
            // Admitted once the first value gives the dimension.
            PropertyKind::Vector => Values::Vector {
                values: Buffer::capacity(0, context)?,
                dimension: 0,
            },
            PropertyKind::Category => Values::Category {
                codes: Buffer::filled(rows, 0, context)?,
                dictionary: Vec::new(),
                _strings: context.memory_account(),
            },
        };
        let valid = match request.missing {
            MissingProperty::Null => Some(Buffer::filled(rows, false, context)?),
            _ => None,
        };
        Ok(Self {
            request,
            values,
            valid,
            rows,
            graph,
            codes: HashMap::new(),
        })
    }

    /// Record that `row` has no value; returns extra work to charge.
    pub(crate) fn absent(&mut self, row: usize, node: &str) -> Result<usize> {
        let key = self.request.key;
        match self.request.missing {
            MissingProperty::Reject => Err(invalid(format!(
                "node {node} has no value for property {key}"
            ))),
            MissingProperty::Null => Ok(0),
            MissingProperty::Default(default) => {
                match &mut self.values {
                    Values::Number(values) => values.values[row] = default,
                    Values::Integer(values) => values.values[row] = default as i64,
                    Values::Vector { values, dimension } => {
                        // Nothing to do while the width is unknown: the column
                        // is allocated already filled with the default, so a
                        // row that arrives before the first value is covered.
                        if *dimension != 0 {
                            let start = row * *dimension;
                            values.values[start..start + *dimension].fill(default as f32);
                        }
                    }
                    Values::Category { .. } => unreachable!("validated: no category default"),
                }
                // A defaulted vector writes `dimension` components, the same
                // work a present one charges for the same number.
                Ok(match &self.values {
                    Values::Vector { dimension, .. } => *dimension,
                    _ => 0,
                })
            }
        }
    }

    /// Store one value; returns extra work to charge (vector components).
    pub(crate) fn present(&mut self, row: usize, node: &str, value: Cell<'_>) -> Result<usize> {
        let key = self.request.key;
        let mismatch =
            |wanted: &str| invalid(format!("node {node}: property {key} is not {wanted}"));
        let mut extra = 0;
        match &mut self.values {
            Values::Number(values) => {
                values.values[row] = match value {
                    Cell::Float(value) if value.is_finite() => value,
                    Cell::Int(value) if value.unsigned_abs() <= 9_007_199_254_740_992 => {
                        value as f64
                    }
                    _ => return Err(mismatch("a finite number within the exact f64 range")),
                };
            }
            Values::Integer(values) => {
                values.values[row] = match value {
                    Cell::Int(value) => value,
                    Cell::Bool(value) => i64::from(value),
                    _ => return Err(mismatch("an integer")),
                };
            }
            Values::Vector { values, dimension } => {
                let narrowed = |component: f64| {
                    let narrow = component as f32;
                    narrow
                        .is_finite()
                        .then_some(narrow)
                        .ok_or_else(|| mismatch("finite in single precision"))
                };
                let length = match value {
                    Cell::Floats(items) => items.len(),
                    #[cfg(feature = "arrow")]
                    Cell::Singles(items) => items.len(),
                    Cell::Ints(items) => items.len(),
                    _ => return Err(mismatch("a numeric list")),
                };
                if length == 0 {
                    return Err(mismatch("a nonempty list"));
                }
                if *dimension == 0 {
                    // First value: the width is now known, so admit the whole
                    // column and fill the rows that arrived before it.
                    let total = self.rows.checked_mul(length).ok_or_else(|| {
                        invalid(format!("node property {key} overflows the address space"))
                    })?;
                    let fill = match self.request.missing {
                        MissingProperty::Default(default) => default as f32,
                        _ => 0.0,
                    };
                    *values = Buffer::filled(total, fill, self.graph.execution())?;
                    *dimension = length;
                } else if length != *dimension {
                    return Err(invalid(format!(
                        "node {node}: property {key} has {length} components where earlier nodes have {dimension}"
                    )));
                }
                // Written at the row's own offset, so batches may arrive in
                // any order: the Arrow path takes them from a caller's
                // DataFrame, whose order is not ours to dictate.
                let start = row * length;
                let slot = &mut values.values[start..start + length];
                match value {
                    Cell::Floats(items) => {
                        for (into, &item) in slot.iter_mut().zip(items) {
                            *into = narrowed(item)?;
                        }
                    }
                    #[cfg(feature = "arrow")]
                    Cell::Singles(items) => {
                        for (into, &item) in slot.iter_mut().zip(items) {
                            *into = narrowed(f64::from(item))?;
                        }
                    }
                    Cell::Ints(items) => {
                        for (into, &item) in slot.iter_mut().zip(items) {
                            *into = narrowed(item as f64)?;
                        }
                    }
                    _ => unreachable!("matched above"),
                }
                extra = length;
            }
            Values::Category {
                codes,
                dictionary,
                _strings,
            } => {
                let Cell::Text(text) = value else {
                    return Err(mismatch("a string"));
                };
                let code = match self.codes.get(text) {
                    Some(&code) => code,
                    None => {
                        let code = u32::try_from(dictionary.len()).map_err(|_| {
                            invalid(format!("node property {key} has too many distinct values"))
                        })?;
                        // Once for the dictionary, once for the lookup key.
                        _strings.charge(2 * (text.len() + size_of::<String>()))?;
                        dictionary.try_reserve(1)?;
                        dictionary.push(text.to_owned());
                        self.codes.insert(text.to_owned(), code);
                        code
                    }
                };
                codes.values[row] = code;
            }
        }
        if let Some(valid) = &mut self.valid {
            valid.values[row] = true;
        }
        Ok(extra)
    }

    pub(crate) fn finish(self) -> Result<Column> {
        debug_assert!(
            !matches!(&self.values, Values::Vector { values, dimension }
                if values.values.len() != self.rows * dimension),
            "a vector column is allocated whole, so it cannot be part-filled"
        );
        Ok(Column {
            key: self.request.key.into(),
            values: self.values,
            valid: self.valid,
        })
    }
}
