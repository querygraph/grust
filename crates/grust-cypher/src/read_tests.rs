use super::*;

fn node(label: &str, id: &str, props: &[(&str, Value)]) -> Node {
    let mut p = Props::new();
    for (k, v) in props {
        p.insert((*k).to_string(), v.clone());
    }
    Node::new(label, id, p)
}

fn graph() -> Graph {
    let nodes = vec![
        node(
            "Person",
            "p1",
            &[("name", Value::from("Ada")), ("age", Value::Int(36))],
        ),
        node(
            "Person",
            "p2",
            &[("name", Value::from("Alan")), ("age", Value::Int(41))],
        ),
        node(
            "Person",
            "p3",
            &[("name", Value::from("Grace")), ("age", Value::Int(85))],
        ),
        node("City", "c1", &[("name", Value::from("London"))]),
    ];
    let edges = vec![
        Edge::new("KNOWS", "p1", "p2", Props::new()),
        Edge::new("KNOWS", "p2", "p3", Props::new()),
        Edge::new("LIVES_IN", "p1", "c1", Props::new()),
    ];
    Graph::new(nodes, edges)
}

fn run(cypher: &str) -> CypherResultTable {
    run_read_query(&graph(), cypher, &CypherParameters::new())
        .unwrap_or_else(|e| panic!("query failed: {e}"))
}

#[test]
fn match_all_by_label() {
    let t = run("MATCH (n:Person) RETURN n.name");
    assert_eq!(t.columns, vec!["n.name".to_string()]);
    assert_eq!(t.rows.len(), 3);
}

#[test]
fn match_with_inline_property() {
    let t = run("MATCH (n:Person {name: 'Ada'}) RETURN n.age");
    assert_eq!(t.rows, vec![vec![Value::Int(36)]]);
}

#[test]
fn where_comparison_filters() {
    let t = run("MATCH (n:Person) WHERE n.age >= 40 RETURN n.name ORDER BY n.name");
    let names: Vec<_> = t.rows.iter().map(|r| r[0].clone()).collect();
    assert_eq!(names, vec![Value::from("Alan"), Value::from("Grace")]);
}

#[test]
fn where_boolean_and_or() {
    let t =
        run("MATCH (n:Person) WHERE n.age < 40 OR n.name = 'Grace' RETURN n.name ORDER BY n.name");
    assert_eq!(t.rows.len(), 2);
}

#[test]
fn where_in_list() {
    let t = run("MATCH (n:Person) WHERE n.name IN ['Ada', 'Grace'] RETURN n.name ORDER BY n.name");
    assert_eq!(
        t.rows.iter().map(|r| r[0].clone()).collect::<Vec<_>>(),
        vec![Value::from("Ada"), Value::from("Grace")]
    );
}

#[test]
fn where_starts_with() {
    let t = run("MATCH (n:Person) WHERE n.name STARTS WITH 'A' RETURN n.name ORDER BY n.name");
    assert_eq!(t.rows.len(), 2);
}

#[test]
fn relationship_hop() {
    let t = run("MATCH (a:Person {name: 'Ada'})-[:KNOWS]->(b:Person) RETURN b.name");
    assert_eq!(t.rows, vec![vec![Value::from("Alan")]]);
}

#[test]
fn relationship_incoming() {
    let t = run("MATCH (a:Person)<-[:KNOWS]-(b:Person {name: 'Ada'}) RETURN a.name");
    assert_eq!(t.rows, vec![vec![Value::from("Alan")]]);
}

#[test]
fn two_hop_path() {
    let t = run("MATCH (a:Person {name:'Ada'})-[:KNOWS]->(b)-[:KNOWS]->(c) RETURN c.name");
    assert_eq!(t.rows, vec![vec![Value::from("Grace")]]);
}

#[test]
fn indexed_undirected_traversal_visits_self_loops_once() {
    let graph = Graph::new(
        vec![
            node("Person", "p1", &[("name", Value::from("Ada"))]),
            node("Person", "p2", &[("name", Value::from("Alan"))]),
        ],
        vec![
            Edge::new("SELF", "p1", "p1", Props::new()),
            Edge::new("KNOWS", "p1", "p2", Props::new()),
        ],
    );
    let table = run_read_query(
        &graph,
        "MATCH (a:Person {name:'Ada'})-[:SELF]-(b)-[:KNOWS]->(c) RETURN c.name",
        &CypherParameters::new(),
    )
    .expect("indexed traversal");
    assert_eq!(table.rows, vec![vec![Value::from("Alan")]]);
}

