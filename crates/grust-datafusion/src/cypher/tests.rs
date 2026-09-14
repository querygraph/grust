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
