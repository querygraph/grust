use super::*;
use datafusion::execution::context::SessionContext;

#[tokio::test]
async fn unsupported_plans_and_invalid_queries_remain_distinct() {
    let context = SessionContext::new();
    for (text, reason) in [
        (
            "MATCH (n)-[r]->(m) RETURN n.x AS x",
            UnsupportedScan::QueryShape,
        ),
        (
            "MATCH (n) RETURN n.x AS x ORDER BY n.unprojected",
            UnsupportedScan::Ordering,
        ),
        (
            "MATCH (n) RETURN n.x AS x LIMIT -1",
            UnsupportedScan::Pagination,
        ),
        ("MATCH (n) RETURN n.x + 1 AS x", UnsupportedScan::Expression),
    ] {
        let query = grust_cypher::parser::parse_query(text).unwrap();
        let plan = plan_node_scan(
            &query,
            context.read_empty().unwrap(),
            &CypherParameters::new(),
        )
        .unwrap();
        assert!(
            matches!(plan, NodeScanPlan::Unsupported(actual) if actual == reason),
            "{text}"
        );
    }
    let invalid = grust_cypher::parser::parse_query("MATCH (n) RETURN absent.x AS x").unwrap();
    assert!(
        plan_node_scan(
            &invalid,
            context.read_empty().unwrap(),
            &CypherParameters::new()
        )
        .is_err()
    );
}

#[tokio::test]
async fn integer_extrema_preserve_nulls_and_exact_limits() {
    use datafusion::arrow::array::{Array, Int64Array, RecordBatch};
    for values in [
        vec![],
        vec![None],
        vec![None, Some(i64::MIN), Some(i64::MAX)],
    ] {
        let expected = (
            values.iter().flatten().min().copied(),
            values.iter().flatten().max().copied(),
        );
        let batch = RecordBatch::try_from_iter([(
            "property.x",
            std::sync::Arc::new(Int64Array::from(values)) as datafusion::arrow::array::ArrayRef,
        )])
        .unwrap();
        let context = SessionContext::new();
        let query = grust_cypher::parser::parse_query(
            "MATCH (n) RETURN min(n.x) AS low, max(DISTINCT n.x) AS high",
        )
        .unwrap();
        let batches = lower_node_scan(&query, context.read_batch(batch).unwrap())
            .unwrap()
            .unwrap()
            .collect()
            .await
            .unwrap();
        for (column, expected) in [expected.0, expected.1].into_iter().enumerate() {
            let array = batches[0]
                .column(column)
                .as_any()
                .downcast_ref::<Int64Array>()
                .unwrap();
            let actual = (!array.is_null(0)).then(|| array.value(0));
            assert_eq!(actual, expected);
        }
    }
}
