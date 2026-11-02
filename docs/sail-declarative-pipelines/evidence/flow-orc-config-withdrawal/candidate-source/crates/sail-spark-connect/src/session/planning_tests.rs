use std::sync::Arc;
use std::time::Duration;

use datafusion::arrow::datatypes::DataType;
use datafusion::common::ScalarValue;
use datafusion::logical_expr::{ColumnarValue, Volatility, create_udf};
use datafusion::prelude::{SessionConfig, SessionContext};
use sail_common_datafusion::datasource::OptionLayer;
use sail_common_datafusion::extension::{SessionExtension, SessionExtensionAccessor};
use sail_data_source::formats::orc::{OrcFormatFactory, OrcWriteCompression, OrcWriteConfig};
use sail_data_source::listing::source::FormatFactory;
use sail_data_source::options::ResolveOptions;
use sail_data_source::options::r#gen::OrcListingReadOptions;
use tokio::sync::Barrier;

use super::*;
use crate::service::handle_config_set;
use crate::session::SparkSessionOptions;
use crate::spark::connect::KeyValue;

type TestResult<T = ()> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;

const COMPRESSION: &str = "spark.sql.orc.compression.codec";
const MERGE: &str = "spark.sql.orc.mergeSchema";
const ZONE: &str = "spark.sql.session.timeZone";

struct SharedService;
impl SessionExtension for SharedService {
    fn name() -> &'static str {
        "planning test shared service"
    }
}

fn context() -> TestResult<SessionContext> {
    pyo3::Python::initialize();
    let spark = SparkSession::try_new(
        "planning-test".into(),
        "planning-user".into(),
        SparkSessionOptions {
            execution_heartbeat_interval: Duration::from_secs(1),
        },
    )?;
    let context = SessionContext::new_with_config(
        SessionConfig::new()
            .with_target_partitions(7)
            .with_extension(Arc::new(spark))
            .with_extension(Arc::new(SharedService)),
    );
    set(
        &context,
        &[(COMPRESSION, "snappy"), (MERGE, "false"), (ZONE, "UTC")],
    )?;
    Ok(context)
}

fn set(context: &SessionContext, pairs: &[(&str, &str)]) -> TestResult {
    handle_config_set(
        context,
        pairs
            .iter()
            .map(|(key, value)| KeyValue {
                key: (*key).into(),
                value: Some((*value).into()),
            })
            .collect(),
    )?;
    Ok(())
}

fn overrides(pairs: &[(&str, &str)]) -> Vec<(String, String)> {
    pairs
        .iter()
        .map(|(k, v)| ((*k).into(), (*v).into()))
        .collect()
}

fn effective(context: &SessionContext) -> TestResult<(bool, OrcWriteCompression, String)> {
    let state = context.state();
    Ok((
        OrcListingReadOptions::resolve(&state, vec![])?.merge_schema,
        OrcWriteConfig::resolve(&state, vec![])?.compression,
        state
            .config_options()
            .execution
            .time_zone
            .clone()
            .ok_or("missing timezone")?,
    ))
}

#[test]
fn flow_snapshot_keeps_plan_and_format_settings_consistent_after_session_changes() -> TestResult {
    let parent = context()?;
    let spark = parent.extension::<SparkSession>()?;
    let planning = spark.planning_context(
        &parent,
        overrides(&[
            (COMPRESSION, "zlib"),
            (MERGE, "true"),
            (ZONE, "America/New_York"),
            ("spark.sql.ansi.enabled", "false"),
        ]),
    )?;
    assert!(!planning.config.ansi_mode);
    assert_eq!(
        planning.config.session_timezone.as_ref(),
        "America/New_York"
    );
    assert_eq!(planning.config.session_user_id, "planning-user");
    let expected = (true, OrcWriteCompression::Zlib, "America/New_York".into());
    assert_eq!(effective(&planning.context)?, expected);
    assert_eq!(
        effective(&parent)?,
        (false, OrcWriteCompression::Snappy, "UTC".into())
    );
    set(&parent, &[(COMPRESSION, "lz4"), (ZONE, "Asia/Tokyo")])?;
    let newer = spark.planning_context(&parent, [])?;
    assert_eq!(
        effective(&newer.context)?,
        (false, OrcWriteCompression::Lz4, "Asia/Tokyo".into())
    );
    assert_eq!(effective(&planning.context)?, expected);
    Ok(())
}

#[test]
fn rejected_override_does_not_partially_mutate_the_parent() -> TestResult {
    let parent = context()?;
    let spark = parent.extension::<SparkSession>()?;
    for invalid in [(MERGE, "invalid"), (COMPRESSION, " zstd ")] {
        assert!(
            spark
                .planning_context(&parent, overrides(&[(COMPRESSION, "zlib"), invalid]))
                .is_err()
        );
        assert_eq!(
            effective(&parent)?,
            (false, OrcWriteCompression::Snappy, "UTC".into())
        );
        assert_eq!(
            spark.get_config(vec![COMPRESSION.into()])?[0]
                .value
                .as_deref(),
            Some("snappy")
        );
    }
    Ok(())
}

