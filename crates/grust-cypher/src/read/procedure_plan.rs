//! Reviewable planning information from the same registry and streaming classifier.

use super::*;
use grust_procedures::{ProcedureDefinition, ProcedureRegistry};

/// Explicit requested execution class. The portable registry executor accepts
/// local snapshots. Backend-native analytics require another implemented adapter
/// and are rejected here rather than silently materializing a remote graph.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ProcedureExecutionTarget {
    LocalSnapshot,
    BackendNative,
}

/// How this implementation consumes one ordinary clause pipeline.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ProcedureRowExecution {
    Incremental,
    Materializing,
}

/// One resolved CALL and the metadata governing its invocation.
#[derive(Clone, Debug)]
pub struct ProcedureCallPlan {
    /// Canonical name, provider identity, semantic version and complete schema.
    pub definition: ProcedureDefinition,
    /// Requested columns and aliases, after implicit YIELD resolution.
    pub yields: Vec<(String, Option<String>)>,
}

/// An execution explanation, built without opening any provider or graph.
#[derive(Clone, Debug)]
pub struct ProcedureQueryPlan {
    /// Explicit graph name fixed at preparation.
    pub graph_name: String,
    /// Present only when explanation was bound to an explicit snapshot. Ordinary
    /// preparation has no snapshot yet and must not invent a revision/principal.
    pub snapshot: Option<grust_procedures::SnapshotIdentity>,
    /// This executor runs against caller-supplied local immutable data.
    pub target: ProcedureExecutionTarget,
    /// Consumer strategy for each query part, including nested subqueries.
    pub pipelines: Vec<ProcedureRowExecution>,
    /// Calls in AST traversal order, resolved from the pinned generation.
    pub calls: Vec<ProcedureCallPlan>,
}

pub(super) fn explain(
    query: &Query,
    graph_name: &str,
    registry: &ProcedureRegistry,
) -> Result<ProcedureQueryPlan> {
    let mut plan = ProcedureQueryPlan {
        graph_name: graph_name.into(),
        snapshot: None,
        target: ProcedureExecutionTarget::LocalSnapshot,
        pipelines: Vec::new(),
        calls: Vec::new(),
    };
    visit(query, registry, &mut plan)?;
    Ok(plan)
}

fn visit(query: &Query, registry: &ProcedureRegistry, plan: &mut ProcedureQueryPlan) -> Result<()> {
    for part in &query.parts {
        plan.pipelines
            .push(if streaming::classify(&part.query).is_some() {
                ProcedureRowExecution::Incremental
            } else {
                ProcedureRowExecution::Materializing
            });
        for clause in &part.query.clauses {
            match clause {
                Clause::Call(call) => {
                    let resolved = registry
                        .resolve(&call.name)
                        .map_err(procedures::translate_error)?;
                    let definition = resolved.definition();
                    plan.calls.push(ProcedureCallPlan {
                        definition: definition.clone(),
                        yields: call.yields.clone(),
                    });
                }
                Clause::Subquery(subquery) => visit(&subquery.query, registry, plan)?,
                _ => {}
            }
        }
    }
    Ok(())
}
