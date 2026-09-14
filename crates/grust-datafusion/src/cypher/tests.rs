use super::*;
use datafusion::arrow::datatypes::Field;

fn property(key: &str) -> CypherExpr {
    CypherExpr::Property {
        base: Box::new(CypherExpr::Variable("n".into())),
        key: key.into(),
    }
}

#[test]
fn property_keys_are_literal_and_missing_values_are_null() {
    let schema = Schema::new(vec![Field::new("property.a.b", DataType::Int64, true)]);
    assert_eq!(
        lower_expression(&property("a.b"), "n", &schema).unwrap(),
        Expr::Column(Column::from_name("property.a.b"))
    );
    assert_eq!(
        lower_expression(&property("missing"), "n", &schema).unwrap(),
        lit(ScalarValue::Null)
    );
    assert_eq!(
        lower_expression(&property("a.b"), "other", &schema),
        Err(UnsupportedExpression::Binding)
    );
}

#[test]
fn mixed_types_and_unqualified_arithmetic_are_not_lowered() {
    let schema = Schema::empty();
    let comparison = CypherExpr::Binary {
        op: BinaryOp::Eq,
        lhs: Box::new(CypherExpr::Integer(1)),
        rhs: Box::new(CypherExpr::String("1".into())),
    };
    assert_eq!(
        lower_expression(&comparison, "n", &schema),
        Err(UnsupportedExpression::Type)
    );
    let addition = CypherExpr::Binary {
        op: BinaryOp::Add,
        lhs: Box::new(CypherExpr::Integer(1)),
        rhs: Box::new(CypherExpr::Integer(2)),
    };
    assert_eq!(
        lower_expression(&addition, "n", &schema),
        Err(UnsupportedExpression::Syntax)
    );
}

#[tokio::test]
async fn boolean_null_truth_tables_execute_with_cypher_results() {
    use datafusion::{arrow::array::BooleanArray, execution::context::SessionContext};
    let context = SessionContext::new();
    let values = [Some(false), Some(true), None];
    for left in values {
        for right in values {
            for op in [BinaryOp::And, BinaryOp::Or, BinaryOp::Xor] {
                let literal = |v: Option<bool>| v.map_or(CypherExpr::Null, CypherExpr::Boolean);
                let expression = CypherExpr::Binary {
                    op,
                    lhs: Box::new(literal(left)),
                    rhs: Box::new(literal(right)),
                };
                let lowered = lower_expression(&expression, "n", &Schema::empty()).unwrap();
                let batches = context
                    .read_empty()
                    .unwrap()
                    .select(vec![lowered])
                    .unwrap()
                    .collect()
                    .await
                    .unwrap();
                let array = batches[0]
                    .column(0)
                    .as_any()
                    .downcast_ref::<BooleanArray>()
                    .unwrap();
                let actual = array.iter().next().unwrap();
                let expected = match (op, left, right) {
                    (BinaryOp::And, Some(false), _) | (BinaryOp::And, _, Some(false)) => {
                        Some(false)
                    }
                    (BinaryOp::And, Some(true), Some(true)) => Some(true),
                    (BinaryOp::Or, Some(true), _) | (BinaryOp::Or, _, Some(true)) => Some(true),
                    (BinaryOp::Or, Some(false), Some(false)) => Some(false),
                    (BinaryOp::Xor, Some(left), Some(right)) => Some(left != right),
                    _ => None,
                };
                assert_eq!(actual, expected, "{left:?} {op:?} {right:?}");
            }
        }
    }
}

