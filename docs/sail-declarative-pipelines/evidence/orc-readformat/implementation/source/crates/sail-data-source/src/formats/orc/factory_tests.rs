#![expect(clippy::unwrap_used)]

use std::cell::Cell;

use datafusion::prelude::{SessionConfig, SessionContext};
use sail_common::error::CommonError;

use super::*;
use crate::listing::source::ReadFormat;
use crate::options::option_list;

#[test]
fn reader_capture_is_once_and_separate_from_the_captured_display_label() -> Result<()> {
    let calls = Cell::new(0);
    let mut config = SessionConfig::new();
    config.options_mut().execution.time_zone = Some("GMT+8".into());
    let context = SessionContext::new_with_config(config);
    let first = read_with_timezone(
        &context.state(),
        vec![option_list(&[
            ("mergeSchema", "true"),
            ("maxSchemaDepth", "17"),
        ])],
        || {
            calls.set(calls.get() + 1);
            Ok("America/Los_Angeles".into())
        },
    )?;
    assert_eq!(calls.get(), 1);
    assert_eq!(
        first.reader_timezone.reader_timezone(),
        "America/Los_Angeles"
    );
    assert_eq!(first.session_timezone, "+08:00");
    assert!(first.listing_options.merge_schema);
    assert_eq!(first.options.max_schema_depth, 17);
    assert_eq!(first.path_glob_filter(), None);

    let mut config = SessionConfig::new();
    config.options_mut().execution.time_zone = Some("UTC".into());
    let other = SessionContext::new_with_config(config);
    let second = read_with_timezone(&other.state(), vec![], || Ok("UTC".into()))?;
    assert_eq!(second.session_timezone, "UTC");
    assert_eq!(second.reader_timezone.reader_timezone(), "UTC");
    assert_eq!(first.session_timezone, "+08:00");
    assert_eq!(
        first.reader_timezone.reader_timezone(),
        "America/Los_Angeles"
    );
    assert_eq!(calls.get(), 1);
    Ok(())
}

#[test]
fn timezone_capture_failures_keep_their_cause_and_writes_are_explicitly_unsupported() {
    let context = SessionContext::new();
    let error = read_with_timezone(&context.state(), vec![], || {
        Err(CommonError::invalid("host zone lookup failed"))
    })
    .unwrap_err();
    assert!(matches!(error,
        DataFusionError::External(cause)
            if cause.downcast_ref::<CommonError>().is_some()
                && cause.to_string().contains("host zone lookup failed")
    ));
    assert!(matches!(
        OrcFormatFactory::write(&context.state(), vec![]),
        Err(DataFusionError::NotImplemented(message)) if message == "ORC writing is not implemented"
    ));
}
