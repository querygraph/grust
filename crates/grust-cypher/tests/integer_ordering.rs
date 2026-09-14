use grust_core::{Graph, Value};
use grust_cypher::{CypherParameters, read::run_read_query};

#[test]
fn integer_ordering_preserves_adjacent_values_above_float_precision() {
    let graph = Graph::new(vec![], vec![]);
    for (a, b) in [
        (9_007_199_254_740_992_i64, 9_007_199_254_740_993_i64),
        (i64::MAX - 1, i64::MAX),
        (i64::MIN, i64::MIN + 1),
    ] {
        let params =
            CypherParameters::from([("a".into(), Value::Int(a)), ("b".into(), Value::Int(b))]);
        let table = run_read_query(&graph, "RETURN $a < $b AS lt, $a <= $b AS le, $b > $a AS gt, $b >= $a AS ge, $b < $a AS reverse", &params).unwrap();
        assert_eq!(
            table.rows,
            vec![vec![
                Value::Bool(true),
                Value::Bool(true),
                Value::Bool(true),
                Value::Bool(true),
                Value::Bool(false)
            ]]
        );
    }
}
