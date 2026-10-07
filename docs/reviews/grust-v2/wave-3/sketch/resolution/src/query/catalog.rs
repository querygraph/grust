use super::*;
use grust_lpg::{Direction, EdgeGroup, GroupId, Lpg, Schema, TypeId, VertexGroup};
use grust_unresolved_plan::{LabelExpr, PathPattern, PatternDirection};
use std::collections::{BTreeMap, BTreeSet};
type Path = (Vec<GroupId>, Vec<(GroupId, bool)>);
pub(super) fn group_properties(
    schema: &Schema,
    group: GroupId,
    edge: bool,
) -> Result<BTreeMap<String, (LogicalType, bool)>, ResolveError> {
    let ty = if edge {
        schema
            .edge_groups()
            .iter()
            .find(|e| e.id() == group)
            .map(EdgeGroup::element_type)
    } else {
        schema
            .vertex_groups()
            .iter()
            .find(|v| v.id() == group)
            .map(VertexGroup::element_type)
    }
    .ok_or(ResolveError::InfeasiblePattern)?;
    let mut pending = vec![ty];
    let mut seen = BTreeSet::new();
    let mut properties = BTreeMap::new();
    while let Some(ty) = pending.pop() {
        if !seen.insert(ty) {
            continue;
        }
        let ty = schema
            .element_type(ty)
            .ok_or(ResolveError::InfeasiblePattern)?;
        pending.extend(ty.supertypes.iter().copied());
        for p in &ty.properties {
            let declaration = (p.ty.clone(), p.nullable);
            if properties
                .get(&p.name)
                .is_some_and(|existing| existing != &declaration)
            {
                return Err(ResolveError::AmbiguousProperty(p.name.clone()));
            }
            properties.insert(p.name.clone(), declaration);
        }
    }
    Ok(properties)
}
pub(super) fn label(schema: &Schema, ty: TypeId, expr: &LabelExpr) -> Result<bool, ResolveError> {
    let labels = schema
        .labels(ty)
        .map_err(|e| unsupported("schema", &e.to_string()))?;
    match expr {
        LabelExpr::Any => Ok(true),
        LabelExpr::Label(name) => {
            if !schema.types().iter().any(|t| t.labels.contains(name)) {
                return Err(ResolveError::UnknownLabel(name.clone()));
            }
            Ok(labels.contains(name.as_str()))
        }
        LabelExpr::And(parts) => {
            let values = parts
                .iter()
                .map(|p| label(schema, ty, p))
                .collect::<Result<Vec<_>, _>>()?;
            Ok(values.iter().all(|x| *x))
        }
        LabelExpr::Or(parts) => {
            let values = parts
                .iter()
                .map(|p| label(schema, ty, p))
                .collect::<Result<Vec<_>, _>>()?;
            Ok(values.iter().any(|x| *x))
        }
        LabelExpr::Not(part) => Ok(!label(schema, ty, part)?),
    }
}
pub(super) fn enumerate(schema: &Schema, pattern: &PathPattern) -> Result<Vec<Path>, ResolveError> {
    let mut paths = Vec::new();
    for vertex in schema.vertex_groups() {
        if label(schema, vertex.element_type(), &pattern.vertices[0].labels)? {
            paths.push((vec![vertex.id()], vec![]));
        }
    }
    // Validate every label even if the earlier path is infeasible.
    for v in &pattern.vertices {
        for ty in schema.types() {
            label(schema, ty.id, &v.labels)?;
        }
    }
    for e in &pattern.edges {
        for ty in schema.types() {
            label(schema, ty.id, &e.labels)?;
        }
    }
    for (i, edge_pattern) in pattern.edges.iter().enumerate() {
        let mut next = Vec::new();
        for (vertices, edges) in &paths {
            for edge in schema.edge_groups() {
                if !label(schema, edge.element_type(), &edge_pattern.labels)? {
                    continue;
                }
                let (s, t) = edge.endpoints();
                for reversed in [false, true] {
                    if edge.direction() == Direction::Directed
                        && ((reversed && edge_pattern.direction == PatternDirection::Outgoing)
                            || (!reversed && edge_pattern.direction == PatternDirection::Incoming))
                    {
                        continue;
                    }
                    let (from, to) = if reversed { (t, s) } else { (s, t) };
                    if vertices.last() != Some(&from) {
                        continue;
                    }
                    let vertex = schema
                        .vertex_groups()
                        .iter()
                        .find(|v| v.id() == to)
                        .ok_or(ResolveError::InfeasiblePattern)?;
                    if !label(
                        schema,
                        vertex.element_type(),
                        &pattern.vertices[i + 1].labels,
                    )? {
                        continue;
                    }
                    let mut v = vertices.clone();
                    v.push(to);
                    let mut e = edges.clone();
                    e.push((edge.id(), reversed));
                    next.push((v, e));
                    if next.len() > 4096 {
                        return Err(unsupported(
                            "schema paths",
                            "more than 4096 alternatives; provide a graph operator",
                        ));
                    }
                }
            }
        }
        paths = next;
    }
    Ok(paths)
}
