use grust_core::{Graph, Value};
use grust_cypher::{CypherParameters, parser::parse_expression, read::run_read_query};

fn evaluate(expression: &str) -> Value {
    let query = format!("RETURN {expression} AS result");
    run_read_query(&Graph::default(), &query, &CypherParameters::new())
        .unwrap_or_else(|e| panic!("{query}: {e}"))
        .rows
        .remove(0)
        .remove(0)
}

#[test]
fn reduce_empty_null_elements_and_nested_scopes() {
    assert_eq!(evaluate("reduce(s = 12, x IN [] | s + x)"), Value::Int(12));
    assert_eq!(evaluate("reduce(s = 12, x IN null | s + x)"), Value::Null);
    assert_eq!(
        evaluate("reduce(s = 0, x IN [1, null, 3] | s + coalesce(x, 0))"),
        Value::Int(4)
    );
    assert_eq!(
        evaluate("reduce(s = 0, x IN [1, null, 3] | s + x)"),
        Value::Null
    );
    assert_eq!(
        evaluate("reduce(s = 0, x IN [1, 2] | s + reduce(t = x, y IN [3, 4] | t + y))"),
        Value::Int(17)
    );
    assert_eq!(
        evaluate("reduce(s = 0, x IN ['2', '3'] | s + toInteger(x))"),
        Value::Int(5)
    );
}

#[test]
fn reduce_in_aggregate_with_and_where() {
    let result = run_read_query(&Graph::default(),
        "UNWIND [[1, 2], [3, 4]] AS xs WITH reduce(s = 0, x IN xs | s + x) AS total WHERE total > 3 RETURN sum(total) AS result",
        &CypherParameters::new()).unwrap();
    assert_eq!(result.rows, vec![vec![Value::Int(7)]]);
    let result = run_read_query(
        &Graph::default(),
        "UNWIND [[1, 2], [3, 4]] AS xs RETURN sum(reduce(s = 0, x IN xs | s + x)) AS result",
        &CypherParameters::new(),
    )
    .unwrap();
    assert_eq!(result.rows, vec![vec![Value::Int(10)]]);
}

#[test]
fn reduce_rejects_shadowing_unbound_names_and_types() {
    for (query, expected) in [
        (
            "WITH 1 AS x RETURN reduce(s = 0, x IN [1] | s + x)",
            "shadows",
        ),
        ("RETURN reduce(s = 0, s IN [1] | s)", "shadows"),
        (
            "RETURN reduce(s = 0, x IN [1] | reduce(t = 0, x IN [1] | t + x))",
            "shadows",
        ),
        ("RETURN reduce(s = 0, x IN [1] | missing)", "not bound"),
        ("RETURN reduce(s = 0, x IN [1] | x), x", "not bound"),
        ("RETURN reduce(s = 0, x IN s | x)", "not bound"),
        ("RETURN reduce(s = 0, x IN 7 | s + x)", "expects a list"),
        (
            "RETURN reduce(s = 0, x IN [1] | 'wrong')",
            "differs from seed",
        ),
        (
            "RETURN reduce(s = 0, x IN ['wrong'] | s + x)",
            "numeric operands",
        ),
    ] {
        let error = run_read_query(&Graph::default(), query, &CypherParameters::new()).unwrap_err();
        assert!(error.to_string().contains(expected), "{query}: {error}");
    }
}

#[test]
fn malformed_reduce_names_the_form() {
    for expression in [
        "reduce(s 0, x IN [] | s)",
        "reduce(s = 0 x IN [] | s)",
        "reduce(s = 0, x [] | s)",
        "reduce(s = 0, x IN [] s)",
        "reduce(s = 0, x IN [] |)",
    ] {
        let error = parse_expression(expression).unwrap_err();
        assert!(error.message.contains("reduce"), "{expression}: {error:?}");
    }
}

#[test]
fn reduce_declines_pushdown_even_inside_return() {
    use grust_cypher::pushdown::{NoTypeHints, plan_node_read, plan_read};
    for query in [
        "MATCH (n:N) RETURN reduce(s = 0, x IN [1, 2] | s + x)",
        "MATCH (n:N) WHERE reduce(s = 0, x IN [1] | s + x) > 0 RETURN n",
        "MATCH (n:N) RETURN coalesce(reduce(s = 0, x IN [1] | s + x), 0)",
    ] {
        assert!(
            plan_read(query, &CypherParameters::new(), &NoTypeHints)
                .unwrap()
                .is_none()
        );
        assert!(
            plan_node_read(query, &CypherParameters::new())
                .unwrap()
                .is_none()
        );
    }
}

