//! Borrowed lexical frames for expression evaluation. Extending a scope never
//! copies or mutates the candidate row, and graph bindings retain their types.

use super::{Bound, Row};

pub(super) enum ExpressionScope<'a> {
    Row(&'a Row),
    Binding {
        parent: &'a ExpressionScope<'a>,
        name: &'a str,
        value: &'a Bound,
    },
}

impl<'a> ExpressionScope<'a> {
    pub(super) fn row(row: &'a Row) -> Self {
        Self::Row(row)
    }

    pub(super) fn bind(&'a self, name: &'a str, value: &'a Bound) -> Self {
        Self::Binding {
            parent: self,
            name,
            value,
        }
    }

    pub(super) fn get(&self, name: &str) -> Option<&Bound> {
        match self {
            Self::Row(row) => row.get(name),
            Self::Binding {
                parent,
                name: bound_name,
                value,
            } => {
                if name == *bound_name {
                    Some(value)
                } else {
                    parent.get(name)
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{CypherParameters, parser::parse_expression, read::eval_scoped};
    use grust_core::Value;

    #[test]
    fn nested_frames_share_resolution_without_modifying_row() {
        let row = Row::from([("base".into(), Bound::Value(Value::Int(7)))]);
        let root = ExpressionScope::row(&row);
        let item = Bound::Value(Value::Json(serde_json::json!({"xs": [2, 3]})));
        let outer = root.bind("item", &item);
        let offset = Bound::Value(Value::Int(1));
        let inner = outer.bind("offset", &offset);
        let expression = parse_expression("base + item.xs[offset]").unwrap();
        assert_eq!(
            eval_scoped(&expression, &inner, &CypherParameters::new()).unwrap(),
            Value::Int(10)
        );
        assert!(root.get("item").is_none());
        assert!(outer.get("offset").is_none());
        assert_eq!(row.len(), 1);
    }
}
