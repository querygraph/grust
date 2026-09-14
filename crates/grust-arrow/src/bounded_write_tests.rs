use super::*;
#[test]
fn sink_limit_rejects_excess_without_extending_the_buffer() {
    let mut writer = ByteLimitWriter::new(Vec::new(), NonZeroUsize::new(3).unwrap());
    writer.write_all(b"abc").unwrap();
    assert_eq!(writer.bytes_written(), 3);
    let error = writer.write_all(b"d").unwrap_err();
    assert!(matches!(
        error.get_ref().and_then(|e| e.downcast_ref::<GrustError>()),
        Some(GrustError::ResourceLimitExceeded {
            resource: "Arrow encoded bytes",
            limit: 3,
            observed: 4
        })
    ));
    assert_eq!(writer.into_inner(), b"abc");
}
