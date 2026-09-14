use super::*;
use datafusion::{
    arrow::{
        array::{ArrayRef, Int64Array},
        datatypes::{DataType, Field, Schema},
    },
    common::DataFusionError,
    physical_plan::stream::RecordBatchStreamAdapter,
};
use futures::{StreamExt, stream};
use grust_procedures::ExecutionLimits;
use std::{
    sync::Arc,
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
fn schema() -> SchemaRef {
    Arc::new(Schema::new(vec![Field::new("n", DataType::Int64, false)]))
}
fn pending_input(execution: &ExecutionContext) -> SendableRecordBatchStream {
    let reservation = execution.reserve(70).unwrap();
    Box::pin(RecordBatchStreamAdapter::new(
        schema(),
        stream::once(async move {
            let _reservation = reservation;
            std::future::pending::<Result<RecordBatch>>().await
        }),
    ))
}

#[tokio::test]
async fn cancellation_drops_pending_provider_and_returns_one_error() {
    let execution = context(None);
    let mut stream = control_stream(pending_input(&execution), execution.clone());
    assert!(futures::poll!(stream.next()).is_pending());
    execution.cancel().unwrap();
    assert!(
        matches!(stream.next().await, Some(Err(DataFusionError::External(error)))
        if matches!(error.downcast_ref::<ProcedureError>(), Some(ProcedureError::Cancelled)))
    );
    assert_eq!(execution.usage().unwrap().live_bytes, 0);
    assert!(stream.next().await.is_none());
    assert!(stream.next().await.is_none());
    assert_eq!(stream.schema(), schema());
}

#[tokio::test(start_paused = true)]
async fn deadline_drops_pending_provider_without_source_wakeups() {
    let execution = context(Some(Instant::now() + Duration::from_secs(60)));
    let mut stream = control_stream(pending_input(&execution), execution.clone());
    assert!(futures::poll!(stream.next()).is_pending());
    tokio::time::advance(Duration::from_secs(120)).await;
    assert!(
        matches!(stream.next().await, Some(Err(DataFusionError::External(error)))
        if matches!(error.downcast_ref::<ProcedureError>(), Some(ProcedureError::DeadlineExceeded)))
    );
    assert_eq!(execution.usage().unwrap().live_bytes, 0);
    assert!(stream.next().await.is_none());
}

#[test]
fn batches_pass_without_copies_and_provider_errors_are_terminal_without_a_runtime() {
    let array = Arc::new(Int64Array::from(vec![1, 2, 3])) as ArrayRef;
    let batch = RecordBatch::try_new(schema(), vec![array.clone()]).unwrap();
    let input = Box::pin(RecordBatchStreamAdapter::new(
        schema(),
        stream::iter(vec![
            Ok(batch.clone()),
            Err(DataFusionError::Execution("source failed".into())),
            Ok(batch),
        ]),
    ));
    let mut stream = control_stream(input, context(None));
    let mut cx = Context::from_waker(std::task::Waker::noop());
    let Poll::Ready(Some(Ok(actual))) = stream.as_mut().poll_next(&mut cx) else {
        panic!("batch");
    };
    assert!(Arc::ptr_eq(actual.column(0), &array));
    assert!(
        matches!(stream.as_mut().poll_next(&mut cx), Poll::Ready(Some(Err(DataFusionError::Execution(message)))) if message == "source failed")
    );
    assert!(matches!(
        stream.as_mut().poll_next(&mut cx),
        Poll::Ready(None)
    ));
}

#[tokio::test]
async fn dropping_stream_releases_provider_without_cancelling_siblings() {
    let execution = context(None);
    let mut stream = control_stream(pending_input(&execution), execution.clone());
    assert!(futures::poll!(stream.next()).is_pending());
    drop(stream);
    assert_eq!(execution.usage().unwrap().live_bytes, 0);
    execution.checkpoint().unwrap();
}

#[tokio::test]
async fn sql_stream_retains_control_through_blocking_arrow_consumption() {
    let engine = crate::DataFusionEngine::new(crate::ExecutionOptions {
        working_memory_bytes: (1 << 20).try_into().unwrap(),
        target_partitions: 1.try_into().unwrap(),
        batch_rows: 10.try_into().unwrap(),
        spill: crate::SpillPolicy::Disabled,
    })
    .unwrap();
    let execution = context(None);
    let stream = engine
        .execute_stream_with_context("SELECT 42 AS n", execution.clone())
        .await
        .unwrap();
    let handle = tokio::runtime::Handle::current();
    execution.cancel().unwrap();
    tokio::task::spawn_blocking(move || {
        let mut reader = crate::BlockingReader::new(stream, handle);
        assert!(reader.next().unwrap().is_err());
        assert!(reader.next().is_none());
    })
    .await
    .unwrap();
    let mut stream = engine
        .execute_stream_with_context("SELECT 42 AS n", context(None))
        .await
        .unwrap();
    assert_eq!(stream.next().await.unwrap().unwrap().num_rows(), 1);
    assert!(stream.next().await.is_none());
}
