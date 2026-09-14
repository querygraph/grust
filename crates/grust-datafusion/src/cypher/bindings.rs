use super::UnsupportedExpression;
use datafusion::{
    arrow::datatypes::{DataType, Schema},
    common::{Column, ScalarValue},
    logical_expr::{Expr, lit},
};

/// Resolve typed graph bindings into physical expressions. Missing properties
/// return a null expression; unknown variables return Binding. Implementations
/// own schema/snapshot validation and must report actual physical types.
pub trait ExpressionBindings {
    fn property(
        &self,
        variable: &str,
        key: &str,
    ) -> Result<(Expr, DataType), UnsupportedExpression>;
    fn node_id(&self, variable: &str) -> Result<(Expr, DataType), UnsupportedExpression>;
}

pub(super) struct SingleBinding<'a> {
    pub variable: &'a str,
    pub schema: &'a Schema,
}
impl ExpressionBindings for SingleBinding<'_> {
    fn property(
        &self,
        variable: &str,
        key: &str,
    ) -> Result<(Expr, DataType), UnsupportedExpression> {
        if variable != self.variable {
            return Err(UnsupportedExpression::Binding);
        }
        let name = format!("property.{key}");
        match self.schema.field_with_name(&name) {
            Ok(field) => Ok((
                Expr::Column(Column::from_name(name)),
                field.data_type().clone(),
            )),
            Err(_) => Ok((lit(ScalarValue::Null), DataType::Null)),
        }
    }
    fn node_id(&self, variable: &str) -> Result<(Expr, DataType), UnsupportedExpression> {
        if variable != self.variable {
            return Err(UnsupportedExpression::Binding);
        }
        let field = self
            .schema
            .field_with_name("node_id")
            .map_err(|_| UnsupportedExpression::Binding)?;
        if field.data_type() != &DataType::Utf8 || field.is_nullable() {
            return Err(UnsupportedExpression::Type);
        }
        Ok((Expr::Column(Column::from_name("node_id")), DataType::Utf8))
    }
}
