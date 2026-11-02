use std::sync::Arc;

use datafusion::common::{DataFusionError, Result};
use datafusion::execution::SendableRecordBatchStream;
use datafusion::physical_plan::ExecutionPlan;
use datafusion::prelude::SessionContext;

use crate::extension::SessionExtension;
use crate::managed_stream::ManagedStreamControl;
use crate::task_resources::TaskResourceScope;

/// An admitted, move-only preparation bound to the runner that created it.
/// Planning remains on the caller, which retains its typed result and borrows
/// this scope. Finish/cancel expose cleanup independently of that result.
#[tonic::async_trait]
pub trait JobPreparation: Send + Sync {
    fn resources(&self) -> &Arc<TaskResourceScope>;
    fn control(&self) -> ManagedStreamControl;
    fn finish(self: Box<Self>) -> ManagedStreamControl;
    fn cancel(self: Box<Self>) -> ManagedStreamControl;
    async fn execute(
        self: Box<Self>,
        plan: Arc<dyn ExecutionPlan>,
    ) -> Result<SendableRecordBatchStream>;
}

#[tonic::async_trait]
pub trait JobRunner: Send + Sync + 'static {
    /// Admit preparation before the caller invokes planning. The object borrows
    /// this runner and cannot be handed to another runner for execution.
    /// Legacy implementations retain execute; migrate planning callers only
    /// after the corresponding runner's preparation path is qualified.
    fn begin_preparation(&self, _ctx: &SessionContext) -> Result<Box<dyn JobPreparation + '_>> {
        Err(DataFusionError::NotImplemented(
            "pre-planning preparation is not supported by this runner".into(),
        ))
    }

    /// Executes a plan.
    async fn execute(
        &self,
        ctx: &SessionContext,
        plan: Arc<dyn ExecutionPlan>,
    ) -> Result<SendableRecordBatchStream>;

    /// Returns the distributed execution plan for EXPLAIN output.
    fn explain(&self, plan: Arc<dyn ExecutionPlan>) -> Result<String>;

    /// Stop admission/execution and report shutdown or resource-cleanup errors.
    /// Implementations specify which local or remote cleanup they can confirm.
    async fn stop(&self) -> Result<()>;
}

pub struct JobService {
    runner: Box<dyn JobRunner>,
}

impl JobService {
    pub fn new(runner: Box<dyn JobRunner>) -> Self {
        Self { runner }
    }

    pub fn runner(&self) -> &dyn JobRunner {
        self.runner.as_ref()
    }
}

impl SessionExtension for JobService {
    fn name() -> &'static str {
        "JobService"
    }
}
