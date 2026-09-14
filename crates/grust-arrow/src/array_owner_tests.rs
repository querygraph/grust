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

#[test]
fn nested_list_child_keeps_owner_after_all_parents_drop() {
    use super::super::array::{
        LargeListArray,
        builder::{LargeListBuilder, StringBuilder},
    };
    let mut builder = LargeListBuilder::new(StringBuilder::new());
    builder.values().append_value("first");
    builder.values().append_null();
    builder.append(true);
    builder.values().append_value("last");
    builder.append(true);
    let input: ArrayRef = Arc::new(builder.finish());
    let token = Arc::new(());
    let weak = Arc::downgrade(&token);
    let owned = retain_array_owner(&input, token).unwrap();
    assert_eq!(input.to_data(), owned.to_data());
    let child = owned
        .as_any()
        .downcast_ref::<LargeListArray>()
        .unwrap()
        .value(0);
    drop(input);
    drop(owned);
    assert!(weak.upgrade().is_some());
    assert_eq!(
        child
            .as_any()
            .downcast_ref::<StringArray>()
            .unwrap()
            .value(0),
        "first"
    );
    drop(child);
    assert!(weak.upgrade().is_none());
}

#[cfg(feature = "ffi")]
#[test]
fn exported_array_holds_owner_until_c_data_release() {
    use super::super::array::ffi::to_ffi;
    let input: ArrayRef = Arc::new(StringArray::from(vec![Some("λ"), None]));
    let token = Arc::new(());
    let weak = Arc::downgrade(&token);
    let owned = retain_array_owner(&input, token).unwrap();
    let (exported, schema) = to_ffi(&owned.to_data()).unwrap();
    drop(input);
    drop(owned);
    assert!(weak.upgrade().is_some());
    drop(schema);
    assert!(weak.upgrade().is_some());
    drop(exported);
    assert!(weak.upgrade().is_none());
}
