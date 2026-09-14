//! Parsed single-hop relationship admission and typed plan construction.
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

/// Plan a parsed single-hop MATCH/WHERE/RETURN on a captured snapshot.
/// Uses the same RETURN compiler as node scans. Unsupported shapes are explicit;
/// semantic and planning errors remain errors. No resource-policy admission or
/// automatic routing is supplied. Binding names must currently be
/// present, with relationship names distinct from node names; variable-length and optional patterns remain
/// unsupported on this relationship route.
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
    let [segment] = pattern.segments.as_slice() else {
        return unsupported();
    };
    let relationship = &segment.relationship;
    let (Some(start), Some(edge), Some(end)) = (
        pattern.start.variable.as_deref(),
        relationship.variable.as_deref(),
        segment.node.variable.as_deref(),
    ) else {
        return unsupported();
    };
    if part.union.is_some()
        || matched.optional
        || pattern.variable.is_some()
        || pattern.shortest.is_some()
        || relationship.length.is_some()
        || start == edge
        || edge == end
    {
        return unsupported();
    }
    let plan = match relationship.direction {
        Direction::Outgoing => snapshot.directed_relationships(context, start, edge, end)?,
        Direction::Incoming => snapshot.directed_relationships(context, end, edge, start)?,
        Direction::Undirected => snapshot.undirected_relationships(context, start, edge, end)?,
    };
    let (mut frame, bindings) = plan.into_parts();
    for (variable, labels) in [(start, &pattern.start.labels), (end, &segment.node.labels)] {
        for label in labels {
            let column = bindings
                .field(variable, "label")
                .map_err(|_| DataFusionError::Plan("missing validated node label".into()))?
                .0;
            frame = frame.filter(column.eq(lit(label.clone())))?;
        }
    }
    if !relationship.types.is_empty() {
        let label = bindings
            .field(edge, "label")
            .map_err(|_| DataFusionError::Plan("missing validated relationship label".into()))?
            .0;
        frame = frame
            .filter(label.in_list(relationship.types.iter().cloned().map(lit).collect(), false))?;
    }
    for (variable, properties) in [
        (start, pattern.start.properties.as_ref()),
        (edge, relationship.properties.as_ref()),
        (end, segment.node.properties.as_ref()),
    ] {
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
