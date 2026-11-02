    }

    sanitize_statistics_for_schema(table_schema.table_schema(), &mut stats);

    let object_store_url = create_object_store_url(&log_store.config().location)?;
    let metadata_size_hint = parquet_options.global.metadata_size_hint;
    let store = session.runtime_env().object_store(&object_store_url)?;
    let metadata_cache = session
        .runtime_env()
        .cache_manager
        .get_file_metadata_cache();
    let reader_factory = Arc::new(CachedParquetFileReaderFactory::new(
        Arc::clone(&store),
        Arc::clone(&metadata_cache),
    ));
    let mut parquet_source = ParquetSource::new(table_schema)
        .with_table_parquet_options(parquet_options)
        .with_parquet_file_reader_factory(reader_factory);

    if let Some(predicate) = params.pushdown_filter
