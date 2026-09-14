//! Parsed fixed-length relationship admission and typed plan construction.
use super::{GraphSnapshot, NodeScanPlan, UnsupportedScan};
use datafusion::{
    arrow::datatypes::DataType,
    common::{DataFusionError, Result},
    execution::context::SessionContext,
    logical_expr::lit,
};
use grust_cypher::{
    CypherParameters,
    ast::{Clause, Direction, Query},
};

/// Plan a parsed fixed-length MATCH/WHERE/RETURN on a captured snapshot.
/// Uses the same RETURN compiler as node scans. Unsupported shapes are explicit;
/// semantic and planning errors remain errors. No resource-policy admission or
/// automatic routing is supplied. Anonymous elements receive private bindings;
/// relationship names must differ from node names. Variable-length and optional
/// patterns remain unsupported. Physical edge reuse is excluded across the path.
pub fn plan_relationship_scan(
    query: &Query,
    snapshot: &GraphSnapshot,
    context: &SessionContext,
    parameters: &CypherParameters,
) -> Result<NodeScanPlan> {
    grust_cypher::semantics::analyze(query)
        .map_err(|error| DataFusionError::Plan(error.to_string()))?;
    let unsupported = || Ok(NodeScanPlan::Unsupported(UnsupportedScan::QueryShape));
    let [part] = query.parts.as_slice() else {
        return unsupported();
    };
    let [Clause::Match(matched), Clause::Return(returned)] = part.query.clauses.as_slice() else {
        return unsupported();
    };
    let [pattern] = matched.patterns.as_slice() else {
        return unsupported();
    };
    if part.union.is_some()
        || matched.optional
        || pattern.variable.is_some()
        || pattern.shortest.is_some()
        || pattern.segments.is_empty()
        || pattern
            .segments
            .iter()
            .any(|segment| segment.relationship.length.is_some())
    {
        return unsupported();
    }
    let mut raw_names = vec![pattern.start.variable.as_deref()];
    for segment in &pattern.segments {
        raw_names.push(segment.relationship.variable.as_deref());
        raw_names.push(segment.node.variable.as_deref());
    }
    let names = super::bindings::resolve_path_names(&raw_names);
    let mut plan: Option<super::RelationshipPlan> = None;
    for (index, segment) in pattern.segments.iter().enumerate() {
        let start = names[index * 2].as_ref();
        let edge = names[index * 2 + 1].as_ref();
        let end = names[index * 2 + 2].as_ref();
        if start == edge || edge == end {
            return unsupported();
        }
        let next = match segment.relationship.direction {
            Direction::Outgoing => snapshot.directed_relationships(context, start, edge, end)?,
            Direction::Incoming => snapshot.directed_relationships(context, end, edge, start)?,
            Direction::Undirected => {
                snapshot.undirected_relationships(context, start, edge, end)?
            }
        };
        plan = Some(match plan {
            Some(previous) => previous.join_trail(next)?,
            None => next,
        });
    }
    let (mut frame, bindings) = plan
        .ok_or_else(|| DataFusionError::Plan("empty relationship path".into()))?
        .into_parts();
    let mut constraints = vec![(
        names[0].as_ref(),
        &pattern.start.labels,
        pattern.start.properties.as_ref(),
        false,
    )];
    for (index, segment) in pattern.segments.iter().enumerate() {
        constraints.push((
            names[index * 2 + 1].as_ref(),
            &segment.relationship.types,
            segment.relationship.properties.as_ref(),
            true,
        ));
        constraints.push((
            names[index * 2 + 2].as_ref(),
            &segment.node.labels,
            segment.node.properties.as_ref(),
            false,
        ));
    }
    for (variable, labels, properties, alternatives) in constraints {
        if !labels.is_empty() {
            let label = bindings
                .field(variable, "label")
                .map_err(|_| DataFusionError::Plan("missing validated label".into()))?
                .0;
            if alternatives {
                frame = frame
                    .filter(label.in_list(labels.iter().cloned().map(lit).collect(), false))?;
            } else {
                for value in labels {
                    frame = frame.filter(label.clone().eq(lit(value.clone())))?;
                }
            }
        }
        let Ok(predicates) = super::inline::predicates(properties, variable, &bindings, parameters)
        else {
            return Ok(NodeScanPlan::Unsupported(UnsupportedScan::Expression));
        };
        for predicate in predicates {
            frame = frame.filter(predicate)?;
        }
    }
    if let Some(predicate) = &matched.where_clause {
        let predicate = match super::lower_bound(predicate, &bindings, parameters) {
            Ok((expression, DataType::Boolean)) => expression,
            Ok(_) => lit(false),
            Err(_) => return Ok(NodeScanPlan::Unsupported(UnsupportedScan::Expression)),
        };
        frame = frame.filter(predicate)?;
    }
    super::projection::project(&returned.projection, frame, &bindings, parameters)
}
