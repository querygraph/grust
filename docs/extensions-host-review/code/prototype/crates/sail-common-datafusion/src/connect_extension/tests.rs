use std::sync::atomic::{AtomicUsize, Ordering};

use datafusion::arrow::array::Int64Array;
use datafusion::arrow::datatypes::{DataType, Field, Schema};
use datafusion::arrow::record_batch::RecordBatch;
use datafusion::datasource::empty::EmptyTable;
use datafusion::physical_expr::{EquivalenceProperties, Partitioning};
use datafusion::physical_plan::common::collect;
use datafusion::physical_plan::execution_plan::{Boundedness, EmissionType};
use datafusion::physical_plan::stream::RecordBatchStreamAdapter;
use datafusion::prelude::SessionContext;

use super::*;

struct EmptyHandler;

impl ConnectRelationHandler for EmptyHandler {
    fn plan(
        &self,
        _payload: &[u8],
        _inputs: Vec<Arc<dyn ExecutionPlan>>,
    ) -> Result<Arc<dyn TableProvider>> {
        Ok(Arc::new(EmptyTable::new(Arc::new(Schema::empty()))))
    }
}

#[test]
fn registry_refuses_collisions_unknown_urls_and_invalid_shapes() -> Result<()> {
    let mut registry = ConnectExtensionRegistry::new();
    registry.register(
        "type.test/Stage".into(),
        false,
        2,
        2,
        Arc::new(EmptyHandler),
    )?;
    registry.register("type.test/Read".into(), true, 0, 0, Arc::new(EmptyHandler))?;
    assert!(registry.resolve("type.test/Stage", true, 2).is_ok());
    assert!(registry.resolve("type.test/Read", false, 0).is_ok());
    assert!(matches!(
        registry.resolve("type.test/Stage", false, 0),
        Err(e) if e.to_string().contains("Stage requires a SailExtensionRequest envelope")
    ));
    assert!(matches!(
        registry.resolve("type.test/Stage", true, 1),
        Err(e) if e.to_string().contains("expects 2..=2 inputs, received 1")
    ));
    assert!(matches!(
        registry.resolve("type.test/Missing", true, 0),
        Err(e) if e.to_string().contains("type.test/Missing")
            && e.to_string().contains("[type.test/Read, type.test/Stage]")
    ));
    assert!(matches!(
        registry.register("type.test/Stage".into(), true, 0, 0, Arc::new(EmptyHandler)),
        Err(e) if e.to_string().contains("duplicate")
    ));
    // A failed duplicate registration leaves the original contract intact.
    assert!(registry.resolve("type.test/Stage", true, 2).is_ok());
    assert!(registry.resolve("type.test/Stage", true, 0).is_err());
    assert!(
        registry
            .register("type.test/Bad".into(), true, 1, 1, Arc::new(EmptyHandler))
            .is_err()
    );
    Ok(())
}

struct ContextProbeExec {
    expected: Arc<TaskContext>,
    properties: Arc<PlanProperties>,
    executions: Arc<AtomicUsize>,
    runtime: tokio::runtime::Id,
}

impl Debug for ContextProbeExec {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        write!(f, "ContextProbeExec")
    }
}

impl DisplayAs for ContextProbeExec {
    fn fmt_as(&self, _t: DisplayFormatType, f: &mut Formatter<'_>) -> std::fmt::Result {
        write!(f, "ContextProbeExec")
    }
}

impl ExecutionPlan for ContextProbeExec {
    fn name(&self) -> &'static str {
        "ContextProbeExec"
    }

    fn properties(&self) -> &Arc<PlanProperties> {
        &self.properties
    }

    fn children(&self) -> Vec<&Arc<dyn ExecutionPlan>> {
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
            return plan_err!("ContextProbeExec has no children");
        }
        Ok(self)
    }

    fn execute(
        &self,
        partition: usize,
        context: Arc<TaskContext>,
    ) -> Result<SendableRecordBatchStream> {
        if !Arc::ptr_eq(&context, &self.expected) {
            return exec_err!("Sail input received a foreign task context");
        }
        assert_eq!(Handle::current().id(), self.runtime);
        self.executions.fetch_add(1, Ordering::SeqCst);
        let values = match partition {
            0 => vec![10, 20],
            1 => vec![],
            2 => vec![30],
            _ => return exec_err!("unexpected partition {partition}"),
        };
        let batch = RecordBatch::try_new(self.schema(), vec![Arc::new(Int64Array::from(values))])?;
        let runtime = self.runtime;
        Ok(Box::pin(RecordBatchStreamAdapter::new(
            self.schema(),
            futures::stream::once(async move {
                assert_eq!(Handle::current().id(), runtime);
                // Constructing a timer needs the correct reactor at poll time,
                // even when the caller is an ordinary foreign worker thread.
                tokio::time::sleep(std::time::Duration::from_millis(1)).await;
                Ok(batch)
            }),
        )))
    }
}

