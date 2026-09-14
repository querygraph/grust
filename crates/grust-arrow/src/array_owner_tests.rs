use super::super::array::StringArray;
use super::*;

#[test]
fn sliced_strings_keep_validity_values_and_ownership() {
    let input: ArrayRef = Arc::new(StringArray::from(vec![Some("outside"), None, Some("λ")]));
    let input = input.slice(1, 2);
    let token = Arc::new(());
    let weak = Arc::downgrade(&token);
    let owned = retain_array_owner(&input, token).unwrap();
    assert_eq!(owned.to_data(), input.to_data());
    assert_eq!(
        owned.to_data().buffers()[1].as_ptr(),
        input.to_data().buffers()[1].as_ptr()
    );
    drop(input);
    let child = owned.slice(1, 1);
    drop(owned);
    assert!(weak.upgrade().is_some());
    assert_eq!(
        child
            .as_any()
            .downcast_ref::<StringArray>()
            .unwrap()
            .value(0),
        "λ"
    );
    drop(child);
    assert!(weak.upgrade().is_none());
}
