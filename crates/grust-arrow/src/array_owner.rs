//! Ownership propagation through nested native array storage.
use super::{
    array::{ArrayRef, make_array},
    buffer::{BooleanBuffer, NullBuffer},
    data::ArrayData,
    retain_buffer_owner,
    schema::ArrowError,
};
use std::sync::Arc;

/// Attach a shared token to every physical buffer, including nested children and
/// validity bits, without copying payload bytes. Independent clones made before
/// attachment do not acquire the token. Arrays with no buffers retain no token;
/// keep a separate owner if metadata-only lifetime must also remain admitted.
/// Array metadata is rebuilt and validated; this does not reserve allocations.
pub fn retain_array_owner<T: Send + Sync + 'static>(
    array: &ArrayRef,
    owner: Arc<T>,
) -> Result<ArrayRef, ArrowError> {
    owned_data(array.to_data(), &owner).map(make_array)
}

fn owned_data<T: Send + Sync + 'static>(
    data: ArrayData,
    owner: &Arc<T>,
) -> Result<ArrayData, ArrowError> {
    let (kind, len, nulls, offset, buffers, children) = data.into_parts();
    let nulls = nulls.map(|nulls| {
        let bits = nulls.into_inner();
        let offset = bits.offset();
        let len = bits.len();
        NullBuffer::new(BooleanBuffer::new(
            retain_buffer_owner(bits.into_inner(), Arc::clone(owner)),
            offset,
            len,
        ))
    });
    let buffers = buffers
        .into_iter()
        .map(|buffer| retain_buffer_owner(buffer, Arc::clone(owner)))
        .collect();
    let children = children
        .into_iter()
        .map(|child| owned_data(child, owner))
        .collect::<Result<Vec<_>, _>>()?;
    ArrayData::builder(kind)
        .len(len)
        .offset(offset)
        .nulls(nulls)
        .buffers(buffers)
        .child_data(children)
        .build()
}

#[cfg(test)]
#[path = "array_owner_tests.rs"]
mod tests;