#[test]
fn adjacency_planning_keeps_short_selective_paths_on_contiguous_scans() {
    let query =
        parse_query("MATCH (a:Person {name:'Ada'})-[:KNOWS]->(b)-[:KNOWS]->(c) RETURN c.name")
            .expect("selective path");
    let selective = query_adjacency_requirements(&query.parts[0].query);
    assert!(!selective.outgoing);
    assert!(!selective.incoming);

    let query = parse_query("MATCH (a:Person)-[:KNOWS]->(b) RETURN b.name").expect("broad path");
    let broad = query_adjacency_requirements(&query.parts[0].query);
    assert!(broad.outgoing);
    assert!(!broad.incoming);
}

#[test]
fn order_by_desc_skip_limit() {
    let t = run("MATCH (n:Person) RETURN n.name AS name ORDER BY n.age DESC SKIP 1 LIMIT 1");
    assert_eq!(t.columns, vec!["name".to_string()]);
    assert_eq!(t.rows, vec![vec![Value::from("Alan")]]);
}

#[test]
fn distinct_dedups() {
    let t = run("MATCH (n:Person) RETURN DISTINCT n.label");
    assert_eq!(t.rows, vec![vec![Value::from("Person")]]);
}

#[test]
fn return_star_lists_bound_variables() {
    let t = run("MATCH (n:Person {name:'Ada'}) RETURN *");
    assert_eq!(t.columns, vec!["n".to_string()]);
    assert_eq!(t.rows.len(), 1);
}

#[test]
fn parameters_bind() {
    let mut params = CypherParameters::new();
    params.insert("min".to_string(), Value::Int(40));
    let t = run_read_query(
        &graph(),
        "MATCH (n:Person) WHERE n.age >= $min RETURN n.name",
        &params,
    )
    .unwrap();
    assert_eq!(t.rows.len(), 2);
}

#[test]
fn null_comparison_is_unknown_and_filters() {
    // p? has no `age`; comparison yields NULL -> row filtered.
    let t = run("MATCH (n:City) WHERE n.population > 0 RETURN n.name");
    assert!(t.rows.is_empty());
}

#[test]
fn is_null_predicate() {
    let t = run("MATCH (n) WHERE n.population IS NULL RETURN n.name ORDER BY n.name");
    // all 4 nodes lack `population`
    assert_eq!(t.rows.len(), 4);
}

#[test]
fn arithmetic_projection() {
    let t = run("MATCH (n:Person {name:'Ada'}) RETURN n.age + 4");
    assert_eq!(t.rows, vec![vec![Value::Int(40)]]);
}

#[test]
fn variable_length_paths() {
    let t = run("MATCH (a:Person {name:'Ada'})-[:KNOWS*1..2]->(b) RETURN b.name ORDER BY b.name");
    assert_eq!(
        t.rows.iter().map(|r| r[0].clone()).collect::<Vec<_>>(),
        vec![Value::from("Alan"), Value::from("Grace")]
    );
}

#[test]
fn variable_length_exact_bound() {
    let t = run("MATCH (a:Person {name:'Ada'})-[:KNOWS*2..2]->(b) RETURN b.name");
    assert_eq!(t.rows, vec![vec![Value::from("Grace")]]);
}

#[test]
fn variable_length_binds_edge_list() {
    let t = run(
        "MATCH (a:Person {name:'Ada'})-[r:KNOWS*1..2]->(b) RETURN b.name AS name, size(r) AS hops ORDER BY name",
    );
    assert_eq!(
        t.rows,
        vec![
            vec![Value::from("Alan"), Value::Int(1)],
            vec![Value::from("Grace"), Value::Int(2)],
        ]
    );
}

#[test]
fn path_variable_length_and_nodes() {
    let t = run("MATCH p = (:Person {name:'Ada'})-[:KNOWS]->(:Person) RETURN length(p) AS len");
    assert_eq!(t.rows, vec![vec![Value::Int(1)]]);
    // nodes(p) returns the 2 nodes on the path.
    let t = run("MATCH p = (:Person {name:'Ada'})-[:KNOWS]->(b:Person) RETURN size(nodes(p)) AS n");
    assert_eq!(t.rows, vec![vec![Value::Int(2)]]);
}

#[test]
fn path_variable_returns_first_class_path_value() {
    let t = run("MATCH p = (:Person {name:'Ada'})-[:KNOWS]->(b:Person) RETURN p");
    let Value::Path(path) = &t.rows[0][0] else {
        panic!("expected Value::Path, got {:?}", t.rows[0][0]);
    };
    assert_eq!(path.nodes.len(), 2);
    assert_eq!(path.relationships.len(), 1);
    assert_eq!(path.nodes[0]["props"]["name"], Value::from("Ada").to_json());

    let json = t.rows[0][0].to_json();
    assert!(json.get("nodes").is_some());
    assert!(json.get("relationships").is_some());
}

