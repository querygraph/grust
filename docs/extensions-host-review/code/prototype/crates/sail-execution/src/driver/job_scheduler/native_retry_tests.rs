use std::sync::atomic::{AtomicUsize, Ordering};

use datafusion::arrow::datatypes::Schema;
use datafusion::physical_plan::empty::EmptyExec;
use sail_common_datafusion::driver_extension::{
    BoundDriverPlan, DriverDescriptor, DriverExtensionBinding, DriverExtensionExec,
};

use super::*;
use crate::job_graph::JobGraphOptions;
use crate::shuffle::ShuffleCompression;

#[derive(Debug)]
struct CommitThenLoseAcknowledgement(Arc<AtomicUsize>);
impl DriverExtensionBinding for CommitThenLoseAcknowledgement {
    fn materialize(
        &self,
        _: &[Arc<dyn ExecutionPlan>],
        _: Arc<TaskContext>,
    ) -> datafusion::common::Result<Arc<dyn ExecutionPlan>> {
        self.0.fetch_add(1, Ordering::SeqCst);
        datafusion::common::exec_err!("injected acknowledgement loss after commit")
    }
}

#[test]
fn driver_mutation_acknowledgement_loss_exhausts_the_region_after_one_attempt()
-> ExecutionResult<()> {
    let commits = Arc::new(AtomicUsize::new(0));
    let empty: Arc<dyn ExecutionPlan> = Arc::new(EmptyExec::new(Arc::new(Schema::empty())));
    let native: Arc<dyn ExecutionPlan> = Arc::new(DriverExtensionExec::new(
        Arc::new(BoundDriverPlan {
            descriptor: DriverDescriptor {
                owner: "fault-fixture@1:code".into(),
                plan_id: "committed-write".into(),
            },
            properties: empty.properties().clone(),
            input_schemas: vec![],
            binding: Arc::new(CommitThenLoseAcknowledgement(commits.clone())),
        }),
        vec![],
    )?);
    let backend = ShuffleBackendKind::Flight {
        compression: ShuffleCompression::None,
    };
    let options = JobSchedulerOptions::for_retry_test(3, backend.clone());
    // Control: an ordinary failed task remains retryable with this configuration.
    for (plan, is_native) in [(empty, false), (native.clone(), true)] {
        let graph = JobGraph::try_new(
            plan,
            JobGraphOptions {
                shuffle_backend: backend.clone(),
            },
        )?;
        let mut job =
            JobDescriptor::try_new(graph, JobState::Draining, Arc::new(TaskContext::default()))?;
        for stage in &mut job.stages {
            for task in &mut stage.tasks {
                task.attempts.push(TaskAttemptDescriptor {
                    state: TaskState::Failed,
                    messages: vec![],
                    cause: None,
                    job_output_fetched: false,
                });
            }
        }
        if is_native {
            assert!(native.execute(0, Arc::new(TaskContext::default())).is_err());
            assert_eq!(commits.load(Ordering::SeqCst), 1);
            assert!(
                job.graph
                    .stages()
                    .iter()
                    .any(|stage| matches!(stage.placement, TaskPlacement::Driver))
            );
        }
        JobScheduler::update_task_regions(&mut job, &options);
        assert_eq!(
            job.regions
                .iter()
                .any(|region| matches!(region.state, TaskRegionState::Failed)),
            is_native
        );
        assert!(
            job.stages
                .iter()
                .all(|stage| stage.tasks.iter().all(|task| task.attempts.len() == 1))
        );
    }
    assert_eq!(commits.load(Ordering::SeqCst), 1);
    Ok(())
}
