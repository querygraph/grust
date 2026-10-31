use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::sync::{Arc, Mutex};

use datafusion::arrow::datatypes::SchemaRef;
use datafusion::common::DFSchema;
use datafusion::logical_expr::{EmptyRelation, LogicalPlan};
use datafusion::prelude::SessionContext;
use sail_catalog::provider::CreateViewOptions;
use sail_common_datafusion::extension::SessionExtensionAccessor;
use sail_common_datafusion::rename::logical_plan::rename_logical_plan;
use sail_plan::error::{PlanError, PlanResult};
use sail_plan::resolver::scope::RelationScope;

use super::graph::{Flow, GraphDefinition, Name, analysis, quoted};
use crate::error::{SparkResult, StructuredSparkError};
use crate::session::SparkSession;
use crate::spark::connect::OutputType;
use crate::spark::connect::pipeline_command::define_output;

/// All declared outputs are known before analysis starts. An unresolved local
/// name must never fall through to a stale table from a previous pipeline run.
pub(super) struct GraphScope<'a> {
    pub graph: &'a GraphDefinition,
    pub resolved: &'a BTreeMap<Name, LogicalPlan>,
    pub reads: Mutex<BTreeSet<Name>>,
    pub flow: &'a Flow,
}

impl<'a> GraphScope<'a> {
    /// A scope over `resolved` relations for `flow`, recording nothing yet.
    pub fn new(
        graph: &'a GraphDefinition,
        resolved: &'a BTreeMap<Name, LogicalPlan>,
        flow: &'a Flow,
    ) -> Self {
        Self {
            graph,
            resolved,
            reads: Mutex::default(),
            flow,
        }
    }
    pub fn input_name(&self, name: &[String]) -> PlanResult<Name> {
        let raw: Name = name.iter().map(|x| x.to_ascii_lowercase()).collect();
        if self.graph.outputs.iter().any(|x| x.name == raw) {
            Ok(raw)
        } else {
            self.qualify(&raw)
        }
    }
}

impl RelationScope for GraphScope<'_> {
    fn resolve(&self, name: &[String]) -> PlanResult<Option<LogicalPlan>> {
        let name = self.input_name(name)?;
        if self.graph.outputs.iter().any(|x| x.name == name) {
            self.reads
                .lock()
                .map_err(|e| PlanError::internal(e.to_string()))?
                .insert(name.clone());
            self.resolved
                .get(&name)
                .cloned()
                .map(Some)
                .ok_or(PlanError::UnresolvedRelation(name))
        } else {
            Ok(None)
        }
    }

    // Computed IDENTIFIER targets materialize after Spark's graph substitution.
    // Their expression subqueries still use this scope; the eventual target does not.
    fn resolve_late_bound(&self, _: &[String]) -> PlanResult<Option<LogicalPlan>> {
        Ok(None)
    }

    fn qualify_late_bound(&self, name: &[String]) -> PlanResult<Name> {
        // Late analysis uses the ordinary session catalog namespace, which may
        // differ from the graph's captured namespace. Do not mutate either one.
        Ok(name.to_vec())
    }

    fn qualify(&self, name: &[String]) -> PlanResult<Name> {
        match name {
            [table] if !self.flow.database.is_empty() => Ok(vec![
                self.flow.catalog.clone(),
                self.flow.database.clone(),
                table.clone(),
            ]),
            [database, table] => Ok(vec![
                self.flow.catalog.clone(),
                database.clone(),
                table.clone(),
            ]),
            [_, _, _] => Ok(name.to_vec()),
            _ => Err(PlanError::analysis(format!(
                "cannot qualify pipeline relation {}",
                quoted(name)
            ))),
        }
    }

    fn default_namespace(&self) -> Option<Vec<String>> {
        Some(vec![self.flow.catalog.clone(), self.flow.database.clone()])
    }
}

pub(super) struct AnalyzedGraph {
    pub order: Vec<Name>,
    pub dependencies: BTreeMap<Name, BTreeSet<Name>>,
    pub schemas: BTreeMap<Name, SchemaRef>,
    pub publications: BTreeMap<Name, CreateViewOptions>,
    pub accepted_confs: BTreeMap<Name, HashMap<String, String>>,
}

mod failure;
pub(super) use failure::{AnalysisError, ResolutionFailures};

pub(super) async fn analyze(
    ctx: &SessionContext,
    graph: &GraphDefinition,
) -> Result<AnalyzedGraph, AnalysisError> {
    analyze_queries(ctx, graph)
        .await?
        .map_err(AnalysisError::from)
}

