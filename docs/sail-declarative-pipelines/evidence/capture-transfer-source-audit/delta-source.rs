///
/// This avoids coupling logical planning / optimization with `TableProvider::scan`
/// behavior. Physical planning is handled by rewriting scans to an extension node.
#[derive(Clone)]
pub struct DeltaTableSource {
    snapshot: Arc<DeltaSnapshot>,
    log_store: LogStoreRef,
    config: DeltaScanConfig,
    schema: SchemaRef,
    file_selection: DeltaFileSelection,
}

#[derive(Debug, Clone)]