#[tokio::test]
async fn parsed_node_scan_filters_and_projects_native_property_columns() {
    use datafusion::{
        arrow::array::{Int64Array, RecordBatch, StringArray},
        execution::context::SessionContext,
    };
    let context = SessionContext::new();
    let batch = RecordBatch::try_from_iter(vec![
        (
            "label",
            std::sync::Arc::new(StringArray::from(vec!["N", "N", "Other"]))
                as datafusion::arrow::array::ArrayRef,
        ),
        (
            "property.age",
            std::sync::Arc::new(Int64Array::from(vec![Some(1), Some(3), Some(5)])),
        ),
    ])
    .unwrap();
    let query =
        grust_cypher::parser::parse_query("MATCH (n:N) WHERE n.age > 1 RETURN n.age AS age")
            .unwrap();
    let frame = lower_node_scan(&query, context.read_batch(batch).unwrap())
        .unwrap()
        .unwrap();
    let batches = frame.collect().await.unwrap();
    let values = batches[0]
        .column(0)
        .as_any()
        .downcast_ref::<Int64Array>()
        .unwrap();
    assert_eq!(values.values().as_ref(), &[3]);
}

#[tokio::test]
async fn native_scan_matches_reference_for_nulls_duplicates_and_large_integers() {
    use datafusion::{arrow::array::Int64Array, execution::context::SessionContext};
    use grust_core::{Graph, Node, Props, Value};
    use grust_cypher::{CypherParameters, read::run_read_query};

    let nodes = [
        None,
        Some(Value::Null),
        Some(Value::Int(1)),
        Some(Value::Int(1)),
        Some(Value::Int(9_007_199_254_740_993)),
    ]
    .into_iter()
    .enumerate()
    .map(|(id, value)| {
        let mut props = Props::new();
        if let Some(value) = value {
            props.insert("age".into(), value);
        }
        Node::new("N", id.to_string(), props)
    })
    .collect();
    let graph = Graph::new(nodes, vec![]);
    let arrow = grust_arrow::ArrowGraph::from_graph(&graph).unwrap();
    let context = SessionContext::new();
    for query_text in [
        "MATCH (n:N) RETURN n.age AS age",
        "MATCH (n:N) RETURN DISTINCT n.age AS age",
        "MATCH (n:N) WHERE n.age IS NULL RETURN n.age AS age",
        "MATCH (n:N) WHERE n.age IS NOT NULL RETURN n.age AS age",
        "MATCH (n:N) WHERE n.age > 9007199254740992 RETURN n.age AS age",
        "MATCH (n:Absent) RETURN n.age AS age",
    ] {
        let expected = run_read_query(&graph, query_text, &CypherParameters::new()).unwrap();
        let mut expected = expected
            .rows
            .into_iter()
            .map(|row| match row[0] {
                Value::Int(value) => Some(value),
                Value::Null => None,
                ref value => panic!("unexpected {value:?}"),
            })
            .collect::<Vec<_>>();
        let query = grust_cypher::parser::parse_query(query_text).unwrap();
        let frame = lower_node_scan(&query, context.read_batch(arrow.nodes().clone()).unwrap())
            .unwrap()
            .unwrap();
        let batches = frame.collect().await.unwrap();
        let mut actual = batches
            .iter()
            .flat_map(|batch| {
                batch
                    .column(0)
                    .as_any()
                    .downcast_ref::<Int64Array>()
                    .unwrap()
                    .iter()
            })
            .collect::<Vec<_>>();
        expected.sort_unstable();
        actual.sort_unstable();
        assert_eq!(actual, expected, "{query_text}");
    }
}

#[tokio::test]
async fn count_star_retains_empty_input_identity() {
    use datafusion::{
        arrow::array::{Int64Array, RecordBatch, StringArray},
        execution::context::SessionContext,
    };
    for labels in [vec![], vec!["N", "N", "Other"]] {
        let expected = labels.iter().filter(|label| **label == "N").count() as i64;
        let batch = RecordBatch::try_from_iter([(
            "label",
            std::sync::Arc::new(StringArray::from(labels)) as datafusion::arrow::array::ArrayRef,
        )])
        .unwrap();
        let context = SessionContext::new();
        let query =
            grust_cypher::parser::parse_query("MATCH (n:N) RETURN count(*) AS count").unwrap();
        let batches = lower_node_scan(&query, context.read_batch(batch).unwrap())
            .unwrap()
            .unwrap()
            .collect()
            .await
            .unwrap();
        assert_eq!(batches.iter().map(|b| b.num_rows()).sum::<usize>(), 1);
        assert_eq!(
            batches[0]
                .column(0)
                .as_any()
                .downcast_ref::<Int64Array>()
                .unwrap()
                .value(0),
            expected
        );
    }
}