async fn analyze_queries(
    ctx: &SessionContext,
    graph: &GraphDefinition,
) -> SparkResult<Result<AnalyzedGraph, ResolutionFailures>> {
    graph.validate_bindings()?;
    let spark = ctx.extension::<SparkSession>()?;
    let mut resolved = BTreeMap::new();
    let mut order = vec![];
    let mut flow_plans: BTreeMap<Name, LogicalPlan> = BTreeMap::new();
    let mut flow_reads: BTreeMap<Name, BTreeSet<Name>> = BTreeMap::new();
    let mut failures: BTreeMap<Name, super::config::resolve::FailedFlow> = BTreeMap::new();
    let mut pending_flows = BTreeMap::new();
    let mut dependencies = BTreeMap::new();
    let mut publications = BTreeMap::new();
    let mut accepted_confs = BTreeMap::new();
    let base = HashMap::new();
    let source_case_sensitive = spark.plan_config()?.case_sensitive;
    while order.len() < graph.outputs.len() {
        let before = order.len();
        for output in &graph.outputs {
            if resolved.contains_key(&output.name) {
                continue;
            }
            let mut inputs = BTreeSet::new();
            let mut plans = vec![];
            let mut pending = false;
            for flow in graph.flows.iter().filter(|x| x.target == output.name) {
                if let Some(plan) = flow_plans.get(&flow.name) {
                    inputs.extend(flow_reads[&flow.name].iter().cloned());
                    plans.push(plan.clone());
                    continue;
                }
                if let Some(failure) = failures.get(&flow.name) {
                    inputs.extend(failure.reads.iter().cloned());
                    pending = true;
                    continue;
                }
                let context = super::config::resolve::FlowContext {
                    ctx,
                    graph,
                    resolved: &resolved,
                    accepted: &accepted_confs,
                    base: &base,
                    source_case_sensitive,
                };
                match context.resolve(flow, output.view.as_ref()).await? {
                    super::config::resolve::FlowResolution::Resolved(result) => {
                        inputs.extend(result.reads.iter().cloned());
                        flow_reads.insert(flow.name.clone(), result.reads);
                        pending_flows.remove(&flow.name);
                        accepted_confs.insert(flow.name.clone(), result.accepted);
                        if let Some(options) = result.publication {
                            publications.insert(output.name.clone(), options);
                        }
                        let plan = result.plan;
                        let plan = if let Some(fields) = plan.fields {
                            rename_logical_plan(plan.plan, &fields)?
                        } else {
                            plan.plan
                        };
                        flow_plans.insert(flow.name.clone(), plan.clone());
                        plans.push(plan);
                    }
                    super::config::resolve::FlowResolution::Pending(waiting) => {
                        inputs.extend(waiting.reads.iter().cloned());
                        pending_flows.insert(flow.name.clone(), waiting);
                        pending = true;
                    }
                    super::config::resolve::FlowResolution::Failed(failure) => {
                        inputs.extend(failure.reads.iter().cloned());
                        pending_flows.remove(&flow.name);
                        failures.insert(flow.name.clone(), failure);
                        pending = true;
                    }
                }
            }
            dependencies.insert(output.name.clone(), inputs);
            if pending {
                continue;
            }
            // A dataset without a producer has no query to resolve. Carry its
            // empty schema until graph validation reports DATASET_WITHOUT_FLOW,
            // including for temporary views.
            let plan = if output.kind == OutputType::TemporaryView && !plans.is_empty() {
                if plans.len() != 1 {
                    return Err(analysis("MULTIPLE_QUERIES_FOR_VIEW", quoted(&output.name)));
                }
                plans.remove(0)
            } else {
                let schema = super::schema::infer(ctx, output, &plans)?;
                LogicalPlan::EmptyRelation(EmptyRelation {
                    produce_one_row: false,
                    schema: Arc::new(DFSchema::try_from(schema)?),
                })
            };
            resolved.insert(output.name.clone(), plan);
            order.push(output.name.clone());
            // Only unfinished multi-flow outputs need cached working plans.
            // Materialized inputs keep schemas rather than source providers.
            for flow in graph.flows.iter().filter(|flow| flow.target == output.name) {
                flow_plans.remove(&flow.name);
                flow_reads.remove(&flow.name);
            }
        }
        if before == order.len() {
            for (name, waiting) in pending_flows {
                failures.insert(name, super::config::resolve::FailedFlow {
                    error: crate::error::SparkError::AnalysisError(format!(
                        "Failed to read dataset '{}'. Dataset is defined in the pipeline but could not be resolved.",
                        waiting.input.join(".")
                    )),
                    reads: waiting.reads,
                });
            }
            return Ok(Err(ResolutionFailures::new(graph, failures)?));
        }
    }
    // Persisted-view source restrictions are graph validation, after successful
    // query resolution (GraphValidations.validateSuccessfulFlowAnalysis).
    for output in &graph.outputs {
        if output.view.is_some()
            && let Some(temporary) = graph.outputs.iter().find(|candidate| {
                candidate.kind == OutputType::TemporaryView
                    && dependencies[&output.name].contains(&candidate.name)
            })
        {
            return Err(Box::new(StructuredSparkError {
                class: "org.apache.spark.sql.AnalysisException".into(),
                condition: "INVALID_TEMP_OBJ_REFERENCE".into(),
                sql_state: "42K0F".into(),
                message: format!(
                    "view {} references temporary view {}",
                    quoted(&output.name),
                    quoted(&temporary.name)
                ),
                parameters: HashMap::from([
                    ("obj".into(), "view".into()),
                    ("objName".into(), quoted(&output.name)),
                    ("tempObj".into(), "temporary view".into()),
                    ("tempObjName".into(), quoted(&temporary.name)),
                ]),
            })
            .into());
        }
    }
    // Spark resolves the graph before validating its semantics. In particular,
    // an unresolved source must not be hidden by flow count or streamingness.
    graph.validate()?;
    for output in &graph.outputs {
        if let Some(define_output::Details::TableDetails(details)) = &output.definition.details {
            super::properties::validate_reset(
                details.table_properties.get("pipelines.reset.allowed"),
            )?;
        }
    }
    Ok(Ok(AnalyzedGraph {
        order: super::topology::order(&dependencies)?,
        dependencies,
        schemas: resolved
            .into_iter()
            .map(|(name, plan)| (name, Arc::new(plan.schema().as_arrow().clone())))
            .collect(),
        publications,
        accepted_confs,
    }))
}

#[cfg(test)]
#[path = "analysis_artifact_tests.rs"]
mod artifact_tests;
