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
