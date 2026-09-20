//! Node properties from Arrow node batches.

use arrow_array::{
    Array, ArrayRef, BooleanArray, FixedSizeListArray, Float32Array, Float64Array, Int32Array,
    Int64Array, LargeStringArray, ListArray, RecordBatch, StringArray,
};

use crate::{
    AlgorithmError, GraphProjection, NodeProperties, PropertyRequest, Result,
    buffer::Buffer,
    properties::{Builder, Cell, invalid, validate_requests},
};

impl NodeProperties {
    /// Read `wanted` from the node batches `projection` was built from.
    ///
    /// Batches carry a Utf8 `node_id` and, per requested key, a
    /// `property.<key>` column: `Float64`, `Float32`, `Int64`, `Int32` or
    /// `Boolean` for numbers and integers; `FixedSizeList` or `List` of
    /// `Float32` or `Float64` for vectors; `Utf8` or `LargeUtf8` for
    /// categories. A dictionary-encoded column must be cast to `Utf8` first.
    ///
    /// A value is absent where the column is null, or where an optional Boolean
    /// `present.<key>` column says so — the convention the projection's weights
    /// follow. A batch with no `property.<key>` column has the value absent on
    /// every one of its rows. Rules, accounting and errors are those of
    /// [`NodeProperties::from_graph`].
    pub fn from_arrow_batches(
        node_batches: &[RecordBatch],
        projection: &GraphProjection,
        wanted: &[PropertyRequest<'_>],
    ) -> Result<Self> {
        let context = projection.execution();
        context.checkpoint()?;
        validate_requests(wanted)?;
        let n = projection.node_count();
        let mut meter = context.work_meter();

        // Projection row per batch row, once, for every column.
        let total = node_batches
            .iter()
            .try_fold(0usize, |sum, batch| sum.checked_add(batch.num_rows()))
            .ok_or_else(|| AlgorithmError::Numerical("Arrow row count overflow".into()))?;
        let mut rows = Buffer::capacity(total, context)?;
        let mut found = 0usize;
        for batch in node_batches {
            let ids = node_ids(batch)?;
            for row in 0..batch.num_rows() {
                meter.charge(1)?;
                if ids.is_null(row) {
                    return Err(invalid("Arrow column node_id must not contain null".into()));
                }
                let projected = projection.source(ids.value(row)).ok();
                found += usize::from(projected.is_some());
                rows.values.push(projected);
            }
        }
        if found != n {
            return Err(invalid(format!(
                "the node batches have {found} of the projection's {n} nodes: properties must be read from the batches the projection was built from"
            )));
        }

        let mut columns = Vec::new();
        columns.try_reserve_exact(wanted.len())?;
        for request in wanted {
            let mut builder = Builder::new(request, n, projection)?;
            let mut offset = 0;
            for batch in node_batches {
                let ids = node_ids(batch)?;
                let source = Source::new(batch, request.key)?;
                for row in 0..batch.num_rows() {
                    let Some(projected) = rows.values[offset + row] else {
                        continue;
                    };
                    meter.charge(1)?;
                    let id = ids.value(row);
                    match source.cell(row) {
                        None => builder.absent(projected, id)?,
                        Some(cell) => {
                            let extra = builder.present(projected, id, cell.borrow())?;
                            meter.charge(extra)?;
                        }
                    }
                }
                offset += batch.num_rows();
            }
            columns.push(builder.finish()?);
        }
        Ok(Self {
            graph: projection.clone(),
            columns,
        })
    }
}

fn node_ids(batch: &RecordBatch) -> Result<&StringArray> {
    column(batch, "node_id")?
        .and_then(|column| column.as_any().downcast_ref())
        .ok_or_else(|| {
            AlgorithmError::Unsupported("Arrow column node_id must exist with Utf8 type".into())
        })
}

// Arrow schemas permit duplicate names; never silently pick one.
fn column<'a>(batch: &'a RecordBatch, name: &str) -> Result<Option<&'a ArrayRef>> {
    let schema = batch.schema();
    let mut matches = schema
        .fields()
        .iter()
        .enumerate()
        .filter(|(_, field)| field.name() == name);
    let first = matches.next().map(|(index, _)| index);
    if matches.next().is_some() {
        return Err(invalid(format!("ambiguous duplicate Arrow column: {name}")));
    }
    Ok(first.map(|index| batch.column(index)))
}

