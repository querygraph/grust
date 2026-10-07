//! An explicit relational program; a plain SQL consumer must refuse iterative steps.
use super::*;
use grust_unresolved_plan::{Hops, PathMode};
#[derive(Clone, Debug)]
pub struct SailProgram {
    pub sql: String,
    pub traversals: Vec<TraversalStep>,
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
        self.traversals.push(TraversalStep {
            view: view.clone(),
            seed_sql,
            adjacency_sql,
            min_hops: hops.min,
            max_hops: hops.max,
            mode,
            shortest_walk,
        });
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
