//! Resolve inputs afresh for one batch command, stopping at committed tables.
use std::collections::{BTreeMap, BTreeSet};
use std::sync::Arc;

use datafusion::logical_expr::LogicalPlan;
use datafusion::prelude::SessionContext;
use sail_common::spec;
use sail_common_datafusion::rename::logical_plan::rename_logical_plan;
use sail_plan::config::PlanConfig;
use sail_plan::resolver::PlanResolver;

use super::analysis::AnalyzedGraph;
use super::graph::{GraphDefinition, Name, analysis, quoted};
use crate::error::{SparkError, SparkResult};
use crate::spark::connect::OutputType;

/// Local views are definitions; tables are materialization boundaries. External
/// relations stay on the ordinary resolver path and are not graph dependencies.
fn inputs(
    graph: &GraphDefinition,
    analyzed: &AnalyzedGraph,
    target: &Name,
) -> SparkResult<BTreeSet<Name>> {
    let mut pending = analyzed
        .dependencies
        .get(target)
        .into_iter()
        .flatten()
        .cloned()
        .collect::<Vec<_>>();
    let mut required = BTreeSet::new();
    while let Some(name) = pending.pop() {
        if !required.insert(name.clone()) {
            continue;
        }
        let output = graph
            .outputs
            .iter()
            .find(|output| output.name == name)
            .ok_or_else(|| SparkError::internal("analyzed dependency output missing"))?;
        if output.kind == OutputType::TemporaryView || output.view.is_some() {
            pending.extend(
                analyzed
                    .dependencies
                    .get(&name)
                    .into_iter()
                    .flatten()
                    .cloned(),
            );
        }
    }
    Ok(required)
}

/// The returned provider plans belong to this command only. This does not admit
/// an owner or pin a backend version. Views re-run flow analysis under the
/// accepted command base; committed reads use that command's metadata config.
/// Later ownership activation must pass its captured Session too.
pub(super) async fn resolve_inputs(
    ctx: &SessionContext,
    graph: &GraphDefinition,
    analyzed: &AnalyzedGraph,
    target: &Name,
    command_config: Arc<PlanConfig>,
    command_conf: &super::config::merge::ConfMap,
) -> SparkResult<BTreeMap<Name, LogicalPlan>> {
    let required = inputs(graph, analyzed, target)?;
    let mut resolved = BTreeMap::new();
    let mut accepted = BTreeMap::new();
    for name in analyzed
        .order
        .iter()
        .filter(|name| required.contains(*name))
    {
        let output = graph
            .outputs
            .iter()
            .find(|output| &output.name == name)
            .ok_or_else(|| SparkError::internal("analyzed input output missing"))?;
        let named = if output.kind == OutputType::TemporaryView || output.view.is_some() {
            let flow = graph
                .flows
                .iter()
                .find(|flow| &flow.target == name)
                .ok_or_else(|| analysis("PIPELINE_DATASET_WITHOUT_FLOW", quoted(name)))?;
            let context = super::config::resolve::FlowContext {
                ctx,
                graph,
                resolved: &resolved,
                accepted: &accepted,
                base: command_conf,
                source_case_sensitive: command_config.case_sensitive,
            };
            match context.resolve(flow, None).await? {
                super::config::resolve::FlowResolution::Resolved(result) => {
                    accepted.insert(flow.name.clone(), result.accepted);
                    result.plan
                }
                super::config::resolve::FlowResolution::Failed(failure) => {
                    return Err(failure.error);
                }
                super::config::resolve::FlowResolution::Pending(_) => {
                    return Err(SparkError::internal("command view inputs did not resolve"));
                }
            }
        } else {
            let query = spec::QueryPlan::new(spec::QueryNode::Read {
                read_type: spec::ReadType::NamedTable(Box::new(spec::ReadNamedTable {
                    name: name.clone().into(),
                    temporal: None,
                    sample: None,
                    options: vec![],
                })),
                is_streaming: false,
            });
            PlanResolver::new(ctx, command_config.clone())
                .resolve_named_plan(spec::Plan::Query(query))
                .await?
        };
        let plan = match named.fields {
            Some(fields) => rename_logical_plan(named.plan, &fields)?,
            None => named.plan,
        };
        resolved.insert(name.clone(), plan);
    }
    Ok(resolved)
}

#[cfg(test)]
mod tests;