#[test]
fn path_variable_two_hop() {
    let t =
        run("MATCH p = (:Person {name:'Ada'})-[:KNOWS]->()-[:KNOWS]->() RETURN length(p) AS len");
    assert_eq!(t.rows, vec![vec![Value::Int(2)]]);
}

#[test]
fn path_variable_over_var_length_rejected() {
    let err = run_read_query(
        &graph(),
        "MATCH p = (:Person {name:'Ada'})-[:KNOWS*1..2]->(b) RETURN p",
        &CypherParameters::new(),
    )
    .unwrap_err();
    assert!(matches!(err, GrustError::Unsupported(_)));
}

#[test]
fn range_with_unwind() {
    let t = run("UNWIND range(1, 3) AS x RETURN x");
    assert_eq!(
        t.rows,
        vec![
            vec![Value::Int(1)],
            vec![Value::Int(2)],
            vec![Value::Int(3)]
        ]
    );
}

#[test]
fn head_and_last_over_collect() {
    let t = run(
        "MATCH (n:Person) WITH collect(n.name) AS names RETURN head(names) AS h, last(names) AS l",
    );
    assert_eq!(t.rows, vec![vec![Value::from("Ada"), Value::from("Grace")]]);
}

#[test]
fn labels_type_id() {
    assert_eq!(
        run("MATCH (n:Person {name:'Ada'}) RETURN labels(n)").rows,
        vec![vec![Value::StringArray(vec!["Person".to_string()])]]
    );
    assert_eq!(
        run("MATCH (:Person {name:'Ada'})-[r:KNOWS]->() RETURN type(r)").rows,
        vec![vec![Value::from("KNOWS")]]
    );
    assert_eq!(
        run("MATCH (n:Person {name:'Ada'}) RETURN id(n)").rows,
        vec![vec![Value::from("p1")]]
    );
}

#[test]
fn map_literals_and_indexing_evaluate() {
    let t = run("MATCH (n:Person {name:'Ada'}) RETURN {name: n.name, older: n.age + 4} AS m");
    assert_eq!(
        t.rows,
        vec![vec![Value::Json(serde_json::json!({
            "name": "Ada",
            "older": 40
        }))]]
    );
    // Map key lookup on the literal; missing keys are NULL.
    let t = run("MATCH (n:Person {name:'Ada'}) RETURN {a: 1}['a'] AS hit, {a: 1}['b'] AS miss");
    assert_eq!(t.rows, vec![vec![Value::Int(1), Value::Null]]);
    // List indexing: 0-based, negative from the end, out of range -> NULL.
    let t = run("UNWIND [[10, 20, 30]] AS xs RETURN xs[0], xs[-1], xs[9]");
    assert_eq!(
        t.rows,
        vec![vec![Value::Int(10), Value::Int(30), Value::Null]]
    );
    // Indexing a non-list is a structured type error.
    let err = run_read_query(
        &graph(),
        "MATCH (n:Person) RETURN n.age[0]",
        &CypherParameters::new(),
    )
    .unwrap_err();
    assert!(err.to_string().contains("gql:type"));
}

#[test]
fn return_distinct_with_order_by() {
    let t = run("MATCH (n) RETURN DISTINCT n.label AS l ORDER BY l DESC");
    assert_eq!(
        t.rows,
        vec![vec![Value::from("Person")], vec![Value::from("City")]]
    );
    // The key may also be the projected expression itself.
    let t = run("MATCH (n) RETURN DISTINCT n.label ORDER BY n.label");
    assert_eq!(
        t.rows,
        vec![vec![Value::from("City")], vec![Value::from("Person")]]
    );
    // A non-projected key is a structured error.
    let err = run_read_query(
        &graph(),
        "MATCH (n:Person) RETURN DISTINCT n.label ORDER BY n.age",
        &CypherParameters::new(),
    )
    .unwrap_err();
    assert!(err.to_string().contains("must reference a projected item"));
}

#[test]
fn star_with_aggregates_groups_by_bound_variables() {
    let t = run("MATCH (n:Person) RETURN *, count(*) AS c");
    // n is the grouping key: three distinct persons, one row each.
    assert_eq!(t.columns, vec!["n".to_string(), "c".to_string()]);
    assert_eq!(t.rows.len(), 3);
    assert!(t.rows.iter().all(|r| r[1] == Value::Int(1)));
    let t = run(
        "MATCH (a:Person)-[:KNOWS]->(b) WITH *, count(*) AS c RETURN a.name, c ORDER BY a.name",
    );
    assert_eq!(t.rows.len(), 2);
}

