//! Materialize write bindings once, then use the read expression evaluator.
use super::*;

pub(crate) async fn evaluate_write_expression<S: GraphStore + Sync>(
    evaluation: &mut CypherReturnEvaluation<'_, S>,
    expression: &CypherReturnExpression,
    row_index: usize,
) -> Result<Value> {
    let mut row = Row::new();
    for name in &expression.variables {
        let bound = if let Some(values) = evaluation.row_node_values.get(name) {
            let node = values
                .get(row_index)
                .ok_or_else(|| gql_cardinality("write RETURN node row missing"))?;
            Bound::Node(node.clone().into())
        } else if let Some(values) = evaluation.row_edge_values.get(name) {
            let edge = values
                .get(row_index)
                .ok_or_else(|| gql_cardinality("write RETURN edge row missing"))?;
            Bound::Edge(Arc::new(edge.clone()), None)
        } else if let Some(id) = evaluation.node_bindings.get(name) {
            let node = resolve_bound_node(evaluation.store, evaluation.nodes, name, id).await?;
            Bound::Node(node.clone().into())
        } else if let Some(identity) = evaluation.edge_bindings.get(name) {
            let edge =
                resolve_bound_edge_cached(evaluation.store, evaluation.edges, identity, name)
                    .await?;
            Bound::Edge(Arc::new(edge.clone()), None)
        } else if evaluation.row_path_bindings.contains_key(name) {
            Bound::Value(
                materialize_return_path_value_at(
                    evaluation.store,
                    evaluation.node_bindings,
                    evaluation.edge_bindings,
                    evaluation.row_node_values,
                    evaluation.row_edge_values,
                    evaluation.row_path_bindings,
                    evaluation.nodes,
                    evaluation.edges,
                    name,
                    row_index,
                )
                .await?,
            )
        } else {
            return Err(gql_name(format!("variable `{name}` is not bound")));
        };
        row.insert(name.clone(), bound);
    }
    eval_scoped(
        &expression.expr,
        &ExpressionScope::WriteRow(&row),
        &expression.parameters,
    )
}