#[tokio::test]
async fn grouped_counts_preserve_null_groups_and_projection_order() {
    use datafusion::{
        arrow::array::{Int64Array, RecordBatch},
        execution::context::SessionContext,
    };
    for ages in [vec![], vec![None, None, Some(1), Some(1), Some(2)]] {
        let expected = if ages.is_empty() {
            vec![]
        } else {
            vec![(1, Some(2)), (2, None), (2, Some(1))]
        };
        let batch = RecordBatch::try_from_iter([(
            "property.age",
            std::sync::Arc::new(Int64Array::from(ages)) as datafusion::arrow::array::ArrayRef,
        )])
        .unwrap();
        let context = SessionContext::new();
        let query =
            grust_cypher::parser::parse_query("MATCH (n) RETURN count(*) AS count, n.age AS age")
                .unwrap();
        let batches = lower_node_scan(&query, context.read_batch(batch).unwrap())
            .unwrap()
            .unwrap()
            .collect()
            .await
            .unwrap();
        let mut actual = Vec::new();
        for batch in batches {
            assert_eq!(batch.schema().field(0).name(), "count");
            assert_eq!(batch.schema().field(1).name(), "age");
            let counts = batch
                .column(0)
                .as_any()
                .downcast_ref::<Int64Array>()
                .unwrap();
            let ages = batch
                .column(1)
                .as_any()
                .downcast_ref::<Int64Array>()
                .unwrap();
            actual.extend(
                counts
                    .iter()
                    .zip(ages.iter())
                    .map(|(count, age)| (count.unwrap(), age)),
            );
        }
        actual.sort_unstable();
        assert_eq!(actual, expected);
    }
}

#[tokio::test]
async fn count_expression_ignores_nulls_and_distinct_removes_duplicates() {
    use datafusion::{
        arrow::array::{Int64Array, RecordBatch},
        execution::context::SessionContext,
    };
    for values in [
        vec![],
        vec![None, None],
        vec![None, Some(1), Some(1), Some(2)],
    ] {
        let expected_count = values.iter().flatten().count() as i64;
        let expected_distinct = values
            .iter()
            .flatten()
            .collect::<std::collections::BTreeSet<_>>()
            .len() as i64;
        let batch = RecordBatch::try_from_iter([(
            "property.x",
            std::sync::Arc::new(Int64Array::from(values)) as datafusion::arrow::array::ArrayRef,
        )])
        .unwrap();
        let context = SessionContext::new();
        let query = grust_cypher::parser::parse_query(
            "MATCH (n) RETURN count(n.x) AS count, count(DISTINCT n.x) AS distinct_count",
        )
        .unwrap();
        let batches = lower_node_scan(&query, context.read_batch(batch).unwrap())
            .unwrap()
            .unwrap()
            .collect()
            .await
            .unwrap();
        for (column, expected) in [expected_count, expected_distinct].into_iter().enumerate() {
            assert_eq!(
                batches[0]
                    .column(column)
                    .as_any()
                    .downcast_ref::<Int64Array>()
                    .unwrap()
                    .value(0),
                expected
            );
        }
    }
}

#[test]
fn scalar_parameters_are_bound_without_lossy_numeric_conversion() {
    let expression = CypherExpr::Parameter("limit".into());
    let parameters = CypherParameters::from([("limit".into(), Value::Int(i64::MAX))]);
    assert_eq!(
        lower_expression_with_parameters(&expression, "n", &Schema::empty(), &parameters).unwrap(),
        lit(i64::MAX)
    );
    assert_eq!(
        lower_expression(&expression, "n", &Schema::empty()),
        Err(UnsupportedExpression::MissingParameter)
    );
}