#[test]
fn multi_label_patterns_are_conjunctive() {
    // Distinct labels can never both hold on a single-label node: empty.
    let t = run("MATCH (n:Person:City) RETURN n.name");
    assert!(t.rows.is_empty());
    // A repeated label is satisfied.
    let t = run("MATCH (n:Person:Person {name:'Ada'}) RETURN n.name");
    assert_eq!(t.rows, vec![vec![Value::from("Ada")]]);
}

#[test]
fn union_all_concatenates() {
    let t = run(
        "MATCH (n:Person {name:'Ada'}) RETURN n.name AS x UNION ALL MATCH (m:City) RETURN m.name AS x",
    );
    assert_eq!(t.columns, vec!["x".to_string()]);
    assert_eq!(t.rows.len(), 2);
}

#[test]
fn union_deduplicates() {
    // The same row from both arms collapses under UNION (distinct).
    let t = run(
        "MATCH (n:Person {name:'Ada'}) RETURN n.label AS l UNION MATCH (m:Person {name:'Alan'}) RETURN m.label AS l",
    );
    assert_eq!(t.rows, vec![vec![Value::from("Person")]]);
}

#[test]
fn union_all_keeps_duplicates() {
    let t = run(
        "MATCH (n:Person {name:'Ada'}) RETURN n.label AS l UNION ALL MATCH (m:Person {name:'Alan'}) RETURN m.label AS l",
    );
    assert_eq!(t.rows.len(), 2);
}

#[test]
fn union_mismatched_columns_rejected() {
    let err = run_read_query(
        &graph(),
        "MATCH (n:Person) RETURN n.name AS a UNION MATCH (m:City) RETURN m.name AS b",
        &CypherParameters::new(),
    )
    .unwrap_err();
    assert!(matches!(err, GrustError::CypherUnresolvedIdentity(_)));
}

#[test]
fn with_carry_and_filter() {
    let t = run("MATCH (n:Person) WITH n WHERE n.age > 40 RETURN n.name ORDER BY n.name");
    assert_eq!(
        t.rows.iter().map(|r| r[0].clone()).collect::<Vec<_>>(),
        vec![Value::from("Alan"), Value::from("Grace")]
    );
}

#[test]
fn with_computed_alias() {
    let t = run("MATCH (n:Person) WITH n.age AS age WHERE age >= 40 RETURN age ORDER BY age");
    assert_eq!(t.rows, vec![vec![Value::Int(41)], vec![Value::Int(85)]]);
}

#[test]
fn with_aggregate_then_return() {
    let t = run("MATCH (n) WITH n.label AS label, count(*) AS c RETURN label, c ORDER BY label");
    assert_eq!(
        t.rows,
        vec![
            vec![Value::from("City"), Value::Int(1)],
            vec![Value::from("Person"), Value::Int(3)],
        ]
    );
}

#[test]
fn with_order_limit_horizon() {
    let t = run("MATCH (n:Person) WITH n ORDER BY n.age DESC LIMIT 1 RETURN n.name");
    assert_eq!(t.rows, vec![vec![Value::from("Grace")]]);
}

#[test]
fn with_carries_node_into_later_match() {
    let t = run("MATCH (a:Person {name:'Ada'}) WITH a MATCH (a)-[:KNOWS]->(b) RETURN b.name");
    assert_eq!(t.rows, vec![vec![Value::from("Alan")]]);
}

#[test]
fn optional_match_null_pads() {
    let t = run(
        "MATCH (a:Person) OPTIONAL MATCH (a)-[:KNOWS]->(b) RETURN a.name, b.name ORDER BY a.name",
    );
    assert_eq!(
        t.rows,
        vec![
            vec![Value::from("Ada"), Value::from("Alan")],
            vec![Value::from("Alan"), Value::from("Grace")],
            vec![Value::from("Grace"), Value::Null],
        ]
    );
}

#[test]
fn optional_match_where_excludes_all_null_pads() {
    let t = run(
        "MATCH (a:Person {name:'Ada'}) OPTIONAL MATCH (a)-[:KNOWS]->(b) WHERE b.name = 'Zzz' RETURN b.name",
    );
    assert_eq!(t.rows, vec![vec![Value::Null]]);
}

#[test]
fn unwind_list() {
    let t = run("UNWIND [1, 2, 3] AS x RETURN x");
    assert_eq!(
        t.rows,
        vec![
            vec![Value::Int(1)],
            vec![Value::Int(2)],
            vec![Value::Int(3)]
        ]
    );
}

#[test]
fn unwind_cross_product_with_match() {
    let t = run("MATCH (n:Person) UNWIND [1, 2] AS k RETURN n.name, k");
    assert_eq!(t.rows.len(), 6);
}

