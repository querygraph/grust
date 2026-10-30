use std::panic::{AssertUnwindSafe, catch_unwind};
use std::sync::Arc;

use datafusion::common::{Result, internal_datafusion_err};
use datafusion::execution::SendableRecordBatchStream;
use datafusion::physical_plan::{ExecutionPlan, execute_stream};
use datafusion::prelude::SessionContext;
use futures::FutureExt;
use sail_common_datafusion::managed_stream::{ManagedStreamControl, StreamPreparation};
use sail_common_datafusion::session::job::JobPreparation;
use sail_common_datafusion::task_resources::{ScopedTaskContext, TaskResourceScope};
use sail_telemetry::telemetry::global_metrics;
use sail_telemetry::{TracingExecOptions, trace_execution_plan};

use super::{LocalJobRunner, panic_error};

/// One admitted preparation. Its minting runner is borrowed, not supplied again
/// at execution. It cannot outlive that runner or be consumed twice. The context
/// is a clone sharing authoritative state, not a new SessionContext snapshot.
pub struct LocalJobPreparation<'a> {
    pub(super) runner: &'a LocalJobRunner,
    pub(super) id: u64,
    pub(super) context: SessionContext,
    pub(super) resources: Arc<TaskResourceScope>,
    pub(super) preparation: StreamPreparation,
    pub(super) control: ManagedStreamControl,
}

impl LocalJobPreparation<'_> {
    pub fn resources(&self) -> &Arc<TaskResourceScope> {
        &self.resources
    }
    pub fn control(&self) -> ManagedStreamControl {
        self.control.clone()
    }
    pub fn finish(self) -> ManagedStreamControl {
        self.preparation.finish()
    }
    pub fn cancel(self) -> ManagedStreamControl {
        self.preparation.cancel()
    }

    /// Capture the authoritative execution state now, retaining the exact scope
    /// admitted before planning. This matches legacy execute's late capture;
    /// it does not claim a frozen query snapshot or install storage routing.
    pub async fn execute(self, plan: Arc<dyn ExecutionPlan>) -> Result<SendableRecordBatchStream> {
        let Self {
            runner,
            id,
            context,
            resources,
            preparation,
            control,
        } = self;
        if resources.cancelled().now_or_never().is_some() {
            let report = preparation.cancel().completion().await;
            runner.reap();
            report.result()?;
            return Err(internal_datafusion_err!(
                "canceled preparation had no error report"
            ));
        }
        let prepared = catch_unwind(AssertUnwindSafe(|| {
            let scoped = ScopedTaskContext::from_resources(&context.task_ctx(), resources);
            let plan = trace_execution_plan(
                plan,
                TracingExecOptions {
                    metrics: global_metrics(),
                    session_id: Some(runner.session_id.clone()),
                    job_id: Some(id),
                    stage: None,
                    attempt: None,
                    operator_id: None,
                },
            )?;
            let schema = plan.schema();
            let stream = execute_stream(plan, scoped.context)?;
            Ok::<_, datafusion::common::DataFusionError>((schema, stream))
        }))
        .unwrap_or_else(|payload| Err(panic_error("preparation", payload)));
        match prepared {
            Ok((schema, stream)) => Ok(Box::pin(preparation.complete(schema, stream))),
            Err(error) => {
                preparation.fail(error);
                let report = control.completion().await;
                runner.reap();
                report.result()?;
                Err(internal_datafusion_err!(
                    "failed preparation had no error report"
                ))
            }
        }
    }
}

#[tonic::async_trait]
impl JobPreparation for LocalJobPreparation<'_> {
    fn resources(&self) -> &Arc<TaskResourceScope> {
        self.resources()
    }
    fn control(&self) -> ManagedStreamControl {
        self.control()
    }
    fn finish(self: Box<Self>) -> ManagedStreamControl {
        (*self).finish()
    }
    fn cancel(self: Box<Self>) -> ManagedStreamControl {
        (*self).cancel()
    }
    async fn execute(
        self: Box<Self>,
        plan: Arc<dyn ExecutionPlan>,
    ) -> Result<SendableRecordBatchStream> {
        (*self).execute(plan).await
    }
}
