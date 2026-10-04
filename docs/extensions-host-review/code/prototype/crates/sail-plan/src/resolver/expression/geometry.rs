//! Keep logical geometry types through value-preserving SQL expressions.
use std::sync::Arc;

use arrow::datatypes::{DataType, Field};
use datafusion_common::tree_node::{Transformed, TreeNode};
use datafusion_common::{DFSchema, Result};
use datafusion_expr::expr::Cast;
use datafusion_expr::{Expr, ExprSchemable};
use sail_common_datafusion::geometry::common_geometry_metadata;

/// DataFusion 55's CASE, coalesce and array_element infer only storage types.
/// An explicit-field identity cast preserves the selected logical type through
/// both logical simplification (coalesce becomes CASE) and physical planning.
pub(super) fn preserve_geometry(expr: Expr, schema: &DFSchema) -> Result<Expr> {
    // Expressions already repaired while resolving an argument need no second
    // traversal. User type-only casts still strip geometry metadata normally.
    if matches!(&expr, Expr::Cast(cast) if !cast.field.metadata().is_empty()) {
        return Ok(expr);
    }
    let mut expr = expr
        .map_children(|child| preserve_geometry(child, schema).map(Transformed::yes))?
        .data;
    let alternatives: Vec<&Expr> = match &expr {
        Expr::Case(case) => case
            .when_then_expr
            .iter()
            .map(|(_, value)| value.as_ref())
            .chain(case.else_expr.iter().map(|value| value.as_ref()))
            .collect(),
        Expr::ScalarFunction(function) if function.func.name() == "coalesce" => {
            function.args.iter().collect()
        }
        Expr::ScalarFunction(function) if function.func.name() == "array_element" => {
            let Some(input) = function.args.first() else {
                return Ok(expr);
            };
            let Ok(data_type) = input.get_type(schema) else {
                return Ok(expr); // An enclosing higher-order lambda may be unresolved.
            };
            let field = match data_type {
                DataType::List(field)
                | DataType::LargeList(field)
                | DataType::FixedSizeList(field, _)
                | DataType::ListView(field)
                | DataType::LargeListView(field) => field,
                _ => return Ok(expr),
            };
            if let Some(metadata) = common_geometry_metadata(std::slice::from_ref(&field)) {
                let field = Arc::new(
                    field
                        .as_ref()
                        .clone()
                        .with_nullable(true)
                        .with_metadata(metadata),
                );
                return Ok(Expr::Cast(Cast::new_from_field(Box::new(expr), field)));
            }
            return Ok(expr);
        }
        _ => return Ok(expr),
    };
    let fields = alternatives
        .iter()
        .map(|value| {
            // A typed NULL cannot change the geometry/CRS selected by other arms.
            if is_null_literal(value) {
                Ok(Arc::new(Field::new("null", DataType::Null, true)))
            } else {
                value.to_field(schema).map(|(_, field)| field)
            }
        })
        .collect::<Result<Vec<_>>>();
    let Ok(fields) = fields else {
        return Ok(expr); // Defer free lambda variables to their enclosing resolver.
    };
    let Some(metadata) = common_geometry_metadata(&fields) else {
        return Ok(expr);
    };
    // DataFusion 55's coalesce coercion accepts equal Binary storage types,
    // but excludes Binary when resolving the union of Binary and Null. Type
    // only untyped NULL operands after establishing a common geometry type;
    // this neither relabels ordinary binary values nor changes null semantics.
    if let Expr::ScalarFunction(function) = &mut expr
        && function.func.name() == "coalesce"
        && let Some(field) = fields.iter().find(|field| !field.data_type().is_null())
    {
        for argument in &mut function.args {
            if argument.get_type(schema)?.is_null() {
                *argument = Expr::Cast(Cast::new(
                    Box::new(argument.clone()),
                    field.data_type().clone(),
                ));
            }
        }
    }
    let field = Arc::new(
        Field::new("", expr.get_type(schema)?, expr.nullable(schema)?).with_metadata(metadata),
    );
    Ok(Expr::Cast(Cast::new_from_field(Box::new(expr), field)))
}

fn is_null_literal(expr: &Expr) -> bool {
    match expr {
        Expr::Literal(value, _) => value.is_null(),
        Expr::Cast(cast) => is_null_literal(&cast.expr),
        Expr::TryCast(cast) => is_null_literal(&cast.expr),
        Expr::Alias(alias) => is_null_literal(&alias.expr),
        // ANSI extraction inserts a typed raise_error arm. It produces no
        // value and therefore cannot change the type of a successful result.
        Expr::ScalarFunction(function) => function
            .func
            .inner()
            .is::<sail_function::scalar::misc::raise_error::RaiseError>(
        ),
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use arrow::datatypes::Schema;
    use datafusion_expr::{col, lit, when};

    use super::*;

    #[test]
    fn selectors_preserve_geometry_but_do_not_type_plain_binary() -> Result<()> {
        let field = Field::new("g", DataType::Binary, true).with_metadata(
            [
                ("ARROW:extension:name".into(), "geoarrow.wkb".into()),
                ("ARROW:extension:metadata".into(), "{}".into()),
            ]
            .into(),
        );
        let schema = DFSchema::try_from(Schema::new(vec![
            field.clone(),
            Field::new("raw", DataType::Binary, true),
        ]))?;
        let case = when(col("g").is_not_null(), col("g")).end()?;
        let fixed = preserve_geometry(case, &schema)?;
        assert_eq!(fixed.to_field(&schema)?.1.metadata(), field.metadata());
        for alternatives in [
            vec![col("g"), lit(datafusion_common::ScalarValue::Null)],
            vec![lit(datafusion_common::ScalarValue::Null), col("g")],
        ] {
            let coalesce = datafusion::functions::expr_fn::coalesce(alternatives);
            let fixed = preserve_geometry(coalesce, &schema)?;
            assert_eq!(fixed.to_field(&schema)?.1.metadata(), field.metadata());
        }
        let mixed = when(col("g").is_not_null(), col("g")).otherwise(col("raw"))?;
        let fixed = preserve_geometry(mixed, &schema)?;
        assert!(fixed.to_field(&schema)?.1.metadata().is_empty());
        Ok(())
    }
}