#[test]
fn searched_case_expression() {
    let t = run(
        "MATCH (n:Person) RETURN CASE WHEN n.age >= 80 THEN 'senior' WHEN n.age >= 40 THEN 'mid' ELSE 'young' END AS bucket ORDER BY n.name",
    );
    assert_eq!(
        t.rows.iter().map(|r| r[0].clone()).collect::<Vec<_>>(),
        vec![
            Value::from("young"),
            Value::from("mid"),
            Value::from("senior")
        ]
    );
}

#[test]
fn simple_case_expression() {
    let t = run(
        "MATCH (n:Person {name:'Ada'}) RETURN CASE n.age WHEN 36 THEN 'yes' ELSE 'no' END AS m",
    );
    assert_eq!(t.rows, vec![vec![Value::from("yes")]]);
}

#[test]
fn case_without_else_is_null() {
    let t = run("MATCH (n:Person {name:'Ada'}) RETURN CASE WHEN n.age > 100 THEN 'old' END AS m");
    assert_eq!(t.rows, vec![vec![Value::Null]]);
}

#[test]
fn unbound_variable_rejected_by_semantics() {
    let err = run_read_query(
        &graph(),
        "MATCH (n:Person) RETURN m.name",
        &CypherParameters::new(),
    )
    .unwrap_err();
    assert!(matches!(err, GrustError::CypherUnresolvedIdentity(_)));
}

#[test]
fn executes_against_memory_graph_store() {
    use futures_executor::block_on;
    use grust_memory::MemoryGraphStore;

    let store = MemoryGraphStore::new();
    block_on(async {
        store
            .put_node(&node("Person", "p1", &[("name", Value::from("Ada"))]))
            .await
            .unwrap();
        store
            .put_node(&node("Person", "p2", &[("name", Value::from("Alan"))]))
            .await
            .unwrap();
        store
            .put_edge(&Edge::new("KNOWS", "p1", "p2", Props::new()))
            .await
            .unwrap();
    });

    // The Memory reference executor reads the materialized graph snapshot.
    let snapshot = store.graph();
    let table = run_read_query(
        &snapshot,
        "MATCH (a:Person {name: 'Ada'})-[:KNOWS]->(b:Person) RETURN b.name AS friend",
        &CypherParameters::new(),
    )
    .unwrap();
    assert_eq!(table.columns, vec!["friend".to_string()]);
    assert_eq!(table.rows, vec![vec![Value::from("Alan")]]);
}

#[test]
fn count_star() {
    let t = run("MATCH (n:Person) RETURN count(*)");
    assert_eq!(t.rows, vec![vec![Value::Int(3)]]);
}

#[test]
fn count_over_empty_match_is_zero() {
    let t = run("MATCH (n:Nonexistent) RETURN count(*)");
    assert_eq!(t.rows, vec![vec![Value::Int(0)]]);
}

#[test]
fn min_max_avg() {
    let t = run("MATCH (n:Person) RETURN min(n.age) AS lo, max(n.age) AS hi");
    assert_eq!(t.columns, vec!["lo".to_string(), "hi".to_string()]);
    assert_eq!(t.rows, vec![vec![Value::Int(36), Value::Int(85)]]);
}

#[test]
fn group_by_label_with_count() {
    let t = run("MATCH (n) RETURN n.label AS label, count(*) AS c ORDER BY label");
    assert_eq!(
        t.rows,
        vec![
            vec![Value::from("City"), Value::Int(1)],
            vec![Value::from("Person"), Value::Int(3)],
        ]
    );
}

#[test]
fn count_property_skips_nulls() {
    // No Person has `population`, so count(n.population) == 0.
    let t = run("MATCH (n:Person) RETURN count(n.population)");
    assert_eq!(t.rows, vec![vec![Value::Int(0)]]);
}

#[test]
fn collect_gathers_values() {
    let t = run("MATCH (n:Person) RETURN collect(n.name) AS names");
    assert_eq!(t.rows.len(), 1);
    match &t.rows[0][0] {
        Value::Json(serde_json::Value::Array(items)) => assert_eq!(items.len(), 3),
        other => panic!("expected a list, got {other:?}"),
    }
}

#[test]
fn count_distinct() {
    let t = run("MATCH (n) RETURN count(DISTINCT n.label) AS kinds");
    assert_eq!(t.rows, vec![vec![Value::Int(2)]]);
}

#[test]
fn scalar_string_functions() {
    let t = run("MATCH (n:Person {name:'Ada'}) RETURN toUpper(n.name) AS u, size(n.name) AS s");
    assert_eq!(t.rows, vec![vec![Value::from("ADA"), Value::Int(3)]]);
}

#[test]
fn scalar_numeric_functions() {
    let t = run("MATCH (n:Person {name:'Ada'}) RETURN abs(0 - n.age) AS a, toString(n.age) AS s");
    assert_eq!(t.rows, vec![vec![Value::Int(36), Value::from("36")]]);
}

