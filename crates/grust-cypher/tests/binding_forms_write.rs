use grust_core::Value;
use grust_cypher::{
    CypherMutationOptions, CypherParameters,
    execute_cypher_mutation_returning_with_options_on_store,
};
use grust_memory::MemoryGraphStore;

#[test]
fn write_returns_use_general_scope_for_all_forms_and_multiple_variables() {
    let store = MemoryGraphStore::new();
    let result = futures_executor::block_on(execute_cypher_mutation_returning_with_options_on_store(
        &store,
        "CREATE (a:N {id:'a', xs: $xs}); CREATE (b:N {id:'b', offset: 10}) RETURN reduce(s = b.offset, x IN a.xs | s + x) AS folded, [x IN a.xs WHERE x > 1 | x + b.offset] AS mapped, all(x IN a.xs WHERE x < b.offset) AS checked",
        CypherMutationOptions { parameters: CypherParameters::from([
            ("xs".into(), Value::IntArray(vec![1,2])),
            ("ys".into(), Value::IntArray(vec![3,4])),
        ]), ..Default::default() },
    )).unwrap();
    assert_eq!(
        result.table.rows,
        vec![vec![
            Value::Int(13),
            Value::Json(serde_json::json!([12])),
            Value::Bool(true)
        ]]
    );
}

#[test]
fn write_aggregate_folds_every_materialized_row() {
    let store = MemoryGraphStore::new();
    let result = futures_executor::block_on(execute_cypher_mutation_returning_with_options_on_store(
        &store,
        "CREATE (:N {id:'a', xs:$xs}); CREATE (:N {id:'b', xs:$ys}); MATCH (n:N) SET n.checked = true RETURN sum(reduce(s = 0, x IN n.xs | s + x)) AS total, collect([x IN n.xs | x * 2]) AS doubled",
        CypherMutationOptions { parameters: CypherParameters::from([
            ("xs".into(), Value::IntArray(vec![1,2])),
            ("ys".into(), Value::IntArray(vec![3,4])),
        ]), ..Default::default() },
    )).unwrap();
    assert_eq!(result.table.rows[0][0], Value::Int(10));
    let mut lists = result.table.rows[0][1]
        .to_json()
        .as_array()
        .unwrap()
        .clone();
    lists.sort_by_key(|v| v.to_string());
    assert_eq!(
        lists,
        vec![serde_json::json!([2, 4]), serde_json::json!([6, 8])]
    );
}

#[test]
fn legacy_write_quantifiers_keep_exact_equality_and_null_contract() {
    let store = MemoryGraphStore::new();
    let result = futures_executor::block_on(execute_cypher_mutation_returning_with_options_on_store(
        &store,
        "CREATE (n:N {id:'compat', xs:$xs, empty:$empty, ints:$ints}) RETURN any(x IN n.xs WHERE x = 2) AS absent, all(x IN n.xs WHERE x = 1) AS every, any(x IN n.empty WHERE x = null) AS null_empty, any(x IN n.ints WHERE x = 1.0) AS exact",
        CypherMutationOptions {
            parameters: CypherParameters::from([
                ("xs".into(), Value::Json(serde_json::json!([1,null]))),
                ("empty".into(), Value::IntArray(vec![])),
                ("ints".into(), Value::IntArray(vec![1])),
            ]),
            ..Default::default()
        },
    )).unwrap();
    assert_eq!(
        result.table.rows,
        vec![vec![
            Value::Bool(false),
            Value::Bool(false),
            Value::Null,
            Value::Bool(false)
        ]]
    );
}

#[test]
fn write_binding_shadowing_is_rejected_before_execution() {
    let store = MemoryGraphStore::new();
    let error =
        futures_executor::block_on(execute_cypher_mutation_returning_with_options_on_store(
            &store,
            "CREATE (n:N {id:'shadow'}) RETURN [n IN [1] | n]",
            CypherMutationOptions::default(),
        ))
        .unwrap_err();
    assert!(error.to_string().contains("shadows"), "{error}");
}

#[test]
fn existing_quantifier_rhs_string_functions_keep_working() {
    let store = MemoryGraphStore::new();
    let result = futures_executor::block_on(execute_cypher_mutation_returning_with_options_on_store(
        &store,
        "CREATE (n:N {id:'strings', xs:$xs, marker:'speaker'}) RETURN any(x IN n.xs WHERE x = left(n.marker, 3)), any(x IN n.xs WHERE x = substring(n.marker, 0, 3)), any(x IN n.xs WHERE x = replace(n.marker, 'aker', ''))",
        CypherMutationOptions { parameters: CypherParameters::from([("xs".into(), Value::StringArray(vec!["spe".into()]))]), ..Default::default() },
    )).unwrap();
    assert_eq!(result.table.rows, vec![vec![Value::Bool(true); 3]]);
}

fn write_return(statement: &str) -> grust_core::Result<Vec<Vec<Value>>> {
    let store = MemoryGraphStore::new();
    futures_executor::block_on(execute_cypher_mutation_returning_with_options_on_store(
        &store,
        statement,
        CypherMutationOptions {
            parameters: CypherParameters::from([("xs".into(), Value::IntArray(vec![1, 2]))]),
            ..Default::default()
        },
    ))
    .map(|result| result.table.rows)
}

#[test]
fn malformed_write_forms_name_the_form() {
    for (statement, form) in [
        (
            "CREATE (n:N {id:'x'}) RETURN reduce(s = 0, x IN [1])",
            "reduce:",
        ),
        (
            "CREATE (n:N {id:'x'}) RETURN [x IN [1] WHERE ]",
            "list comprehension:",
        ),
        ("CREATE (n:N {id:'x'}) RETURN any(x IN [1])", "quantifier:"),
    ] {
        let error = write_return(statement).unwrap_err().to_string();
        assert!(error.contains(form), "{statement}: {error}");
    }
}

#[test]
fn write_forms_compose_with_grouping_distinct_ordering_and_enclosing_expressions() {
    const TWO: &str = "CREATE (:N {id:'a', g:'k', xs:$xs}); CREATE (:N {id:'b', g:'k', xs:$xs}); MATCH (n:N) SET n.c = 1 ";
    assert_eq!(
        write_return(&format!(
            "{TWO}RETURN n.g AS g, sum(reduce(s = 0, x IN n.xs | s + x)) AS t"
        ))
        .unwrap(),
        vec![vec![Value::from("k"), Value::Int(6)]]
    );
    assert_eq!(
        write_return(&format!("{TWO}RETURN DISTINCT [x IN n.xs | x + 1] AS ys")).unwrap(),
        vec![vec![Value::Json(serde_json::json!([2, 3]))]]
    );
    assert_eq!(
        write_return(&format!("{TWO}RETURN n.id AS id, reduce(s = 0, x IN n.xs | s + x) AS t ORDER BY t DESC, id LIMIT 1")).unwrap(),
        vec![vec![Value::from("a"), Value::Int(3)]]
    );
    assert_eq!(
        write_return("CREATE (n:N {id:'x', xs:$xs}) RETURN size([x IN n.xs WHERE x > 1]) AS c, reduce(s = 0, x IN $xs | s + x) + 1 AS d, n.id").unwrap(),
        vec![vec![Value::Int(1), Value::Int(4), Value::from("x")]]
    );
}
