//! Composition of relationship plans under trail identity semantics.
use super::{EDGE_ORDINAL, RelationshipPlan};
use datafusion::{
    common::{Column, DataFusionError, Result},
    logical_expr::{Expr, JoinType},
};
use std::{collections::BTreeMap, sync::Arc};

impl RelationshipPlan {
    /// Join two parts of one trail through their shared node bindings. Every
    /// relationship in the left part must differ physically from every one in
    /// the right part; parallel edges remain distinct even without external IDs.
    /// Shared node names retain identity, and name/type collisions are errors.
    ///
    /// Both plans must originate from the same captured snapshot (clones qualify).
    /// At least one shared node is required. This is a lazy operator, not policy
    /// admission or parsed multi-hop/variable-length query routing.
    pub fn join_trail(self, mut right: Self) -> Result<Self> {
        if !Arc::ptr_eq(&self.snapshot, &right.snapshot) {
            return Err(DataFusionError::Plan(
                "trail parts belong to different snapshots".into(),
            ));
        }
        right.rename_for_join(self.frame.schema().fields().len())?;
        let mut predicates = Vec::new();
        let mut shared_node = false;
        for (name, left) in &self.bindings.variables {
            if let Some(other) = right.bindings.variables.get(name) {
                let key = if left.contains_key("node_id") {
                    "node_id"
                } else {
                    EDGE_ORDINAL
                };
                let Some(value) = other.get(key) else {
                    return Err(DataFusionError::Plan(format!(
                        "incompatible trail binding {name}"
                    )));
                };
                shared_node |= key == "node_id";
                predicates.push(left[key].0.clone().eq(value.0.clone()));
            }
        }
        if !shared_node {
            return Err(DataFusionError::Plan(
                "trail parts require a shared node binding".into(),
            ));
        }
        for left in self
            .bindings
            .variables
            .values()
            .filter_map(|columns| columns.get(EDGE_ORDINAL))
        {
            for other in right
                .bindings
                .variables
                .values()
                .filter_map(|columns| columns.get(EDGE_ORDINAL))
            {
                predicates.push(left.0.clone().not_eq(other.0.clone()));
            }
        }
        let frame = self
            .frame
            .join_on(right.frame, JoinType::Inner, predicates)?;
        let mut bindings = self.bindings;
        for (name, columns) in right.bindings.variables {
            bindings.variables.entry(name).or_insert(columns);
        }
        Ok(Self {
            frame,
            bindings,
            snapshot: self.snapshot,
        })
    }

    fn rename_for_join(&mut self, offset: usize) -> Result<()> {
        let mut names = BTreeMap::new();
        let expressions: Vec<Expr> = self
            .frame
            .schema()
            .fields()
            .iter()
            .enumerate()
            .map(|(index, field)| {
                let name = format!("__grust_trail_{}", offset + index);
                names.insert(field.name().clone(), Expr::Column(Column::from_name(&name)));
                Expr::Column(Column::from_name(field.name())).alias(name)
            })
            .collect();
        for columns in self.bindings.variables.values_mut() {
            for (expression, _) in columns.values_mut() {
                let Expr::Column(column) = expression else {
                    return Err(DataFusionError::Plan(
                        "trail binding is not a physical column".into(),
                    ));
                };
                *expression = names
                    .get(&column.name)
                    .cloned()
                    .ok_or_else(|| DataFusionError::Plan("trail column is missing".into()))?;
            }
        }
        self.frame = self.frame.clone().select(expressions)?;
        Ok(())
    }
}
