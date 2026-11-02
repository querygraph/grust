pub struct IcebergScan {
    pub(crate) row_level_options: crate::logical::row_level::IcebergRowLevelOptions,
    /// The table location (URI)
    table_uri: String,
    /// The current schema of the table
    schema: Schema,
    schema_history: Vec<Schema>,
    name_mapping: Option<crate::spec::name_mapping::NameMapping>,
    format_version: crate::spec::FormatVersion,
    /// The current snapshot of the table
    snapshot: Option<Snapshot>,
    /// All partition specs referenced by the table
    partition_specs: Vec<PartitionSpec>,
    /// Default partition spec id (for schema ordering / partition metadata)
    default_spec_id: i32,
    /// Arrow schema for DataFusion
    arrow_schema: Arc<ArrowSchema>,
    /// Output schema exposed to DataFusion; may include MERGE metadata columns.
    output_schema: Arc<ArrowSchema>,
    /// Optional file-path metadata column for row-level write planning.
    file_column_name: Option<String>,
    /// Optional file-local row-index metadata column for row-level write planning.
    row_index_column_name: Option<String>,
    /// Candidate-file selection only; never a row filter on the rewrite input.
    copy_on_write_predicate: Option<Expr>,
    /// Whether to use the metadata-as-data read path (lazy manifest scanning)
    metadata_as_data_read: bool,
}

