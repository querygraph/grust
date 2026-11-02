async fn build_iceberg_scan(ctx: &dyn Session, info: SourceInfo) -> Result<Arc<IcebergScan>> {
    let (table, iceberg_options) =
        load_iceberg_read_table(ctx, info, IcebergReadPurpose::DataScan).await?;
    Ok(Arc::new(table.new_scan(&iceberg_options)?))
}

#[derive(Clone, Copy)]
pub(crate) enum IcebergReadPurpose {
    DataScan,
    MetadataRelation,
}

pub(crate) async fn load_iceberg_read_table(
    ctx: &dyn Session,
    info: SourceInfo,
    read_purpose: IcebergReadPurpose,
) -> Result<(Table, IcebergReadOptions)> {
    let read = resolve_iceberg_read(ctx, info, read_purpose).await?;
    let table = Table::load_with_metadata_location(
        ctx.runtime_env().as_ref(),
        read.table_url,
        read.metadata_location,
    )
    .await?;
    Ok((table, read.options))
}

