use std::fmt::Debug;
use std::marker::PhantomData;
use std::sync::Arc;

use async_trait::async_trait;
#[cfg(test)]
use datafusion::arrow::datatypes::{DataType, Field};
use datafusion::arrow::datatypes::{Schema, SchemaRef};
use datafusion::catalog::Session;
use datafusion::datasource::physical_plan::FileSinkConfig;
use datafusion::execution::object_store::ObjectStoreUrl;
use datafusion::logical_expr::{Extension, LogicalPlan, LogicalPlanBuilder, TableSource};
use datafusion::physical_expr::{LexRequirement, Partitioning};
use datafusion::physical_expr_common::sort_expr::LexOrdering;
use datafusion::physical_plan::ExecutionPlan;
use datafusion_common::parsers::CompressionTypeVariant;
use datafusion_common::{Result, Statistics, not_impl_err, plan_err};
use datafusion_datasource::file_groups::FileGroup;
use datafusion_datasource::file_scan_config::FileScanConfig;
use datafusion_datasource::{ListingTableUrl, TableSchema};
use futures::TryStreamExt;
use object_store::{ObjectMeta, ObjectStore};
use sail_common_datafusion::datasource::{
    DataSource, OptionLayer, SinkInfo, SinkMode, SourceInfo, find_path_in_options,
};
use url::Url;

use crate::listing::partition::{
    inferred_partition_fields, partition_directory_names, prepare_explicit_partitions,
};
use crate::listing::table::{ListingTableSource, ListingTableSourceConfig};
use crate::listing::utils::{
    infer_partitions, rewrite_unsupported_fields, select_listing_files,
    validate_partition_directory_names,
};
use crate::listing::write::{FileWriteNode, FileWriteOptions};
use crate::resolve_listing_urls;
use crate::url::{PathGlobFilter, resolve_listing_writer_url};

/// A trait for creating format instances when reading and writing listing files.
pub trait FormatFactory: Debug + Send + Sync + 'static {
    type Read: ReadFormat;
    type Write: WriteFormat;

    /// The name of the format.
    fn name() -> &'static str;

    /// Creates the read format.
    fn read(ctx: &dyn Session, options: Vec<OptionLayer>) -> Result<Self::Read>;

    /// Creates the write format.
    fn write(ctx: &dyn Session, options: Vec<OptionLayer>) -> Result<Self::Write>;
}