#[test]
fn coalesce_picks_first_non_null() {
    let t = run("MATCH (n:Person {name:'Ada'}) RETURN coalesce(n.population, n.age, 0) AS c");
    assert_eq!(t.rows, vec![vec![Value::Int(36)]]);
}

#[test]
fn scalar_function_null_propagates() {
    let t = run("MATCH (n:Person {name:'Ada'}) RETURN toUpper(n.population) AS u");
    assert_eq!(t.rows, vec![vec![Value::Null]]);
}

#[test]
fn scalar_in_where_filters() {
    let t = run("MATCH (n:Person) WHERE toUpper(n.name) = 'ADA' RETURN n.name");
    assert_eq!(t.rows, vec![vec![Value::from("Ada")]]);
}

#[test]
fn graph_constructor_builds_first_class_graph_value() {
    let t = run(
        "MATCH (a:Person)-[r:KNOWS]->(b:Person) WITH collect(a) AS ns, collect(r) AS rs RETURN graph(ns, rs) AS g",
    );
    let Value::Graph(g) = &t.rows[0][0] else {
        panic!("expected Value::Graph, got {:?}", t.rows[0][0]);
    };
    // Two KNOWS edges (p1->p2, p2->p3); start nodes p1, p2 deduplicate.
    assert_eq!(g.nodes.len(), 2);
    assert_eq!(g.relationships.len(), 2);

    let json = t.rows[0][0].to_json();
    assert!(json.get("nodes").is_some());
    assert!(json.get("relationships").is_some());
}

#[test]
fn graph_value_deduplicates_repeated_elements() {
    // Every KNOWS edge contributes its start node; collecting the same node
    // twice still yields a set-shaped graph value.
    let t = run(
        "MATCH (a:Person {name:'Ada'})-[r:KNOWS]->(b) WITH collect(a) AS ns RETURN graph(ns, null) AS g",
    );
    let Value::Graph(g) = &t.rows[0][0] else {
        panic!("expected Value::Graph");
    };
    assert_eq!(g.nodes.len(), 1);
    assert!(g.relationships.is_empty());
}

#[test]
fn graph_value_nodes_and_relationships_accessors() {
    let t = run(
        "MATCH (a:Person)-[r:KNOWS]->(b:Person) WITH collect(a) AS ns, collect(r) AS rs WITH graph(ns, rs) AS g RETURN size(nodes(g)) AS n, size(relationships(g)) AS r",
    );
    assert_eq!(t.rows, vec![vec![Value::Int(2), Value::Int(2)]]);
}

#[test]
fn graph_constructor_rejects_non_list_arguments() {
    let err = run_read_query(
        &graph(),
        "MATCH (n:Person {name:'Ada'}) RETURN graph(n.age, null)",
        &CypherParameters::new(),
    )
    .unwrap_err();
    assert!(err.to_string().contains("gql:type"));
}

#[test]
fn shortest_path_finds_minimal_route() {
    // p1 -KNOWS-> p2 -KNOWS-> p3; add a direct long-way-around check by
    // asking for the Ada -> Grace shortest path: exactly 2 hops.
    let t = run(
        "MATCH p = shortestPath((a:Person {name:'Ada'})-[:KNOWS*]->(b:Person {name:'Grace'})) RETURN length(p) AS len",
    );
    assert_eq!(t.rows, vec![vec![Value::Int(2)]]);
}

#[test]
fn shortest_path_prefers_direct_edge() {
    // Diamond with a shortcut: s -> m1 -> t and s -> t.
    let nodes = vec![
        node("N", "s", &[]),
        node("N", "m1", &[]),
        node("N", "t", &[]),
    ];
    let edges = vec![
        Edge::new("R", "s", "m1", Props::new()),
        Edge::new("R", "m1", "t", Props::new()),
        Edge::new("R", "s", "t", Props::new()),
    ];
    let g = Graph::new(nodes, edges);
    let t = run_read_query(
        &g,
        "MATCH p = shortestPath((a:N {id:'s'})-[:R*]->(b:N {id:'t'})) RETURN length(p) AS len",
        &CypherParameters::new(),
    )
    .unwrap();
    assert_eq!(t.rows, vec![vec![Value::Int(1)]]);
}

