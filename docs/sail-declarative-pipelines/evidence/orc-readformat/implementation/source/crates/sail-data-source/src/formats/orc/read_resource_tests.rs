use arrow::compute::SortOptions;
use datafusion::execution::memory_pool::GreedyMemoryPool;
use datafusion::execution::object_store::ObjectStoreUrl;
use datafusion::execution::runtime_env::RuntimeEnvBuilder;
use datafusion::physical_expr::expressions::Column;
use datafusion::physical_expr::{LexOrdering, Partitioning, PhysicalSortExpr};
use datafusion_common::stats::Precision;
use datafusion_common::{Constraint, ScalarValue, Statistics};
use datafusion_datasource::file_groups::FileGroup;
use datafusion_datasource::source::DataSource as PhysicalDataSource;
use datafusion_datasource::{PartitionedFile, TableSchema};
use futures::TryStreamExt;

use super::*;

#[tokio::test]
async fn inference_uses_listed_identity_and_reports_replaced_or_identityless_objects() {
    let fixture = Fixture::new();
    let original = fixture.put("values.orc", integers("id", vec![1])).await;
    let read = format(&fixture.context.state(), vec![]);
    fixture.infer(&read, vec![original.clone()]).await.unwrap();
    {
        let requests = fixture.store.requests.lock().unwrap();
        assert!(!requests.is_empty());
        assert!(
            requests
                .iter()
                .all(|(path, options)| path == &original.location
                    && options.if_match == original.e_tag
                    && options.version == original.version
                    && !options.head
                    && options.range.is_some())
        );
    }
    fixture.store.requests.lock().unwrap().clear();
    let mut no_identity = original.clone();
    no_identity.e_tag = None;
    no_identity.version = None;
    let error = fixture.infer(&read, vec![no_identity]).await.unwrap_err();
    assert!(
        error
            .to_string()
            .contains("require a version or usable ETag"),
        "{error}"
    );
    assert!(error.to_string().contains("data/values.orc"), "{error}");
    assert!(fixture.store.requests.lock().unwrap().is_empty());
    let replacement = fixture.put("values.orc", integers("id", vec![2])).await;
    assert_ne!(replacement.e_tag, original.e_tag);
    let error = fixture
        .infer(&read, vec![original.clone()])
        .await
        .unwrap_err();
    assert!(error.to_string().contains("data/values.orc"), "{error}");
    let requests = fixture.store.requests.lock().unwrap();
    assert_eq!(requests.len(), 1);
    assert!(!requests[0].1.head);
    assert_eq!(requests[0].1.if_match, original.e_tag);
}

#[tokio::test]
async fn inference_applies_configured_metadata_limits_and_the_local_pool() {
    let fixture = Fixture::new();
    let object = fixture.put("values.orc", integers("id", vec![1])).await;
    for (key, expected) in [
        (
            "maxEncodedMetadataBytes",
            "Encoded footer and metadata exceed the configured limit",
        ),
        (
            "maxDecodedMetadataBytes",
            "Decoded stream exceeds the configured output limit",
        ),
        ("maxSchemaDepth", "exceeding maximum schema depth 0"),
    ] {
        let read = format(&fixture.context.state(), vec![option_list(&[(key, "0")])]);
        let error = fixture
            .infer(&read, vec![object.clone()])
            .await
            .unwrap_err();
        assert!(error.to_string().contains(expected), "{error}");
        assert!(error.to_string().contains("data/values.orc"), "{error}");
        assert_eq!(fixture.context.runtime_env().memory_pool.reserved(), 0);
    }
    fixture.store.requests.lock().unwrap().clear();
    let pool = Arc::new(GreedyMemoryPool::new(0));
    let context = SessionContext::new_with_config_rt(
        SessionConfig::new(),
        RuntimeEnvBuilder::new()
            .with_memory_pool(pool.clone())
            .build_arc()
            .unwrap(),
    );
    let limited = Fixture {
        context,
        store: fixture.store.clone(),
    };
    let error = limited
        .infer(&format(&limited.context.state(), vec![]), vec![object])
        .await
        .unwrap_err();
    assert!(error.to_string().contains("memory"), "{error}");
    assert!(fixture.store.requests.lock().unwrap().is_empty());
    assert_eq!(limited.context.runtime_env().memory_pool.reserved(), 0);
}

fn scan_input(object: ObjectMeta) -> ListingScanInput {
    let schema = TableSchema::builder(Arc::new(Schema::new(vec![Field::new(
        "id",
        DataType::Int64,
        true,
    )])))
    .with_table_partition_cols(vec![Arc::new(Field::new("part", DataType::Utf8, true))])
    .build();
    let mut file = PartitionedFile::new_from_meta(object);
    file.partition_values = vec![ScalarValue::Utf8(Some("west".into()))];
    let mut statistics = Statistics::new_unknown(schema.table_schema());
    statistics.num_rows = Precision::Exact(3);
    ListingScanInput {
        object_store_url: ObjectStoreUrl::parse("memory://orc-read").unwrap(),
        file_groups: vec![FileGroup::from(vec![file])],
        constraints: Constraints::new_unverified(vec![Constraint::Unique(vec![0])]),
        projection: Some(vec![1, 0, 0]),
        limit: Some(2),
        preserve_order: true,
        output_ordering: vec![
            LexOrdering::new(vec![PhysicalSortExpr::new(
                Arc::new(Column::new("id", 0)),
                SortOptions::default(),
            )])
            .unwrap(),
        ],
        statistics,
        output_partitioning: Some(Partitioning::Hash(
            vec![Arc::new(Column::new("part", 1))],
            1,
        )),
        schema,
        compression: CompressionTypeVariant::UNCOMPRESSED,
        read_case_sensitive: false,
    }
}

