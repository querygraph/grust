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
            for op in [BinaryOp::And, BinaryOp::Or] {
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
