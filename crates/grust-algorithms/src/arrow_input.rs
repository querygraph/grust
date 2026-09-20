//! Direct typed Arrow ingestion: no Graph, Props, JSON or Value materialization.

use std::collections::HashMap;

use arrow_array::{Array, BooleanArray, Float64Array, Int64Array, RecordBatch, StringArray};

use crate::{
    AlgorithmError, ExecutionContext, GraphProjection, ProjectionEdge, ProjectionOptions, Result,
    SnapshotIdentity, WeightSelection,
    buffer::Buffer,
    graph_input::{
        integer_weight, missing_weight, selects, validate_weight, validate_weight_selection,
    },
};

impl GraphProjection {
    /// Prepare topology directly from multiple node and edge record batches.
    /// Structural columns follow grust-arrow: Utf8 `node_id`, `label`, `source`,
    /// `target`, nullable Utf8 `edge_id`. Selected weights use Float64 or Int64
    /// `property.<key>` with a nonnullable Boolean `present.<key>` column.
    /// Node and original-edge order span batches. Caller-owned input Arrow
    /// buffers require caller admission; copied IDs and topology are charged here.
    pub fn from_arrow_batches(
        identity: SnapshotIdentity,
        node_batches: &[RecordBatch],
        edge_batches: &[RecordBatch],
        options: ProjectionOptions<'_>,
        context: &ExecutionContext,
    ) -> Result<Self> {
        validate_weight_selection(options.weight)?;
        let n = row_count(node_batches, context)?;
        let m = row_count(edge_batches, context)?;
        let map_reservation = context.reserve(
            n.saturating_add(4)
                .saturating_mul(2 * (size_of::<&str>() + size_of::<Option<usize>>() + 1)),
        )?;
        let mut mapping = HashMap::new();
        mapping.try_reserve(n)?;
        let mut nodes = Buffer::capacity(n, context)?;
        // Admit all copied string bytes before constructing IDs. This also polls
        // and validates the structural string columns before allocating output.
        let id_reservation =
            context.reserve(identity_bytes(node_batches, edge_batches, context)?)?;
        for batch in node_batches {
            let ids = strings(batch, "node_id")?;
            let labels = strings(batch, "label")?;
            for row in 0..batch.num_rows() {
                context.charge_work(1)?;
                let id = required(ids, row, "node_id")?;
                let selected = selects(
                    options.node_labels,
                    required(labels, row, "label")?,
                    context,
                )?;
                let index = selected.then_some(nodes.values.len());
                if mapping.insert(id, index).is_some() {
                    return Err(AlgorithmError::InvalidArguments(format!(
                        "duplicate node ID: {id}"
                    )));
                }
                if selected {
                    nodes.values.push(id.into());
                }
            }
        }
        let mut edges = Buffer::capacity(m, context)?;
        let signed = options
            .weight
            .property()
            .is_some_and(|(_, _, signed)| signed);
        let mut weights = match options.weight.property() {
            None => None,
            Some(_) => Some(Buffer::capacity(m, context)?),
        };
        let mut ordinal = 0;
        for batch in edge_batches {
            let sources = strings(batch, "source")?;
            let targets = strings(batch, "target")?;
            let labels = strings(batch, "label")?;
            let ids = strings(batch, "edge_id")?;
            let weight_column = WeightColumn::new(batch, options.weight)?;
            for row in 0..batch.num_rows() {
                context.charge_work(1)?;
                let original = ordinal;
                ordinal += 1;
                let source = mapping
                    .get(required(sources, row, "source")?)
                    .ok_or_else(|| {
                        AlgorithmError::InvalidArguments(format!(
                            "edge {original} has missing source"
                        ))
                    })?;
                let target = mapping
                    .get(required(targets, row, "target")?)
                    .ok_or_else(|| {
                        AlgorithmError::InvalidArguments(format!(
                            "edge {original} has missing target"
                        ))
                    })?;
                let label = required(labels, row, "label")?;
                let (Some(source), Some(target)) = (*source, *target) else {
                    continue;
                };
                if !selects(options.relationship_labels, label, context)? {
                    continue;
                }
                if let Some((key, missing, signed)) = options.weight.property() {
                    let value = weight_column
                        .value(row)?
                        .map_or_else(|| missing_weight(missing, key, original), Ok)?;
                    validate_weight(value, signed)?;
                    if let Some(weights) = &mut weights {
                        weights.values.push(value);
                    }
                }
                edges.values.push(ProjectionEdge {
                    source,
                    target,
                    ordinal: original,
                    id: (!ids.is_null(row)).then(|| ids.value(row).into()),
                });
            }
        }
        drop(mapping);
        drop(map_reservation);
        let projection = Self::from_buffers(
            identity,
            nodes,
            edges,
            weights,
            signed,
            options.orientation,
            context,
        )?
        .with_origin(crate::ProjectionRepresentation::ArrowBatches, options)?;
        drop(id_reservation);
        Ok(projection)
    }
}

