//! The writable-Cypher entry points over the AST planner: split the script
//! into `;`-separated statements, parse each with the typed parser, and plan
//! it against the bindings of the statements before it.

use super::{parse_write_statement, split_final_return_ast, top_level_return};
use crate::*;

impl CypherMutationPlanner {
    pub(crate) fn from_options(
        options: CypherMutationOptions,
        bind_delete_return_rows: bool,
    ) -> Self {
        CypherMutationPlanner {
            node_id_policy: options.node_id_policy,
            relationship_id_policy: options.relationship_id_policy,
            null_assignment: options.null_assignment,
            parameters: options.parameters,
            bind_delete_return_rows,
            ..CypherMutationPlanner::default()
        }
    }

    /// Parse and plan one statement, appending its operations to `plan`.
    fn plan_ast_text(&mut self, statement: &str, plan: &mut GraphMutationPlan) -> Result<()> {
        let query = parse_write_statement(statement)?;
        plan.operations
            .extend(self.plan_ast_statement(statement, &query)?.operations);
        Ok(())
    }
}

pub(crate) fn ast_mutation_plan_with_options(
    cypher: &str,
    options: CypherMutationOptions,
) -> Result<(GraphMutationPlan, Vec<CypherGeneratedNodeId>)> {
    let cypher = strip_cypher_comments(cypher)?;
    let statements = split_cypher_statements(&cypher)?;
    if statements.is_empty() {
        return Err(cypher_syntax("writable Cypher statement is empty"));
    }
    let mut planner = CypherMutationPlanner::from_options(options, false);
    let mut plan = GraphMutationPlan::default();
    for statement in statements {
        planner.plan_ast_text(statement, &mut plan)?;
    }
    Ok((plan, planner.generated_node_ids))
}

pub(crate) fn ast_mutation_plan_with_return_options(
    cypher: &str,
    options: CypherMutationOptions,
) -> Result<CypherPlannedMutationWithReturn> {
    let cypher = strip_cypher_comments(cypher)?;
    let mut statements = split_cypher_statements(&cypher)?;
    if statements.is_empty() {
        return Err(cypher_syntax("writable Cypher statement is empty"));
    }
    let final_statement = statements
        .pop()
        .expect("checked non-empty statement collection");
    if statements
        .iter()
        .any(|statement| top_level_return(statement).is_some())
    {
        return Err(cypher_syntax(
            "writable Cypher only supports RETURN on the final statement",
        ));
    }
    let (final_mutation, return_clause) = split_final_return_ast(final_statement)?;
    if final_mutation.is_empty() {
        return Err(cypher_syntax(
            "writable Cypher RETURN requires a preceding mutation statement",
        ));
    }

    let mut planner = CypherMutationPlanner::from_options(options, true);
    let mut plan = GraphMutationPlan::default();
    for statement in statements {
        planner.plan_ast_text(statement, &mut plan)?;
    }
    planner.plan_ast_text(final_mutation, &mut plan)?;
    let return_clause = parse_cypher_return_clause(
        return_clause,
        &CypherReturnScope {
            node_bindings: &planner.node_bindings,
            edge_bindings: &planner.edge_bindings,
            row_node_bindings: &planner.row_node_bindings,
            row_edge_match_bindings: &planner.row_edge_match_bindings,
            row_edge_bindings: &planner.row_edge_bindings,
            row_path_bindings: &planner.row_path_bindings,
        },
        &planner.parameters,
    )?;
    Ok(CypherPlannedMutationWithReturn {
        plan,
        generated_node_ids: planner.generated_node_ids,
        node_bindings: planner.node_bindings,
        edge_bindings: planner.edge_bindings,
        row_node_bindings: planner.row_node_bindings,
        row_edge_match_bindings: planner.row_edge_match_bindings,
        row_edge_bindings: planner.row_edge_bindings,
        row_path_bindings: planner.row_path_bindings,
        return_clause,
    })
}
