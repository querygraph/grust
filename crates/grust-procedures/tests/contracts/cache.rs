use super::*;

#[test]
fn preparation_cache_initializes_once_and_keeps_retained_storage_admitted() {
    let execution = context(4096);
    let cache = InvocationCache::new(execution.clone());
    let mut calls = 0;
    let first = cache
        .get_or_try_init("provider:snapshot:options", || {
            calls += 1;
            Ok(42u64)
        })
        .unwrap();
    let second = cache
        .get_or_try_init("provider:snapshot:options", || {
            calls += 1;
            Ok(99u64)
        })
        .unwrap();
    assert!(std::ptr::eq(first.as_ref(), second.as_ref()));
    assert_eq!(calls, 1);
    assert!(
        cache
            .get_or_try_init("provider:snapshot:options", || Ok(42u32))
            .is_err()
    );
    let retained = execution.usage().unwrap().live_bytes;
    assert!(
        cache
            .get_or_try_init::<u64>("failure", || Err(ProcedureError::InvalidArguments(
                "failed preparation".into()
            )))
            .is_err()
    );
    assert_eq!(execution.usage().unwrap().live_bytes, retained);
    assert_eq!(*cache.get_or_try_init("failure", || Ok(7u64)).unwrap(), 7);
    drop(cache);
    assert!(execution.usage().unwrap().live_bytes > 0);
    drop(first);
    drop(second);
    assert_eq!(execution.usage().unwrap().live_bytes, 0);
}
