use sail_data_source::formats::orc::OrcListingSessionDefaults;
use sail_data_source::options::parsers::parse_spark_bool;

use super::SparkRuntimeConfig;
use crate::error::{SparkError, SparkResult};
use crate::spark::config::SparkConfigKey;

pub(super) fn parse_merge_schema(value: &str) -> SparkResult<bool> {
    // SQLConf applies Java String.trim (only characters <= U+0020) before
    // Scala's strict boolean parser. Operation options do not trim.
    parse_spark_bool(
        SparkConfigKey::SPARK_SQL_ORC_MERGE_SCHEMA,
        value.trim_matches(|character| character <= '\u{20}'),
    )
    .map_err(|_| {
        SparkError::invalid(format!(
            "{} must be a boolean: {value}",
            SparkConfigKey::SPARK_SQL_ORC_MERGE_SCHEMA
        ))
    })
}

impl SparkRuntimeConfig {
    pub(crate) fn orc_listing_defaults(&self) -> SparkResult<OrcListingSessionDefaults> {
        let merge_schema = self
            .get_option(SparkConfigKey::SPARK_SQL_ORC_MERGE_SCHEMA)
            .map(parse_merge_schema)
            .transpose()?
            .unwrap_or_default();
        Ok(OrcListingSessionDefaults { merge_schema })
    }
}
