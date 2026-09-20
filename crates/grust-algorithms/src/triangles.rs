//! Triangle counts and local clustering coefficients on the simple undirected
//! graph underlying a projection, by the degree-ordered forward algorithm.

use std::sync::atomic::{AtomicU64, Ordering};

use crate::{
    AlgorithmError, GraphProjection, Orientation, Result,
    buffer::Buffer,
    parallel,
    table::{NodeColumn, NodeTable, TableScalar},
};

/// Triangle controls.
#[derive(Clone, Copy, Debug, Default)]
pub struct TriangleOptions {
    /// Leave out nodes whose simple degree exceeds this. Such a node reports
    /// `-1` triangles and no coefficient, and triangles through it are not
    /// counted for anyone: hubs dominate the cost and rarely the question.
    pub max_degree: Option<usize>,
}

/// Per-node triangle counts and clustering coefficients.
pub struct Triangles {
    graph: GraphProjection,
    triangles: Buffer<i64>,
    coefficients: Buffer<f64>,
    total: i64,
    average: f64,
}

impl Triangles {
    /// Projection supplying external ids and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        &self.graph
    }
    /// Triangles through each node; `-1` for a node left out by `max_degree`.
    pub fn triangles(&self) -> &[i64] {
        &self.triangles.values
    }
    /// `2t / (d(d-1))` per node, NaN where it is undefined: simple degree below
    /// two, or a node left out by `max_degree`.
    pub fn coefficients(&self) -> &[f64] {
        &self.coefficients.values
    }
    /// Distinct triangles in the graph.
    pub fn triangle_count(&self) -> i64 {
        self.total
    }
    /// Mean coefficient over the nodes that have one; zero if none do.
    pub fn average_coefficient(&self) -> f64 {
        self.average
    }
    /// `triangles`, then the `triangleCount` scalar.
    pub fn into_triangle_table(self) -> Result<NodeTable> {
        Ok(NodeTable::new(&self.graph)
            .column("triangles", NodeColumn::Integer(self.triangles))?
            .scalar("triangleCount", TableScalar::Integer(self.total)))
    }
    /// `coefficient`, `triangles`, then the `averageCoefficient` scalar.
    pub fn into_coefficient_table(self) -> Result<NodeTable> {
        Ok(NodeTable::new(&self.graph)
            .column("coefficient", NodeColumn::OptionalNumber(self.coefficients))?
            .column("triangles", NodeColumn::Integer(self.triangles))?
            .scalar("averageCoefficient", TableScalar::Number(self.average)))
    }
}

