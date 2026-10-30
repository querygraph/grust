pub(crate) async fn load_delta_read_state(
    ctx: &dyn Session,
    table_url: Url,
    schema: Option<Schema>,
    options: DeltaReadOptions,
    metadata_only: bool,
    lakehouse_table: Option<LakehouseExecutionContext>,
) -> Result<(Arc<DeltaSnapshot>, LogStoreRef, DeltaScanConfig)> {
    let reads_catalog_table = lakehouse_table.is_some();
    let url = ListingTableUrl::try_new(table_url.clone(), None)?;
    let object_store = ctx.runtime_env().object_store(&url)?;
    let storage_config = StorageConfig;
    let log_store =
        create_logstore_with_object_store(object_store, table_url.clone(), storage_config)?;

    let catalog_managed_commits = match catalog_managed_commit_context(lakehouse_table.as_ref()) {
        Some(lakehouse_table) => {
            load_catalog_managed_commits_for_snapshot(
                &ctx,
                lakehouse_table,
                &table_url,
                log_store.clone(),
                options.version_as_of,
            )
            .await?
        }
        None => None,
    };

    let mut table_config = delta_read_snapshot_config(metadata_only, &options);
    table_config.catalog_managed_commits = catalog_managed_commits;
    let mut deltalake_table = DeltaTable::new(log_store.clone(), table_config);

    // Load the table state according to the provided time travel options.
