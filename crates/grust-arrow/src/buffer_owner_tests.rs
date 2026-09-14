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
