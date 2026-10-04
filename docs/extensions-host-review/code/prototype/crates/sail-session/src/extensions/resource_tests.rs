use std::fmt::Formatter;
use std::io::Write;
use std::sync::Arc;

use datafusion::arrow::datatypes::Schema;
use datafusion::arrow::record_batch::RecordBatch;
use datafusion::execution::disk_manager::{DiskManagerBuilder, DiskManagerMode};
use datafusion::execution::memory_pool::{GreedyMemoryPool, MemoryConsumer, MemoryPool};
use datafusion::execution::runtime_env::RuntimeEnvBuilder;
use datafusion::execution::{SendableRecordBatchStream, TaskContext};
use datafusion::physical_expr::PhysicalExpr;
use datafusion::physical_plan::common::collect;
use datafusion::physical_plan::empty::EmptyExec;
use datafusion::physical_plan::stream::RecordBatchStreamAdapter;
use datafusion::physical_plan::{DisplayAs, DisplayFormatType, ExecutionPlan, PlanProperties};
use datafusion::prelude::{SessionConfig, SessionContext};
use datafusion_common::tree_node::TreeNodeRecursion;
use datafusion_common::{Result, plan_err};
use datafusion_ffi::execution_plan::{FFI_ExecutionPlan, ForeignExecutionPlan};
use sail_common_datafusion::connect_extension::HostInputExec;
use sail_common_datafusion::native_resource::reserve_native_quota;

/// A participating host input whose fixed reservation gives the pressure test
/// an exact boundary independent of allocator sizes or DataFusion heuristics.
#[derive(Debug)]
struct ReservingInput {
    bytes: usize,
    spill_bytes: usize,
    properties: Arc<PlanProperties>,
}

impl DisplayAs for ReservingInput {
    fn fmt_as(&self, _: DisplayFormatType, f: &mut Formatter<'_>) -> std::fmt::Result {
        write!(f, "ReservingInput: bytes={}", self.bytes)
    }
}

impl ExecutionPlan for ReservingInput {
    fn name(&self) -> &str {
        "ReservingInput"
    }
    fn properties(&self) -> &Arc<PlanProperties> {
        &self.properties
    }
    fn children(&self) -> Vec<&Arc<dyn ExecutionPlan>> {
        vec![]
    }
    fn apply_expressions(
        &self,
        _: &mut dyn FnMut(&Arc<dyn PhysicalExpr>) -> Result<TreeNodeRecursion>,
    ) -> Result<TreeNodeRecursion> {
        Ok(TreeNodeRecursion::Continue)
    }
    fn with_new_children(
        self: Arc<Self>,
        children: Vec<Arc<dyn ExecutionPlan>>,
    ) -> Result<Arc<dyn ExecutionPlan>> {
        if !children.is_empty() {
            return plan_err!("reserving input has no children");
        }
        Ok(self)
    }
    fn execute(&self, _: usize, context: Arc<TaskContext>) -> Result<SendableRecordBatchStream> {
        let reservation =
            MemoryConsumer::new("foreign parent host input").register(context.memory_pool());
        reservation.try_grow(self.bytes)?;
        let spill = if self.spill_bytes > 0 {
            let file = context
                .runtime_env()
                .disk_manager
                .create_tmp_file("foreign input spill")?;
            let mut writer = file.open_writer()?;
            writer.write_all(&vec![0; self.spill_bytes])?;
            writer.finish()?;
            Some(file)
        } else {
            None
        };
        let schema = self.schema();
        Ok(Box::pin(RecordBatchStreamAdapter::new(
            schema.clone(),
            futures::stream::once(async move {
                let _reservation = reservation;
                let _spill = spill;
                Ok(RecordBatch::new_empty(schema))
            }),
        )))
    }
}

