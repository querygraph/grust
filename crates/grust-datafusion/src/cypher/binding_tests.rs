use super::*;
use datafusion::{
    arrow::{array::Int64Array, datatypes::Field, record_batch::RecordBatch},
    common::Column,
    execution::context::SessionContext,
};
use std::sync::Arc;

struct JoinedBindings;
impl ExpressionBindings for JoinedBindings {
    fn property(
        &self,
        variable: &str,
        key: &str,
    ) -> Result<(Expr, DataType), UnsupportedExpression> {
        if !matches!(variable, "a" | "b") {
            return Err(UnsupportedExpression::Binding);
        }
        if key != "x.y" {
            return Ok((lit(ScalarValue::Null), DataType::Null));
        }
        Ok((
            Expr::Column(Column::from_name(format!("{variable}.x.y"))),
            DataType::Int64,
        ))
    }

    fn node_id(&self, _: &str) -> Result<(Expr, DataType), UnsupportedExpression> {
        // Deliberately invalid: the compiler must reject integer node identity.
        Ok((lit(1_i64), DataType::Int64))
    }
}

#[tokio::test]
async fn multiple_bindings_keep_literal_columns_distinct() {
    let property = |variable: &str| CypherExpr::Property {
        base: Box::new(CypherExpr::Variable(variable.into())),
        key: "x.y".into(),
    };
    let comparison = CypherExpr::Binary {
        op: BinaryOp::Lt,
        lhs: Box::new(property("a")),
        rhs: Box::new(property("b")),
    };
    let parameters = CypherParameters::new();
    let predicate =
        lower_expression_with_bindings(&comparison, &JoinedBindings, &parameters).unwrap();
    let batch = RecordBatch::try_new(
        Arc::new(Schema::new(vec![
            Field::new("a.x.y", DataType::Int64, true),
            Field::new("b.x.y", DataType::Int64, true),
        ])),
        vec![
            Arc::new(Int64Array::from(vec![Some(1), Some(4), None])),
            Arc::new(Int64Array::from(vec![Some(2), Some(3), Some(5)])),
        ],
    )
    .unwrap();
    let results = SessionContext::new()
        .read_batch(batch)
        .unwrap()
        .filter(predicate)
        .unwrap()
        .collect()
        .await
        .unwrap();
    assert_eq!(results.iter().map(RecordBatch::num_rows).sum::<usize>(), 1);
    let values = results[0]
        .column(0)
        .as_any()
        .downcast_ref::<Int64Array>()
        .unwrap();
    assert_eq!(values.value(0), 1);
    assert_eq!(
        lower_expression_with_bindings(&property("unknown"), &JoinedBindings, &parameters),
        Err(UnsupportedExpression::Binding)
    );
    let identity = CypherExpr::Function {
        name: "id".into(),
        distinct: false,
        star: false,
        args: vec![CypherExpr::Variable("a".into())],
    };
    assert_eq!(
        lower_expression_with_bindings(&identity, &JoinedBindings, &parameters),
        Err(UnsupportedExpression::Type)
    );
}

#[tokio::test]
async fn aggregates_resolve_multiple_bindings_and_preserve_nulls() {
    let aggregate = |name: &str, variable: &str, distinct| CypherExpr::Function {
        name: name.into(),
        distinct,
        star: false,
        args: vec![CypherExpr::Property {
            base: Box::new(CypherExpr::Variable(variable.into())),
            key: "x.y".into(),
        }],
    };
    let parameters = CypherParameters::new();
    let expressions = [
        ("count", "a", true),
        ("count", "b", false),
        ("max", "a", false),
        ("min", "b", false),
    ]
    .into_iter()
    .enumerate()
    .map(|(index, (name, variable, distinct))| {
        lower_aggregate_with_bindings(
            &aggregate(name, variable, distinct),
            &JoinedBindings,
            &parameters,
        )
        .unwrap()
        .alias(format!("result_{index}"))
    })
    .collect();
    let batch = RecordBatch::try_new(
        Arc::new(Schema::new(vec![
            Field::new("a.x.y", DataType::Int64, true),
            Field::new("b.x.y", DataType::Int64, true),
        ])),
        vec![
            Arc::new(Int64Array::from(vec![Some(4), Some(4), None])),
            Arc::new(Int64Array::from(vec![Some(2), None, Some(i64::MIN)])),
        ],
    )
    .unwrap();
    let results = SessionContext::new()
        .read_batch(batch)
        .unwrap()
        .aggregate(vec![], expressions)
        .unwrap()
        .collect()
        .await
        .unwrap();
    for (index, expected) in [1, 2, 4, i64::MIN].into_iter().enumerate() {
        let values = results[0]
            .column(index)
            .as_any()
            .downcast_ref::<Int64Array>()
            .unwrap();
        assert_eq!(values.value(0), expected);
    }
    assert_eq!(
        lower_aggregate_with_bindings(&aggregate("sum", "a", false), &JoinedBindings, &parameters),
        Err(UnsupportedExpression::Syntax)
    );
    assert_eq!(
        lower_aggregate_with_bindings(
            &aggregate("count", "unknown", false),
            &JoinedBindings,
            &parameters
        ),
        Err(UnsupportedExpression::Binding)
    );
}