#[tokio::test]
async fn scan_preserves_properties_captured_configuration_and_actual_projection() -> Result<()> {
    let fixture = Fixture::new();
    let object = fixture
        .put("values.orc", integers("id", vec![1, 2, 3]))
        .await;
    let mut read = format(
        &fixture.context.state(),
        vec![option_list(&[
            ("maxEncodedMetadataBytes", "4096"),
            ("maxDecodedMetadataBytes", "8192"),
            ("maxDecodedStripeFooterBytes", "2048"),
            ("maxSchemaDepth", "17"),
        ])],
    );
    read.reader_timezone =
        OrcJavaTimeZoneConfig::for_reader_timezone("America/Los_Angeles".into())?;
    read.session_timezone = "+02:00".into();
    let input = scan_input(object.clone());
    let constraints = input.constraints.clone();
    let ordering = input.output_ordering.clone();
    let config = read.scan(&fixture.context.state(), input).await?;
    assert_eq!(
        config.object_store_url,
        ObjectStoreUrl::parse("memory://orc-read")?
    );
    assert_eq!(
        config.file_groups[0].iter().next().unwrap().object_meta,
        object
    );
    assert_eq!(config.constraints, constraints);
    assert_eq!(config.output_ordering, ordering);
    assert_eq!(config.limit, Some(2));
    assert!(config.preserve_order);
    assert_eq!(config.statistics().num_rows, Precision::Exact(3));
    assert!(
        matches!(&config.output_partitioning, Some(Partitioning::Hash(expressions, 1)) if expressions.len() == 1 && expressions[0].downcast_ref::<Column>().unwrap().index() == 1)
    );
    // The config stores full-table expressions; its DataSource property maps
    // them to the actual [part, id, id] output, unlike a separate exec override.
    assert!(
        matches!(config.output_partitioning(), Partitioning::Hash(expressions, 1) if expressions.len() == 1 && expressions[0].downcast_ref::<Column>().unwrap().index() == 0)
    );
    let source = config.file_source.downcast_ref::<OrcSource>().unwrap();
    assert_eq!(source.options().max_encoded_metadata_bytes, 4096);
    assert_eq!(source.options().max_decoded_metadata_bytes, 8192);
    assert_eq!(source.options().max_decoded_stripe_footer_bytes, 2048);
    assert_eq!(source.options().max_schema_depth, 17);
    assert_eq!(
        source.reader_timezone().reader_timezone(),
        "America/Los_Angeles"
    );
    assert_eq!(source.session_timezone(), "+02:00");
    assert!(!source.read_case_sensitive());
    let batches: Vec<RecordBatch> = config
        .open(0, fixture.context.task_ctx())?
        .try_collect()
        .await?;
    assert_eq!(batches.iter().map(RecordBatch::num_rows).sum::<usize>(), 2);
    let ids = batches
        .iter()
        .flat_map(|batch| {
            assert_eq!(batch.column(1), batch.column(2));
            batch
                .column(1)
                .as_any()
                .downcast_ref::<Int64Array>()
                .unwrap()
                .iter()
        })
        .collect::<Vec<_>>();
    assert_eq!(ids, [Some(1), Some(2)]);
    Ok(())
}

#[tokio::test]
async fn scan_binds_the_current_pool_and_direct_paths_reject_outer_compression() {
    let fixture = Fixture::new();
    let object = fixture
        .put("values.orc", integers("id", vec![1, 2, 3]))
        .await;
    let read = format(&fixture.context.state(), vec![]);
    let runtime = RuntimeEnvBuilder::new()
        .with_memory_pool(Arc::new(GreedyMemoryPool::new(0)))
        .build_arc()
        .unwrap();
    let limited = SessionContext::new_with_config_rt(SessionConfig::new(), runtime);
    limited.register_object_store(
        &Url::parse("memory://orc-read").unwrap(),
        fixture.store.clone(),
    );
    let config = read
        .scan(&limited.state(), scan_input(object.clone()))
        .await
        .unwrap();
    let error = config
        .open(0, limited.task_ctx())
        .unwrap()
        .try_collect::<Vec<_>>()
        .await
        .unwrap_err();
    assert!(error.to_string().contains("memory"), "{error}");
    assert!(fixture.store.requests.lock().unwrap().is_empty());

    let mut input = scan_input(object);
    input.compression = CompressionTypeVariant::GZIP;
    assert!(
        read.scan(&fixture.context.state(), input)
            .await
            .unwrap_err()
            .to_string()
            .contains("outer file compression")
    );
    assert!(
        read.infer_schema(
            &fixture.context.state(),
            &[],
            CompressionTypeVariant::GZIP,
            true
        )
        .await
        .unwrap_err()
        .to_string()
        .contains("outer file compression")
    );
    assert!(fixture.store.requests.lock().unwrap().is_empty());
}
