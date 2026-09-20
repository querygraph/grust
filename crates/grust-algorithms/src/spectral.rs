//! Eigenvector centrality, Katz centrality and HITS: power iterations that pull
//! each node's next value from its neighbours' current ones.

use crate::{
    AlgorithmError, GraphProjection, Result,
    buffer::Buffer,
    parallel,
    projection::Adjacency,
    table::{NodeColumn, NodeTable, TableScalar},
};
use grust_procedures::ExecutionContext;

/// Stopping rule shared by the three iterations.
#[derive(Clone, Copy, Debug)]
pub struct IterationOptions {
    /// Stop when the L1 change between iterations is at most this.
    pub tolerance: f64,
    /// Positive maximum number of iterations.
    pub max_iterations: usize,
}

impl Default for IterationOptions {
    fn default() -> Self {
        Self {
            tolerance: 1e-8,
            max_iterations: 1000,
        }
    }
}

/// Katz controls.
#[derive(Clone, Copy, Debug)]
pub struct KatzOptions {
    /// Attenuation per hop; positive. The series converges only below
    /// `1 / λmax`. `1 / (largest in-strength)` is below that, so it is a safe
    /// choice, not the largest one.
    ///
    /// **Choose it from the graph.** The default of 0.1 suits sparse graphs and
    /// fails on dense ones: a 4,000-node social graph with a hub of degree 1,045
    /// has `λmax` well above 10, and the run then diverges and says so. Take the
    /// largest in-strength from `degree`, and start from a fraction of its
    /// reciprocal.
    pub alpha: f64,
    /// What every node starts from; positive.
    pub beta: f64,
    /// Scale the result to unit Euclidean length.
    pub normalized: bool,
    /// When to stop.
    pub iteration: IterationOptions,
}

impl Default for KatzOptions {
    fn default() -> Self {
        Self {
            alpha: 0.1,
            beta: 1.0,
            normalized: false,
            iteration: IterationOptions::default(),
        }
    }
}

/// Scores with convergence evidence. Reaching the iteration limit returns
/// `converged() == false`; convergence is never asserted silently.
pub struct IteratedScores {
    graph: GraphProjection,
    columns: Vec<(&'static str, Buffer<f64>)>,
    iterations: usize,
    residual: f64,
    converged: bool,
}

impl IteratedScores {
    /// Projection supplying external ids and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        &self.graph
    }
    /// A score column by name: `score`, or `hub` and `authority` for HITS.
    pub fn values(&self, name: &str) -> Option<&[f64]> {
        self.columns
            .iter()
            .find_map(|(column, values)| (*column == name).then_some(values.values.as_slice()))
    }
    /// Completed iterations.
    pub fn iterations(&self) -> usize {
        self.iterations
    }
    /// Last L1 change.
    pub fn residual(&self) -> f64 {
        self.residual
    }
    /// Whether the tolerance was reached.
    pub fn converged(&self) -> bool {
        self.converged
    }
    /// The score columns, then `iterations`, `converged` and `residual`.
    pub fn into_table(self) -> Result<NodeTable> {
        let iterations = i64::try_from(self.iterations)
            .map_err(|_| AlgorithmError::Numerical("iteration count exceeds Int64".into()))?;
        let mut table = NodeTable::new(&self.graph);
        for (name, values) in self.columns {
            table = table.column(name, NodeColumn::Number(values))?;
        }
        Ok(table
            .scalar("iterations", TableScalar::Integer(iterations))
            .scalar("converged", TableScalar::Boolean(self.converged))
            .scalar("residual", TableScalar::Number(self.residual)))
    }
}

/// Nodes per chunk. Fixed, so every sum groups its terms the same way whatever
/// the worker count, and results are identical at any.
const CHUNK: usize = 4096;

fn validate(options: IterationOptions) -> Result<()> {
    if !options.tolerance.is_finite() || options.tolerance < 0.0 || options.max_iterations == 0 {
        return Err(AlgorithmError::InvalidArguments(
            "tolerance must be finite and nonnegative, and maxIterations positive".into(),
        ));
    }
    Ok(())
}