/// Count triangles on an undirected projection.
///
/// Triangles are a property of the **simple** graph: **parallel edges count
/// once and self-loops are ignored**, unlike `degree` and `kCore`, which count
/// multiplicity. A node's degree here is its number of distinct neighbours. Any
/// other orientation is rejected rather than symmetrized — project with
/// `orientation: "undirected"`.
///
/// Each triangle is found once, at its lowest-ranked corner, where rank orders
/// nodes by (degree, row): O(A^1.5) intersections. Nodes are split into blocks
/// of equal estimated work and counted on as many workers as the execution asked for into atomic
/// per-node counters; the counts, and the work charged, are the same at any
/// worker count.
pub fn triangles(graph: &GraphProjection, options: TriangleOptions) -> Result<Triangles> {
    let context = graph.execution();
    context.checkpoint()?;
    if graph.orientation() != Orientation::Undirected {
        return Err(AlgorithmError::InvalidArguments(
            "triangles are defined on undirected graphs; project with orientation \"undirected\""
                .into(),
        ));
    }
    let n = graph.node_count();
    let adjacency = graph.outgoing();
    let mut meter = context.work_meter();

    // Distinct neighbours per node, sorted, loops removed.
    let mut simple_offsets = Buffer::filled(n + 1, 0usize, context)?;
    let mut simple = Buffer::capacity(adjacency.targets.values.len(), context)?;
    for node in 0..n {
        let range = adjacency.range(node);
        meter.charge(1 + range.len())?;
        let first = simple.values.len();
        simple.values.extend(
            adjacency.targets.values[range]
                .iter()
                .copied()
                .filter(|&target| target != node),
        );
        simple.values[first..].sort_unstable();
        let mut kept = first;
        for index in first..simple.values.len() {
            if kept == first || simple.values[kept - 1] != simple.values[index] {
                simple.values[kept] = simple.values[index];
                kept += 1;
            }
        }
        simple.values.truncate(kept);
        simple_offsets.values[node + 1] = kept;
    }
    let degree = |node: usize| simple_offsets.values[node + 1] - simple_offsets.values[node];
    let included = |node: usize| options.max_degree.is_none_or(|limit| degree(node) <= limit);
    let rank = |node: usize| (degree(node), node);

    // Forward lists: included neighbours of higher rank, still sorted by row.
    let mut forward_offsets = Buffer::filled(n + 1, 0usize, context)?;
    let mut forward = Buffer::capacity(simple.values.len() / 2 + 1, context)?;
    for node in 0..n {
        meter.charge(1 + degree(node))?;
        if included(node) {
            let row = &simple.values[simple_offsets.values[node]..simple_offsets.values[node + 1]];
            forward.values.extend(
                row.iter()
                    .copied()
                    .filter(|&other| included(other) && rank(other) > rank(node)),
            );
        }
        forward_offsets.values[node + 1] = forward.values.len();
    }
    let forward_row = |node: usize| {
        &forward.values[forward_offsets.values[node]..forward_offsets.values[node + 1]]
    };

    // Work per node is about |fwd(u)| merges of length up to |fwd(u)| + |fwd(v)|.
    let mut weights = Buffer::capacity(n, context)?;
    for node in 0..n {
        let len = forward_row(node).len();
        weights.values.push(len.saturating_mul(len));
    }
    let workers = parallel::concurrency(context, n.saturating_add(adjacency.targets.values.len()));
    let ranges = parallel::balanced_ranges(&weights.values, workers);
    let counts = Buffer::filled_with(n, || AtomicU64::new(0), context)?;

    parallel::map_ranges(workers, &ranges, |range| {
        let mut meter = context.work_meter();
        for u in range {
            let row_u = forward_row(u);
            for &v in row_u {
                let row_v = forward_row(v);
                meter.charge(1 + row_u.len() + row_v.len())?;
                // Both rows are sorted by node row: a plain merge finds every
                // common forward neighbour w, closing the triangle u-v-w once.
                let (mut i, mut j) = (0, 0);
                while i < row_u.len() && j < row_v.len() {
                    match row_u[i].cmp(&row_v[j]) {
                        std::cmp::Ordering::Less => i += 1,
                        std::cmp::Ordering::Greater => j += 1,
                        std::cmp::Ordering::Equal => {
                            for corner in [u, v, row_u[i]] {
                                counts.values[corner].fetch_add(1, Ordering::Relaxed);
                            }
                            i += 1;
                            j += 1;
                        }
                    }
                }
            }
        }
        Ok(())
    })?;

    let mut triangles = Buffer::capacity(n, context)?;
    let mut coefficients = Buffer::capacity(n, context)?;
    let mut corners: u128 = 0;
    let mut coefficient_sum = 0.0f64;
    let mut coefficient_count = 0usize;
    let mut meter = context.work_meter();
    for node in 0..n {
        meter.charge(1)?;
        if !included(node) {
            triangles.values.push(-1);
            coefficients.values.push(f64::NAN);
            continue;
        }
        let count = counts.values[node].load(Ordering::Relaxed);
        corners += u128::from(count);
        triangles.values.push(
            i64::try_from(count)
                .map_err(|_| AlgorithmError::Numerical("triangle count exceeds Int64".into()))?,
        );
        let d = degree(node);
        if d < 2 {
            coefficients.values.push(f64::NAN);
        } else {
            let coefficient = 2.0 * count as f64 / (d as f64 * (d as f64 - 1.0));
            coefficient_sum += coefficient;
            coefficient_count += 1;
            coefficients.values.push(coefficient);
        }
    }
    let total = i64::try_from(corners / 3)
        .map_err(|_| AlgorithmError::Numerical("triangle count exceeds Int64".into()))?;
    Ok(Triangles {
        graph: graph.clone(),
        triangles,
        coefficients,
        total,
        average: if coefficient_count == 0 {
            0.0
        } else {
            coefficient_sum / coefficient_count as f64
        },
    })
}
