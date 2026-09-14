use super::*;

#[test]
fn token_and_storage_survive_cloning_slicing_and_original_drop() {
    let token = Arc::new(());
    let weak = Arc::downgrade(&token);
    let original = Buffer::from_vec(vec![1_u64, 2, 3]);
    let input = original.slice_with_length(8, 8);
    let pointer = input.as_ptr();
    let retained = retain_buffer_owner(input, token);
    assert_eq!(retained.as_ptr(), pointer);
    assert_eq!(retained.as_slice(), 2_u64.to_ne_bytes());
    let sliced = retained.slice_with_length(0, 8);
    drop(original);
    drop(retained);
    assert!(weak.upgrade().is_some());
    assert_eq!(sliced.as_slice(), 2_u64.to_ne_bytes());
    drop(sliced);
    assert!(weak.upgrade().is_none());
}

#[test]
fn empty_buffers_still_retain_the_owner() {
    let token = Arc::new(());
    let weak = Arc::downgrade(&token);
    let retained = retain_buffer_owner(Buffer::from_vec(Vec::<u64>::new()), token);
    let clone = retained.clone();
    drop(retained);
    assert!(weak.upgrade().is_some());
    assert!(clone.is_empty());
    drop(clone);
    assert!(weak.upgrade().is_none());
}

#[test]
fn native_array_slice_retains_owner_after_parent_drop() {
    use super::super::{array::UInt64Array, buffer::ScalarBuffer};
    let token = Arc::new(());
    let weak = Arc::downgrade(&token);
    let buffer = retain_buffer_owner(Buffer::from_vec(vec![7_u64, 11, 13]), token);
    let array = UInt64Array::new(ScalarBuffer::new(buffer, 0, 3), None);
    let slice = array.slice(1, 1);
    drop(array);
    assert!(weak.upgrade().is_some());
    assert_eq!(slice.value(0), 11);
    drop(slice);
    assert!(weak.upgrade().is_none());
}

#[cfg(feature = "ffi")]
#[test]
fn c_data_export_retains_owner_until_release() {
    use super::super::{
        array::{Array, UInt64Array, ffi::to_ffi},
        buffer::ScalarBuffer,
    };
    let token = Arc::new(());
    let weak = Arc::downgrade(&token);
    let buffer = retain_buffer_owner(Buffer::from_vec(vec![7_u64, 11]), token);
    let array = UInt64Array::new(ScalarBuffer::new(buffer, 0, 2), None);
    let (exported, schema) = to_ffi(&array.to_data()).unwrap();
    drop(array);
    assert!(weak.upgrade().is_some());
    drop(schema);
    assert!(weak.upgrade().is_some());
    drop(exported);
    assert!(weak.upgrade().is_none());
}

#[test]
fn custom_owner_cannot_be_detached_by_mutable_conversion() {
    let token = Arc::new(());
    let weak = Arc::downgrade(&token);
    let buffer = retain_buffer_owner(Buffer::from_vec(vec![1_u64]), token);
    let buffer = buffer
        .into_mutable()
        .expect_err("custom storage stays immutable");
    assert!(weak.upgrade().is_some());
    assert_eq!(buffer.as_slice(), 1_u64.to_ne_bytes());
    drop(buffer);
    assert!(weak.upgrade().is_none());
}