#[test]
fn all_shortest_paths_keeps_ties() {
    // Two distinct 2-hop routes s -> {m1|m2} -> t and no direct edge.
    let nodes = vec![
        node("N", "s", &[]),
        node("N", "m1", &[]),
        node("N", "m2", &[]),
        node("N", "t", &[]),
    ];
    let edges = vec![
        Edge::new("R", "s", "m1", Props::new()),
        Edge::new("R", "s", "m2", Props::new()),
        Edge::new("R", "m1", "t", Props::new()),
        Edge::new("R", "m2", "t", Props::new()),
    ];
    let g = Graph::new(nodes, edges);
    let all = run_read_query(
        &g,
        "MATCH p = allShortestPaths((a:N {id:'s'})-[:R*]->(b:N {id:'t'})) RETURN length(p) AS len",
        &CypherParameters::new(),
    )
    .unwrap();
    assert_eq!(all.rows, vec![vec![Value::Int(2)], vec![Value::Int(2)]]);
    // shortestPath keeps exactly one of the ties.
    let single = run_read_query(
        &g,
        "MATCH p = shortestPath((a:N {id:'s'})-[:R*]->(b:N {id:'t'})) RETURN length(p) AS len",
        &CypherParameters::new(),
    )
    .unwrap();
    assert_eq!(single.rows, vec![vec![Value::Int(2)]]);
}

#[test]
fn shortest_path_binds_endpoints_and_relationships() {
    let t = run(
        "MATCH shortestPath((a:Person {name:'Ada'})-[r:KNOWS*]->(b:Person {name:'Grace'})) RETURN a.name, b.name, size(r) AS hops",
    );
    assert_eq!(
        t.rows,
        vec![vec![
            Value::from("Ada"),
            Value::from("Grace"),
            Value::Int(2)
        ]]
    );
}

#[test]
fn shortest_path_without_star_is_one_hop() {
    // `-[:R]->` inside shortestPath means exactly one hop, like every
    // other pattern position; only `*` opens the bound. Ada's only 1-hop
    // KNOWS endpoint is Alan (Grace is 2 hops away and must not appear).
    let t = run("MATCH shortestPath((a:Person {name:'Ada'})-[:KNOWS]->(b:Person)) RETURN b.name");
    assert_eq!(t.rows, vec![vec![Value::from("Alan")]]);
}

#[test]
fn shortest_path_per_endpoint_pair() {
    // Unbound end node: one shortest path per reachable endpoint.
    let t = run(
        "MATCH p = shortestPath((a:Person {name:'Ada'})-[:KNOWS*]->(b:Person)) RETURN b.name, length(p) AS len ORDER BY b.name",
    );
    assert_eq!(
        t.rows,
        vec![
            vec![Value::from("Alan"), Value::Int(1)],
            vec![Value::from("Grace"), Value::Int(2)],
        ]
    );
}

#[test]
fn shortest_path_no_route_yields_no_rows() {
    let t = run(
        "MATCH p = shortestPath((a:Person {name:'Grace'})-[:KNOWS*]->(b:City)) RETURN length(p)",
    );
    assert!(t.rows.is_empty());
}

#[test]
fn shortest_path_multi_segment_is_rejected() {
    let err = run_read_query(
        &graph(),
        "MATCH p = shortestPath((a)-[:KNOWS*]->(m)-[:KNOWS*]->(b)) RETURN p",
        &CypherParameters::new(),
    )
    .unwrap_err();
    assert!(matches!(err, GrustError::CypherSyntax(_)));
}

#[test]
fn tvf_range_yields_rows() {
    let t = run("CALL tvf.range(1, 3) YIELD value RETURN value");
    assert_eq!(
        t.rows,
        vec![
            vec![Value::Int(1)],
            vec![Value::Int(2)],
            vec![Value::Int(3)]
        ]
    );
}

#[test]
fn scalar_range_handles_integer_max_without_overflow() {
    let t = run("MATCH (n:City) RETURN range(9223372036854775806, 9223372036854775807) AS values");
    assert_eq!(
        t.rows,
        vec![vec![Value::IntArray(vec![i64::MAX - 1, i64::MAX])]]
    );
}

#[test]
fn scalar_range_rejects_unbounded_allocation_without_a_policy() {
    let error = run_read_query(
        &graph(),
        "MATCH (n:City) RETURN range(0, 9223372036854775807) AS values",
        &CypherParameters::new(),
    )
    .unwrap_err();
    assert!(error.to_string().contains("executor maximum"));
}

#[test]
fn tvf_range_standalone_call_shapes_result() {
    let t = run("CALL tvf.range(1, 2) YIELD value AS v");
    assert_eq!(t.columns, vec!["v".to_string()]);
    assert_eq!(t.rows.len(), 2);
}

#[test]
fn tvf_keys_is_correlated_per_row() {
    // `id` is a real property key: Node::new mirrors the id into props.
    let t = run("MATCH (n:Person {name:'Ada'}) CALL tvf.keys(n) YIELD key RETURN key ORDER BY key");
    assert_eq!(
        t.rows,
        vec![
            vec![Value::from("age")],
            vec![Value::from("id")],
            vec![Value::from("name")]
        ]
    );
}