/// A list row's values, owned because a list array hands out a fresh array per
/// row rather than a slice of itself.
enum Owned<'a> {
    Borrowed(Cell<'a>),
    Floats(Vec<f64>),
    Singles(Vec<f32>),
}

impl Owned<'_> {
    fn borrow(&self) -> Cell<'_> {
        match self {
            Self::Borrowed(cell) => *cell,
            Self::Floats(values) => Cell::Floats(values),
            Self::Singles(values) => Cell::Singles(values),
        }
    }
}

struct Source<'a> {
    values: Option<&'a ArrayRef>,
    presence: Option<&'a BooleanArray>,
}

impl<'a> Source<'a> {
    fn new(batch: &'a RecordBatch, key: &str) -> Result<Self> {
        let present = format!("present.{key}");
        let presence = match column(batch, &present)? {
            None => None,
            Some(column) => {
                let flags = column
                    .as_any()
                    .downcast_ref::<BooleanArray>()
                    .ok_or_else(|| {
                        AlgorithmError::Unsupported(format!(
                            "Arrow column {present} must be Boolean"
                        ))
                    })?;
                if flags.null_count() != 0 {
                    return Err(invalid(format!(
                        "Arrow column {present} must not contain null"
                    )));
                }
                Some(flags)
            }
        };
        Ok(Self {
            values: column(batch, &format!("property.{key}"))?,
            presence,
        })
    }

    /// The value at `row`, or `None` where it is absent. A type no kind accepts
    /// comes back as `Cell::Other`, which every kind refuses by name.
    fn cell(&self, row: usize) -> Option<Owned<'a>> {
        let values = self.values?;
        if values.is_null(row) || self.presence.is_some_and(|flags| !flags.value(row)) {
            return None;
        }
        let any = values.as_any();
        let scalar = if let Some(column) = any.downcast_ref::<Float64Array>() {
            Cell::Float(column.value(row))
        } else if let Some(column) = any.downcast_ref::<Float32Array>() {
            Cell::Float(f64::from(column.value(row)))
        } else if let Some(column) = any.downcast_ref::<Int64Array>() {
            Cell::Int(column.value(row))
        } else if let Some(column) = any.downcast_ref::<Int32Array>() {
            Cell::Int(i64::from(column.value(row)))
        } else if let Some(column) = any.downcast_ref::<BooleanArray>() {
            Cell::Bool(column.value(row))
        } else if let Some(column) = any.downcast_ref::<StringArray>() {
            Cell::Text(column.value(row))
        } else if let Some(column) = any.downcast_ref::<LargeStringArray>() {
            Cell::Text(column.value(row))
        } else {
            let items = if let Some(column) = any.downcast_ref::<FixedSizeListArray>() {
                Some(column.value(row))
            } else {
                any.downcast_ref::<ListArray>()
                    .map(|column| column.value(row))
            };
            return Some(items.map_or(Owned::Borrowed(Cell::Other), |items| list(&items)));
        };
        Some(Owned::Borrowed(scalar))
    }
}

/// A list row as floats. A null element has no honest reading as a component,
/// so it becomes NaN, which the builder refuses as not finite.
fn list(items: &ArrayRef) -> Owned<'static> {
    let any = items.as_any();
    if let Some(column) = any.downcast_ref::<Float32Array>() {
        Owned::Singles(
            (0..column.len())
                .map(|index| {
                    if column.is_null(index) {
                        f32::NAN
                    } else {
                        column.value(index)
                    }
                })
                .collect(),
        )
    } else if let Some(column) = any.downcast_ref::<Float64Array>() {
        Owned::Floats(
            (0..column.len())
                .map(|index| {
                    if column.is_null(index) {
                        f64::NAN
                    } else {
                        column.value(index)
                    }
                })
                .collect(),
        )
    } else {
        Owned::Borrowed(Cell::Other)
    }
}
