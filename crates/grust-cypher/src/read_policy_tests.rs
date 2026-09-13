use super::*;
use grust_core::prelude::GraphBuilder;

#[test]
fn parser_backed_policy_executes_bounded_reads() {
    let mut builder = GraphBuilder::new();
    let _ = builder.node("Person", "ada").prop("name", "Ada").finish();
    let graph = builder.build();
    let result = run_bounded_read_query(
        &graph,
        "MATCH (n:Person) RETURN n.name AS name LIMIT 5",
        &CypherParameters::new(),
        &ReadQueryPolicy::default(),
    )
    .unwrap();
    assert_eq!(result.rows.len(), 1);
}

#[test]
fn policy_rejects_updates_and_nonliteral_or_unbounded_limits() {
    let policy = ReadQueryPolicy::default();
    assert!(validate_read_query("MATCH (n) DELETE n RETURN n LIMIT 1", &policy).is_err());
    assert!(validate_read_query("MATCH (n) RETURN n", &policy).is_err());
    assert!(validate_read_query("MATCH (n) RETURN n LIMIT $limit", &policy).is_err());
    assert!(validate_read_query("MATCH (n) RETURN n LIMIT 4294967297", &policy).is_err());
    assert!(validate_read_query("MATCH (n)-[*]->(m) RETURN m LIMIT 5", &policy).is_err());
}

#[test]
fn keywords_inside_values_do_not_confuse_the_policy() {
    let policy = ReadQueryPolicy::default();
    assert!(
        validate_read_query(
            "MATCH (n {label: 'DELETE USE CREATE'}) RETURN n LIMIT 1",
            &policy
        )
        .is_ok()
    );
}

#[test]
fn path_limit_is_cumulative_across_segments() {
    let policy = ReadQueryPolicy::default();
    assert!(
        validate_read_query(
            "MATCH (a)-[*1..3]->(b)-[*1..2]->(c) RETURN c LIMIT 1",
            &policy,
        )
        .is_err()
    );
}

#[test]
fn candidate_work_stops_cartesian_expansion_before_return_limit() {
    let mut builder = GraphBuilder::new();
    for index in 0..8 {
        let _ = builder.node("N", format!("n{index}")).finish();
    }
    let graph = builder.build();
    let policy = ReadQueryPolicy {
        max_candidate_work: 60,
        ..ReadQueryPolicy::default()
    };
    let error = run_bounded_read_query(
        &graph,
        "MATCH (a), (b), (c) RETURN a LIMIT 1",
        &CypherParameters::new(),
        &policy,
    )
    .unwrap_err();
    assert!(error.to_string().contains("candidate-work"));
}

#[test]
fn intermediate_byte_budget_stops_deep_binding_clone_amplification() {
    let mut builder = GraphBuilder::new();
    let _ = builder
        .node("N", "large")
        .prop("payload", "x".repeat(2 * 1024))
        .finish();
    let graph = builder.build();
    let query = "MATCH (n:N) UNWIND range(1, 100) AS item RETURN item LIMIT 1";
    let policy = ReadQueryPolicy {
        max_graph_bytes: 16 * 1024,
        max_candidate_work: 10_000,
        max_intermediate_bytes: 8 * 1024,
        max_range_items: 100,
        ..ReadQueryPolicy::default()
    };

    let error = run_bounded_read_query(&graph, query, &CypherParameters::new(), &policy)
        .expect_err("deep row copies must exhaust the cumulative byte budget");
    assert!(error.to_string().contains("cumulative intermediate bytes"));
    assert!(error.to_string().contains("expanding UNWIND rows"));

    let result = crate::read::run_read_query(&graph, query, &CypherParameters::new())
        .expect("the unrestricted executor retains its existing behavior");
    assert_eq!(result.rows, vec![vec![grust_core::Value::Int(1)]]);
}

#[test]
fn intermediate_byte_budget_stops_literal_projection_amplification_before_limit() {
    let mut builder = GraphBuilder::new();
    for index in 0..128 {
        let _ = builder.node("N", format!("n{index}")).finish();
    }
    let graph = builder.build();
    let literal = "x".repeat(512);
    let query = format!("MATCH (n:N) RETURN '{literal}' AS payload LIMIT 1");
    let policy = ReadQueryPolicy {
        max_query_bytes: 2_000,
        max_candidate_work: 10_000,
        // Leave room for MATCH bindings and relationship-scope framing;
        // the repeated 512-byte projection must still exhaust the budget.
        max_intermediate_bytes: 96 * 1024,
        ..ReadQueryPolicy::default()
    };

    let error = run_bounded_read_query(&graph, &query, &CypherParameters::new(), &policy)
        .expect_err("repeated literal results must exhaust the cumulative byte budget");
    assert!(
        error.to_string().contains("cumulative intermediate bytes"),
        "{error}"
    );
    assert!(
        error
            .to_string()
            .contains("materializing expression results"),
        "{error}"
    );
}