#[test]
fn reduce_budget_fails_inside_fold() {
    use grust_cypher::{ReadQueryPolicy, run_bounded_read_query};
    let params = CypherParameters::from([("xs".into(), Value::IntArray(vec![1; 100]))]);
    let policy = ReadQueryPolicy {
        require_match: false,
        max_candidate_work: 10,
        ..Default::default()
    };
    let error = run_bounded_read_query(
        &Graph::default(),
        "RETURN reduce(s = 0, x IN $xs | s + x) AS result LIMIT 1",
        &params,
        &policy,
    )
    .unwrap_err();
    assert!(
        error.to_string().contains("evaluating reduce element"),
        "{error}"
    );
}

#[test]
fn comprehension_optional_clauses_nulls_and_nested_scopes() {
    for (expression, expected) in [
        ("[x IN [1, 2, null]]", serde_json::json!([1, 2, null])),
        ("[x IN [1, 2, null] WHERE x > 1]", serde_json::json!([2])),
        ("[x IN [1, 2] | x * 2]", serde_json::json!([2, 4])),
        (
            "[x IN [1, 2, 3] WHERE x > 1 | x * 2]",
            serde_json::json!([4, 6]),
        ),
        ("[x IN [] | 1 / 0]", serde_json::json!([])),
        ("[x IN [null] WHERE null | 1 / 0]", serde_json::json!([])),
        (
            "[x IN [[1, 2], [3]] | reduce(s = 0, y IN x | s + y)]",
            serde_json::json!([3, 3]),
        ),
        ("[x IN [{xs: [2, 3]}] | x.xs[1]]", serde_json::json!([3])),
    ] {
        assert_eq!(evaluate(expression).to_json(), expected, "{expression}");
    }
    assert_eq!(evaluate("[x IN null | x]"), Value::Null);
}

#[test]
fn comprehension_rejects_bad_scope_types_and_syntax() {
    for (query, expected) in [
        ("WITH 1 AS x RETURN [x IN [1] | x]", "shadows"),
        ("RETURN [x IN [1] | [x IN [2] | x]]", "shadows"),
        ("RETURN [x IN [1] | missing]", "not bound"),
        ("RETURN [x IN [1]], x", "not bound"),
        ("RETURN [x IN 1]", "expects a list"),
        ("RETURN [x IN [1] WHERE x]", "boolean"),
    ] {
        let error = run_read_query(&Graph::default(), query, &CypherParameters::new()).unwrap_err();
        assert!(error.to_string().contains(expected), "{query}: {error}");
    }
    for expression in [
        "[x IN ]",
        "[x IN [] WHERE ]",
        "[x IN [] | ]",
        "[x IN [] WHERE true | x",
    ] {
        let error = parse_expression(expression).unwrap_err();
        assert!(
            error.message.contains("list comprehension"),
            "{expression}: {error:?}"
        );
    }
}

#[test]
fn quantifiers_accept_general_lists_predicates_and_three_valued_logic() {
    for (expression, expected) in [
        ("any(x IN [1, 2, 3] WHERE x > 2)", Value::Bool(true)),
        ("all(x IN [1, 2, 3] WHERE x > 0)", Value::Bool(true)),
        ("none(x IN [1, 2, 3] WHERE x < 0)", Value::Bool(true)),
        ("single(x IN [1, 2, 3] WHERE x > 2)", Value::Bool(true)),
        ("any(x IN [] WHERE x)", Value::Bool(false)),
        ("all(x IN [] WHERE x)", Value::Bool(true)),
        ("none(x IN [] WHERE x)", Value::Bool(true)),
        ("single(x IN [] WHERE x)", Value::Bool(false)),
        ("any(x IN null WHERE x)", Value::Null),
        ("any(x IN [null, false] WHERE x)", Value::Null),
        ("any(x IN [null, true] WHERE x)", Value::Bool(true)),
        ("all(x IN [null, false] WHERE x)", Value::Bool(false)),
        ("all(x IN [null, true] WHERE x)", Value::Null),
        ("none(x IN [null, true] WHERE x)", Value::Bool(false)),
        ("single(x IN [null, true] WHERE x)", Value::Null),
        (
            "single(x IN [null, true, true] WHERE x)",
            Value::Bool(false),
        ),
        (
            "all(x IN [1, 2] WHERE any(y IN [x, x + 1] WHERE y > x))",
            Value::Bool(true),
        ),
    ] {
        assert_eq!(evaluate(expression), expected, "{expression}");
    }
}