#[tokio::test]
async fn foreign_input_refuses_host_pressure_instead_of_using_an_unbounded_default() -> Result<()> {
    let pool: Arc<dyn MemoryPool> = Arc::new(GreedyMemoryPool::new(128));
    let runtime = Arc::new(
        RuntimeEnvBuilder::default()
            .with_memory_pool(pool.clone())
            .build()?,
    );
    let host = SessionContext::new_with_config_rt(SessionConfig::new(), runtime);
    let quota = reserve_native_quota(&pool, "nutmeg-test", 96)?;
    let input: Arc<dyn ExecutionPlan> = Arc::new(ReservingInput {
        bytes: 33,
        spill_bytes: 0,
        properties: EmptyExec::new(Arc::new(Schema::empty()))
            .properties()
            .clone(),
    });
    let foreign_context = Arc::new(TaskContext::default());
    // Control proves that losing the host's pool would silently admit the work.
    collect(input.execute(0, foreign_context.clone())?).await?;
    let adapter = Arc::new(HostInputExec::new(
        input,
        host.task_ctx(),
        tokio::runtime::Handle::current(),
    ));
    let ffi = FFI_ExecutionPlan::new(adapter, Some(tokio::runtime::Handle::current()));
    // Force the real foreign adapter, bypassing its same-library shortcut.
    let foreign: Arc<dyn ExecutionPlan> = Arc::new(ForeignExecutionPlan::try_from(ffi)?);
    let result = match foreign.execute(0, foreign_context.clone()) {
        Ok(stream) => collect(stream).await.map(|_| ()),
        Err(error) => Err(error),
    };
    let message = match result {
        Ok(()) => return plan_err!("96 native + 33 input unexpectedly fitted the 128-byte pool"),
        Err(error) => error.to_string(),
    };
    assert!(message.contains("Resources exhausted"), "{message}");
    assert!(message.contains("foreign parent host input"), "{message}");
    assert_eq!(
        pool.reserved(),
        96,
        "refused host input must leak no reservation"
    );
    drop(quota);
    collect(foreign.execute(0, foreign_context)?).await?;
    assert_eq!(pool.reserved(), 0);
    Ok(())
}

#[tokio::test]
async fn foreign_input_preserves_disabled_and_exhausted_host_spill_policies() -> Result<()> {
    for (mode, expected) in [
        (DiskManagerMode::Disabled, "DiskManager is disabled"),
        (
            DiskManagerMode::OsTmpDirectory,
            "spilling process has exceeded the allowable limit",
        ),
    ] {
        let runtime = Arc::new(
            RuntimeEnvBuilder::default()
                .with_disk_manager_builder(
                    DiskManagerBuilder::default()
                        .with_mode(mode)
                        .with_max_temp_directory_size(1),
                )
                .build()?,
        );
        let host = SessionContext::new_with_config_rt(SessionConfig::new(), runtime.clone());
        let input: Arc<dyn ExecutionPlan> = Arc::new(ReservingInput {
            bytes: 0,
            spill_bytes: 2,
            properties: EmptyExec::new(Arc::new(Schema::empty()))
                .properties()
                .clone(),
        });
        let foreign_context = Arc::new(TaskContext::default());
        // Losing the disk policy would permit this exact two-byte spill.
        collect(input.execute(0, foreign_context.clone())?).await?;
        let adapted = Arc::new(HostInputExec::new(
            input,
            host.task_ctx(),
            tokio::runtime::Handle::current(),
        ));
        let ffi = FFI_ExecutionPlan::new(adapted, Some(tokio::runtime::Handle::current()));
        let foreign = ForeignExecutionPlan::try_from(ffi)?;
        let result = match foreign.execute(0, foreign_context) {
            Ok(stream) => collect(stream).await.map(|_| ()),
            Err(error) => Err(error),
        };
        let message = match result {
            Ok(()) => return plan_err!("foreign input ignored its host spill policy"),
            Err(error) => error.to_string(),
        };
        assert!(message.contains(expected), "{message}");
        assert_eq!(runtime.disk_manager.used_disk_space(), 0);
    }
    Ok(())
}