#[test]
fn planning_state_retains_shared_resources_and_registered_functions() -> TestResult {
    let parent = context()?;
    parent.register_udf(create_udf(
        "planning_identity",
        vec![],
        DataType::Int32,
        Volatility::Immutable,
        Arc::new(|_| Ok(ColumnarValue::Scalar(ScalarValue::Int32(Some(7))))),
    ));
    let planning = parent
        .extension::<SparkSession>()?
        .planning_context(&parent, [])?;
    let child = &planning.context;
    assert_eq!(parent.session_id(), child.session_id());
    assert!(!Arc::ptr_eq(&parent.state_ref(), &child.state_ref()));
    assert!(Arc::ptr_eq(&parent.runtime_env(), &child.runtime_env()));
    assert!(Arc::ptr_eq(
        &parent.extension::<SharedService>()?,
        &child.extension::<SharedService>()?
    ));
    assert!(Arc::ptr_eq(
        &parent.extension::<SparkSession>()?,
        &child.extension::<SparkSession>()?
    ));
    let a = parent.state();
    let b = child.state();
    assert!(Arc::ptr_eq(a.query_planner(), b.query_planner()));
    assert!(Arc::ptr_eq(a.catalog_list(), b.catalog_list()));
    assert!(Arc::ptr_eq(
        a.scalar_functions()
            .get("planning_identity")
            .ok_or("parent UDF absent")?,
        b.scalar_functions()
            .get("planning_identity")
            .ok_or("child UDF absent")?,
    ));
    child
        .state_ref()
        .write()
        .config_mut()
        .options_mut()
        .execution
        .target_partitions = 9;
    assert_eq!(
        parent.state().config_options().execution.target_partitions,
        7
    );
    Ok(())
}

#[tokio::test]
async fn concurrent_flow_format_planning_is_isolated_from_parent_updates() -> TestResult {
    let parent = context()?;
    let ready = Arc::new(Barrier::new(3));
    let release = Arc::new(Barrier::new(3));
    let mut tasks = vec![];
    for (implementation, codec, expected) in [
        ("native", "zlib", OrcWriteCompression::Zlib),
        ("hive", "snappy", OrcWriteCompression::Snappy),
    ] {
        let parent = parent.clone();
        let ready = ready.clone();
        let release = release.clone();
        tasks.push(tokio::spawn(async move {
            let planning = parent.extension::<SparkSession>()?.planning_context(
                &parent,
                overrides(&[("spark.sql.orc.impl", implementation), (COMPRESSION, codec)]),
            )?;
            ready.wait().await;
            release.wait().await;
            let state = planning.context.state();
            let read = OrcFormatFactory::read(&state, vec![]);
            if implementation == "native" {
                read?;
            } else {
                let error = read.err().ok_or("Hive ORC mode was lost")?;
                assert!(error.to_string().contains("Hive ORC reader"));
            }
            assert_eq!(
                OrcWriteConfig::resolve(&state, vec![])?.compression,
                expected
            );
            Ok::<(), Box<dyn std::error::Error + Send + Sync>>(())
        }));
    }
    ready.wait().await;
    set(&parent, &[(COMPRESSION, "lz4"), (MERGE, "true")])?;
    release.wait().await;
    for task in tasks {
        task.await??;
    }
    assert_eq!(
        effective(&parent)?,
        (true, OrcWriteCompression::Lz4, "UTC".into())
    );
    Ok(())
}

#[test]
fn explicit_format_options_override_flow_defaults_after_context_capture() -> TestResult {
    let parent = context()?;
    let planning = parent.extension::<SparkSession>()?.planning_context(
        &parent,
        overrides(&[
            (COMPRESSION, "zlib"),
            (MERGE, "true"),
            ("orc.force.positional.evolution", "true"),
        ]),
    )?;
    let state = planning.context.state();
    assert!(OrcFormatFactory::read(&state, vec![]).is_err());
    let layer = OptionLayer::OptionList {
        items: overrides(&[
            ("mergeSchema", "false"),
            ("orc.force.positional.evolution", "false"),
        ]),
    };
    assert!(!OrcListingReadOptions::resolve(&state, vec![layer.clone()])?.merge_schema);
    OrcFormatFactory::read(&state, vec![layer])?;
    let codec = OrcWriteConfig::resolve(
        &state,
        vec![OptionLayer::OptionList {
            items: overrides(&[("compression", "none")]),
        }],
    )?;
    assert_eq!(codec.compression, OrcWriteCompression::None);
    assert_eq!(
        effective(&parent)?,
        (false, OrcWriteCompression::Snappy, "UTC".into())
    );
    Ok(())
}
