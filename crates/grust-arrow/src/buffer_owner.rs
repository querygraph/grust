//! Attach an owning token to immutable Arrow storage without copying its bytes.
use super::buffer::Buffer;
use std::{panic::RefUnwindSafe, ptr::NonNull, sync::Arc};

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
    T: Send + Sync + RefUnwindSafe + 'static,
{
    let pointer = NonNull::from(buffer.as_slice()).cast::<u8>();
    let length = buffer.len();
    let owner = Arc::new((buffer, owner));
    // SAFETY: pointer/length come from the immutable Buffer moved into owner.
    // Moving its handle does not move its allocation. The owner keeps that
    // allocation alive until all returned clones/slices release it. No mutable
    // access is exposed, and an empty slice supplies a valid non-null pointer
    // for its zero-byte region. Arrow preserves this custom owner on slicing.
    unsafe { Buffer::from_custom_allocation(pointer, length, owner) }
}

#[cfg(test)]
#[path = "buffer_owner_tests.rs"]
mod tests;