#[test]
fn candidate_work_accounts_for_correlated_subquery_index_builds() {
    let mut builder = GraphBuilder::new();
    for index in 0..64 {
        let _ = builder.node("N", format!("n{index}")).finish();
    }
    let graph = builder.build();
    let policy = ReadQueryPolicy {
        max_candidate_work: 2_000,
        ..ReadQueryPolicy::default()
    };
    let error = run_bounded_read_query(
        &graph,
        "MATCH (n) CALL { MATCH (n) RETURN n AS m LIMIT 1 } RETURN n LIMIT 1",
        &CypherParameters::new(),
        &policy,
    )
    .unwrap_err();
    assert!(error.to_string().contains("candidate-work"));
    assert!(error.to_string().contains("subquery node index"));
}

#[test]
fn candidate_work_accounts_for_correlated_catalog_scans() {
    let mut builder = GraphBuilder::new();
    for index in 0..64 {
        let _ = builder
            .node("N", format!("n{index}"))
            .prop("name", format!("node {index}"))
            .finish();
    }
    let graph = builder.build();
    let policy = ReadQueryPolicy {
        max_candidate_work: 2_000,
        allow_catalog_procedures: true,
        ..ReadQueryPolicy::default()
    };
    let error = run_bounded_read_query(
        &graph,
        "MATCH (n) CALL db.propertyKeys() YIELD propertyKey RETURN n LIMIT 1",
        &CypherParameters::new(),
        &policy,
    )
    .unwrap_err();
    assert!(error.to_string().contains("candidate-work"));
    assert!(error.to_string().contains("db.propertyKeys()"));
}

#[test]
fn parameter_graph_output_and_range_budgets_are_enforced() {
    let mut builder = GraphBuilder::new();
    let _ = builder
        .node("N", "n")
        .prop("payload", "x".repeat(256))
        .finish();
    let graph = builder.build();
    let query = "MATCH (n) RETURN n LIMIT 1";

    let mut params = CypherParameters::new();
    params.insert("payload".into(), grust_core::Value::String("x".repeat(256)));
    let parameter_policy = ReadQueryPolicy {
        max_parameter_bytes: 32,
        ..ReadQueryPolicy::default()
    };
    assert!(
        run_bounded_read_query(&graph, query, &params, &parameter_policy)
            .unwrap_err()
            .to_string()
            .contains("parameters")
    );

    let graph_policy = ReadQueryPolicy {
        max_graph_nodes: 1,
        max_graph_bytes: 32,
        ..ReadQueryPolicy::default()
    };
    assert!(
        run_bounded_read_query(&graph, query, &CypherParameters::new(), &graph_policy,)
            .unwrap_err()
            .to_string()
            .contains("graph")
    );

    let output_policy = ReadQueryPolicy {
        max_output_bytes: 32,
        ..ReadQueryPolicy::default()
    };
    assert!(
        run_bounded_read_query(&graph, query, &CypherParameters::new(), &output_policy,)
            .unwrap_err()
            .to_string()
            .contains("query output")
    );

    let range_policy = ReadQueryPolicy {
        max_range_items: 3,
        ..ReadQueryPolicy::default()
    };
    assert!(
        run_bounded_read_query(
            &graph,
            "MATCH (n) RETURN range(1, 4) AS values LIMIT 1",
            &CypherParameters::new(),
            &range_policy,
        )
        .unwrap_err()
        .to_string()
        .contains("read policy maximum")
    );
}

#[test]
fn execution_deadline_is_enforced() {
    let mut builder = GraphBuilder::new();
    let _ = builder.node("N", "n").finish();
    let policy = ReadQueryPolicy {
        max_execution_time: Duration::from_nanos(1),
        ..ReadQueryPolicy::default()
    };
    let error = run_bounded_read_query(
        &builder.build(),
        "MATCH (n) RETURN n LIMIT 1",
        &CypherParameters::new(),
        &policy,
    )
    .unwrap_err();
    assert!(error.to_string().contains("timed out"));
}
