use std::sync::Arc;

use async_trait::async_trait;
use datafusion::catalog::Session;
use datafusion::physical_plan::ExecutionPlan;
use datafusion_common::{DataFusionError, Result, not_impl_err};
use sail_common::error::CommonResult;
use sail_common::utils::datetime::get_system_timezone;
use sail_common_datafusion::datasource::OptionLayer;
use sail_common_datafusion::utils::datetime::arrow_timezone_label;

use super::{OrcJavaTimeZoneConfig, OrcReadFormat};
use crate::listing::source::{FormatFactory, ListingDataSource, ListingSinkInput, WriteFormat};
use crate::options::ResolveOptions;
use crate::options::r#gen::{OrcListingReadOptions, OrcReadOptions};

pub type OrcDataSource = ListingDataSource<OrcFormatFactory>;

#[derive(Debug, Default)]
pub struct OrcFormatFactory;

impl FormatFactory for OrcFormatFactory {
    type Read = OrcReadFormat;
    type Write = OrcWriteFormat;

    fn name() -> &'static str {
        "orc"
    }

    fn read(ctx: &dyn Session, options: Vec<OptionLayer>) -> Result<Self::Read> {
        read_with_timezone(ctx, options, get_system_timezone)
    }

    fn write(_ctx: &dyn Session, _options: Vec<OptionLayer>) -> Result<Self::Write> {
        not_impl_err!("ORC writing is not implemented")
    }
}

fn read_with_timezone(
    ctx: &dyn Session,
    options: Vec<OptionLayer>,
    timezone: impl FnOnce() -> CommonResult<String>,
) -> Result<OrcReadFormat> {
    let resource_options = OrcReadOptions::resolve(ctx, options.clone())?;
    let listing_options = OrcListingReadOptions::resolve(ctx, options)?;
    // This is Sail's host IANA-zone capture policy, not a JVM-default lookup.
    // Neither later session display changes nor workers recapture this value.
    let reader_timezone = OrcJavaTimeZoneConfig::for_reader_timezone(
        timezone().map_err(|error| DataFusionError::External(Box::new(error)))?,
    )?;
    let session_timezone = arrow_timezone_label(
        ctx.config_options()
            .execution
            .time_zone
            .as_deref()
            .unwrap_or("UTC"),
    )
    .into_owned();
    Ok(OrcReadFormat {
        options: resource_options,
        listing_options,
        reader_timezone,
        session_timezone,
    })
}

/// The factory rejects writes before constructing a sink.
#[derive(Debug)]
pub struct OrcWriteFormat;

#[async_trait]
impl WriteFormat for OrcWriteFormat {
    async fn sink(
        &self,
        _ctx: &dyn Session,
        _input: ListingSinkInput,
    ) -> Result<Arc<dyn ExecutionPlan>> {
        not_impl_err!("ORC writing is not implemented")
    }
}

#[cfg(test)]
#[path = "factory_tests.rs"]
mod tests;
