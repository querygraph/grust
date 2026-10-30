use arrow::array::StringArray;
use datafusion::logical_expr::physical_planning_context::PhysicalPlanningContext;
use datafusion::logical_expr::{Expr, LogicalPlan, LogicalPlanBuilder};
use datafusion::physical_plan::{ExecutionPlan, collect};
use datafusion::physical_planner::{DefaultPhysicalPlanner, ExtensionPlanner};
use datafusion::prelude::{col, lit};
use datafusion_common::{Column, ScalarValue};
use datafusion_datasource::source::DataSourceExec;

use super::*;
use crate::listing::planner::ListingPhysicalPlanner;
use crate::listing::table::ListingTableSource;

async fn plan(
    fixture: &Fixture,
    source: Arc<dyn TableSource>,
    projection: Option<Vec<usize>>,
    filters: Vec<Expr>,
) -> Result<Arc<dyn ExecutionPlan>> {
    let logical =
        LogicalPlanBuilder::scan_with_filters("orc_files", source, projection, filters)?.build()?;
    let LogicalPlan::TableScan(scan) = logical else {
        unreachable!()
    };
    let planner = DefaultPhysicalPlanner::with_extension_planners(vec![]);
    Ok(ListingPhysicalPlanner
        .plan_table_scan(
            &planner,
            &scan,
            &fixture.context.state(),
            &PhysicalPlanningContext::default(),
        )
        .await?
        .unwrap())
}

#[tokio::test]
async fn supplied_empty_bypasses_inference_and_keeps_nonempty_file_row_counts() -> Result<()> {
    let fixture = Fixture::new();
    fixture
        .put("values.orc", integers("id", vec![11, 12, 13]))
        .await;
    let source = fixture
        .source(
            Some(Schema::empty()),
            vec![option_list(&[("mergeSchema", "true")])],
            false,
        )
        .await?;
    assert!(source.schema().fields().is_empty());
    assert!(fixture.store.requests.lock().unwrap().is_empty());
    let physical = plan(&fixture, source, None, vec![]).await?;
    let batches = collect(physical, fixture.context.task_ctx()).await?;
    assert_eq!(batches.iter().map(RecordBatch::num_rows).sum::<usize>(), 3);
    assert!(batches.iter().all(|batch| batch.num_columns() == 0));

    // A supplied schema must not accidentally trigger footer inference even
    // when a listed object is corrupt. Its later read still reports corruption.
    let invalid = Fixture::new();
    invalid.put("bad.orc", Bytes::from_static(b"invalid")).await;
    let source = invalid.source(Some(Schema::empty()), vec![], true).await?;
    assert!(invalid.store.requests.lock().unwrap().is_empty());
    let physical = plan(&invalid, source, None, vec![]).await?;
    assert!(collect(physical, invalid.context.task_ctx()).await.is_err());
    Ok(())
}

#[tokio::test]
async fn explicit_schema_nullability_is_published_before_scan_and_missing_columns_are_null()
-> Result<()> {
    let fixture = Fixture::new();
    fixture
        .put("values.orc", integers("id", vec![11, 12]))
        .await;
    let source = fixture
        .source(
            Some(Schema::new(vec![
                Field::new("id", DataType::Int64, false),
                Field::new("missing", DataType::Int64, false),
            ])),
            vec![],
            true,
        )
        .await?;
    assert!(
        source
            .schema()
            .fields()
            .iter()
            .all(|field| field.is_nullable())
    );
    assert!(fixture.store.requests.lock().unwrap().is_empty());
    let physical = plan(&fixture, source, Some(vec![1, 0]), vec![]).await?;
    let batches = collect(physical, fixture.context.task_ctx()).await?;
    assert_eq!(batches.iter().map(RecordBatch::num_rows).sum::<usize>(), 2);
    assert!(
        batches
            .iter()
            .all(|batch| batch.column(0).null_count() == batch.num_rows())
    );
    let ids = batches
        .iter()
        .flat_map(|batch| {
            batch
                .column(1)
                .as_any()
                .downcast_ref::<Int64Array>()
                .unwrap()
                .iter()
        })
        .collect::<Vec<_>>();
    assert_eq!(ids, [Some(11), Some(12)]);
    Ok(())
}