#[tokio::test]
async fn host_input_is_lazy_consumes_every_partition_and_preserves_context_after_replacement()
-> Result<()> {
    let host = SessionContext::new().task_ctx();
    let foreign = SessionContext::new().task_ctx();
    let executions = Arc::new(AtomicUsize::new(0));
    let schema = Arc::new(Schema::new(vec![Field::new("id", DataType::Int64, false)]));
    let probe = Arc::new(ContextProbeExec {
        expected: Arc::clone(&host),
        properties: Arc::new(PlanProperties::new(
            EquivalenceProperties::new(schema),
            Partitioning::UnknownPartitioning(3),
            EmissionType::Incremental,
            Boundedness::Bounded,
        )),
        executions: Arc::clone(&executions),
        runtime: Handle::current().id(),
    });
    let input = Arc::new(HostInputExec::new(probe.clone(), host, Handle::current()));
    assert_eq!(executions.load(Ordering::SeqCst), 0);
    assert!(input.execute(1, Arc::clone(&foreign)).is_err());
    let batches = collect(input.execute(0, Arc::clone(&foreign))?).await?;
    assert_eq!(batches.iter().map(RecordBatch::num_rows).sum::<usize>(), 3);
    assert_eq!(executions.load(Ordering::SeqCst), 3);

    #[expect(deprecated)]
    let replaced = input.with_new_children(vec![probe])?;
    let batches = collect(replaced.execute(0, foreign)?).await?;
    assert_eq!(batches.iter().map(RecordBatch::num_rows).sum::<usize>(), 3);
    assert_eq!(executions.load(Ordering::SeqCst), 6);
    Ok(())
}

#[test]
fn host_input_preserves_runtime_when_replaced_and_polled_on_a_foreign_thread() -> Result<()> {
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .worker_threads(2)
        .enable_all()
        .build()?;
    let host = SessionContext::new().task_ctx();
    let foreign = SessionContext::new().task_ctx();
    let executions = Arc::new(AtomicUsize::new(0));
    let schema = Arc::new(Schema::new(vec![Field::new("id", DataType::Int64, false)]));
    let probe = Arc::new(ContextProbeExec {
        expected: Arc::clone(&host),
        properties: Arc::new(PlanProperties::new(
            EquivalenceProperties::new(schema),
            Partitioning::UnknownPartitioning(1),
            EmissionType::Incremental,
            Boundedness::Bounded,
        )),
        executions: Arc::clone(&executions),
        runtime: runtime.handle().id(),
    });
    let input = Arc::new(HostInputExec::new(
        probe.clone(),
        host,
        runtime.handle().clone(),
    ));
    // The single-partition coalescer delegates its stream directly. Thus this
    // tests the wrapper's poll guard itself, without a Tokio task hiding it.
    std::thread::spawn(move || -> Result<()> {
        assert!(Handle::try_current().is_err());
        let batches =
            futures::executor::block_on(collect(input.execute(0, Arc::clone(&foreign))?))?;
        assert_eq!(batches.iter().map(RecordBatch::num_rows).sum::<usize>(), 2);
        assert!(Handle::try_current().is_err());
        #[expect(deprecated)]
        let replaced = input.with_new_children(vec![probe])?;
        let batches = futures::executor::block_on(collect(replaced.execute(0, foreign)?))?;
        assert_eq!(batches.iter().map(RecordBatch::num_rows).sum::<usize>(), 2);
        assert!(Handle::try_current().is_err());
        Ok(())
    })
    .join()
    .map_err(|_| datafusion_common::internal_datafusion_err!("foreign thread panicked"))??;
    assert_eq!(executions.load(Ordering::SeqCst), 2);
    Ok(())
}
