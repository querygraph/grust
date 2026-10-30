use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::sync::{Arc, Mutex};

use datafusion::common::DFSchema;
use datafusion::logical_expr::{EmptyRelation, LogicalPlan};
use datafusion::prelude::SessionContext;
use sail_common::spec;
use sail_common_datafusion::extension::SessionExtensionAccessor;
use sail_common_datafusion::rename::logical_plan::rename_logical_plan;
use sail_plan::error::{PlanError, PlanResult};
use sail_plan::resolver::PlanResolver;
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

impl RelationScope for GraphScope<'_> {
    fn resolve(&self, name: &[String]) -> PlanResult<Option<LogicalPlan>> {
        let raw: Name = name.iter().map(|x| x.to_ascii_lowercase()).collect();
        let name = if self.graph.outputs.iter().any(|x| x.name == raw) {
            raw
        } else {
            self.qualify(&raw)?
        };
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
    pub relations: BTreeMap<Name, LogicalPlan>,
}

pub(super) async fn analyze(
    ctx: &SessionContext,
    graph: &GraphDefinition,
) -> SparkResult<AnalyzedGraph> {
    graph.validate()?;
    let spark = ctx.extension::<SparkSession>()?;
    let mut resolved = BTreeMap::new();
    let mut order = vec![];
    let mut dependencies = BTreeMap::new();
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
                let scope = GraphScope {
                    graph,
                    resolved: &resolved,
                    reads: Mutex::default(),
                    flow,
                };
                let planning = spark.planning_context(ctx, flow.sql_conf.clone())?;
                let resolver = PlanResolver::new(&planning.context, planning.config)
                    .with_relation_scope(&scope);
                let result = resolver
                    .resolve_named_plan(spec::Plan::Query(flow.query.clone()))
                    .await;
                inputs.extend(scope.reads.into_inner()?);
                match result {
                    Ok(plan) => {
                        let plan = if let Some(fields) = plan.fields {
                            rename_logical_plan(plan.plan, &fields)?
                        } else {
                            plan.plan
                        };
                        plans.push(plan);
                    }
                    Err(PlanError::UnresolvedRelation(_)) => {
                        pending = true;
                        break;
                    }
                    Err(error) => return Err(error.into()),
                }
            }
            dependencies.insert(output.name.clone(), inputs);
            if pending {
                continue;
            }
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
            let plan = if output.kind == OutputType::TemporaryView {
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
        }
        if before == order.len() {
            // Even partial resolution records the blocked dependency for every
            // pending output. Grust returns the closed cycle, without naming
            // unrelated consumers as members of it.
            super::topology::order(&dependencies)?;
            let pending = graph
                .outputs
                .iter()
                .filter(|x| !resolved.contains_key(&x.name))
                .map(|x| quoted(&x.name))
                .collect::<Vec<_>>()
                .join(", ");
            return Err(analysis("PIPELINE_CIRCULAR_DEPENDENCY", pending));
        }
    }
    for output in &graph.outputs {
        if let Some(define_output::Details::TableDetails(details)) = &output.definition.details {
            super::properties::validate_reset(
                details.table_properties.get("pipelines.reset.allowed"),
            )?;
        }
    }
    Ok(AnalyzedGraph {
        order: super::topology::order(&dependencies)?,
        dependencies,
        relations: resolved,
    })
}
