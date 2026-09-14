//! Typed endpoint joins over a captured graph, without SQL serialization.
use super::{EDGE_ORDINAL, ExpressionBindings, GraphSnapshot, UnsupportedExpression};
use datafusion::{
    arrow::datatypes::DataType,
    common::{Column, DataFusionError, Result, ScalarValue},
    dataframe::DataFrame,
    execution::context::SessionContext,
    logical_expr::{Expr, JoinType, lit},
};
use std::collections::BTreeMap;

type Columns = BTreeMap<String, (Expr, DataType)>;

/// Binding resolution retained alongside an endpoint-join plan.
/// Physical names are generated independently of user variable/property names.
pub struct GraphBindings {
    variables: BTreeMap<String, Columns>,
}
impl GraphBindings {
    /// Physical relationship identity for trail exclusion in this snapshot.
    pub fn relationship_ordinal(&self, variable: &str) -> Result<Expr, UnsupportedExpression> {
        self.field(variable, EDGE_ORDINAL)
            .map(|(expression, _)| expression)
    }

    pub(super) fn field(
        &self,
        variable: &str,
        name: &str,
    ) -> Result<(Expr, DataType), UnsupportedExpression> {
        self.variables
            .get(variable)
            .and_then(|columns| columns.get(name))
            .cloned()
            .ok_or(UnsupportedExpression::Binding)
    }
}
impl ExpressionBindings for GraphBindings {
    fn property(
        &self,
        variable: &str,
        key: &str,
    ) -> Result<(Expr, DataType), UnsupportedExpression> {
        let columns = self
            .variables
            .get(variable)
            .ok_or(UnsupportedExpression::Binding)?;
        Ok(columns
            .get(&format!("property.{key}"))
            .cloned()
            .unwrap_or_else(|| (lit(ScalarValue::Null), DataType::Null)))
    }
    fn node_id(&self, variable: &str) -> Result<(Expr, DataType), UnsupportedExpression> {
        self.field(variable, "node_id")
    }
}

/// A lazy relationship plan and the bindings used to compile its expressions.
pub struct RelationshipPlan {
    frame: DataFrame,
    bindings: GraphBindings,
}
impl RelationshipPlan {
    pub fn bindings(&self) -> &GraphBindings {
        &self.bindings
    }
    /// Transfer the lazy frame and its resolver to projection/filter planning.
    pub fn into_parts(self) -> (DataFrame, GraphBindings) {
        (self.frame, self.bindings)
    }
}

impl GraphSnapshot {
    /// Plan every directed `(source)-[edge]->(target)` in this snapshot.
    /// All three binding names must be distinct; repeated-variable patterns
    /// require an explicit equality constraint in a higher-level pattern planner.
    /// Inner endpoint joins preserve loops and parallel edges, omit isolates and
    /// do not collapse rows by optional external relationship ID. No execution or
    /// resource admission occurs here. This is not an automatic Cypher route.
    pub fn directed_relationships(
        &self,
        context: &SessionContext,
        source: &str,
        edge: &str,
        target: &str,
    ) -> Result<RelationshipPlan> {
        self.endpoint_relationships(context, source, edge, target, false)
    }

    /// Plan both orientations of each non-loop edge, and each self-loop once.
    /// Physical relationship ordinals are retained across both orientations.
    /// This has the same distinct-binding and admission contract as the directed
    /// operator; row order is unspecified without an explicit sort.
    pub fn undirected_relationships(
        &self,
        context: &SessionContext,
        source: &str,
        edge: &str,
        target: &str,
    ) -> Result<RelationshipPlan> {
        let forward = self.endpoint_relationships(context, source, edge, target, false)?;
        let reverse = self.endpoint_relationships(context, source, edge, target, true)?;
        let different = reverse.bindings.variables[source]["node_id"]
            .0
            .clone()
            .not_eq(reverse.bindings.variables[target]["node_id"].0.clone());
        Ok(RelationshipPlan {
            frame: forward.frame.union(reverse.frame.filter(different)?)?,
            bindings: forward.bindings,
        })
    }

    fn endpoint_relationships(
        &self,
        context: &SessionContext,
        source: &str,
        edge: &str,
        target: &str,
        reverse: bool,
    ) -> Result<RelationshipPlan> {
        if source == edge || source == target || edge == target {
            return Err(DataFusionError::Plan(
                "relationship bindings must be distinct".into(),
            ));
        }
        let (source_frame, source_columns) = rename(self.nodes(context)?, 0)?;
        let (edge_frame, edge_columns) = rename(self.edges(context)?, 1)?;
        let (target_frame, target_columns) = rename(self.nodes(context)?, 2)?;
        let (from_key, to_key) = if reverse {
            ("target", "source")
        } else {
            ("source", "target")
        };
        let from = source_columns["node_id"]
            .0
            .clone()
            .eq(edge_columns[from_key].0.clone());
        let to = edge_columns[to_key]
            .0
            .clone()
            .eq(target_columns["node_id"].0.clone());
        let frame = edge_frame
            .join_on(source_frame, JoinType::Inner, [from])?
            .join_on(target_frame, JoinType::Inner, [to])?;
        Ok(RelationshipPlan {
            frame,
            bindings: GraphBindings {
                variables: BTreeMap::from([
                    (source.into(), source_columns),
                    (edge.into(), edge_columns),
                    (target.into(), target_columns),
                ]),
            },
        })
    }
}

fn rename(frame: DataFrame, binding: usize) -> Result<(DataFrame, Columns)> {
    let mut columns = BTreeMap::new();
    let expressions: Vec<Expr> = frame
        .schema()
        .fields()
        .iter()
        .enumerate()
        .map(|(index, field)| {
            let physical = format!("__grust_binding_{binding}_{index}");
            columns.insert(
                field.name().clone(),
                (
                    Expr::Column(Column::from_name(&physical)),
                    field.data_type().clone(),
                ),
            );
            Expr::Column(Column::from_name(field.name())).alias(physical)
        })
        .collect();
    Ok((frame.select(expressions)?, columns))
}
