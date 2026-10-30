use datafusion::execution::SessionState;
use datafusion::prelude::SessionContext;
use sail_common_datafusion::datasource::OptionLayer;
use sail_common_datafusion::extension::SessionExtensionAccessor;
use sail_data_source::error::{DataSourceError, DataSourceResult};
use sail_data_source::formats::orc::OrcReadSessionModes;
use sail_data_source::options::ResolveOptions;
use sail_data_source::options::r#gen::{JsonReadOptions, OrcListingReadOptions};

use super::*;
use crate::config::ConfigKeyValue;
use crate::service::{handle_config_set, handle_config_unset};
use crate::spark::config::SparkConfigKey;
use crate::spark::connect::KeyValue;

type TestResult<T = ()> = std::result::Result<T, Box<dyn std::error::Error>>;

const IMPL: &str = SparkConfigKey::SPARK_SQL_ORC_IMPL;
const FORCE: &str = "orc.force.positional.evolution";
const SHUFFLE: &str = SparkConfigKey::SPARK_SQL_SHUFFLE_PARTITIONS;

fn context(settings: &[(&str, &str)]) -> TestResult<SessionContext> {
    pyo3::Python::initialize();
    let spark = SparkSession::try_new(
        "orc-modes-test".into(),
        "test-user".into(),
        SparkSessionOptions {
            execution_heartbeat_interval: Duration::from_secs(1),
        },
    )?;
    spark.set_config(
        settings
            .iter()
            .map(|(key, value)| ConfigKeyValue {
                key: (*key).into(),
                value: Some((*value).into()),
            })
            .collect(),
    )?;
    Ok(SessionContext::new_with_config(spark_session_config(
        SessionConfig::new(),
        spark,
    )?))
}

fn pair(key: &str, value: &str) -> KeyValue {
    KeyValue {
        key: key.into(),
        value: Some(value.into()),
    }
}

fn read_options(state: &SessionState) -> DataSourceResult<OrcListingReadOptions> {
    OrcListingReadOptions::resolve(state, vec![])
}

#[test]
fn creation_retains_modes_until_an_orc_read_requests_them() -> TestResult {
    for settings in [
        [(IMPL, "hive"), (FORCE, "false")],
        [(IMPL, "native"), (FORCE, "TrUe")],
    ] {
        let ctx = context(&settings)?;
        assert!(read_options(&ctx.state()).is_err());
        JsonReadOptions::resolve(&ctx.state(), vec![])?;
    }
    let ctx = context(&[])?;
    assert_eq!(
        *ctx.extension::<OrcReadSessionModes>()?,
        OrcReadSessionModes::default()
    );
    read_options(&ctx.state())?;
    Ok(())
}

#[test]
fn set_unset_modes_preserve_old_snapshots_and_unrelated_reads() -> TestResult {
    let ctx = context(&[])?;
    let native = ctx.state();
    handle_config_set(&ctx, vec![pair(IMPL, "hive")])?;
    let hive = ctx.state();
    let hive_modes = ctx.extension::<OrcReadSessionModes>()?;
    assert!(read_options(&hive).is_err());
    read_options(&native)?;
    JsonReadOptions::resolve(&hive, vec![])?;

    handle_config_unset(&ctx, vec![IMPL.into()])?;
    read_options(&ctx.state())?;
    assert_eq!(hive_modes.implementation, "hive");
    assert!(read_options(&hive).is_err());

    handle_config_set(&ctx, vec![pair(IMPL, "Native")])?;
    assert!(matches!(read_options(&ctx.state()),
        Err(DataSourceError::InvalidOption { key, value, .. })
            if key == IMPL && value == "Native"
    ));
    JsonReadOptions::resolve(&ctx.state(), vec![])?;
    handle_config_unset(&ctx, vec![IMPL.into()])?;
    read_options(&ctx.state())?;
    Ok(())
}

#[test]
fn exact_session_key_and_case_insensitive_read_override_follow_hadoop_handoff() -> TestResult {
    let ctx = context(&[])?;
    handle_config_set(
        &ctx,
        vec![
            pair("ORC.FORCE.POSITIONAL.EVOLUTION", "true"),
            pair("spark.hadoop.orc.force.positional.evolution", "true"),
        ],
    )?;
    read_options(&ctx.state())?;
    handle_config_set(&ctx, vec![pair(FORCE, "TrUe")])?;
    let forced = ctx.state();
    assert!(read_options(&forced).is_err());
    OrcListingReadOptions::resolve(
        &forced,
        vec![OptionLayer::OptionList {
            items: vec![("ORC.FORCE.POSITIONAL.EVOLUTION".into(), "false".into())],
        }],
    )?;
    for value in [" true ", "yes", "1", "false"] {
        handle_config_set(&ctx, vec![pair(FORCE, value)])?;
        read_options(&ctx.state())?;
    }
    handle_config_unset(&ctx, vec![FORCE.into()])?;
    read_options(&ctx.state())?;
    assert!(read_options(&forced).is_err());
    Ok(())
}

#[test]
fn partial_mode_batches_refresh_the_snapshot_and_return_original_errors() -> TestResult {
    for mode in [pair(IMPL, "hive"), pair(FORCE, "true")] {
        for mode_first in [true, false] {
            let ctx = context(&[])?;
            let mut values = vec![mode.clone(), pair(SHUFFLE, "0")];
            if !mode_first {
                values.reverse();
            }
            let error = handle_config_set(&ctx, values)
                .err()
                .ok_or("expected the unrelated invalid configuration error")?;
            assert!(
                error
                    .to_string()
                    .contains("spark.sql.shuffle.partitions must be positive")
            );
            assert_eq!(read_options(&ctx.state()).is_err(), mode_first);
            JsonReadOptions::resolve(&ctx.state(), vec![])?;
        }
    }
    Ok(())
}