#[tokio::test]
async fn ordering_and_parameterized_pagination_match_cypher_null_order() {
    use datafusion::{
        arrow::array::{Int64Array, RecordBatch},
        execution::context::SessionContext,
    };
    let context = SessionContext::new();
    let batch = RecordBatch::try_from_iter([(
        "property.x",
        std::sync::Arc::new(Int64Array::from(vec![Some(2), None, Some(1), Some(3)]))
            as datafusion::arrow::array::ArrayRef,
    )])
    .unwrap();
    let parameters = CypherParameters::from([
        ("skip".into(), Value::Int(1)),
        ("take".into(), Value::Int(2)),
    ]);
    for (direction, expected) in [
        ("ASC", vec![Some(2), Some(3)]),
        ("DESC", vec![Some(3), Some(2)]),
    ] {
        let query = grust_cypher::parser::parse_query(&format!(
            "MATCH (n) RETURN n.x AS x ORDER BY x {direction} SKIP $skip LIMIT $take"
        ))
        .unwrap();
        let batches = lower_node_scan_with_parameters(
            &query,
            context.read_batch(batch.clone()).unwrap(),
            &parameters,
        )
        .unwrap()
        .unwrap()
        .collect()
        .await
        .unwrap();
        let actual = batches
            .iter()
            .flat_map(|batch| {
                batch
                    .column(0)
                    .as_any()
                    .downcast_ref::<Int64Array>()
                    .unwrap()
                    .iter()
            })
            .collect::<Vec<_>>();
        assert_eq!(actual, expected);
    }
}

#[tokio::test]
async fn implicit_projection_names_match_the_reference_contract() {
    use datafusion::{
        arrow::array::{Int64Array, RecordBatch},
        execution::context::SessionContext,
    };
    let batch = RecordBatch::try_from_iter([(
        "property.x",
        std::sync::Arc::new(Int64Array::from(vec![1, 2])) as datafusion::arrow::array::ArrayRef,
    )])
    .unwrap();
    let context = SessionContext::new();
    for (text, expected) in [
        ("MATCH (n) RETURN n.x ORDER BY n.x DESC", "n.x"),
        ("MATCH (n) RETURN count(*)", "expr"),
    ] {
        let query = grust_cypher::parser::parse_query(text).unwrap();
        let batches = lower_node_scan(&query, context.read_batch(batch.clone()).unwrap())
            .unwrap()
            .unwrap()
            .collect()
            .await
            .unwrap();
        assert_eq!(batches[0].schema().field(0).name(), expected);
        let values = batches
            .iter()
            .flat_map(|batch| {
                batch
                    .column(0)
                    .as_any()
                    .downcast_ref::<Int64Array>()
                    .unwrap()
                    .iter()
            })
            .collect::<Vec<_>>();
        assert_eq!(
            values,
            if expected == "n.x" {
                vec![Some(2), Some(1)]
            } else {
                vec![Some(2)]
            }
        );
    }
}

#[tokio::test]
async fn inline_parameter_maps_select_nodes_and_duplicate_names_decline() {
    use datafusion::{
        arrow::array::{Int64Array, RecordBatch},
        execution::context::SessionContext,
    };
    let context = SessionContext::new();
    let batch = RecordBatch::try_from_iter([(
        "property.x",
        std::sync::Arc::new(Int64Array::from(vec![1, 2, 2])) as datafusion::arrow::array::ArrayRef,
    )])
    .unwrap();
    let parameters = CypherParameters::from([("value".into(), Value::Int(2))]);
    let query = grust_cypher::parser::parse_query("MATCH (n {x: $value}) RETURN count(*) AS count")
        .unwrap();
    let batches = lower_node_scan_with_parameters(
        &query,
        context.read_batch(batch.clone()).unwrap(),
        &parameters,
    )
    .unwrap()
    .unwrap()
    .collect()
    .await
    .unwrap();
    assert_eq!(
        batches[0]
            .column(0)
            .as_any()
            .downcast_ref::<Int64Array>()
            .unwrap()
            .value(0),
        2
    );
    let query = grust_cypher::parser::parse_query("MATCH (n) RETURN n.x, n.x").unwrap();
    assert!(
        lower_node_scan(&query, context.read_batch(batch).unwrap())
            .unwrap()
            .is_none()
    );
}
