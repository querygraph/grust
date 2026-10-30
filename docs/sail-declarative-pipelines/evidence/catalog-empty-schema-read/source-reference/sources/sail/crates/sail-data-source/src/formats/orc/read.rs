use std::sync::Arc;

use async_trait::async_trait;
use datafusion::arrow::datatypes::{Schema, SchemaRef};
use datafusion::catalog::Session;
use datafusion_common::parsers::CompressionTypeVariant;
use datafusion_common::{DataFusionError, Result, not_impl_err, plan_err};
use datafusion_datasource::file_scan_config::{FileScanConfig, FileScanConfigBuilder};
use orc_rust::reader::metadata::read_metadata_async_with_options;
use sail_common_datafusion::column_change::validate_field_names;
use sail_common_datafusion::schema_merge::merge_spark_file_schemas;

use super::{OrcJavaTimeZoneConfig, OrcObjectReader, OrcRequestedSchemaAdapter, OrcSource};
use crate::listing::source::{
    ListingFileSample, ListingFileSelection, ListingScanInput, PreparedExplicitSchema, ReadFormat,
};
use crate::options::r#gen::{OrcListingReadOptions, OrcReadOptions};

/// Ordinary listing reads with a captured reader zone and display label.
///
/// Inference and execution each use their listed object identities. Execution
/// uses the shared listing/cache again; this does not establish a snapshot
/// spanning schema inference and execution.
#[derive(Debug, Clone)]
pub struct OrcReadFormat {
    pub(super) options: OrcReadOptions,
    pub(super) listing_options: OrcListingReadOptions,
    pub(super) reader_timezone: OrcJavaTimeZoneConfig,
    pub(super) session_timezone: String,
}

fn check_compression(compression: CompressionTypeVariant) -> Result<()> {
    if compression != CompressionTypeVariant::UNCOMPRESSED {
        return not_impl_err!("ORC reads do not support outer file compression");
    }
    Ok(())
}

#[async_trait]
impl ReadFormat for OrcReadFormat {
    fn schema_inference_file_selection(&self) -> ListingFileSelection {
        // Even without schema merging, the first usable root may be beyond
        // the default ten samples. Partition inference uses this same inventory.
        ListingFileSelection::All
    }

    async fn infer_compression(
        &self,
        _ctx: &dyn Session,
        _files: &[ListingFileSample<'_>],
    ) -> Result<CompressionTypeVariant> {
        // ORC records its internal compression in the postscript.
        Ok(CompressionTypeVariant::UNCOMPRESSED)
    }

    async fn infer_schema(
        &self,
        ctx: &dyn Session,
        files: &[ListingFileSample<'_>],
        compression: CompressionTypeVariant,
        read_case_sensitive: bool,
    ) -> Result<SchemaRef> {
        check_compression(compression)?;
        let pool = ctx.runtime_env().memory_pool.clone();
        let limits = self.options.resource_limits(pool.as_ref());
        let mut schema: Option<(SchemaRef, &object_store::path::Path)> = None;
        for group in files {
            for object in &group.objects {
                let context = |error: DataFusionError| {
                    DataFusionError::Context(
                        format!("inferring ORC schema from {}", object.location),
                        Box::new(error),
                    )
                };
                let mut reader =
                    OrcObjectReader::new(group.store.clone(), object.clone(), pool.clone());
                let metadata =
                    read_metadata_async_with_options(&mut reader, limits.metadata_options())
                        .await
                        .map_err(|error| context(DataFusionError::External(Box::new(error))))?;
                let next =
                    super::infer_orc_schema(&metadata, &self.session_timezone).map_err(context)?;
                if next.fields().is_empty() {
                    continue;
                }
                let merged = match schema {
                    Some((previous, _)) => Arc::new(
                        merge_spark_file_schemas(&previous, &next, read_case_sensitive)
                            .map_err(context)?,
                    ),
                    None => next,
                };
                if !self.listing_options.merge_schema {
                    validate_field_names(merged.fields(), read_case_sensitive).map_err(context)?;
                    return Ok(merged);
                }
                schema = Some((merged, &object.location));
            }
        }
        let Some((schema, last_schema_path)) = schema else {
            return plan_err!("Unable to infer ORC schema: no nonempty physical schema found");
        };
        // Merging may introduce duplicate nested names even when root fields
        // matched case-insensitively. Validate the final relation recursively.
        validate_field_names(schema.fields(), read_case_sensitive).map_err(|error| {
            DataFusionError::Context(
                format!("validating merged ORC schema through {last_schema_path}"),
                Box::new(error),
            )
        })?;
        Ok(schema)
    }

    async fn prepare_explicit_schema(
        &self,
        _ctx: &dyn Session,
        schema: Schema,
        _files: &[ListingFileSample<'_>],
        compression: CompressionTypeVariant,
        _read_case_sensitive: bool,
    ) -> Result<Option<PreparedExplicitSchema>> {
        check_compression(compression)?;
        Ok(Some(PreparedExplicitSchema {
            schema: OrcRequestedSchemaAdapter::nullable_schema(&schema)
                .as_ref()
                .clone(),
            physical: None,
        }))
    }

    async fn scan(&self, ctx: &dyn Session, input: ListingScanInput) -> Result<FileScanConfig> {
        check_compression(input.compression)?;
        let source = OrcSource::try_new(
            input.schema,
            self.options.clone(),
            self.reader_timezone.clone(),
            self.session_timezone.clone(),
            input.read_case_sensitive,
            ctx.runtime_env().memory_pool.clone(),
        )?;
        Ok(
            FileScanConfigBuilder::new(input.object_store_url, Arc::new(source))
                .with_file_groups(input.file_groups)
                .with_constraints(input.constraints)
                .with_statistics(input.statistics)
                .with_projection_indices(input.projection)?
                .with_limit(input.limit)
                .with_output_ordering(input.output_ordering)
                .with_preserve_order(input.preserve_order)
                .with_output_partitioning(input.output_partitioning)
                .build(),
        )
    }

    fn path_glob_filter(&self) -> Option<&str> {
        self.listing_options.path_glob_filter.as_deref()
    }
}

#[cfg(test)]
#[path = "read_tests.rs"]
mod tests;
