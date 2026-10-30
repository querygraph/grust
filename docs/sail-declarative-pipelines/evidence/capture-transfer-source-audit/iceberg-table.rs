
/// High-level representation of an Iceberg table backed by ObjectStore + metadata.
pub struct Table {
    table_url: Url,
    store_ctx: StoreContext,
    metadata_location: String,
    metadata: TableMetadata,
}

impl Table {
    /// Load table metadata and IO context using the provided execution session.
    pub async fn load(ctx: &dyn Session, table_url: Url) -> Result<Self> {
        Self::load_with_metadata_location(ctx.runtime_env().as_ref(), table_url, None).await
    }

    /// Load table metadata from an explicit metadata location when one is provided.
    pub async fn load_with_metadata_location(
        runtime: &datafusion::execution::runtime_env::RuntimeEnv,
        table_url: Url,
        metadata_location: Option<String>,
    ) -> Result<Self> {
        log::trace!(
            "Loading Iceberg table: table_url={}, metadata_location={:?}",
            table_url,
            metadata_location,
        );
        let object_store = runtime
            .object_store_registry
            .get_store(&table_url)
            .map_err(|e| DataFusionError::External(Box::new(e)))?;
        let store_ctx = StoreContext::new(object_store.clone(), &table_url)?;
        let (metadata_file, metadata_location) = match metadata_location {
            Some(location) => {
                let metadata_file =
                    metadata_loader::metadata_location_to_object_path_string(&location)?;
                let metadata_location = if crate::utils::parse_absolute_url(&location).is_some() {
                    location
                } else {
                    metadata_loader::table_metadata_location(&table_url, &metadata_file)?
                };
                (metadata_file, metadata_location)
