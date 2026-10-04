//! Local physical-plan boundary for an already-planned native relation.
//!
//! DataFusion's FFI does not preserve all input requirements, and foreign child
//! replacement can export host-added nodes without a host Tokio runtime. Do not
//! let the outer host optimizer rewrite this mixed-library execution region.

use std::fmt::{Formatter, Result as FmtResult};
use std::sync::Arc;

use arrow_schema::SchemaRef;
use async_trait::async_trait;
use datafusion::catalog::{Session, TableProvider};
use datafusion::execution::{SendableRecordBatchStream, TaskContext};
use datafusion::physical_expr::PhysicalExpr;
use datafusion::physical_plan::{DisplayAs, DisplayFormatType, ExecutionPlan, PlanProperties};
use datafusion_common::tree_node::TreeNodeRecursion;
use datafusion_common::{Result, Statistics, plan_err};
use datafusion_expr::{Expr, TableProviderFilterPushDown, TableType};

#[derive(Debug)]
pub(super) struct NativeTableProvider {
    inner: Arc<dyn TableProvider>,
}

impl NativeTableProvider {
    pub fn new(inner: Arc<dyn TableProvider>) -> Self {
        Self { inner }
    }
}

#[async_trait]
impl TableProvider for NativeTableProvider {
    fn schema(&self) -> SchemaRef {
        self.inner.schema()
    }

    fn table_type(&self) -> TableType {
        self.inner.table_type()
    }

    fn supports_filters_pushdown(
        &self,
        filters: &[&Expr],
    ) -> Result<Vec<TableProviderFilterPushDown>> {
        self.inner.supports_filters_pushdown(filters)
    }

    fn statistics(&self) -> Option<Statistics> {
        self.inner.statistics()
    }

    async fn scan(
        &self,
        session: &dyn Session,
        projection: Option<&Vec<usize>>,
        filters: &[Expr],
        limit: Option<usize>,
    ) -> Result<Arc<dyn ExecutionPlan>> {
        let inner = self.inner.scan(session, projection, filters, limit).await?;
        Ok(Arc::new(NativeRelationExec {
            inner,
            // Keep provider-owned native resources alive with its execution.
            _provider: Arc::clone(&self.inner),
        }))
    }
}

#[derive(Debug)]
struct NativeRelationExec {
    inner: Arc<dyn ExecutionPlan>,
    _provider: Arc<dyn TableProvider>,
}

impl DisplayAs for NativeRelationExec {
    fn fmt_as(&self, _t: DisplayFormatType, f: &mut Formatter<'_>) -> FmtResult {
        write!(
            f,
            "NativeRelationExec: local, opaque_region=true, native={}",
            self.inner.name()
        )
    }
}

impl ExecutionPlan for NativeRelationExec {
    fn name(&self) -> &'static str {
        "NativeRelationExec"
    }

    fn properties(&self) -> &Arc<PlanProperties> {
        self.inner.properties()
    }

    fn children(&self) -> Vec<&Arc<dyn ExecutionPlan>> {
        // Host inputs were optimized before export. The package owns the
        // complete region below this leaf, including its input distribution.
        vec![]
    }

    fn apply_expressions(
        &self,
        _f: &mut dyn FnMut(&Arc<dyn PhysicalExpr>) -> Result<TreeNodeRecursion>,
    ) -> Result<TreeNodeRecursion> {
        Ok(TreeNodeRecursion::Continue)
    }

    fn with_new_children(
        self: Arc<Self>,
        children: Vec<Arc<dyn ExecutionPlan>>,
    ) -> Result<Arc<dyn ExecutionPlan>> {
        if !children.is_empty() {
            return plan_err!("NativeRelationExec is an opaque leaf and does not accept children");
        }
        Ok(self)
    }

    fn execute(
        &self,
        partition: usize,
        context: Arc<TaskContext>,
    ) -> Result<SendableRecordBatchStream> {
        self.inner.execute(partition, context)
    }
}

#[cfg(test)]
mod tests;