/// A trait for format-specific logic for reading listing files.
#[async_trait]
pub trait ReadFormat: Debug + Send + Sync + 'static {
    /// Select files supplied to schema, compression, and partition inference.
    /// Formats retain the first-ten-nonempty-files-per-URL default unless they opt in.
    fn schema_inference_file_selection(&self) -> ListingFileSelection {
        ListingFileSelection::Sample
    }

    async fn infer_compression(
        &self,
        ctx: &dyn Session,
        files: &[ListingFileSample<'_>],
    ) -> Result<CompressionTypeVariant>;

    /// Infer the file schema from the given files.
    ///
    /// `read_case_sensitive` is the policy captured in [`SourceInfo`] for this
    /// read. Formats that use it must not derive it from SQL identifier
    /// normalization or other session settings.
    async fn infer_schema(
        &self,
        ctx: &dyn Session,
        files: &[ListingFileSample<'_>],
        compression: CompressionTypeVariant,
        read_case_sensitive: bool,
    ) -> Result<SchemaRef>;

    /// Prepare a supplied schema before partition columns are separated.
    ///
    /// The default retains legacy name reconciliation and physical-schema
    /// inference. An empty schema returns `None`, requesting ordinary inference.
    /// Formats can instead retain an explicit schema (including an empty one)
    /// and defer per-file compatibility checks by returning `Some` without a
    /// physical schema. This hook is not called when no schema was supplied.
    async fn prepare_explicit_schema(
        &self,
        ctx: &dyn Session,
        schema: Schema,
        files: &[ListingFileSample<'_>],
        compression: CompressionTypeVariant,
        read_case_sensitive: bool,
    ) -> Result<Option<PreparedExplicitSchema>> {
        if schema.fields().is_empty() {
            return Ok(None);
        }
        let physical = if self.requires_explicit_schema_validation() {
            Some(
                self.infer_schema(ctx, files, compression, read_case_sensitive)
                    .await?,
            )
        } else if read_case_sensitive {
            None
        } else {
            self.infer_schema(ctx, files, compression, read_case_sensitive)
                .await
                .ok()
        };
        // Reconcile names so readers and file statistics that resolve columns
        // by exact name can find the requested case-insensitive columns.
        let schema = if read_case_sensitive {
            schema
        } else if let Some(physical) = &physical {
            reconcile_schema_names_case_insensitive(schema, physical)?
        } else {
            // Keep the user schema when optional physical inference fails.
            schema
        };
        Ok(Some(PreparedExplicitSchema { schema, physical }))
    }

    /// Infer file-level metadata needed for planning.
    /// The metadata includes statistics and ordering.
    async fn infer_file_meta(
        &self,
        ctx: &dyn Session,
        store: &Arc<dyn ObjectStore>,
        object: &ObjectMeta,
        file_schema: SchemaRef,
        compression: CompressionTypeVariant,
    ) -> Result<ListingFileMeta> {
        let _ = (ctx, store, object, compression);
        Ok(ListingFileMeta {
            statistics: Statistics::new_unknown(&file_schema),
            ordering: None,
        })
    }

    /// Build a scan configuration for listing reads.
    async fn scan(&self, ctx: &dyn Session, input: ListingScanInput) -> Result<FileScanConfig>;

    /// Whether validating an explicit schema requires the physical file schema.
    fn requires_explicit_schema_validation(&self) -> bool {
        false
    }

    /// Validate a user-provided file schema against the physical file schema.
    fn validate_explicit_schema(&self, _schema: &Schema, _physical: &Schema) -> Result<()> {
        Ok(())
    }

    /// File-name glob restricting which listed files compose the dataset.
    fn path_glob_filter(&self) -> Option<&str> {
        None
    }
}

/// Which eligible, nonempty objects are supplied to listing inference.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ListingFileSelection {
    /// The first ten nonempty files per URL in the existing listing order.
    Sample,
    /// All nonempty files, sorted by location within each URL's group.
    /// Input URL order and complete object metadata are retained. This collects
    /// all eligible objects in memory and also broadens compression and partition
    /// inference and partition validation to those files.
    All,
}

#[derive(Debug)]
pub struct ListingFileSample<'a> {
    pub url: &'a ListingTableUrl,
    pub store: Arc<dyn ObjectStore>,
    pub objects: Vec<ObjectMeta>,
}

/// A format's supplied schema before partition-column extraction.
#[derive(Debug)]
pub struct PreparedExplicitSchema {
    /// Logical schema, including any supplied directory partition columns.
    pub schema: Schema,
    /// When present, validate the remaining file schema against this physical
    /// schema after partition-column extraction.
    pub physical: Option<SchemaRef>,
}

#[derive(Debug, Clone)]
pub struct ListingFileMeta {
    pub statistics: Statistics,
    pub ordering: Option<LexOrdering>,
}

#[derive(Debug)]
pub struct ListingScanInput {
    pub object_store_url: ObjectStoreUrl,
    pub file_groups: Vec<FileGroup>,
    pub constraints: datafusion_common::Constraints,
    pub projection: Option<Vec<usize>>,
    pub limit: Option<usize>,
    pub preserve_order: bool,
    pub output_ordering: Vec<LexOrdering>,
    pub statistics: Statistics,
    pub output_partitioning: Option<Partitioning>,
    pub schema: TableSchema,
    pub compression: CompressionTypeVariant,
    /// Whether this read matches requested columns against file schemas by exact case.
    pub read_case_sensitive: bool,
}

