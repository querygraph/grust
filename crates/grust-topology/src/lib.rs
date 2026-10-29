//! Dense directed-graph ordering, without stores, serialization, or runtimes.
//!
//! Extracted from Grust's iterative DFS. Callers retain control of allocation,
//! work accounting, cancellation, and graph identity. Adjacency is valid by
//! contract: every target is in `0..node_count()` and ranges index valid arcs.

use std::ops::Range;

/// Read-only dense adjacency. Node and arc order determine the cycle witness.
pub trait DirectedGraph {
    fn node_count(&self) -> usize;
    fn outgoing(&self, node: usize) -> Range<usize>;
    fn target(&self, arc: usize) -> usize;
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum Visit {
    #[default]
    Unseen,
    Active,
    Finished,
}

/// Caller-owned scratch. `visits` has one slot per node; `order` and `stack`
/// each need capacity for all nodes to avoid allocation during traversal.
pub struct Scratch<'a> {
    pub visits: &'a mut [Visit],
    pub order: &'a mut Vec<usize>,
    pub stack: &'a mut Vec<(usize, usize)>,
}

/// On success `Scratch::order` holds every node, producers before consumers.
/// A cycle leaves the DFS path in `Scratch::stack`: take the suffix starting
/// at `entry` and append `entry` to obtain a concrete closed directed cycle.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Outcome {
    Acyclic,
    Cycle { entry: usize },
}

/// Iterative O(V + E) topological ordering. `charge` admits work before each
/// step and can return any caller error, including cancellation or exhaustion.
/// A failure or cycle never returns a successful partial topological order.
pub fn topological_sort<G: DirectedGraph, E>(
    graph: &G,
    scratch: Scratch<'_>,
    mut charge: impl FnMut(usize) -> Result<(), E>,
) -> Result<Outcome, E> {
    let n = graph.node_count();
    let Scratch {
        visits,
        order,
        stack,
    } = scratch;
    visits.fill(Visit::Unseen);
    order.clear();
    stack.clear();
    for seed in 0..n {
        charge(1)?;
        if visits[seed] != Visit::Unseen {
            continue;
        }
        visits[seed] = Visit::Active;
        stack.push((seed, graph.outgoing(seed).start));
        while let Some(&mut (node, ref mut next)) = stack.last_mut() {
            charge(1)?;
            if *next == graph.outgoing(node).end {
                visits[node] = Visit::Finished;
                order.push(node);
                stack.pop();
                continue;
            }
            let target = graph.target(*next);
            *next += 1;
            match visits[target] {
                Visit::Unseen => {
                    visits[target] = Visit::Active;
                    stack.push((target, graph.outgoing(target).start));
                }
                Visit::Active => return Ok(Outcome::Cycle { entry: target }),
                Visit::Finished => {}
            }
        }
    }
    for index in 0..order.len() / 2 {
        charge(1)?;
        order.swap(index, n - index - 1);
    }
    Ok(Outcome::Acyclic)
}

#[cfg(test)]
mod tests;
