use grust_core::{Graph, Value};
use grust_cypher::procedures::{RegistryBuilder, register_builtins};
use grust_cypher::{CypherParameters, ReadQueryPolicy, run_bounded_read_query_with_registry};
use std::time::Duration;

fn run(query: &str, memory: usize) -> grust_core::Result<grust_cypher::CypherResultTable> {
    let mut builder = RegistryBuilder::default();
    register_builtins(&mut builder).unwrap();
    let policy = ReadQueryPolicy {
        require_match: false,
        allow_catalog_procedures: true,
        max_intermediate_bytes: memory,
        max_candidate_work: 10_000_000,
        max_range_items: 100_000,
        max_execution_time: Duration::from_secs(20),
        ..ReadQueryPolicy::default()
    };
    run_bounded_read_query_with_registry(
        &Graph::default(),
        "default",
        query,
        &CypherParameters::new(),
        &policy,
        &builder.build(),
    )
}

#[test]
fn incremental_aggregates_do_not_retain_consumed_range_rows() {
    let result = run("CALL tvf.range(1, 100000) YIELD value WITH value WHERE value % 2 = 0 RETURN count(value), sum(value), avg(value) LIMIT 1", 192 * 1024).unwrap();
    assert_eq!(
        result.rows,
        vec![vec![
            Value::Int(50_000),
            Value::Int(2_500_050_000),
            Value::Float(50_001.0)
        ]]
    );
}

#[test]
fn limit_stops_an_enormous_provider_without_consuming_its_tail() {
    let result = run(
        "CALL tvf.range(0, 9223372036854775807) YIELD value RETURN value SKIP 3 LIMIT 2",
        192 * 1024,
    )
    .unwrap();
    assert_eq!(result.rows, vec![vec![Value::Int(3)], vec![Value::Int(4)]]);
}

#[test]
fn unwind_reuses_large_live_arrays_and_matches_empty_aggregate_rules() {
    let result = run("CALL tvf.range(1, 1000) YIELD value WITH range(1, 100) AS items UNWIND items AS item RETURN count(item), sum(item) LIMIT 1", 192 * 1024).unwrap();
    assert_eq!(
        result.rows,
        vec![vec![Value::Int(100_000), Value::Int(5_050_000)]]
    );
    let empty = run(
        "CALL tvf.range(1, 0) YIELD value RETURN count(value), sum(value), avg(value) LIMIT 1",
        192 * 1024,
    )
    .unwrap();
    assert_eq!(
        empty.rows,
        vec![vec![Value::Int(0), Value::Null, Value::Null]]
    );
}

#[test]
fn retained_rows_still_share_the_streaming_memory_ceiling() {
    assert!(
        run(
            "CALL tvf.range(1, 50) YIELD value RETURN value LIMIT 50",
            1024
        )
        .is_err()
    );
}

#[test]
fn indexed_array_consumption_copies_only_the_selected_element() {
    let result = run("CALL tvf.range(1, 1) YIELD value WITH range(1, 50000) AS items UNWIND range(0, 49999) AS i RETURN count(items[i]), sum(items[i]) LIMIT 1", 4 * 1024 * 1024).unwrap();
    assert_eq!(
        result.rows,
        vec![vec![Value::Int(50_000), Value::Int(1_250_025_000)]]
    );
}

#[test]
fn fused_array_aggregates_match_the_ordinary_incremental_path() {
    for (array, aggregates) in [
        ("[1, 2, 3]", "count(item), sum(item), avg(item)"),
        ("[1.5, 2.5]", "count(item), sum(item), avg(item)"),
        (
            "['1', '2', '3']",
            "count(item), sum(toInteger(item)), avg(toFloat(item))",
        ),
        ("[]", "count(item), sum(item), avg(item)"),
        ("[1, null, 2.5]", "count(item), sum(item), avg(item)"),
    ] {
        let prefix =
            format!("CALL tvf.range(1, 1) YIELD value WITH {array} AS items UNWIND items AS item");
        let fused = run(&format!("{prefix} RETURN {aggregates} LIMIT 1"), 192 * 1024).unwrap();
        // An intervening WITH keeps this on the ordinary per-row evaluator.
        let ordinary = run(
            &format!("{prefix} WITH item AS item RETURN {aggregates} LIMIT 1"),
            192 * 1024,
        )
        .unwrap();
        assert_eq!(fused.rows, ordinary.rows, "{array}");
    }
    for query in [
        "CALL tvf.range(1, 1) YIELD value WITH ['invalid'] AS items UNWIND items AS item RETURN sum(toInteger(item)) LIMIT 1",
        "CALL tvf.range(1, 1) YIELD value WITH [9223372036854775807, 1] AS items UNWIND items AS item RETURN sum(item) LIMIT 1",
    ] {
        assert!(run(query, 192 * 1024).is_err());
    }
}
