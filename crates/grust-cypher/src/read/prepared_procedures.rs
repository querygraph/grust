//! Prepared CALL schemas and immutable provider generations.

use grust_procedures::{ProcedureDefinition, ProcedureRegistry};

use super::*;

/// A parsed and semantically checked query retaining its provider generation.
///
/// Replacing the application's registry cannot change this plan's schemas or
/// provider implementations. Graph selection is fixed by name at preparation;
/// execution still requires the caller to supply that explicit local graph.
/// This plan does not claim a remote backend or cache an algorithm result.
#[derive(Clone)]
pub struct PreparedProcedureQuery {
    query: Query,
    graph_name: String,
    registry: ProcedureRegistry,
    source: String,
}

impl PreparedProcedureQuery {
    /// Prepare for an explicit execution target. Native backend requests are
    /// unsupported by this local executor and fail before provider invocation.
    pub fn prepare_for_target(
        graph_name: &str,
        cypher: &str,
        registry: &ProcedureRegistry,
        target: ProcedureExecutionTarget,
    ) -> Result<Self> {
        match target {
            ProcedureExecutionTarget::LocalSnapshot => Self::prepare(graph_name, cypher, registry),
            ProcedureExecutionTarget::BackendNative => Err(procedures::translate_error(grust_procedures::ProcedureError::Unsupported("backend-native procedure execution requires an explicit supported backend adapter".into()))),
        }
    }

    /// Parse once, resolve CALL output scopes, and validate names and static
    /// argument schemas. Parameter values are validated at execution.
    ///
    /// # Errors
    /// Rejects unknown procedures/outputs/options, invalid arity/literal values,
    /// write providers, graph selection mismatch and ordinary semantic errors.
    pub fn prepare(graph_name: &str, cypher: &str, registry: &ProcedureRegistry) -> Result<Self> {
        let mut query = parse_query(cypher).map_err(|error| error.into_grust(cypher))?;
        ensure_query_uses_graph(&query, graph_name)?;
        let execution = ProcedureExecution::new(registry.clone())?;
        execution.prepare(&mut query)?;
        Ok(Self {
            query,
            graph_name: graph_name.to_owned(),
            registry: registry.clone(),
            source: cypher.to_owned(),
        })
    }

    /// Execute this plan against the caller's selected local graph. Parameters
    /// are revalidated each time; correlated CALL still runs per incoming row.
    /// The ordinary materializing CALL ceiling is 256 MiB.
    pub fn execute(&self, graph: &Graph, params: &CypherParameters) -> Result<CypherResultTable> {
        execute_read_query_with_registry(
            graph,
            &self.graph_name,
            &self.query,
            params,
            &self.registry,
        )
    }

    /// Execute against an explicit adapter-authorized snapshot. Rejects a
    /// different graph name before invoking any provider. Revision and principal
    /// identity are passed intact to providers; this plan caches no graph data.
    pub fn execute_snapshot(
        &self,
        snapshot: grust_procedures::LocalSnapshot<'_>,
        params: &CypherParameters,
    ) -> Result<CypherResultTable> {
        if snapshot.identity().graph() != self.graph_name {
            return Err(procedures::translate_error(
                grust_procedures::ProcedureError::Stale(
                    "prepared graph differs from supplied snapshot".into(),
                ),
            ));
        }
        let execution = ProcedureExecution::new(self.registry.clone())?
            .with_identity(snapshot.identity().clone());
        execute_read_query_with_procedures(
            GraphRef::Owned(snapshot.graph()),
            &self.query,
            params,
            &execution,
        )
    }

    /// Apply a caller's current bounded policy to this plan's source and pinned
    /// registry. This revalidates the source under that policy before execution;
    /// it does not claim to reuse a policy-specific compiled plan.
    pub fn execute_snapshot_bounded(
        &self,
        snapshot: grust_procedures::LocalSnapshot<'_>,
        params: &CypherParameters,
        policy: &crate::ReadQueryPolicy,
    ) -> Result<CypherResultTable> {
        if snapshot.identity().graph() != self.graph_name {
            return Err(procedures::translate_error(
                grust_procedures::ProcedureError::Stale(
                    "prepared graph differs from supplied snapshot".into(),
                ),
            ));
        }
        crate::read_policy::run_bounded_read_query_on_snapshot(
            snapshot,
            &self.source,
            params,
            policy,
            &self.registry,
        )
    }

    /// The name of the local graph selected when the plan was prepared.
    pub fn graph_name(&self) -> &str {
        &self.graph_name
    }

    /// Explain schemas, provider identities, graph requirements, correlation and
    /// the actual consumer classifier without opening any provider.
    pub fn explain(&self) -> Result<ProcedureQueryPlan> {
        procedure_plan::explain(&self.query, &self.graph_name, &self.registry)
    }

    /// Explain the local plan bound to a caller-authorized snapshot without
    /// preparing projections or opening providers. A mismatched graph is stale.
    pub fn explain_snapshot(
        &self,
        snapshot: grust_procedures::LocalSnapshot<'_>,
    ) -> Result<ProcedureQueryPlan> {
        if snapshot.identity().graph() != self.graph_name {
            return Err(procedures::translate_error(
                grust_procedures::ProcedureError::Stale(
                    "prepared graph differs from supplied snapshot".into(),
                ),
            ));
        }
        let mut plan = self.explain()?;
        plan.snapshot = Some(snapshot.identity().clone());
        Ok(plan)
    }

    /// Registered schemas/providers pinned by this plan's registry generation.
    /// This is registry introspection, not a claim about backend-native execution.
    pub fn definitions(&self) -> impl Iterator<Item = &ProcedureDefinition> {
        self.registry.definitions()
    }
}

/// Establish CALL output bindings from the same schema used for execution.
/// Existing explicit YIELD aliases remain untouched. This runs before semantic
/// analysis so implicit outputs get ordinary collision/unbound-name checks.
pub(super) fn resolve_output_scopes(query: &mut Query, registry: &ProcedureRegistry) -> Result<()> {
    for part in &mut query.parts {
        for clause in &mut part.query.clauses {
            match clause {
                Clause::Call(call) if call.yields.is_empty() => {
                    let procedure = registry
                        .resolve(&call.name)
                        .map_err(procedures::translate_error)?;
                    call.yields = procedure
                        .definition()
                        .outputs
                        .iter()
                        .map(|field| (field.name.clone(), None))
                        .collect();
                }
                Clause::Subquery(subquery) => resolve_output_scopes(&mut subquery.query, registry)?,
                Clause::Call(_)
                | Clause::Use(_)
                | Clause::Match(_)
                | Clause::With(_)
                | Clause::Unwind(_)
                | Clause::Return(_)
                | Clause::Create(_)
                | Clause::Merge(_)
                | Clause::Delete(_)
                | Clause::Set(_)
                | Clause::Remove(_) => {}
            }
        }
    }
    Ok(())
}
