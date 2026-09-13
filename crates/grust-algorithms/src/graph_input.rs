//! Property-graph selection and scalar weight extraction outside kernel loops.

use std::collections::HashMap;

use grust_core::{Graph, NodeId, Value};

use crate::{
    AlgorithmError, ExecutionContext, GraphProjection, Orientation, ProjectionEdge, Result,
    SnapshotIdentity, buffer::Buffer,
};

/// Handling of an absent or explicitly null selected weight property.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum MissingWeight {
    /// Reject the projection, naming the edge and property.
    Reject,
    /// Substitute this finite nonnegative scalar.
    Default(f64),
}

/// Edge weight extraction. Unit projections allocate no weight array.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum WeightSelection<'a> {
    /// Every edge costs one.
    Unit,
    /// Read one named numeric property per selected edge.
    Property {
        key: &'a str,
        missing: MissingWeight,
    },
}

/// Explicit projection selection. `None` selects every label; an empty slice
/// selects none. Edges crossing outside the selected vertex set are excluded.
#[derive(Clone, Copy, Debug)]
pub struct ProjectionOptions<'a> {
    /// Selected node labels, preserving snapshot node order and isolates.
    pub node_labels: Option<&'a [String]>,
    /// Selected relationship labels, preserving original snapshot ordinals.
    pub relationship_labels: Option<&'a [String]>,
    /// Traversal orientation.
    pub orientation: Orientation,
    /// Optional numeric edge property.
    pub weight: WeightSelection<'a>,
}

impl Default for ProjectionOptions<'_> {
    fn default() -> Self {
        Self {
            node_labels: None,
            relationship_labels: None,
            orientation: Orientation::Outgoing,
            weight: WeightSelection::Unit,
        }
    }
}

impl GraphProjection {
    /// Copy selected topology from an immutable borrowed Graph. The caller owns
    /// admission of the input Graph itself; this method accounts its temporary
    /// lookup, selected inputs, CSR, ID mapping and subsequent kernel storage.
    /// All snapshot IDs and endpoints are validated, even outside the selection.
    pub fn from_graph(
        graph: &Graph,
        identity: SnapshotIdentity,
        options: ProjectionOptions<'_>,
        context: &ExecutionContext,
    ) -> Result<Self> {
        validate_weight_selection(options.weight)?;
        let mapping_bytes = graph
            .nodes
            .len()
            .saturating_add(4)
            .saturating_mul(2 * (size_of::<&NodeId>() + size_of::<Option<usize>>() + 1));
        let mapping_reservation = context.reserve(mapping_bytes)?;
        let mut mapping = HashMap::new();
        mapping.try_reserve(graph.nodes.len())?;
        let mut nodes = Buffer::capacity(graph.nodes.len(), context)?;
        for node in &graph.nodes {
            context.charge_work(1)?;
            let selected = selects(options.node_labels, node.label.as_str(), context)?;
            let row = selected.then_some(nodes.values.len());
            if mapping.insert(&node.id, row).is_some() {
                return Err(AlgorithmError::InvalidArguments(format!(
                    "duplicate node ID: {}",
                    node.id
                )));
            }
            if selected {
                nodes.values.push(node.id.clone());
            }
        }
        let mut edges = Buffer::capacity(graph.edges.len(), context)?;
        let mut weights = match options.weight {
            WeightSelection::Unit => None,
            WeightSelection::Property { .. } => Some(Buffer::capacity(graph.edges.len(), context)?),
        };
        for (ordinal, edge) in graph.edges.iter().enumerate() {
            context.charge_work(1)?;
            let source = mapping.get(&edge.from).ok_or_else(|| {
                AlgorithmError::InvalidArguments(format!(
                    "edge {ordinal} has missing source: {}",
                    edge.from
                ))
            })?;
            let target = mapping.get(&edge.to).ok_or_else(|| {
                AlgorithmError::InvalidArguments(format!(
                    "edge {ordinal} has missing target: {}",
                    edge.to
                ))
            })?;
            let (Some(source), Some(target)) = (*source, *target) else {
                continue;
            };
            if !selects(options.relationship_labels, edge.label.as_str(), context)? {
                continue;
            }
            if let WeightSelection::Property { key, missing } = options.weight {
                let value = match edge.props.get(key) {
                    None | Some(Value::Null) => missing_weight(missing, key, ordinal)?,
                    Some(Value::Float(value)) => *value,
                    Some(Value::Int(value)) => integer_weight(*value)?,
                    Some(_) => {
                        return Err(AlgorithmError::InvalidArguments(format!(
                            "edge {ordinal} weight property {key} is not numeric"
                        )));
                    }
                };
                validate_weight(value)?;
                if let Some(weights) = &mut weights {
                    weights.values.push(value);
                }
            }
            edges.values.push(ProjectionEdge {
                source,
                target,
                ordinal,
                id: edge.id.clone(),
            });
        }
        drop(mapping);
        drop(mapping_reservation);
        // Transfer the already admitted inputs; from_topology takes over their
        // retained admission synchronously before allocating its lookup and CSR.
        Self::from_topology(
            identity,
            nodes.into_values(),
            edges.into_values(),
            weights.map(Buffer::into_values),
            options.orientation,
            context,
        )?
        .with_origin(crate::ProjectionRepresentation::PropertyGraph, options)
    }
}

pub(crate) fn selects(
    labels: Option<&[String]>,
    label: &str,
    context: &ExecutionContext,
) -> Result<bool> {
    let Some(labels) = labels else {
        return Ok(true);
    };
    for selected in labels {
        context.charge_work(1)?;
        if selected == label {
            return Ok(true);
        }
    }
    Ok(false)
}

pub(crate) fn validate_weight_selection(selection: WeightSelection<'_>) -> Result<()> {
    if let WeightSelection::Property { key, missing } = selection {
        if key.is_empty() {
            return Err(AlgorithmError::InvalidArguments(
                "weight property must be nonempty".into(),
            ));
        }
        if let MissingWeight::Default(value) = missing {
            validate_weight(value)?;
        }
    }
    Ok(())
}

pub(crate) fn validate_weight(value: f64) -> Result<()> {
    if !value.is_finite() || value < 0.0 {
        return Err(AlgorithmError::InvalidArguments(
            "weights must be finite and nonnegative".into(),
        ));
    }
    Ok(())
}

pub(crate) fn missing_weight(missing: MissingWeight, key: &str, ordinal: usize) -> Result<f64> {
    match missing {
        MissingWeight::Default(value) => Ok(value),
        MissingWeight::Reject => Err(AlgorithmError::InvalidArguments(format!(
            "edge {ordinal} has absent or null weight property {key}"
        ))),
    }
}

pub(crate) fn integer_weight(value: i64) -> Result<f64> {
    // The public contract admits only the consecutive exact integer domain;
    // silently rounding large property integers would change path ordering.
    if !(0..=9_007_199_254_740_992).contains(&value) {
        return Err(AlgorithmError::InvalidArguments(
            "integer weights must be in the exact f64 domain 0..=2^53".into(),
        ));
    }
    Ok(value as f64)
}
