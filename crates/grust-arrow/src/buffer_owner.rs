//! Attach an owning token to immutable Arrow storage without copying its bytes.
use super::buffer::Buffer;

/// Retain `owner` until the last clone or slice of the returned buffer is dropped.
/// The original buffer and token move into one allocation owner. Existing clones
/// of the input are not retroactively attached to the token. Obtain any required
/// admission before creating the input allocation; this function only preserves
/// ownership, and does not measure or charge memory.
///
/// Bytes, pointer alignment and slice boundaries are unchanged. Arrow reports
/// this custom allocation's visible length as capacity, not the original backing
/// allocation's capacity. Empty buffers retain the token too.
pub fn retain_buffer_owner<T>(buffer: Buffer, owner: T) -> Buffer
where
    T: Send + 'static,
{
    bytes::Bytes::from_owner(OwnedBuffer {
        buffer,
        _owner: owner,
    })
    .into()
}

struct OwnedBuffer<T> {
    buffer: Buffer,
    _owner: T,
}

impl<T> AsRef<[u8]> for OwnedBuffer<T> {
    fn as_ref(&self) -> &[u8] {
        self.buffer.as_slice()
    }
}

#[cfg(test)]
#[path = "buffer_owner_tests.rs"]
mod tests;
