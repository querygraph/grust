//! An explicit relational program; a plain SQL consumer must refuse iterative steps.
use super::*;
use grust_unresolved_plan::{Hops, PathMode};
#[derive(Clone, Debug)]
pub struct SailProgram {
    pub sql: String,
    pub traversals: Vec<TraversalStep>,
    /// Ordered materialization/traversal dependencies. Legacy traversal-only clients may inspect traversals.
    pub steps: Vec<ExecutionStep>,
}
#[derive(Clone, Debug)]
pub enum ExecutionStep {
    Materialize(MaterializationStep),
    Traverse(TraversalStep),
}
#[derive(Clone, Debug)]
pub struct MaterializationStep {
    pub view: String,
    pub sql: String,
}
#[derive(Clone, Debug)]
pub struct TraversalStep {
    pub view: String,
    pub seed_sql: String,
    pub adjacency_sql: String,
    pub min_hops: u64,
    pub max_hops: Option<u64>,
    pub mode: PathMode,
    pub shortest_walk: bool,
}
impl Emitter<'_, '_> {
    pub(super) fn materialization(&mut self, input: &Node, id: u32) -> Result<String, EmitError> {
        let view = if let Some((original, view)) = self.materialized.get(&id) {
            if original != input {
                return Err(refusal("conflicting materialization identity"));
            }
            view.clone()
        } else {
            let root = self.node(input)?;
            let cols = input
                .fields
                .iter()
                .map(|f| slot(f.slot))
                .collect::<Vec<_>>()
                .join(", ");
            let sql = format!("WITH {} SELECT {cols} FROM {root}", self.ctes.join(",\n"));
            let view = format!("__grust_materialize_{id}");
            self.steps
                .push(ExecutionStep::Materialize(MaterializationStep {
                    view: view.clone(),
                    sql,
                }));
            self.materialized.insert(id, (input.clone(), view.clone()));
            view
        };
        Ok(format!("SELECT * FROM {view}"))
    }
    pub(super) fn partition_slice(
        &mut self,
        node: &Node,
        input: &Node,
        partitions: &[Expr],
        keys: &[grust_resolved_plan::query::SortKey],
        offset: Option<&Expr>,
        limit: Option<&Expr>,
    ) -> Result<String, EmitError> {
        let child = self.node(input)?;
        let env = environment(&input.fields, "");
        let partition = partitions
            .iter()
            .map(|e| self.expression(e, &env))
            .collect::<Result<Vec<_>, _>>()?
            .join(", ");
        let order = if keys.is_empty() {
            partition.clone()
        } else {
            keys.iter()
                .map(|key| {
                    Ok(format!(
                        "{} {} NULLS {}",
                        self.expression(&key.expression, &env)?,
                        if key.descending { "DESC" } else { "ASC" },
                        if key.nulls_first { "FIRST" } else { "LAST" }
                    ))
                })
                .collect::<Result<Vec<_>, EmitError>>()?
                .join(", ")
        };
        let offset = offset
            .map(|e| self.expression(e, &env))
            .transpose()?
            .unwrap_or_else(|| "0".into());
        let end = limit
            .map(|e| self.expression(e, &env))
            .transpose()?
            .map(|limit| format!(" AND `@local_rank` <= ({offset}+{limit})"))
            .unwrap_or_default();
        let cols = node
            .fields
            .iter()
            .map(|f| slot(f.slot))
            .collect::<Vec<_>>()
            .join(", ");
        Ok(format!("SELECT {cols} FROM (SELECT *, row_number() OVER (PARTITION BY {partition} ORDER BY {order}) AS `@local_rank` FROM {child}) ranked WHERE `@local_rank` > {offset}{end}"))
    }
    pub(super) fn traversal(
        &mut self,
        node: &Node,
        seed: &Node,
        adjacency: &Node,
        hops: Hops,
        mode: PathMode,
        shortest_walk: bool,
    ) -> Result<String, EmitError> {
        if !hops.is_valid()
            || (shortest_walk && mode != PathMode::Walk)
            || (hops.max.is_none() && mode == PathMode::Walk && !shortest_walk)
        {
            return Err(refusal("invalid or infinite iterative traversal contract"));
        }
        if seed.fields.len() != 2 || adjacency.fields.len() != 6 || node.fields.len() != 7 {
            return Err(refusal("iterative positional schema"));
        }
        let seed_root = self.node(seed)?;
        let seed_sql = input_sql(&self.ctes, &seed_root, &seed.fields, &["sg", "si"]);
        let adjacency_root = self.node(adjacency)?;
        let adjacency_sql = input_sql(
            &self.ctes,
            &adjacency_root,
            &adjacency.fields,
            &["sg", "si", "dg", "di", "eg", "ei"],
        );
        let view = format!("__grust_traverse_{}", self.traversals.len());
        let step = TraversalStep {
            view: view.clone(),
            seed_sql,
            adjacency_sql,
            min_hops: hops.min,
            max_hops: hops.max,
            mode,
            shortest_walk,
        };
        self.traversals.push(step.clone());
        self.steps.push(ExecutionStep::Traverse(step));
        let columns = ["sg", "si", "dg", "di", "edges", "vertices", "length"]
            .iter()
            .zip(&node.fields)
            .map(|(name, field)| format!("{} AS {}", quote(name), slot(field.slot)))
            .collect::<Vec<_>>()
            .join(", ");
        Ok(format!("SELECT {columns} FROM {view}"))
    }
}
fn input_sql(ctes: &[String], root: &str, fields: &[Field], names: &[&str]) -> String {
    let columns = fields
        .iter()
        .zip(names)
        .map(|(f, n)| format!("{} AS {}", slot(f.slot), quote(n)))
        .collect::<Vec<_>>()
        .join(", ");
    format!("WITH {} SELECT {columns} FROM {root}", ctes.join(",\n"))
}
