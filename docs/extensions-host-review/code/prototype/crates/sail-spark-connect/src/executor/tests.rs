use std::sync::atomic::{AtomicUsize, Ordering};
use std::task::{Context, Poll};

use datafusion::arrow::datatypes::Schema;
use datafusion::execution::RecordBatchStream;
use sail_common_datafusion::session::lifecycle::SessionResource;

use super::*;
use crate::session::{SparkSession, SparkSessionOptions};

struct PendingStream(Arc<AtomicUsize>);

impl Stream for PendingStream {
    type Item = datafusion::common::Result<RecordBatch>;

    fn poll_next(self: Pin<&mut Self>, _: &mut Context<'_>) -> Poll<Option<Self::Item>> {
        Poll::Pending
    }
}

impl RecordBatchStream for PendingStream {
    fn schema(&self) -> SchemaRef {
        Arc::new(Schema::empty())
    }
}

impl Drop for PendingStream {
    fn drop(&mut self) {
        self.0.fetch_add(1, Ordering::SeqCst);
    }
}

fn executor() -> (Executor, Arc<AtomicUsize>) {
    let dropped = Arc::new(AtomicUsize::new(0));
    let executor = Executor::new(
        ExecutorMetadata {
            operation_id: "interrupted-operation".into(),
            tags: vec![],
            reattachable: true,
        },
        Box::pin(PendingStream(Arc::clone(&dropped))),
        Duration::from_secs(3600),
        ExecutorMode::Query,
    );
    (executor, dropped)
}

fn assert_terminal(executor: &Executor, dropped: &AtomicUsize) {
    assert_eq!(dropped.load(Ordering::SeqCst), 1);
    // Repeated reattach cannot consume the error and accidentally restart work.
    for _ in 0..2 {
        assert!(matches!(
            executor.start(),
            Err(SparkError::OperationInterrupted(id)) if id == "interrupted-operation"
        ));
    }
}

#[tokio::test]
async fn interrupt_drops_pending_and_running_contexts_but_preserves_terminal_identity()
-> SparkResult<()> {
    for started in [false, true] {
        let (executor, dropped) = executor();
        let mut output = if started {
            Some(executor.start()?)
        } else {
            None
        };
        if let Some(output) = &mut output {
            assert!(matches!(
                output.next().await,
                Some(Ok(ExecutorOutput {
                    batch: ExecutorBatch::Schema(_),
                    ..
                }))
            ));
        }
        assert!(executor.interrupt().await?);
        assert!(!executor.interrupt().await?);
        assert_terminal(&executor, &dropped);
    }
    Ok(())
}

#[tokio::test]
async fn concurrent_pause_cannot_restore_an_interrupted_context() -> SparkResult<()> {
    let (executor, dropped) = executor();
    let mut output = executor.start()?;
    assert!(output.next().await.is_some());
    let mut pause = Box::pin(executor.pause_if_running());
    // This current-thread runtime cannot join the executor task until yielding.
    // Hold the exact Pausing state without a sleep or a clock race.
    assert!(futures::poll!(pause.as_mut()).is_pending());
    assert!(executor.interrupt().await?);
    pause.await?;
    assert_terminal(&executor, &dropped);
    Ok(())
}

#[tokio::test]
async fn session_stop_drops_owned_plans_and_rejects_in_flight_planning_completion()
-> SparkResult<()> {
    pyo3::Python::initialize();
    let session = SparkSession::try_new(
        "teardown-session".into(),
        "test".into(),
        SparkSessionOptions {
            execution_heartbeat_interval: Duration::from_secs(3600),
        },
    )?;
    let (pending, dropped) = executor();
    session.add_executor(pending)?;
    session.stop().await?;
    assert_eq!(dropped.load(Ordering::SeqCst), 1);
    assert!(session.get_executor("interrupted-operation")?.is_none());
    // A request may have begun planning before teardown. Its completed plan
    // must be dropped instead of resurrecting operations in the deleted session.
    let (late, dropped) = executor();
    assert!(matches!(
        session.add_executor(late),
        Err(SparkError::OperationInterrupted(_))
    ));
    assert_eq!(dropped.load(Ordering::SeqCst), 1);
    session.stop().await?;
    Ok(())
}
