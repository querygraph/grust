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
