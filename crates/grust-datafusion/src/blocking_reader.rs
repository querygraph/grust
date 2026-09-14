//! Explicit async-to-blocking Arrow reader bridge for ADBC ingestion.
use datafusion::{
    arrow::{
        array::{RecordBatch, RecordBatchReader},
        datatypes::SchemaRef,
        error::ArrowError,
    },
    physical_plan::SendableRecordBatchStream,
};
use futures::StreamExt;
use tokio::runtime::Handle;

/// A synchronous reader over a DataFusion stream, suitable for ADBC binding.
/// No queue, worker, IPC or full-result collection is introduced. The caller
/// supplies and keeps alive the Tokio runtime that drives the source.
///
/// # Panics
/// Pulling this reader on an async runtime worker panics as documented by
/// `Handle::block_on`. Consume it on an ordinary thread or `spawn_blocking`,
/// while its runtime remains alive. A current-thread runtime must also be driven
/// by `Runtime::block_on` elsewhere when the source requires I/O/timers.
pub struct BlockingReader {
    stream: SendableRecordBatchStream,
    runtime: Handle,
    finished: bool,
}
impl BlockingReader {
    /// Wrap an already-created stream without polling it or copying buffers.
    pub fn new(stream: SendableRecordBatchStream, runtime: Handle) -> Self {
        Self {
            stream,
            runtime,
            finished: false,
        }
    }
}
impl Iterator for BlockingReader {
    type Item = Result<RecordBatch, ArrowError>;
    fn next(&mut self) -> Option<Self::Item> {
        if self.finished {
            return None;
        }
        match self.runtime.block_on(self.stream.next()) {
            None => {
                self.finished = true;
                None
            }
            Some(Ok(batch)) => Some(Ok(batch)),
            Some(Err(error)) => {
                self.finished = true;
                Some(Err(ArrowError::ExternalError(Box::new(error))))
            }
        }
    }
}
impl RecordBatchReader for BlockingReader {
    fn schema(&self) -> SchemaRef {
        self.stream.schema()
    }
}
impl std::iter::FusedIterator for BlockingReader {}
