use std::io;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};

use futures::FutureExt;
use tokio::sync::oneshot;

use super::*;

type TestResult = std::result::Result<(), Box<dyn std::error::Error>>;

#[tokio::test]
async fn abandoned_drain_retains_supervisors_and_rejects_new_admission() -> TestResult {
    let scope = TaskResourceScope::new(Handle::current());
    let (release, pending) = oneshot::channel();
    scope.spawn(|_| async move {
        pending
            .await
            .map_err(|error| DataFusionError::External(Box::new(error)))?;
        Ok(())
    })?;
    assert!(scope.drain().now_or_never().is_none());
    let called = Arc::new(AtomicBool::new(false));
    let flag = called.clone();
    assert!(
        scope
            .spawn(move |_| async move {
                flag.store(true, Ordering::SeqCst);
                Ok(())
            })
            .is_err()
    );
    release.send(()).map_err(|_| "supervisor was lost")?;
    let report = scope.drain().await?;
    assert!(report.is_clean());
    assert_eq!(report.registered, 1);
    assert!(!called.load(Ordering::SeqCst));
    Ok(())
}

#[tokio::test]
async fn cancellation_waits_for_confirmed_cleanup() -> TestResult {
    let scope = TaskResourceScope::new(Handle::current());
    let (observed, observation) = oneshot::channel();
    let (complete, completion) = oneshot::channel();
    scope.spawn(|mut canceled| async move {
        canceled
            .wait_for(|value| *value)
            .await
            .map_err(|error| DataFusionError::External(Box::new(error)))?;
        let _ = observed.send(());
        completion
            .await
            .map_err(|error| DataFusionError::External(Box::new(error)))?;
        Ok(())
    })?;
    scope.cancel()?;
    observation.await?;
    assert!(scope.drain().now_or_never().is_none());
    complete
        .send(())
        .map_err(|_| "cleanup supervisor was lost")?;
    assert!(scope.drain().await?.is_clean());
    Ok(())
}

#[tokio::test]
async fn simultaneous_drainers_share_one_report_and_execution() -> TestResult {
    let scope = TaskResourceScope::new(Handle::current());
    let calls = Arc::new(AtomicUsize::new(0));
    let counter = calls.clone();
    scope.spawn(|_| async move {
        counter.fetch_add(1, Ordering::SeqCst);
        Ok(())
    })?;
    let (a, b) = tokio::join!(scope.drain(), scope.drain());
    let (a, b) = (a?, b?);
    assert!(Arc::ptr_eq(&a, &b));
    assert_eq!(calls.load(Ordering::SeqCst), 1);
    assert!(Arc::ptr_eq(&a, &scope.drain().await?));
    Ok(())
}

#[tokio::test]
async fn typed_failure_does_not_skip_other_supervisors() -> TestResult {
    let scope = TaskResourceScope::new(Handle::current());
    let failed = scope.spawn(|_| async {
        Err(DataFusionError::External(Box::new(io::Error::other(
            "unresolved upload",
        ))))
    })?;
    let (release, pending) = oneshot::channel();
    scope.spawn(|_| async move {
        pending
            .await
            .map_err(|error| DataFusionError::External(Box::new(error)))?;
        Ok(())
    })?;
    assert!(scope.drain().now_or_never().is_none());
    release.send(()).map_err(|_| "second supervisor was lost")?;
    let report = scope.drain().await?;
    assert_eq!(report.registered, 2);
    assert_eq!(report.failures.len(), 1);
    assert_eq!(report.failures[0].id, failed);
    assert!(
        matches!(&report.failures[0].error,DataFusionError::External(error) if error.downcast_ref::<io::Error>().is_some())
    );
    assert!(!report.is_clean());
    Ok(())
}

#[tokio::test]
async fn canceling_one_scope_preserves_sibling_admission() -> TestResult {
    let a = TaskResourceScope::new(Handle::current());
    let b = TaskResourceScope::new(Handle::current());
    a.cancel()?;
    b.spawn(|canceled| async move {
        assert!(!*canceled.borrow());
        Ok(())
    })?;
    assert_eq!(a.drain().await?.registered, 0);
    assert_eq!(b.drain().await?.registered, 1);
    Ok(())
}

#[tokio::test]
async fn panicking_supervisor_remains_a_failed_join() -> TestResult {
    let scope = TaskResourceScope::new(Handle::current());
    scope.spawn(|_| {
        futures::future::poll_fn::<Result<()>, _>(|_| {
            std::panic::resume_unwind(Box::new("resource panic"))
        })
    })?;
    let report = scope.drain().await?;
    assert_eq!(report.failures.len(), 1);
    assert!(
        matches!(&report.failures[0].error,DataFusionError::External(error) if error.downcast_ref::<tokio::task::JoinError>().is_some_and(|join| join.is_panic()))
    );
    Ok(())
}

#[test]
fn shutdown_runtime_reports_failed_join_without_spawning_a_drainer() -> TestResult {
    let runtime = tokio::runtime::Runtime::new()?;
    let scope = TaskResourceScope::new(runtime.handle().clone());
    scope.spawn(|_| futures::future::pending())?;
    runtime.shutdown_background();
    let report = futures::executor::block_on(scope.drain())?;
    assert_eq!(report.failures.len(), 1);
    assert!(!report.is_clean());
    Ok(())
}
