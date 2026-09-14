//! Async lifetime control shared by SQL, Cypher and native Arrow consumers.
use datafusion::common::{DataFusionError, Result};
use grust_procedures::{ExecutionContext, ProcedureError};
use std::future::Future;

/// Run an operation under shared explicit cancellation and an absolute deadline.
/// The losing future is dropped, so its owned streams and reservations are
/// released. Cancellation already observed at entry prevents the first poll.
/// Errors retain their source and never cause a retry.
///
/// This is cooperative: synchronous work within one poll cannot be preempted.
/// Providers/kernels must also checkpoint during computation. This wrapper does
/// not charge work or memory, and a stream returned by the operation is outside
/// its lifetime: wrap consumption as well as creation. A deadline requires a
/// Tokio runtime with time enabled. With no deadline no timer is constructed.
pub async fn run_cancellable<T>(
    execution: &ExecutionContext,
    operation: impl Future<Output = Result<T>>,
) -> Result<T> {
    execution.checkpoint().map_err(resource_error)?;
    let deadline = async {
        match execution.limits().deadline {
            Some(deadline) => tokio::time::sleep_until(deadline.into()).await,
            None => std::future::pending().await,
        }
    };
    tokio::select! {
        biased;
        cancelled = execution.cancelled() => {
            cancelled.map_err(resource_error)?;
            Err(resource_error(ProcedureError::Cancelled))
        }
        () = deadline => Err(resource_error(ProcedureError::DeadlineExceeded)),
        result = operation => {
            let value = result?;
            execution.checkpoint().map_err(resource_error)?;
            Ok(value)
        }
    }
}

fn resource_error(error: ProcedureError) -> DataFusionError {
    DataFusionError::External(Box::new(error))
}

#[cfg(test)]
#[path = "control_tests.rs"]
mod tests;