/// Configuration for creating a listing-file sink execution plan.
pub struct ListingSinkInput {
    pub input: Arc<dyn ExecutionPlan>,
    pub sink: FileSinkConfig,
    pub sort_order: Option<LexRequirement>,
}

/// A trait for format-specific logic for writing listing files.
#[async_trait]
pub trait WriteFormat: Debug + Send + Sync + 'static {
    async fn sink(
        &self,
        ctx: &dyn Session,
        input: ListingSinkInput,
    ) -> Result<Arc<dyn ExecutionPlan>>;
}

#[derive(Debug, Default)]
pub struct ListingDataSource<T: FormatFactory> {
    phantom: PhantomData<T>,
}

#[async_trait]
impl<T: FormatFactory> DataSource for ListingDataSource<T> {
    fn name(&self) -> &str {
        T::name()
    }

    async fn create_source(
        &self,
        ctx: &dyn Session,
        info: SourceInfo,
    ) -> Result<Arc<dyn TableSource>> {
        let SourceInfo {
            paths,
            lakehouse_table: _,
            schema,
            constraints,
            partition_by,
            bucket_by: _,
            sort_order,
            options,
            read_case_sensitive,
        } = info;

        let read_format = T::read(ctx, options)?;
        let path_glob_filter = read_format
            .path_glob_filter()
            .map(PathGlobFilter::parse)
            .transpose()?;
        let urls = resolve_listing_urls(ctx, paths).await?;
        let inference_files = select_listing_files(
            ctx,
            &urls,
            path_glob_filter.as_ref(),
            read_format.schema_inference_file_selection(),
        )
        .await?;
        let compression = read_format.infer_compression(ctx, &inference_files).await?;

        let prepared = match schema {
            Some(schema) => {
                read_format
                    .prepare_explicit_schema(
                        ctx,
                        schema,
                        &inference_files,
                        compression,
                        read_case_sensitive,
                    )
                    .await?
            }
            None => None,
        };
        let (schema, partition_fields, discovered_partitions) = match prepared {
            Some(PreparedExplicitSchema { schema, physical }) => {
                let discovered_partitions = infer_partitions(&inference_files)?;
                let (schema, partition_fields) = prepare_explicit_partitions(
                    &schema,
                    &discovered_partitions,
                    &partition_by,
                    read_case_sensitive,
                )?;
                if let Some(physical) = physical {
                    read_format.validate_explicit_schema(&schema, &physical)?;
                }
                (Arc::new(schema), partition_fields, discovered_partitions)
            }
            None => {
                let schema = read_format
                    .infer_schema(ctx, &inference_files, compression, read_case_sensitive)
                    .await?;
                let schema = rewrite_unsupported_fields(schema);

                let discovered_partitions = infer_partitions(&inference_files)?;
                // With no prepared supplied schema, Spark uses all discovered
                // partitions even when explicit selectors were provided.
                let partition_fields = inferred_partition_fields(&discovered_partitions);
                (schema, partition_fields, discovered_partitions)
            }
        };

        let partition_directory_names =
            partition_directory_names(&partition_fields, &discovered_partitions)?;
        validate_partition_directory_names(&inference_files, &partition_directory_names)?;

        let source = ListingTableSource::try_new(ListingTableSourceConfig {
            table_paths: urls,
            schema: TableSchema::builder(schema)
                .with_table_partition_cols(partition_fields)
                .build(),
            partition_directory_names,
            constraints,
            file_sort_order: vec![sort_order],
            collect_stat: ctx.config().collect_statistics(),
            target_partitions: ctx.config().target_partitions(),
            read_format: Arc::new(read_format),
            path_glob_filter,
            compression,
            read_case_sensitive,
        })?;
        Ok(Arc::new(source))
    }