#[test]
fn tvf_range_with_correlated_argument() {
    // end = n.age - 34 -> Ada (36) yields 1..2.
    let t =
        run("MATCH (n:Person {name:'Ada'}) CALL tvf.range(1, n.age - 34) YIELD value RETURN value");
    assert_eq!(t.rows, vec![vec![Value::Int(1)], vec![Value::Int(2)]]);
}

#[test]
fn catalog_procedure_rejects_arguments() {
    let err = run_read_query(
        &graph(),
        "CALL db.labels('x') YIELD label RETURN label",
        &CypherParameters::new(),
    )
    .unwrap_err();
    assert!(err.to_string().contains("expects no arguments"));
}

#[test]
fn with_distinct_over_computed_alias() {
    // DISTINCT dedups by the produced (post-projection) values; the source
    // expression's variable is out of scope after the horizon.
    let t = run("MATCH (n:Person) WITH DISTINCT n.label AS l RETURN l");
    assert_eq!(t.rows, vec![vec![Value::from("Person")]]);
}

#[test]
fn call_subquery_distinct_computed_return() {
    let t = run(
        "MATCH (a:City) CALL { MATCH (p:Person) RETURN DISTINCT p.label AS l } RETURN a.name, l",
    );
    assert_eq!(
        t.rows,
        vec![vec![Value::from("London"), Value::from("Person")]]
    );
}

#[test]
fn call_subquery_correlated_join() {
    // The outer binding `a` is visible inside; a row whose subquery
    // returns nothing (Grace has no outgoing KNOWS) is dropped.
    let t = run(
        "MATCH (a:Person) CALL { MATCH (a)-[:KNOWS]->(b) RETURN b.name AS friend } RETURN a.name, friend ORDER BY a.name",
    );
    assert_eq!(
        t.rows,
        vec![
            vec![Value::from("Ada"), Value::from("Alan")],
            vec![Value::from("Alan"), Value::from("Grace")],
        ]
    );
}

#[test]
fn call_subquery_uncorrelated_aggregate() {
    let t = run(
        "MATCH (a:Person) CALL { MATCH (c:City) RETURN count(*) AS cities } RETURN a.name, cities ORDER BY a.name",
    );
    assert_eq!(t.rows.len(), 3);
    assert!(t.rows.iter().all(|r| r[1] == Value::Int(1)));
}

#[test]
fn call_subquery_returns_node_binding_for_later_match() {
    // A bare-variable subquery RETURN keeps its node binding, so a later
    // MATCH can extend from it.
    let t = run(
        "CALL { MATCH (a:Person {name:'Ada'}) RETURN a } MATCH (a)-[:KNOWS]->(b) RETURN b.name",
    );
    assert_eq!(t.rows, vec![vec![Value::from("Alan")]]);
}

#[test]
fn call_subquery_union_arms() {
    let t = run(
        "CALL { MATCH (p:Person {name:'Ada'}) RETURN p.name AS n UNION MATCH (c:City) RETURN c.name AS n } RETURN n ORDER BY n",
    );
    assert_eq!(
        t.rows,
        vec![vec![Value::from("Ada")], vec![Value::from("London")]]
    );
}

#[test]
fn call_subquery_column_collision_rejected() {
    let err = run_read_query(
        &graph(),
        "MATCH (a:Person) CALL { MATCH (x:City) RETURN x.name AS a } RETURN a",
        &CypherParameters::new(),
    )
    .unwrap_err();
    assert!(matches!(err, GrustError::CypherUnresolvedIdentity(_)));
    assert!(err.to_string().contains("already bound"));
}

#[test]
fn call_subquery_requires_return() {
    let err = run_read_query(
        &graph(),
        "MATCH (a:Person) CALL { MATCH (c:City) } RETURN a.name",
        &CypherParameters::new(),
    )
    .unwrap_err();
    assert!(err.to_string().contains("must end in RETURN"));
}

#[test]
fn call_subquery_return_star_is_feature_tagged() {
    let err = run_read_query(
        &graph(),
        "MATCH (a:Person) CALL { MATCH (c:City) RETURN * } RETURN a.name",
        &CypherParameters::new(),
    )
    .unwrap_err();
    assert!(matches!(err, GrustError::Unsupported(_)));
}

#[test]
fn unknown_scalar_function_is_feature_tagged() {
    let err = run_read_query(
        &graph(),
        "MATCH (n:Person) RETURN notafunction(n.age)",
        &CypherParameters::new(),
    )
    .unwrap_err();
    assert!(matches!(err, GrustError::Unsupported(_)));
}