#[tokio::test]
async fn glob_partition_alias_pruning_and_projection_use_the_normal_listing_path() -> Result<()> {
    let fixture = Fixture::new();
    let west = fixture
        .put("part=west/values.orc", integers("id", vec![11, 12]))
        .await;
    fixture
        .put("part=east/values.orc", integers("id", vec![21]))
        .await;
    for path in [
        "part=west/skipped.txt",
        "part=east/_hidden.orc",
        "_staging/bad.orc",
    ] {
        fixture.put(path, Bytes::from_static(b"not ORC")).await;
    }
    let options = || {
        vec![option_list(&[
            ("pathGlobFilter", "*.orc"),
            ("maxSchemaDepth", "17"),
        ])]
    };
    let inferred = fixture.source(None, options(), false).await?;
    assert_eq!(
        inferred
            .schema()
            .fields()
            .iter()
            .map(|f| f.name().as_str())
            .collect::<Vec<_>>(),
        ["id", "part"]
    );
    assert!(
        fixture
            .store
            .requests
            .lock()
            .unwrap()
            .iter()
            .all(|(path, _)| path.as_ref().ends_with("/values.orc"))
    );
    fixture.store.requests.lock().unwrap().clear();

    let mut info = request(
        Some(Schema::new(vec![
            Field::new("PART", DataType::Utf8, false),
            Field::new("id", DataType::Int64, false),
        ])),
        options(),
        false,
    );
    info.partition_by = vec!["part".into()];
    let source = OrcDataSource::default()
        .create_source(&fixture.context.state(), info)
        .await?;
    assert_eq!(
        source
            .schema()
            .fields()
            .iter()
            .map(|f| f.name().as_str())
            .collect::<Vec<_>>(),
        ["id", "PART"]
    );
    let table = source.downcast_ref::<ListingTableSource>().unwrap();
    assert_eq!(table.config().partition_directory_names, ["part"]);
    assert!(fixture.store.requests.lock().unwrap().is_empty());
    let physical = plan(
        &fixture,
        source,
        Some(vec![1, 0]),
        vec![col(Column::from_name("PART")).eq(lit("west"))],
    )
    .await?;
    let config = physical
        .downcast_ref::<DataSourceExec>()
        .unwrap()
        .data_source()
        .downcast_ref::<FileScanConfig>()
        .unwrap();
    let files = config
        .file_groups
        .iter()
        .flat_map(|group| group.iter())
        .collect::<Vec<_>>();
    assert_eq!(files.len(), 1);
    assert_eq!(files[0].object_meta, west);
    assert_eq!(
        files[0].partition_values,
        [ScalarValue::Utf8(Some("west".into()))]
    );
    let reader = config.file_source.downcast_ref::<OrcSource>().unwrap();
    assert!(!reader.read_case_sensitive());
    assert_eq!(reader.options().max_schema_depth, 17);
    let batches = collect(physical, fixture.context.task_ctx()).await?;
    let mut rows = vec![];
    for batch in batches {
        let parts = batch
            .column(0)
            .as_any()
            .downcast_ref::<StringArray>()
            .unwrap();
        let ids = batch
            .column(1)
            .as_any()
            .downcast_ref::<Int64Array>()
            .unwrap();
        rows.extend((0..batch.num_rows()).map(|i| (parts.value(i).to_string(), ids.value(i))));
    }
    assert_eq!(rows, [("west".into(), 11), ("west".into(), 12)]);
    let requests = fixture.store.requests.lock().unwrap();
    assert!(!requests.is_empty());
    assert!(requests.iter().all(|(path, options)| path == &west.location
        && !options.head
        && options.if_match == west.e_tag
        && options.version == west.version
        && options.range.is_some()));
    Ok(())
}