/// `into[v] = keep * from[v] + beta + alpha * Σ weight * from[u]` over the arcs
/// `arcs` lists for `v`. Returns the sum of squares of `into`.
fn pull(
    arcs: &Adjacency,
    from: &[f64],
    into: &mut [f64],
    (keep, beta, alpha): (f64, f64, f64),
    context: &ExecutionContext,
) -> Result<f64> {
    // Chunks are fixed, so the worker count cannot change a sum; it only
    // decides how many chunks run at once.
    let workers = parallel::concurrency(
        context,
        into.len().saturating_add(arcs.targets.values.len()),
    );
    let sums = parallel::for_chunks(workers, into, CHUNK, |first, chunk| {
        let mut meter = context.work_meter();
        let mut squares = 0.0;
        for (offset, value) in chunk.iter_mut().enumerate() {
            let node = first + offset;
            let range = arcs.range(node);
            meter.charge(1 + range.len())?;
            let mut sum = 0.0;
            for arc in range {
                sum += arcs.weight(arc) * from[arcs.targets.values[arc]];
            }
            *value = keep * from[node] + beta + alpha * sum;
            squares += *value * *value;
        }
        Ok(squares)
    })?;
    Ok(sums.into_iter().sum())
}

/// Divide `values` by `divisor` and return their L1 distance from `previous`.
fn settle(
    values: &mut [f64],
    previous: &[f64],
    divisor: f64,
    context: &ExecutionContext,
) -> Result<f64> {
    let workers = parallel::concurrency(context, values.len());
    let sums = parallel::for_chunks(workers, values, CHUNK, |first, chunk| {
        context.charge_work(chunk.len())?;
        let mut change = 0.0;
        for (offset, value) in chunk.iter_mut().enumerate() {
            *value /= divisor;
            change += (*value - previous[first + offset]).abs();
        }
        Ok(change)
    })?;
    Ok(sums.into_iter().sum())
}

fn nonfinite(what: &str) -> AlgorithmError {
    AlgorithmError::Numerical(format!("{what} left the finite range"))
}

/// Eigenvector centrality: a node is important when important nodes point at it.
///
/// The score is the principal eigenvector of the adjacency matrix, of unit
/// Euclidean length and nonnegative, with influence flowing **along** the
/// projection's arcs. It iterates `x ← (A + I)x`, not `x ← Ax`: the shift
/// leaves the eigenvectors alone and removes the oscillation that stops plain
/// power iteration from converging on a bipartite graph. It starts uniform.
///
/// Where the principal eigenvector is not unique (a disconnected graph) the
/// result is *an* eigenvector, the one reached from the uniform start. On a
/// graph with no cycle there is nothing to be principal; the iteration drifts
/// toward the sinks and usually stops at the limit with `converged == false`.
///
/// Identical at any worker count.
pub fn eigenvector(graph: &GraphProjection, options: IterationOptions) -> Result<IteratedScores> {
    graph.require_nonnegative("eigenvector")?;
    let context = graph.execution();
    context.checkpoint()?;
    validate(options)?;
    let n = graph.node_count();
    let incoming = graph.incoming()?;
    let mut current = Buffer::filled(n, 1.0 / (n.max(1) as f64).sqrt(), context)?;
    let mut next = Buffer::filled(n, 0.0, context)?;
    let (mut iterations, mut residual, mut converged) = (0, 0.0, n == 0);
    while !converged && iterations < options.max_iterations {
        let squares = pull(
            &incoming,
            &current.values,
            &mut next.values,
            (1.0, 0.0, 1.0),
            context,
        )?;
        if !squares.is_finite() {
            return Err(nonfinite("eigenvector scores"));
        }
        residual = settle(&mut next.values, &current.values, squares.sqrt(), context)?;
        std::mem::swap(&mut current, &mut next);
        iterations += 1;
        converged = residual <= options.tolerance;
    }
    Ok(IteratedScores {
        graph: graph.clone(),
        columns: vec![("score", current)],
        iterations,
        residual,
        converged,
    })
}

