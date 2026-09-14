//! Byte admission for caller-owned IPC sinks, independent of Arrow version.
use grust_core::GrustError;
use std::{
    io::{self, Write},
    num::NonZeroUsize,
};

/// A writer that rejects a write exceeding the inclusive encoded-byte limit.
/// Earlier bytes remain in the sink on error. A downstream partial write counts
/// only the bytes it accepted; flush delegates to the caller's sink.
pub struct ByteLimitWriter<W> {
    inner: W,
    limit: NonZeroUsize,
    written: usize,
}
impl<W> ByteLimitWriter<W> {
    /// Wrap a sink before encoding so limits apply to schema and payload bytes.
    pub fn new(inner: W, limit: NonZeroUsize) -> Self {
        Self {
            inner,
            limit,
            written: 0,
        }
    }
    /// Bytes actually accepted by the sink.
    pub fn bytes_written(&self) -> usize {
        self.written
    }
    /// Return the sink, including any prefix written before a failure.
    pub fn into_inner(self) -> W {
        self.inner
    }
}
impl<W: Write> Write for ByteLimitWriter<W> {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        let observed = self.written.saturating_add(bytes.len());
        if bytes.len() > self.limit.get() - self.written {
            return Err(io::Error::other(GrustError::ResourceLimitExceeded {
                resource: "Arrow encoded bytes",
                limit: self.limit.get(),
                observed,
            }));
        }
        let accepted = self.inner.write(bytes)?;
        self.written += accepted;
        Ok(accepted)
    }
    fn flush(&mut self) -> io::Result<()> {
        self.inner.flush()
    }
}

#[cfg(test)]
#[path = "bounded_write_tests.rs"]
mod tests;
