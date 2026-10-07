//! Bounded schema feasibility example: a single named-label hop.
use grust_lpg::{Direction, EdgeGroup, GroupId, Lpg, Schema, SchemaError, VertexGroup};
use grust_resolved_plan::{Orientation, SchemaPath};
use grust_unresolved_plan::PatternDirection;

pub fn one_hop(
    schema: &Schema,
    source_label: &str,
    edge_label: &str,
    target_label: &str,
    direction: PatternDirection,
) -> Result<Vec<SchemaPath>, SchemaError> {
    let has_vertex = |group: GroupId, label: &str| -> Result<bool, SchemaError> {
        let vertex = schema
            .vertex_groups()
            .iter()
            .find(|v| v.id() == group)
            .ok_or(SchemaError::UnknownVertex(group))?;
        Ok(schema.labels(vertex.element_type())?.contains(label))
    };
    let mut paths = Vec::new();
    for edge in schema.edge_groups() {
        if !schema.labels(edge.element_type())?.contains(edge_label) {
            continue;
        }
        let (source, target) = edge.endpoints();
        let stored =
            edge.direction() == Direction::Undirected || direction != PatternDirection::Incoming;
        let reversed =
            edge.direction() == Direction::Undirected || direction != PatternDirection::Outgoing;
        if stored && has_vertex(source, source_label)? && has_vertex(target, target_label)? {
            paths.push(SchemaPath {
                vertices: vec![source, target],
                edges: vec![(edge.id(), Orientation::Stored)],
            });
        }
        // A schema self-pair does not imply an object self-loop: preserve both orientations.
        // Runtime undirected expansion must deduplicate an actual self-loop by identity.
        if reversed && has_vertex(target, source_label)? && has_vertex(source, target_label)? {
            paths.push(SchemaPath {
                vertices: vec![target, source],
                edges: vec![(edge.id(), Orientation::Reversed)],
            });
        }
    }
    Ok(paths)
}