fn row_count(batches: &[RecordBatch], context: &ExecutionContext) -> Result<usize> {
    batches.iter().try_fold(0usize, |total, batch| {
        context.charge_work(1)?;
        total
            .checked_add(batch.num_rows())
            .ok_or_else(|| AlgorithmError::Numerical("Arrow row count overflow".into()))
    })
}

fn strings<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a StringArray> {
    column(batch, name)?
        .and_then(|column| column.as_any().downcast_ref())
        .ok_or_else(|| {
            AlgorithmError::Unsupported(format!("Arrow column {name} must exist with Utf8 type"))
        })
}

fn required<'a>(column: &'a StringArray, row: usize, name: &str) -> Result<&'a str> {
    if column.is_null(row) {
        return Err(AlgorithmError::InvalidArguments(format!(
            "Arrow column {name} must not contain null"
        )));
    }
    Ok(column.value(row))
}

fn identity_bytes(
    nodes: &[RecordBatch],
    edges: &[RecordBatch],
    context: &ExecutionContext,
) -> Result<usize> {
    let mut bytes = 0usize;
    for (batches, name) in [(nodes, "node_id"), (edges, "edge_id")] {
        for batch in batches {
            let values = strings(batch, name)?;
            for row in 0..batch.num_rows() {
                context.charge_work(1)?;
                if !values.is_null(row) {
                    bytes = bytes
                        .saturating_add(values.value(row).len())
                        .saturating_add(2 * size_of::<usize>());
                }
            }
        }
    }
    Ok(bytes)
}

enum WeightValues<'a> {
    Integer(&'a Int64Array),
    Float(&'a Float64Array),
}
enum WeightColumn<'a> {
    Absent,
    Present {
        presence: &'a BooleanArray,
        values: WeightValues<'a>,
    },
}

impl<'a> WeightColumn<'a> {
    fn new(batch: &'a RecordBatch, selection: WeightSelection<'_>) -> Result<Self> {
        let Some((key, _, _)) = selection.property() else {
            return Ok(Self::Absent);
        };
        let property = format!("property.{key}");
        let present = format!("present.{key}");
        let column = column(batch, &property)?;
        let presence = self::column(batch, &present)?;
        let (Some(column), Some(presence)) = (column, presence) else {
            if column.is_none() && presence.is_none() {
                return Ok(Self::Absent);
            }
            return Err(AlgorithmError::InvalidArguments(format!(
                "Arrow weight requires both {property} and {present}"
            )));
        };
        let presence = presence
            .as_any()
            .downcast_ref::<BooleanArray>()
            .ok_or_else(|| {
                AlgorithmError::Unsupported(format!("Arrow column {present} must be Boolean"))
            })?;
        if presence.null_count() != 0 {
            return Err(AlgorithmError::InvalidArguments(format!(
                "Arrow column {present} must not contain null"
            )));
        }
        let values = if let Some(values) = column.as_any().downcast_ref::<Float64Array>() {
            WeightValues::Float(values)
        } else if let Some(values) = column.as_any().downcast_ref::<Int64Array>() {
            WeightValues::Integer(values)
        } else {
            return Err(AlgorithmError::Unsupported(format!(
                "Arrow weight {property} must be Float64 or Int64"
            )));
        };
        Ok(Self::Present { presence, values })
    }

    fn value(&self, row: usize) -> Result<Option<f64>> {
        let Self::Present { presence, values } = self else {
            return Ok(None);
        };
        if !presence.value(row) {
            return Ok(None);
        }
        match values {
            WeightValues::Integer(values) => {
                if values.is_null(row) {
                    Ok(None)
                } else {
                    integer_weight(values.value(row)).map(Some)
                }
            }
            WeightValues::Float(values) => Ok((!values.is_null(row)).then(|| values.value(row))),
        }
    }
}

// Arrow schemas permit duplicate names. Never silently select one ambiguous
// structural or requested property column; unrelated properties remain unused.
fn column<'a>(batch: &'a RecordBatch, name: &str) -> Result<Option<&'a arrow_array::ArrayRef>> {
    let schema = batch.schema();
    let mut matches = schema
        .fields()
        .iter()
        .enumerate()
        .filter(|(_, field)| field.name() == name);
    let first = matches.next().map(|(index, _)| index);
    if matches.next().is_some() {
        return Err(AlgorithmError::InvalidArguments(format!(
            "ambiguous duplicate Arrow column: {name}"
        )));
    }
    Ok(first.map(|index| batch.column(index)))
}