/// Katz centrality: `x = beta + alpha * Σ x[u]` over the nodes `u` pointing at
/// each node, so every walk into a node counts, attenuated by `alpha` per hop.
///
/// The series converges only for `alpha < 1 / λmax`. That is not checked up
/// front, because the cheap bound `1 / (largest in-strength)` would refuse many
/// valid values. Instead a run that does not settle returns
/// `converged == false`, and one whose scores overflow fails and says why.
///
/// Identical at any worker count.
pub fn katz(graph: &GraphProjection, options: KatzOptions) -> Result<IteratedScores> {
    graph.require_nonnegative("katz")?;
    let context = graph.execution();
    context.checkpoint()?;
    validate(options.iteration)?;
    let positive = |value: f64| value.is_finite() && value > 0.0;
    if !positive(options.alpha) || !positive(options.beta) {
        return Err(AlgorithmError::InvalidArguments(
            "alpha and beta must be finite and positive".into(),
        ));
    }
    let n = graph.node_count();
    let incoming = graph.incoming()?;
    let mut current = Buffer::filled(n, 0.0, context)?;
    let mut next = Buffer::filled(n, 0.0, context)?;
    let (mut iterations, mut residual, mut converged) = (0, 0.0, n == 0);
    let mut squares = 0.0;
    while !converged && iterations < options.iteration.max_iterations {
        squares = pull(
            &incoming,
            &current.values,
            &mut next.values,
            (0.0, options.beta, options.alpha),
            context,
        )?;
        if !squares.is_finite() {
            return Err(AlgorithmError::Numerical(
                "Katz scores left the finite range: alpha must be below 1/λmax, and any alpha below 1/(largest in-strength) is".into(),
            ));
        }
        residual = settle(&mut next.values, &current.values, 1.0, context)?;
        std::mem::swap(&mut current, &mut next);
        iterations += 1;
        converged = residual <= options.iteration.tolerance;
    }
    if options.normalized && squares > 0.0 {
        settle(&mut current.values, &next.values, squares.sqrt(), context)?;
    }
    Ok(IteratedScores {
        graph: graph.clone(),
        columns: vec![("score", current)],
        iterations,
        residual,
        converged,
    })
}

/// HITS: a good **hub** points at good authorities, a good **authority** is
/// pointed at by good hubs. Both have unit Euclidean length; a graph with no
/// arcs scores zero everywhere. The residual is the L1 change of both together.
///
/// Identical at any worker count.
pub fn hits(graph: &GraphProjection, options: IterationOptions) -> Result<IteratedScores> {
    graph.require_nonnegative("hits")?;
    let context = graph.execution();
    context.checkpoint()?;
    validate(options)?;
    let n = graph.node_count();
    let incoming = graph.incoming()?;
    let outgoing = graph.outgoing();
    let mut hubs = Buffer::filled(n, 1.0 / (n.max(1) as f64).sqrt(), context)?;
    let mut authorities = Buffer::filled(n, 0.0, context)?;
    let mut scratch = Buffer::filled(n, 0.0, context)?;
    let (mut iterations, mut residual, mut converged) = (0, 0.0, n == 0);
    while !converged && iterations < options.max_iterations {
        // Authorities from hubs, over in-arcs; then hubs from the new
        // authorities, over out-arcs. A zero vector stays zero, undivided.
        let squares = pull(
            &incoming,
            &hubs.values,
            &mut scratch.values,
            (0.0, 0.0, 1.0),
            context,
        )?;
        if !squares.is_finite() {
            return Err(nonfinite("authority scores"));
        }
        let divisor = if squares > 0.0 { squares.sqrt() } else { 1.0 };
        residual = settle(&mut scratch.values, &authorities.values, divisor, context)?;
        std::mem::swap(&mut authorities, &mut scratch);

        let squares = pull(
            outgoing,
            &authorities.values,
            &mut scratch.values,
            (0.0, 0.0, 1.0),
            context,
        )?;
        if !squares.is_finite() {
            return Err(nonfinite("hub scores"));
        }
        let divisor = if squares > 0.0 { squares.sqrt() } else { 1.0 };
        residual += settle(&mut scratch.values, &hubs.values, divisor, context)?;
        std::mem::swap(&mut hubs, &mut scratch);

        iterations += 1;
        converged = residual <= options.tolerance;
    }
    Ok(IteratedScores {
        graph: graph.clone(),
        columns: vec![("hub", hubs), ("authority", authorities)],
        iterations,
        residual,
        converged,
    })
}
