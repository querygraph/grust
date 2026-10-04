use std::future::Future;

use log::warn;
use tokio::task::JoinSet;

/// Session deletion is acknowledged before its asynchronous cleanup completes.
/// Keep those tasks separate from abortable actor timers, and drain them before
/// graceful shutdown releases the actor and its already-deleted sessions.
#[derive(Default)]
pub(super) struct SessionCleanup {
    tasks: JoinSet<()>,
}

impl SessionCleanup {
    pub(super) fn spawn(&mut self, task: impl Future<Output = ()> + Send + 'static) {
        while let Some(result) = self.tasks.try_join_next() {
            Self::report(result);
        }
        self.tasks.spawn(task);
    }

    pub(super) async fn finish(&mut self) {
        while let Some(result) = self.tasks.join_next().await {
            Self::report(result);
        }
    }

    fn report(result: Result<(), tokio::task::JoinError>) {
        if let Err(error) = result {
            warn!("session cleanup task failed: {error}");
        }
    }
}

#[cfg(test)]
mod tests {
    use std::sync::Arc;
    use std::sync::atomic::{AtomicBool, Ordering};

    use datafusion::execution::memory_pool::{GreedyMemoryPool, MemoryPool};
    use sail_common_datafusion::native_resource::NativeResourceTracker;
    use tokio::sync::oneshot;

    use super::*;

    #[tokio::test]
    async fn immediate_shutdown_waits_for_held_cleanup_and_final_native_release()
    -> Result<(), Box<dyn std::error::Error>> {
        let pool: Arc<dyn MemoryPool> = Arc::new(GreedyMemoryPool::new(64));
        let tracker = Arc::new(NativeResourceTracker::default());
        let output = tracker.reserve(&pool, "deleted-session-output", 64)?;
        let completed = Arc::new(AtomicBool::new(false));
        let (entered, entered_rx) = oneshot::channel();
        let (released, released_rx) = oneshot::channel();
        let producer = std::thread::spawn(move || -> Result<(), oneshot::error::RecvError> {
            // Hold the last output independently of the Tokio scheduler. Its
            // admission cannot disappear because an actor dropped its tasks.
            released_rx.blocking_recv()?;
            drop(output);
            Ok(())
        });
        let mut cleanup = SessionCleanup::default();
        let ended = completed.clone();
        cleanup.spawn(async move {
            assert!(entered.send(()).is_ok());
            tracker.wait_for_release().await;
            ended.store(true, Ordering::SeqCst);
        });
        entered_rx.await?;
        let mut shutdown = Box::pin(cleanup.finish());
        assert!(futures::poll!(shutdown.as_mut()).is_pending());
        assert_eq!(pool.reserved(), 64);
        assert!(!completed.load(Ordering::SeqCst));
        released
            .send(())
            .map_err(|_| "native producer exited before release")?;
        shutdown.await;
        producer
            .join()
            .map_err(|_| "native producer thread panicked")??;
        assert!(completed.load(Ordering::SeqCst));
        assert_eq!(pool.reserved(), 0);
        Ok(())
    }
}
