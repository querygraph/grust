//! Registry adaptation at the Cypher boundary. Providers never see AST or rows.

use grust_procedures::{
    ExecutionContext, Invocation, InvocationCache, LocalSnapshot, ProcedureError, ProcedureMode,
    ProcedureRegistry, RegistryBuilder, ResolvedProcedure, SnapshotIdentity, register_builtins,
};

use super::*;

/// Per-query immutable provider generation and shared execution envelope.
pub(super) struct ProcedureExecution {
    registry: ProcedureRegistry,
    execution: ExecutionContext,
    identity: SnapshotIdentity,
    cache: InvocationCache,
}

impl ProcedureExecution {
    pub(super) fn builtins() -> Result<Self> {
        let mut builder = RegistryBuilder::default();
        register_builtins(&mut builder).map_err(translate_error)?;
        Self::new(builder.build())
    }

    pub(super) fn new(registry: ProcedureRegistry) -> Result<Self> {
        let execution = read_budget::procedure_execution_context()?;
        Ok(Self {
            cache: InvocationCache::new(execution.clone()),
            identity: SnapshotIdentity::new(
                "default".into(),
                uuid::Uuid::new_v4().to_string(),
                "local-caller".into(),
            )
            .map_err(translate_error)?,
            registry,
            execution,
        })
    }

    pub(super) fn with_identity(mut self, identity: SnapshotIdentity) -> Self {
        self.identity = identity;
        self
    }

    pub(super) fn with_graph_name(mut self, graph_name: &str) -> Result<Self> {
        self.identity = SnapshotIdentity::new(
            graph_name.into(),
            self.identity.revision().into(),
            self.identity.principal().into(),
        )
        .map_err(translate_error)?;
        Ok(self)
    }

    pub(super) fn prepare(&self, query: &mut Query) -> Result<()> {
        self.preflight(query, None)?;
        prepared_procedures::resolve_output_scopes(query, &self.registry)?;
        crate::semantics::analyze(query)?;
        Ok(())
    }

    pub(super) fn preflight(&self, query: &Query, params: Option<&CypherParameters>) -> Result<()> {
        for part in &query.parts {
            for clause in &part.query.clauses {
                match clause {
                    Clause::Call(call) => {
                        let procedure = self.resolve(call)?;
                        procedure
                            .validate_arity(call.args.len())
                            .map_err(translate_error)?;
                        for (column, _) in &call.yields {
                            procedure.output_index(column).map_err(translate_error)?;
                        }
                        if let Some(index) = procedure.definition().options_argument
                            && let Some(Expr::Map(options)) = call.args.get(index)
                        {
                            for (name, _) in options {
                                if !procedure
                                    .definition()
                                    .options
                                    .iter()
                                    .any(|option| option.field.name == *name)
                                {
                                    return Err(translate_error(ProcedureError::UnknownOption(
                                        name.clone(),
                                    )));
                                }
                            }
                        }
                        // Literal/parameter-only arguments are checked even when
                        // the incoming stream will be empty. Row expressions are
                        // validated dynamically once for each invocation.
                        for (index, expression) in call.args.iter().enumerate() {
                            if let Some(value) = static_value(expression, params) {
                                procedure
                                    .validate_argument(index, &value?)
                                    .map_err(translate_error)?;
                            }
                        }
                    }
                    Clause::Subquery(subquery) => self.preflight(&subquery.query, params)?,
                    Clause::Use(_)
                    | Clause::Match(_)
                    | Clause::With(_)
                    | Clause::Unwind(_)
                    | Clause::Return(_) => {}
                    Clause::Create(_)
                    | Clause::Merge(_)
                    | Clause::Delete(_)
                    | Clause::Set(_)
                    | Clause::Remove(_) => {
                        return Err(gql_execution("procedure queries must be read-only"));
                    }
                }
            }
        }
        Ok(())
    }

    pub(super) fn cache(&self) -> &InvocationCache {
        &self.cache
    }

    pub(super) fn execution(&self) -> &ExecutionContext {
        &self.execution
    }
    pub(super) fn identity(&self) -> &SnapshotIdentity {
        &self.identity
    }

    pub(super) fn resolve(&self, call: &CallClause) -> Result<ResolvedProcedure> {
        let procedure = self.registry.resolve(&call.name).map_err(translate_error)?;
        match procedure.definition().mode {
            ProcedureMode::Catalog | ProcedureMode::Table | ProcedureMode::Read => Ok(procedure),
            ProcedureMode::Write => Err(translate_error(ProcedureError::Denied(
                "write provider in a read query".into(),
            ))),
        }
    }

