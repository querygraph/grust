use super::*;
use grust_procedures::ExecutionLimits;
use std::{
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    time::{Duration, Instant},
};

fn context(deadline: Option<Instant>) -> ExecutionContext {
    ExecutionContext::new(ExecutionLimits {
        memory_bytes: 100,
        work_units: 100,
        batch_rows: 10,
        deadline,
    })
    .unwrap()
}

#[tokio::test]
async fn cancellation_drops_pending_operation_and_its_reservation() {
    let execution = context(None);
    let retained = execution.reserve(70).unwrap();
    let operation = async move {
        let _retained = retained;
        std::future::pending::<Result<()>>().await
    };
    let mut future = Box::pin(run_cancellable(&execution, operation));
    assert!(futures::poll!(future.as_mut()).is_pending());
    execution.cancel().unwrap();
    assert!(matches!(future.await, Err(DataFusionError::External(error))
        if matches!(error.downcast_ref::<ProcedureError>(), Some(ProcedureError::Cancelled))));
    assert_eq!(execution.usage().unwrap().live_bytes, 0);
}

#[tokio::test]
async fn cancelled_entry_never_polls_operation_and_errors_are_not_retried() {
    let execution = context(None);
    execution.cancel().unwrap();
    let polled = Arc::new(AtomicBool::new(false));
    let flag = polled.clone();
    assert!(
        run_cancellable(&execution, async move {
            flag.store(true, Ordering::Relaxed);
            Ok(())
        })
        .await
        .is_err()
    );
    assert!(!polled.load(Ordering::Relaxed));
    let error = run_cancellable(&context(None), async {
        Err::<(), _>(DataFusionError::Execution("provider failure".into()))
    })
    .await
    .unwrap_err();
    assert!(matches!(error, DataFusionError::Execution(message) if message == "provider failure"));
}

#[tokio::test(start_paused = true)]
async fn deadline_ends_a_pending_operation_without_provider_wakeups() {
    let execution = context(Some(Instant::now() + Duration::from_secs(60)));
    let mut future = Box::pin(run_cancellable(
        &execution,
        std::future::pending::<Result<()>>(),
    ));
    assert!(futures::poll!(future.as_mut()).is_pending());
    tokio::time::advance(Duration::from_secs(120)).await;
    assert!(matches!(future.await, Err(DataFusionError::External(error))
        if matches!(error.downcast_ref::<ProcedureError>(), Some(ProcedureError::DeadlineExceeded))));
}

#[tokio::test]
async fn dropping_wrapper_releases_resources_without_cancelling_sibling_work() {
    let execution = context(None);
    let retained = execution.reserve(70).unwrap();
    let mut future = Box::pin(run_cancellable(&execution, async move {
        let _retained = retained;
        std::future::pending::<Result<()>>().await
    }));
    assert!(futures::poll!(future.as_mut()).is_pending());
    drop(future);
    assert_eq!(execution.usage().unwrap().live_bytes, 0);
    execution.checkpoint().unwrap();
    assert_eq!(
        run_cancellable(&execution, async { Ok(42) }).await.unwrap(),
        42
    );
}
