//! Keep a frozen native region on the driver while exposing its host inputs to
//! Sail's stage planner. Task decoding reuses the original read snapshot/write
//! attempt, and task execution substitutes prepared shuffle inputs across FFI.
use std::fmt::{Debug, Formatter};
use std::sync::{Arc, Mutex};

use arrow_schema::SchemaRef;
use async_trait::async_trait;
use datafusion::catalog::{Session, TableProvider};
use datafusion::execution::{SendableRecordBatchStream, TaskContext};
use datafusion::physical_plan::{DisplayAs, DisplayFormatType, ExecutionPlan, PlanProperties};
use datafusion_common::{Result, plan_err};
use datafusion_expr::{Expr, TableType};
use sail_common_datafusion::connect_extension::HostInputExec;
use sail_common_datafusion::driver_extension::{
    BoundDriverPlan, DriverDescriptor, DriverExtensionBinding, DriverExtensionExec,
    DriverExtensionRegistry,
};

#[derive(Debug)]
pub(super) struct InputPlaceholder {
    pub name: String,
    pub properties: Arc<PlanProperties>,
}

impl DisplayAs for InputPlaceholder {
    fn fmt_as(&self, _: DisplayFormatType, f: &mut Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.name)
    }
}

impl ExecutionPlan for InputPlaceholder {
    fn apply_expressions(
        &self,
        _f: &mut dyn FnMut(
            &Arc<dyn datafusion::physical_expr::PhysicalExpr>,
        ) -> Result<datafusion_common::tree_node::TreeNodeRecursion>,
    ) -> Result<datafusion_common::tree_node::TreeNodeRecursion> {
        Ok(datafusion_common::tree_node::TreeNodeRecursion::Continue)
    }
    fn name(&self) -> &str {
        &self.name
    }
    fn properties(&self) -> &Arc<PlanProperties> {
        &self.properties
    }
    fn children(&self) -> Vec<&Arc<dyn ExecutionPlan>> {
        vec![]
    }
    fn with_new_children(
        self: Arc<Self>,
        children: Vec<Arc<dyn ExecutionPlan>>,
    ) -> Result<Arc<dyn ExecutionPlan>> {
        if !children.is_empty() {
            return plan_err!("native input placeholder has no children");
        }
        Ok(self)
    }
    fn execute(&self, _: usize, _: Arc<TaskContext>) -> Result<SendableRecordBatchStream> {
        plan_err!("native input placeholder must be bound before execution")
    }
}

#[derive(Debug)]
pub(super) struct DriverTableProvider {
    pub inner: Arc<dyn TableProvider>,
    pub inputs: Vec<Arc<dyn ExecutionPlan>>,
    pub names: Vec<String>,
    pub owner: String,
    pub registry: Arc<DriverExtensionRegistry>,
}

#[async_trait]
impl TableProvider for DriverTableProvider {
    fn schema(&self) -> SchemaRef {
        self.inner.schema()
    }
    fn table_type(&self) -> TableType {
        self.inner.table_type()
    }
    async fn scan(
        &self,
        session: &dyn Session,
        projection: Option<&Vec<usize>>,
        filters: &[Expr],
        limit: Option<usize>,
    ) -> Result<Arc<dyn ExecutionPlan>> {
        let native = self.inner.scan(session, projection, filters, limit).await?;
        if native.properties().partitioning.partition_count() != 1 {
            return plan_err!("driver-only native relation must produce exactly one partition");
        }
        let bound = Arc::new(BoundDriverPlan {
            descriptor: DriverDescriptor {
                owner: self.owner.clone(),
                plan_id: uuid::Uuid::new_v4().to_string(),
            },
            properties: native.properties().clone(),
            input_schemas: self.inputs.iter().map(|input| input.schema()).collect(),
            binding: Arc::new(NativeBinding {
                resources: Mutex::new(Some(NativeResources {
                    native,
                    _provider: self.inner.clone(),
                })),
                names: self.names.clone(),
            }),
        });
        self.registry.register(&bound)?;
        Ok(Arc::new(DriverExtensionExec::new(
            bound,
            self.inputs.clone(),
        )?))
    }
}

