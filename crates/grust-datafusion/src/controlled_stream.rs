//! Stream-lifetime cancellation without batch copies, queues or worker tasks.
use datafusion::{
    arrow::{datatypes::SchemaRef, record_batch::RecordBatch},
    common::Result,
    physical_plan::{RecordBatchStream, SendableRecordBatchStream},
};
use futures::Stream;
use grust_procedures::{Cancellation, ExecutionContext, ProcedureError};
use std::{
    future::Future,
    pin::Pin,
    task::{Context, Poll},
};
use tokio::time::Sleep;

/// Apply shared cancellation/deadline control to the entire Arrow stream.
/// Batches pass through unchanged. Completion or the first error drops the
/// upstream stream and unregisters the cancellation waiter immediately; later
/// polls return `None`. This also composes with [`crate::BlockingReader`].
///
/// This is cooperative, not work/memory accounting or a full Cypher policy.
/// Synchronous provider work inside one poll must checkpoint independently.
/// Construction with a deadline requires Tokio's time driver; without a
/// deadline the wrapper is runtime-independent and constructs no timer.
pub fn control_stream(
    stream: SendableRecordBatchStream,
    execution: ExecutionContext,
) -> SendableRecordBatchStream {
    let schema = stream.schema();
    let deadline = execution
        .limits()
        .deadline
        .map(|deadline| Box::pin(tokio::time::sleep_until(deadline.into())));
    let cancellation = Some(execution.cancelled());
    Box::pin(ControlledStream {
        stream: Some(stream),
        schema,
        execution,
        cancellation,
        deadline,
    })
}

struct ControlledStream {
    stream: Option<SendableRecordBatchStream>,
    schema: SchemaRef,
    execution: ExecutionContext,
    cancellation: Option<Cancellation>,
    deadline: Option<Pin<Box<Sleep>>>,
}

impl ControlledStream {
    fn finish(&mut self) {
        self.stream = None;
        self.cancellation = None;
        self.deadline = None;
    }

    fn check_control(&mut self, cx: &mut Context<'_>) -> Result<()> {
        self.execution
            .checkpoint()
            .map_err(super::control::resource_error)?;
        if let Some(cancellation) = &mut self.cancellation
            && let Poll::Ready(result) = Pin::new(cancellation).poll(cx)
        {
            result.map_err(super::control::resource_error)?;
            return Err(super::control::resource_error(ProcedureError::Cancelled));
        }
        if let Some(deadline) = &mut self.deadline
            && deadline.as_mut().poll(cx).is_ready()
        {
            return Err(super::control::resource_error(
                ProcedureError::DeadlineExceeded,
            ));
        }
        Ok(())
    }
}

impl Stream for ControlledStream {
    type Item = Result<RecordBatch>;

    fn poll_next(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Option<Self::Item>> {
        let this = self.get_mut();
        if this.stream.is_none() {
            return Poll::Ready(None);
        }
        if let Err(error) = this.check_control(cx) {
            this.finish();
            return Poll::Ready(Some(Err(error)));
        }
        let next = match &mut this.stream {
            Some(stream) => stream.as_mut().poll_next(cx),
            None => return Poll::Ready(None),
        };
        match next {
            Poll::Ready(Some(Ok(batch))) => {
                if let Err(error) = this.execution.checkpoint() {
                    this.finish();
                    Poll::Ready(Some(Err(super::control::resource_error(error))))
                } else {
                    Poll::Ready(Some(Ok(batch)))
                }
            }
            Poll::Ready(terminal) => {
                this.finish();
                Poll::Ready(terminal)
            }
            Poll::Pending => Poll::Pending,
        }
    }
}

impl RecordBatchStream for ControlledStream {
    fn schema(&self) -> SchemaRef {
        self.schema.clone()
    }
}

#[cfg(test)]
#[path = "controlled_stream_tests.rs"]
mod tests;
