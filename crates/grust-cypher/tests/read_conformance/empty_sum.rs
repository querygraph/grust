//! Cypher SUM uses integer zero for empty and all-null aggregate inputs.
use grust_core::{Graph, Node, Props, TypedGraphIndex, Value};
use grust_cypher::{
    CypherParameters,
    read::{run_read_query, run_read_query_indexed},
};
use std::sync::Arc;

#[test]
fn empty_and_null_sums_match_across_owned_and_indexed_reads() {
    let graph = Arc::new(Graph::new(vec![Node::new("N", "n", Props::new())], vec![]));
    let index = TypedGraphIndex::new(Arc::clone(&graph)).unwrap();
    let params = CypherParameters::new();
    for query in [
        "MATCH (n:Missing) RETURN sum(n.x), avg(n.x)",
        "MATCH (n:N) RETURN sum(n.x), avg(n.x)",
        "MATCH (n:N) RETURN sum(DISTINCT n.x), avg(DISTINCT n.x)",
        "MATCH (n:Missing) RETURN sum(DISTINCT n.x), avg(DISTINCT n.x)",
        "UNWIND [null, null] AS x RETURN sum(x), avg(x)",
        "UNWIND [] AS x RETURN sum(x), avg(x)",
    ] {
        for result in [
            run_read_query(&graph, query, &params),
            run_read_query_indexed(&index, query, &params),
        ] {
            assert_eq!(
                result.unwrap().rows,
                vec![vec![Value::Int(0), Value::Null]],
                "{query}"
            );
        }
    }
}

#[test]
fn null_only_groups_have_zero_sum_but_empty_grouped_input_has_no_rows() {
    let graph = Graph::new(vec![Node::new("N", "n", Props::new())], vec![]);
    let params = CypherParameters::new();
    let result = run_read_query(
        &graph,
        "MATCH (n:N) RETURN n.label, sum(n.x), sum(DISTINCT n.x)",
        &params,
    )
    .unwrap();
    assert_eq!(
        result.rows,
        vec![vec![Value::from("N"), Value::Int(0), Value::Int(0)]]
    );
    let result = run_read_query(
        &graph,
        "MATCH (n:Missing) RETURN n.label, sum(n.x)",
        &params,
    )
    .unwrap();
    assert!(result.rows.is_empty());
}