#[derive(Debug)]
struct NativeBinding {
    resources: Mutex<Option<NativeResources>>,
    names: Vec<String>,
}

#[derive(Debug)]
struct NativeResources {
    native: Arc<dyn ExecutionPlan>,
    _provider: Arc<dyn TableProvider>,
}

impl DriverExtensionBinding for NativeBinding {
    fn close(&self) {
        if let Ok(mut resources) = self.resources.lock() {
            resources.take();
        }
    }
    fn materialize(
        &self,
        inputs: &[Arc<dyn ExecutionPlan>],
        context: Arc<TaskContext>,
    ) -> Result<Arc<dyn ExecutionPlan>> {
        let native = self
            .resources
            .lock()
            .map_err(|_| {
                datafusion_common::plan_datafusion_err!("native plan lifetime lock poisoned")
            })?
            .as_ref()
            .ok_or_else(|| {
                datafusion_common::plan_datafusion_err!("native driver query has already finished")
            })?
            .native
            .clone();
        let runtime = tokio::runtime::Handle::try_current().map_err(|e| {
            datafusion_common::plan_datafusion_err!("driver native runtime missing: {e}")
        })?;
        let replacements: Vec<Arc<dyn ExecutionPlan>> = inputs
            .iter()
            .map(|input| {
                Arc::new(HostInputExec::new(
                    input.clone(),
                    context.clone(),
                    runtime.clone(),
                )) as Arc<dyn ExecutionPlan>
            })
            .collect();
        fn substitute(
            plan: Arc<dyn ExecutionPlan>,
            names: &[String],
            replacements: &[Arc<dyn ExecutionPlan>],
            seen: &mut [bool],
        ) -> Result<Arc<dyn ExecutionPlan>> {
            if let Some(index) = names.iter().position(|name| name == plan.name()) {
                if plan.schema() != replacements[index].schema() {
                    return plan_err!("native input placeholder schema changed");
                }
                seen[index] = true;
                return Ok(replacements[index].clone());
            }
            let children = plan.children();
            if children.is_empty() {
                return Ok(plan);
            }
            let replaced = children
                .iter()
                .map(|child| substitute((*child).clone(), names, replacements, seen))
                .collect::<Result<Vec<_>>>()?;
            if children
                .iter()
                .zip(&replaced)
                .all(|(before, after)| Arc::ptr_eq(before, after))
            {
                return Ok(plan);
            }
            plan.replace_children(
                replaced,
                datafusion::physical_plan::ReplaceChildrenOptions::new(
                    datafusion::physical_plan::execution_plan::ChildrenPropertiesMode::Recompute,
                ),
            )
        }
        let mut seen = vec![false; self.names.len()];
        let plan = substitute(native, &self.names, &replacements, &mut seen)?;
        if seen.iter().any(|value| !value) {
            return plan_err!("native relation lost a declared host input");
        }
        Ok(plan)
    }
}

#[cfg(test)]
mod tests {
    use datafusion::datasource::empty::EmptyTable;
    use datafusion::physical_plan::empty::EmptyExec;

    use super::*;

    #[tokio::test]
    async fn driver_binding_releases_archived_snapshot_but_keeps_inflight_plan_alive() -> Result<()>
    {
        let schema = Arc::new(arrow_schema::Schema::empty());
        let native: Arc<dyn ExecutionPlan> = Arc::new(EmptyExec::new(schema.clone()));
        let weak = Arc::downgrade(&native);
        let binding = NativeBinding {
            resources: Mutex::new(Some(NativeResources {
                native,
                _provider: Arc::new(EmptyTable::new(schema)),
            })),
            names: vec![],
        };
        let inflight = binding.materialize(&[], Arc::new(TaskContext::default()))?;
        binding.close();
        assert!(weak.upgrade().is_some());
        assert!(
            binding
                .materialize(&[], Arc::new(TaskContext::default()))
                .is_err()
        );
        drop(inflight);
        assert!(weak.upgrade().is_none());
        binding.close();
        Ok(())
    }
}