    pub(super) fn advance(
        &self,
        graph: &Graph,
        call: &CallClause,
        rows: Vec<Row>,
        params: &CypherParameters,
    ) -> Result<(Vec<Row>, Option<Vec<String>>)> {
        let procedure = self.resolve(call)?;
        let full_columns = procedure
            .definition()
            .outputs
            .iter()
            .map(|field| field.name.clone())
            .collect::<Vec<_>>();
        let (columns, indices) = yield_projection(&call.name, &full_columns, &call.yields)?;
        let mut output = Vec::new();
        for row in rows {
            let args = call
                .args
                .iter()
                .map(|arg| eval(arg, &row, params))
                .collect::<Result<Vec<_>>>()?;
            let mut cursor = procedure
                .open(
                    args,
                    Invocation {
                        snapshot: Some(LocalSnapshot::new(graph, &self.identity)),
                        cache: Some(&self.cache),
                        execution: &self.execution,
                    },
                )
                .map_err(|error| invocation_error(error, call))?;
            while let Some(batch) = cursor
                .next_batch()
                .map_err(|error| invocation_error(error, call))?
            {
                for values in batch.rows() {
                    if !read_budget::intermediate_accounting_active() {
                        // The ordinary entrypoint has no legacy budget scope.
                        // Admit retained CALL bindings before copying them.
                        let bytes = columns.iter().zip(&indices).fold(
                            row_copy_bytes(&row),
                            |bytes, (name, &index)| {
                                bytes
                                    .saturating_add(name.len())
                                    .saturating_add(size_of::<(String, Bound)>() * 2)
                                    .saturating_add(read_budget::value_copy_bytes(&values[index]))
                            },
                        );
                        self.execution
                            .charge_cumulative_memory(bytes)
                            .map_err(translate_error)?;
                    }
                    let mut next = clone_row(&row, "producing procedure rows")?;
                    for (column, &index) in columns.iter().zip(&indices) {
                        next.insert(
                            column.clone(),
                            Bound::Value(clone_value(
                                &values[index],
                                "binding procedure result values",
                            )?),
                        );
                    }
                    read_budget::charge_candidate_work(1, "producing procedure rows")?;
                    if let Some(predicate) = &call.where_clause
                        && !matches!(eval(predicate, &next, params)?, Value::Bool(true))
                    {
                        continue;
                    }
                    output.push(next);
                }
            }
        }
        Ok((output, Some(columns)))
    }
}

fn static_value(expr: &Expr, params: Option<&CypherParameters>) -> Option<Result<Value>> {
    if static_expression(expr, params.is_some()) {
        Some(eval(
            expr,
            &Row::new(),
            params.unwrap_or(&CypherParameters::new()),
        ))
    } else {
        None
    }
}

fn static_expression(expr: &Expr, parameters_available: bool) -> bool {
    match expr {
        Expr::Null | Expr::Boolean(_) | Expr::Integer(_) | Expr::Float(_) | Expr::String(_) => true,
        Expr::Parameter(_) => parameters_available,
        Expr::List(items) => items
            .iter()
            .all(|item| static_expression(item, parameters_available)),
        Expr::Map(entries) => entries
            .iter()
            .all(|(_, value)| static_expression(value, parameters_available)),
        Expr::Unary { operand, .. } | Expr::IsNull { operand, .. } => {
            static_expression(operand, parameters_available)
        }
        Expr::Binary { lhs, rhs, .. } => {
            static_expression(lhs, parameters_available)
                && static_expression(rhs, parameters_available)
        }
        // Functions can observe volatile state. Row bindings and other
        // expressions stay in the ordinary per-row evaluator.
        _ => false,
    }
}

/// Preserve the existing Cypher transport categories; direct registry callers
/// retain the full typed ProcedureError and provider source chain.
pub(super) fn translate_error(error: ProcedureError) -> GrustError {
    match error {
        ProcedureError::UnknownProcedure(_) | ProcedureError::Unsupported(_) => {
            unsupported_gql_feature(
                GqlFeature::ProcedureCall,
                GqlConformanceProfile::PortableGql,
                error.to_string(),
            )
        }
        ProcedureError::UnknownOutput(_) => gql_name(error.to_string()),
        ProcedureError::InvalidArguments(_) | ProcedureError::UnknownOption(_) => {
            gql_type(error.to_string())
        }
        _ => gql_execution(error.to_string()),
    }
}

/// Parse, validate and execute ordinary Cypher using an application registry.
///
/// The supplied graph is the explicit local snapshot selected by `graph_name`;
/// this function never downloads or switches graphs. The registry is pinned for
/// the whole query, including correlated CALL subqueries. Output is currently
/// materialized into the ordinary result table. CALL bindings have a 256 MiB
/// ceiling; use the bounded registry entrypoint to select another envelope.
pub fn run_read_query_with_registry(
    graph: &Graph,
    graph_name: &str,
    cypher: &str,
    params: &CypherParameters,
    registry: &ProcedureRegistry,
) -> Result<CypherResultTable> {
    PreparedProcedureQuery::prepare(graph_name, cypher, registry)?.execute(graph, params)
}

pub(crate) fn execute_read_query_with_registry(
    graph: &Graph,
    graph_name: &str,
    query: &Query,
    params: &CypherParameters,
    registry: &ProcedureRegistry,
) -> Result<CypherResultTable> {
    execute_read_query_with_procedures(
        GraphRef::Owned(graph),
        query,
        params,
        &ProcedureExecution::new(registry.clone())?.with_graph_name(graph_name)?,
    )
}

pub(crate) fn execute_read_query_on_snapshot(
    snapshot: LocalSnapshot<'_>,
    query: &Query,
    params: &CypherParameters,
    registry: &ProcedureRegistry,
) -> Result<CypherResultTable> {
    ensure_query_uses_graph(query, snapshot.identity().graph())?;
    let execution =
        ProcedureExecution::new(registry.clone())?.with_identity(snapshot.identity().clone());
    execute_read_query_with_procedures(GraphRef::Owned(snapshot.graph()), query, params, &execution)
}

pub(crate) fn prepare_query_with_registry(
    query: &mut Query,
    registry: &ProcedureRegistry,
) -> Result<()> {
    ProcedureExecution::new(registry.clone())?.prepare(query)
}

pub(super) fn invocation_error(error: ProcedureError, call: &CallClause) -> GrustError {
    match error {
        ProcedureError::BudgetExceeded {
            resource: "work",
            limit,
        } => gql_execution(format!(
            "bounded read exceeded {limit} candidate-work units while executing {}()",
            call.name
        )),
        ProcedureError::BudgetExceeded {
            resource: "memory",
            limit,
        } => gql_execution(format!(
            "bounded read exceeded {limit} cumulative intermediate bytes while executing {}()",
            call.name
        )),
        error => translate_error(error),
    }
}
