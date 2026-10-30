use datafusion::execution::SessionState;
use datafusion::prelude::SessionContext;
use sail_common_datafusion::datasource::OptionLayer;
use sail_common_datafusion::extension::SessionExtensionAccessor;
use sail_data_source::formats::orc::OrcListingSessionDefaults;
use sail_data_source::options::ResolveOptions;
use sail_data_source::options::r#gen::OrcListingReadOptions;

use super::*;
use crate::config::ConfigKeyValue;
use crate::service::{handle_config_set, handle_config_unset};
use crate::spark::config::SparkConfigKey;
use crate::spark::connect::KeyValue;

type TestResult<T = ()> = std::result::Result<T, Box<dyn std::error::Error>>;

const MERGE: &str = SparkConfigKey::SPARK_SQL_ORC_MERGE_SCHEMA;
const SHUFFLE: &str = SparkConfigKey::SPARK_SQL_SHUFFLE_PARTITIONS;

fn spark_session() -> SparkResult<SparkSession> {
    pyo3::Python::initialize();
    SparkSession::try_new(
        "orc-options-test".into(),
        "test-user".into(),
        SparkSessionOptions {
            execution_heartbeat_interval: Duration::from_secs(1),
        },
    )
}

fn context() -> TestResult<SessionContext> {
    Ok(SessionContext::new_with_config(spark_session_config(
        SessionConfig::new(),
        spark_session()?,
    )?))
}

fn pair(key: &str, value: &str) -> KeyValue {
    KeyValue {
        key: key.into(),
        value: Some(value.into()),
    }
}

fn resolved(state: &SessionState) -> TestResult<OrcListingReadOptions> {
    Ok(OrcListingReadOptions::resolve(state, vec![])?)
}

fn assert_effective(ctx: &SessionContext, expected: bool) -> TestResult {
    assert_eq!(
        ctx.extension::<SparkSession>()?
            .orc_listing_defaults()?
            .merge_schema,
        expected
    );
    assert_eq!(
        ctx.extension::<OrcListingSessionDefaults>()?.merge_schema,
        expected
    );
    assert_eq!(resolved(&ctx.state())?.merge_schema, expected);
    Ok(())
}

#[test]
fn creation_reads_effective_spark_defaults() -> TestResult {
    let ctx = context()?;
    assert_effective(&ctx, false)?;

    let spark = spark_session()?;
    spark.set_config(vec![ConfigKeyValue {
        key: MERGE.into(),
        value: Some(" TrUe \t".into()),
    }])?;
    let ctx = SessionContext::new_with_config(spark_session_config(SessionConfig::new(), spark)?);
    assert_effective(&ctx, true)?;
    Ok(())
}

#[test]
fn set_unset_and_operation_override_preserve_prior_read_snapshots() -> TestResult {
    let ctx = context()?;
    let initial_state = ctx.state();
    let initial_defaults = ctx.extension::<OrcListingSessionDefaults>()?;
    let initial_options = resolved(&initial_state)?;

    handle_config_set(&ctx, vec![pair(MERGE, " \tTrUe\n")])?;
    assert_effective(&ctx, true)?;
    let enabled_state = ctx.state();
    let enabled_defaults = ctx.extension::<OrcListingSessionDefaults>()?;
    let enabled_options = resolved(&enabled_state)?;
    assert!(!Arc::ptr_eq(&initial_defaults, &enabled_defaults));

    let operation = OrcListingReadOptions::resolve(
        &enabled_state,
        vec![OptionLayer::OptionList {
            items: vec![("mergeSchema".into(), "false".into())],
        }],
    )?;
    assert!(!operation.merge_schema);
    assert_effective(&ctx, true)?;

    handle_config_unset(&ctx, vec![MERGE.into()])?;
    assert_effective(&ctx, false)?;
    assert!(!initial_defaults.merge_schema);
    assert!(!initial_options.merge_schema);
    assert!(!resolved(&initial_state)?.merge_schema);
    assert!(enabled_defaults.merge_schema);
    assert!(enabled_options.merge_schema);
    assert!(resolved(&enabled_state)?.merge_schema);
    Ok(())
}

#[test]
fn invalid_sql_booleans_fail_before_changing_the_effective_default() -> TestResult {
    let ctx = context()?;
    handle_config_set(&ctx, vec![pair(MERGE, "true")])?;
    for value in [
        "",
        "yes",
        "1",
        "0",
        "true false",
        "\u{a0}true\u{a0}",
        "\u{2003}true\u{2003}",
    ] {
        let error = handle_config_set(&ctx, vec![pair(MERGE, value)]).err();
        assert!(error.is_some());
        let message = error.map(|error| error.to_string()).unwrap_or_default();
        assert!(message.contains(MERGE));
        assert!(message.contains("must be a boolean"));
        assert_effective(&ctx, true)?;
    }
    Ok(())
}

#[test]
fn sql_boolean_trimming_uses_java_control_characters_and_case_rules() -> TestResult {
    let ctx = context()?;
    for (value, expected) in [("\0\u{1f}TrUe\u{1f}\0", true), (" FALſE ", false)] {
        handle_config_set(&ctx, vec![pair(MERGE, value)])?;
        assert_effective(&ctx, expected)?;
    }
    Ok(())
}

#[test]
fn partial_batches_refresh_defaults_and_preserve_the_original_error() -> TestResult {
    for orc_first in [true, false] {
        let ctx = context()?;
        let before = ctx.state();
        let mut values = vec![pair(MERGE, "true"), pair(SHUFFLE, "0")];
        if !orc_first {
            values.reverse();
        }
        let error = handle_config_set(&ctx, values).err();
        assert!(error.is_some());
        let message = error.map(|error| error.to_string()).unwrap_or_default();
        assert!(message.contains("spark.sql.shuffle.partitions must be positive"));
        assert_effective(&ctx, orc_first)?;
        assert!(!resolved(&before)?.merge_schema);
    }
    Ok(())
}

#[test]
fn later_invalid_merge_value_keeps_the_earlier_partial_update() -> TestResult {
    let ctx = context()?;
    let error = handle_config_set(&ctx, vec![pair(MERGE, "true"), pair(MERGE, "invalid")]).err();
    assert!(error.is_some());
    let message = error.map(|error| error.to_string()).unwrap_or_default();
    assert!(message.contains(MERGE));
    assert!(message.contains("invalid"));
    assert_effective(&ctx, true)?;
    handle_config_unset(&ctx, vec![MERGE.into()])?;
    assert_effective(&ctx, false)?;
    Ok(())
}
