//! Initial typed node-scan lowering over a caller-owned immutable provider.
use datafusion::{
    common::{Column, DataFusionError, Result},
    dataframe::DataFrame,
    logical_expr::{Expr, lit},
};
use grust_cypher::CypherParameters;
use grust_cypher::ast::{Clause, Query};

/// Why the typed node-scan route was not selected.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum UnsupportedScan {
    QueryShape,
    Ordering,
    Pagination,
    Expression,
}

/// Planning result without executing or collecting input rows.
pub enum NodeScanPlan {
    Supported(DataFrame),
    Unsupported(UnsupportedScan),
}

/// Lower an analyzed single-node MATCH/WHERE/RETURN into a typed DataFrame.
/// Returns None for unsupported shapes or expression types. Semantic errors
/// remain errors. The provider must expose the validated native node-table
/// schema and one immutable graph snapshot. This does not enforce a Cypher read
/// policy or choose an execution route; callers must admit resources separately.
/// Implicit output names follow the shared Cypher projection contract.
pub fn lower_node_scan(query: &Query, input: DataFrame) -> Result<Option<DataFrame>> {
    lower_node_scan_with_parameters(query, input, &CypherParameters::new())
}

/// Parameter-bound form of [`lower_node_scan`]. Parameter types participate in
/// eligibility; callers must replan when bindings change.
pub fn lower_node_scan_with_parameters(
    query: &Query,
    input: DataFrame,
    parameters: &CypherParameters,
) -> Result<Option<DataFrame>> {
    Ok(match plan_node_scan(query, input, parameters)? {
        NodeScanPlan::Supported(frame) => Some(frame),
        NodeScanPlan::Unsupported(_) => None,
    })
}

/// Plan with an explicit unsupported reason suitable for execution explain.
/// Semantic and DataFusion planning errors remain errors, never fallback advice.
pub fn plan_node_scan(
    query: &Query,
    input: DataFrame,
    parameters: &CypherParameters,
) -> Result<NodeScanPlan> {
    grust_cypher::semantics::analyze(query)
        .map_err(|error| DataFusionError::Plan(error.to_string()))?;
    let [part] = query.parts.as_slice() else {
        return Ok(NodeScanPlan::Unsupported(UnsupportedScan::QueryShape));
    };
    let [Clause::Match(matched), Clause::Return(returned)] = part.query.clauses.as_slice() else {
        return Ok(NodeScanPlan::Unsupported(UnsupportedScan::QueryShape));
    };
    let [pattern] = matched.patterns.as_slice() else {
        return Ok(NodeScanPlan::Unsupported(UnsupportedScan::QueryShape));
    };
    let names = super::bindings::resolve_names([pattern.start.variable.as_deref()]);
    let variable = names[0].as_ref();
    let projection = &returned.projection;
    if part.union.is_some()
        || matched.optional
        || pattern.variable.is_some()
        || pattern.shortest.is_some()
        || !pattern.segments.is_empty()
        || projection.star
    {
        return Ok(NodeScanPlan::Unsupported(UnsupportedScan::QueryShape));
    }
    let projection_schema = input.schema().as_arrow().clone();
    let schema = &projection_schema;
    let predicate = match &matched.where_clause {
        Some(expression) => {
            match super::lower(expression, variable, schema, parameters) {
                Ok((expression, datafusion::arrow::datatypes::DataType::Boolean)) => {
                    Some(expression)
                }
                // The portable WHERE executor retains only Value::Bool(true).
                // Supported non-Boolean scalar expressions cannot retain rows.
                Ok(_) => Some(lit(false)),
                Err(_) => return Ok(NodeScanPlan::Unsupported(UnsupportedScan::Expression)),
            }
        }
        None => None,
    };
    let Ok(inline) = super::inline::predicates(
        pattern.start.properties.as_ref(),
        variable,
        &super::bindings::SingleBinding { variable, schema },
        parameters,
    ) else {
        return Ok(NodeScanPlan::Unsupported(UnsupportedScan::Expression));
    };
    let mut frame = input;
    for label in &pattern.start.labels {
        frame = frame.filter(Expr::Column(Column::from_name("label")).eq(lit(label.clone())))?;
    }
    for predicate in inline {
        frame = frame.filter(predicate)?;
    }
    if let Some(predicate) = predicate {
        frame = frame.filter(predicate)?;
    }
    super::projection::project(
        projection,
        frame,
        &super::bindings::SingleBinding {
            variable,
            schema: &projection_schema,
        },
        parameters,
    )
}
