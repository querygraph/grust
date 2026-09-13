//! Reuse immutable projection preparation without caching algorithm results.

use super::*;
use algorithms::{GraphProjection, MissingWeight, Orientation, ProjectionOptions, WeightSelection};

pub(super) fn prepare(
    snapshot: LocalSnapshot<'_>,
    options: ProjectionOptions<'_>,
    invocation: &Invocation<'_>,
) -> Result<GraphProjection> {
    let context = invocation.execution;
    let initialize = || {
        let _identity = context.reserve(snapshot.identity().owned_bytes())?;
        GraphProjection::from_graph(
            snapshot.graph(),
            snapshot.identity().clone(),
            options,
            context,
        )
    };
    let Some(cache) = invocation.cache else {
        return initialize();
    };
    let identity = snapshot.identity();
    let orientation = match options.orientation {
        Orientation::Outgoing => "outgoing",
        Orientation::Incoming => "incoming",
        Orientation::Undirected => "undirected",
    };
    let (weight_property, default_weight) = match options.weight {
        WeightSelection::Unit => (None, None),
        WeightSelection::Property { key, missing } => (
            Some(key),
            match missing {
                MissingWeight::Reject => None,
                MissingWeight::Default(value) => Some(value),
            },
        ),
    };
    // JSON escaping expands a byte by at most six. Serialize borrowed fields
    // directly into a fallibly reserved buffer; do not construct a JSON tree.
    let mut key_bytes = 256usize
        .saturating_add(identity.owned_bytes())
        .saturating_add(weight_property.map_or(0, str::len));
    for labels in [options.node_labels, options.relationship_labels]
        .into_iter()
        .flatten()
    {
        for label in labels {
            context.charge_work(1)?;
            key_bytes = key_bytes.saturating_add(label.len()).saturating_add(3);
        }
    }
    let key_bytes = key_bytes.saturating_mul(6);
    let _key_admission = context.reserve(key_bytes)?;
    let mut encoded = Vec::new();
    encoded.try_reserve_exact(key_bytes)?;
    serde_json::to_writer(
        &mut encoded,
        &(
            "grust.projection.v1",
            identity.graph(),
            identity.revision(),
            identity.principal(),
            options.node_labels,
            options.relationship_labels,
            orientation,
            weight_property,
            default_weight,
        ),
    )
    .map_err(|error| ProcedureError::Provider(Box::new(error)))?;
    let key =
        String::from_utf8(encoded).map_err(|error| ProcedureError::Provider(Box::new(error)))?;
    Ok(cache.get_or_try_init(&key, initialize)?.as_ref().clone())
}
