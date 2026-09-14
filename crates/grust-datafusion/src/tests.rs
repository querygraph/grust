use super::*;
use datafusion::{
    arrow::array::{Array, ArrayRef, Int64Array, RecordBatch, RecordBatchReader, StringArray},
    common::DataFusionError,
};
use futures::TryStreamExt;
use grust_arrow::ArrowGraph;
use grust_core::{Edge, Graph, Node, Props};

fn options() -> ExecutionOptions {
    ExecutionOptions {
        working_memory_bytes: NonZeroUsize::new(32 << 20).unwrap(),
        target_partitions: NonZeroUsize::new(2).unwrap(),
        batch_rows: NonZeroUsize::new(4096).unwrap(),
        spill: SpillPolicy::Disabled,
    }
}
fn numbers() -> ArrowTable {
    let batch =
        RecordBatch::try_from_iter([("n", Arc::new(Int64Array::from(vec![1, 2, 3])) as ArrayRef)])
            .unwrap();
    ArrowTable::try_new(batch.schema(), vec![batch.clone(), batch]).unwrap()
}
#[tokio::test]
async fn relational_queries_consume_shared_multi_batch_tables() {
    let engine = DataFusionEngine::new(options()).unwrap();
    engine.register_table("numbers", numbers()).unwrap();
    let batches = engine
        .execute_stream("SELECT COUNT(*) AS c, SUM(n) AS s FROM numbers WHERE n > 1")
        .await
        .unwrap()
        .try_collect::<Vec<_>>()
        .await
        .unwrap();
    assert_eq!(batches.len(), 1);
    let count = batches[0]
        .column(0)
        .as_any()
        .downcast_ref::<Int64Array>()
        .unwrap()
        .value(0);
    let sum = batches[0]
        .column(1)
        .as_any()
        .downcast_ref::<Int64Array>()
        .unwrap()
        .value(0);
    assert_eq!((count, sum), (4, 10));
}
#[tokio::test]
async fn read_only_queries_reject_ddl_and_dml_before_mutation() {
    let engine = DataFusionEngine::new(options()).unwrap();
    engine.register_table("numbers", numbers()).unwrap();
    for sql in [
        "CREATE TABLE probe (n BIGINT)",
        "INSERT INTO numbers VALUES (9)",
        "SET datafusion.execution.batch_size = 5",
    ] {
        assert!(matches!(
            engine.dataframe(sql).await,
            Err(DataFusionError::Plan(_))
        ));
    }
    assert!(engine.context().table("probe").await.is_err());
}
#[tokio::test]
async fn graph_registration_preserves_isolates_and_parallel_edges() {
    let graph = Graph::new(
        vec![
            Node::new("N", "a", Props::new()),
            Node::new("N", "z", Props::new()),
        ],
        vec![
            Edge::new("E", "a", "a", Props::new()),
            Edge::new("E", "a", "a", Props::new()),
        ],
    );
    let (nodes, edges) = ArrowGraph::from_graph(&graph).unwrap().into_tables();
    let engine = DataFusionEngine::new(options()).unwrap();
    engine
        .register_graph("g", ArrowGraphTables::try_new(nodes, edges).unwrap())
        .unwrap();
    let batches = engine.execute_stream("SELECT n.node_id, COUNT(e.source) AS degree FROM g.graph.nodes n LEFT JOIN g.graph.edges e ON n.node_id = e.source GROUP BY n.node_id ORDER BY n.node_id").await.unwrap().try_collect::<Vec<_>>().await.unwrap();
    let mut rows = Vec::new();
    for batch in batches {
        let ids = batch
            .column(0)
            .as_any()
            .downcast_ref::<StringArray>()
            .unwrap();
        let counts = batch
            .column(1)
            .as_any()
            .downcast_ref::<Int64Array>()
            .unwrap();
        for i in 0..batch.num_rows() {
            rows.push((ids.value(i).to_string(), counts.value(i)));
        }
    }
    assert_eq!(rows, [("a".into(), 2), ("z".into(), 0)]);
}
#[test]
fn blocking_reader_composes_with_arrow_and_adbc_reader_contract() {
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .worker_threads(2)
        .enable_all()
        .build()
        .unwrap();
    let engine = DataFusionEngine::new(options()).unwrap();
    engine.register_table("numbers", numbers()).unwrap();
    let stream = runtime
        .block_on(engine.execute_stream("SELECT n FROM numbers ORDER BY n"))
        .unwrap();
    let mut reader: Box<dyn RecordBatchReader + Send> =
        Box::new(BlockingReader::new(stream, runtime.handle().clone()));
    assert_eq!(reader.schema().fields()[0].name(), "n");
    let mut values = Vec::new();
    for batch in &mut reader {
        let batch = batch.unwrap();
        let column = batch
            .column(0)
            .as_any()
            .downcast_ref::<Int64Array>()
            .unwrap();
        values.extend(column.values().iter().copied());
    }
    assert_eq!(values, [1, 1, 2, 2, 3, 3]);
    assert!(reader.next().is_none());
}
#[tokio::test]
async fn disabled_spill_and_small_pool_reject_sort_work() {
    let mut settings = options();
    settings.working_memory_bytes = NonZeroUsize::new(1).unwrap();
    let engine = DataFusionEngine::new(settings).unwrap();
    let batch = RecordBatch::try_from_iter([(
        "n",
        Arc::new(Int64Array::from_iter_values(0..32768)) as ArrayRef,
    )])
    .unwrap();
    engine
        .register_table("numbers", ArrowTable::from(batch))
        .unwrap();
    let error = engine
        .execute_stream("SELECT n FROM numbers ORDER BY n DESC")
        .await
        .unwrap()
        .try_collect::<Vec<_>>()
        .await
        .unwrap_err();
    fn resource_error(error: &DataFusionError) -> bool {
        match error {
            DataFusionError::ResourcesExhausted(_) => true,
            DataFusionError::Context(_, source) => resource_error(source),
            _ => false,
        }
    }
    assert!(resource_error(&error), "unexpected error: {error}");
}

#[tokio::test]
async fn typed_relational_plans_execute_without_sql_serialization() {
    use datafusion::logical_expr::{col, lit};

    let engine = DataFusionEngine::new(options()).unwrap();
    engine.register_table("numbers", numbers()).unwrap();
    let plan = engine
        .context()
        .table("numbers")
        .await
        .unwrap()
        .filter(col("n").gt(lit(1_i64)))
        .unwrap()
        .select(vec![(col("n") + lit(10_i64)).alias("shifted")])
        .unwrap()
        .into_unoptimized_plan();
    let batches = engine
        .context()
        .execute_logical_plan(plan)
        .await
        .unwrap()
        .execute_stream()
        .await
        .unwrap()
        .try_collect::<Vec<_>>()
        .await
        .unwrap();
    let mut values = batches
        .iter()
        .flat_map(|batch| {
            assert_eq!(batch.schema().field(0).name(), "shifted");
            batch
                .column(0)
                .as_any()
                .downcast_ref::<Int64Array>()
                .unwrap()
                .values()
                .iter()
                .copied()
        })
        .collect::<Vec<_>>();
    values.sort_unstable();
    assert_eq!(values, [12, 12, 13, 13]);
}
