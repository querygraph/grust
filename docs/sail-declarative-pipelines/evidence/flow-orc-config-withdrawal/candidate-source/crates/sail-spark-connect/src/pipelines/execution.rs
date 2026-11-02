use std::collections::BTreeMap;
use std::sync::{Arc, Mutex};

use datafusion::prelude::SessionContext;
use futures::TryStreamExt;
use sail_common::spec;
use sail_common_datafusion::extension::SessionExtensionAccessor;
use sail_common_datafusion::rename::logical_plan::rename_logical_plan;
use sail_common_datafusion::session::job::JobService;
use sail_plan::config::PlanConfig;
use sail_plan::resolve_and_execute_plan_with_scope;
use sail_plan::resolver::PlanResolver;
use sail_plan::resolver::scope::RelationScope;

use super::analysis::{AnalyzedGraph, GraphScope};
use super::graph::{Flow, GraphDefinition, Output, analysis};
use super::selection::Selection;
use crate::error::{SparkError, SparkResult};
use crate::session::SparkSession;
use crate::spark::connect::{OutputType, pipeline_command as pc};

pub(super) async fn execute(
    ctx: &SessionContext,
    graph: &GraphDefinition,
    analyzed: AnalyzedGraph,
    selection: Selection,
) -> SparkResult<()> {
    // Reject unsupported modes before the first write, rather than partially
    // publishing a batch graph that contains an incremental or sink output.
    if graph
        .outputs
        .iter()
        .any(|x| matches!(x.kind, OutputType::Table | OutputType::Sink))
    {
        return Err(SparkError::unsupported("incremental pipeline execution"));
    }
    let spark = ctx.extension::<SparkSession>()?;
    super::materialize::tables(ctx, graph, &analyzed, &selection).await?;
    super::materialize::views(ctx, graph, &analyzed).await?;
    let mut resolved = BTreeMap::new();
    for name in analyzed.order {
        let output = graph
            .outputs
            .iter()
            .find(|x| x.name == name)
            .ok_or_else(|| SparkError::internal("analyzed output missing"))?;
        if output.view.is_some()
            || !selection.required.contains(&name)
            || (output.kind != OutputType::TemporaryView && !selection.runs(&name))
        {
            continue;
        }
        let flow = graph
            .flows
            .iter()
            .find(|x| x.target == name)
            .ok_or_else(|| analysis("PIPELINE_DATASET_WITHOUT_FLOW", name.join(".")))?;
        let planning = spark.planning_context(ctx, flow.sql_conf.clone())?;
        let ctx = &planning.context;
        let config = planning.config;
        // Read catalog inputs only when a query consumes them, after selected
        // upstream tables have been written, using that consumer's settings.
        // Persisted scans cannot be cached across flows with different defaults.
        // Temporary-view definitions keep their own already-resolved plans.
        for input in analyzed.dependencies.get(&name).into_iter().flatten() {
            if graph
                .outputs
                .iter()
                .any(|output| &output.name == input && output.kind != OutputType::TemporaryView)
            {
                resolved.insert(
                    input.clone(),
                    read_output(ctx, config.clone(), input.clone()).await?,
                );
            }
        }
        let scope = GraphScope {
            graph,
            resolved: &resolved,
            reads: Mutex::default(),
            flow,
        };
        let resolver = PlanResolver::new(ctx, config.clone()).with_relation_scope(&scope);
        if output.kind == OutputType::TemporaryView {
            let plan = resolver
                .resolve_named_plan(spec::Plan::Query(flow.query.clone()))
                .await?;
            let plan = match plan.fields {
                Some(fields) => rename_logical_plan(plan.plan, &fields)?,
                None => plan.plan,
            };
            resolved.insert(name, plan);
            continue;
        }
        run_command(ctx, config, table_write_command(output, flow), Some(&scope)).await?;
        // Downstream consumers scan this committed table in their own context;
        // they never inline/recompute the producer's definition.
    }
    Ok(())
}

pub(super) async fn run_command(
    ctx: &SessionContext,
    config: Arc<PlanConfig>,
    command: spec::CommandNode,
    scope: Option<&dyn RelationScope>,
) -> SparkResult<()> {
    let (physical, _) = resolve_and_execute_plan_with_scope(
        ctx,
        config,
        spec::Plan::Command(spec::CommandPlan::new(command)),
        scope,
    )
    .await?;
    let service = ctx.extension::<JobService>()?;
    let mut stream = service.runner().execute(ctx, physical).await?;
    while stream.try_next().await?.is_some() {}
    Ok(())
}

fn table_write_command(output: &Output, flow: &Flow) -> spec::CommandNode {
    let details = match &output.definition.details {
        Some(pc::define_output::Details::TableDetails(details)) => details.clone(),
        _ => pc::define_output::TableDetails::default(),
    };
    spec::CommandNode::WriteTo(spec::WriteTo {
        input: Box::new(flow.query.clone()),
        provider: details.format,
        table: output.name.clone().into(),
        mode: spec::WriteToMode::Append,
        partitioning_columns: details
            .partition_cols
            .into_iter()
            .map(|name| spec::Expr::UnresolvedAttribute {
                name: spec::ObjectName::bare(name),
                plan_id: None,
                is_metadata_column: false,
            })
            .collect(),
        clustering_columns: details
            .clustering_columns
            .into_iter()
            .map(Into::into)
            .collect(),
        options: vec![],
        table_properties: vec![],
    })
}

async fn read_output(
    ctx: &SessionContext,
    config: Arc<PlanConfig>,
    name: super::graph::Name,
) -> SparkResult<datafusion::logical_expr::LogicalPlan> {
    let read = spec::QueryPlan::new(spec::QueryNode::Read {
        read_type: spec::ReadType::NamedTable(Box::new(spec::ReadNamedTable {
            name: name.clone().into(),
            temporal: None,
            sample: None,
            options: vec![],
        })),
        is_streaming: false,
    });
    let plan = PlanResolver::new(ctx, config)
        .resolve_named_plan(spec::Plan::Query(read))
        .await?;
    let plan = match plan.fields {
        Some(fields) => rename_logical_plan(plan.plan, &fields)?,
        None => plan.plan,
    };
    Ok(plan)
}
