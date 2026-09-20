//! Label propagation with a deterministic, sequential update schedule.

use crate::{
    AlgorithmError, GraphProjection, Result,
    buffer::Buffer,
    random,
    table::{NodeColumn, NodeTable, TableScalar},
};

/// Label propagation controls.
#[derive(Clone, Copy, Debug)]
pub struct LabelPropagationOptions {
    /// Stop after this many passes over the nodes, converged or not.
    pub max_iterations: usize,
    /// `None` visits nodes in row order on every pass. A seed shuffles the order
    /// afresh for each pass; the same seed gives the same result.
    pub seed: Option<u64>,
}

impl Default for LabelPropagationOptions {
    fn default() -> Self {
        Self {
            max_iterations: 10,
            seed: None,
        }
    }
}

/// A community per node.
pub struct LabelPropagation {
    graph: GraphProjection,
    communities: Buffer<usize>,
    iterations: usize,
    converged: bool,
}

impl LabelPropagation {
    /// Projection supplying external ids and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        &self.graph
    }
    /// For each node, the smallest row in its community.
    pub fn communities(&self) -> &[usize] {
        &self.communities.values
    }
    /// Passes run, including the one that changed nothing.
    pub fn iterations(&self) -> usize {
        self.iterations
    }
    /// Whether a pass changed nothing, rather than `max_iterations` stopping it.
    pub fn converged(&self) -> bool {
        self.converged
    }
    /// `communityId`, then the `iterations` and `converged` scalars.
    pub fn into_table(self) -> Result<NodeTable> {
        let iterations = i64::try_from(self.iterations)
            .map_err(|_| AlgorithmError::Numerical("iteration count exceeds Int64".into()))?;
        Ok(NodeTable::new(&self.graph)
            .column("communityId", NodeColumn::Node(self.communities))?
            .scalar("iterations", TableScalar::Integer(iterations))
            .scalar("converged", TableScalar::Boolean(self.converged)))
    }
}

/// Every node starts in its own community and repeatedly adopts the label that
/// carries the most weight among the nodes with an arc **into** it, so labels
/// flow along the projection's arcs. A self-loop supports the node's own label.
///
/// **Schedule.** Updates are asynchronous — a node sees labels already changed
/// in the same pass — and sequential, in row order or a seeded order per pass.
/// An asynchronous parallel schedule would not be reproducible, and a
/// synchronous one oscillates on bipartite graphs.
///
/// **Ties.** A node keeps its label when that label is among the heaviest;
/// otherwise it takes the smallest of the heaviest. On an undirected projection
/// every change then strictly raises the weight of same-label edges, so the run
/// converges given enough passes. On a directed one it may not, and `converged`
/// says so.
///
/// Communities are named by their smallest member, as `wcc` names components.
pub fn label_propagation(
    graph: &GraphProjection,
    options: LabelPropagationOptions,
) -> Result<LabelPropagation> {
    graph.require_nonnegative("labelPropagation")?;
    let context = graph.execution();
    context.checkpoint()?;
    if options.max_iterations == 0 {
        return Err(AlgorithmError::InvalidArguments(
            "maxIterations must be positive".into(),
        ));
    }
    let n = graph.node_count();
    let incoming = graph.incoming()?;
    let mut labels = Buffer::capacity(n, context)?;
    labels.values.extend(0..n);
    let mut order = Buffer::capacity(n, context)?;
    order.values.extend(0..n);
    // Weight per label for the node in hand, and which labels it touched.
    let mut support = Buffer::filled(n, 0.0f64, context)?;
    let mut touched = Buffer::<usize>::capacity(n, context)?;
    let mut meter = context.work_meter();

    let mut iterations = 0;
    let mut converged = false;
    while iterations < options.max_iterations && !converged {
        if let Some(seed) = options.seed {
            meter.charge(n)?;
            random::shuffle(&mut order.values, seed, iterations as u64);
        }
        iterations += 1;
        let mut changed = false;
        for &node in &order.values {
            let range = incoming.range(node);
            meter.charge(1 + range.len())?;
            for arc in range {
                let weight = incoming.weight(arc);
                if weight == 0.0 {
                    // No support, and it must not register its label twice.
                    continue;
                }
                let label = labels.values[incoming.targets.values[arc]];
                if support.values[label] == 0.0 {
                    touched.values.push(label);
                }
                support.values[label] += weight;
            }
            let current = labels.values[node];
            let mut best = current;
            let mut best_weight = support.values[current];
            for &label in &touched.values {
                let weight = support.values[label];
                if weight > best_weight
                    || (weight == best_weight && best != current && label < best)
                {
                    best = label;
                    best_weight = weight;
                }
            }
            for &label in &touched.values {
                support.values[label] = 0.0;
            }
            touched.values.clear();
            if best != current {
                labels.values[node] = best;
                changed = true;
            }
        }
        converged = !changed;
    }

    // Name each community by its smallest member: a label's first owner may
    // have left it.
    meter.charge(2 * n)?;
    let mut smallest = Buffer::filled(n, usize::MAX, context)?;
    for (node, &label) in labels.values.iter().enumerate() {
        smallest.values[label] = smallest.values[label].min(node);
    }
    for label in &mut labels.values {
        *label = smallest.values[*label];
    }
    Ok(LabelPropagation {
        graph: graph.clone(),
        communities: labels,
        iterations,
        converged,
    })
}