    async fn create_writer(&self, ctx: &dyn Session, info: SinkInfo) -> Result<LogicalPlan> {
        let Some(path) = find_path_in_options(&info.options) else {
            return plan_err!("missing path in listing table options");
        };
        let SinkInfo {
            input,
            mode,
            partition_by,
            bucket_by,
            sort_order,
            options,
            lakehouse_table,
        } = info;
        let catalog_managed = lakehouse_table.is_some();
        if bucket_by.is_some() {
            return not_impl_err!("bucketing for writing listing data source");
        }
        if partition_by.iter().any(|field| field.transform.is_some()) {
            return not_impl_err!("partition transforms for writing listing data source");
        }
        let url = resolve_listing_writer_url(path.clone())?;
        let overwrite = match mode {
            SinkMode::ErrorIfExists => {
                if (!catalog_managed && listing_target_exists(ctx, &url).await?)
                    || (catalog_managed && listing_target_nonempty(ctx, &url).await?)
                {
                    return plan_err!("listing table path already exists: {path}");
                }
                false
            }
            SinkMode::IgnoreIfExists => {
                if listing_target_exists(ctx, &url).await? {
                    return LogicalPlanBuilder::empty(false).build();
                }
                false
            }
            SinkMode::Append => false,
            SinkMode::Overwrite => true,
            mode => return not_impl_err!("unsupported sink mode for listing table: {mode:?}"),
        };
        let write_format = T::write(ctx, options)?;
        Ok(LogicalPlan::Extension(Extension {
            node: Arc::new(FileWriteNode::new(
                Arc::new(input),
                FileWriteOptions {
                    format: Arc::new(write_format),
                    url,
                    overwrite,
                    partition_by,
                    sort_by: sort_order,
                },
            )),
        }))
    }
}
async fn listing_target_exists(ctx: &dyn Session, url: &Url) -> Result<bool> {
    // For file systems, treat the target as existing even if it is an empty directory.
    if url.scheme() == "file"
        && let Ok(path) = url.to_file_path()
        && path.exists()
    {
        return Ok(true);
    }
    listing_target_nonempty(ctx, url).await
}
async fn listing_target_nonempty(ctx: &dyn Session, url: &Url) -> Result<bool> {
    let path = ListingTableUrl::try_new(url.clone(), None)?;
    let store = ctx.runtime_env().object_store(&path)?;
    Ok(store.list(Some(path.prefix())).try_next().await?.is_some())
}

// Reconciles a user-specified schema's field names with the physical file schema
// case-insensitively, matching Spark's default `spark.sql.caseSensitive=false`.
fn reconcile_schema_names_case_insensitive(schema: Schema, physical: &Schema) -> Result<Schema> {
    let mut fields = Vec::with_capacity(schema.fields().len());
    for field in schema.fields() {
        let name = field.name();
        let mut matches = physical
            .fields()
            .iter()
            .filter(|f| f.name().eq_ignore_ascii_case(name));
        let reconciled = match matches.next() {
            None => Arc::clone(field),
            Some(first) => {
                if let Some(second) = matches.next() {
                    let mut names = vec![first.name().as_str(), second.name().as_str()];
                    names.extend(matches.map(|f| f.name().as_str()));
                    return plan_err!(
                        "Ambiguous case-insensitive column match for `{name}`: [{}]",
                        names.join(", ")
                    );
                }
                if first.name() == name {
                    Arc::clone(field)
                } else {
                    Arc::new(field.as_ref().clone().with_name(first.name().as_str()))
                }
            }
        };
        fields.push(reconciled);
    }
    Ok(Schema::new_with_metadata(fields, schema.metadata().clone()))
}

#[cfg(test)]
#[path = "case_sensitivity_tests.rs"]
mod case_sensitivity_tests;

#[cfg(test)]
#[path = "inference_selection_tests.rs"]
mod inference_selection_tests;

#[cfg(test)]
#[path = "explicit_schema_tests.rs"]
mod explicit_schema_tests;
