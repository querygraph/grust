//! Louvain community detection: greedy modularity optimization by local moves
//! and coarsening (Blondel et al. 2008), for undirected and directed graphs.
//!
//! One formula serves both. With `A` the (weighted) adjacency matrix, `M` the
//! sum of all its entries, and per community `in_c = Σ A_ij` over members,
//! `out_c = Σ k_out`, `into_c = Σ k_in`:
//!
//! ```text
//! Q = Σ_c [ in_c / M  −  γ · out_c · into_c / M² ]
//! ```
//!
//! On an `Undirected` projection `A` is symmetric (each edge is two arcs, a
//! loop contributes `2w` to `A_uu`), `M = 2m`, and this is Newman's modularity.
//! On `Outgoing` and `Incoming` projections `A_ij` is the arc weight, `M = m`,
//! and this is Leicht and Newman's directed modularity.

use crate::{
    AlgorithmError, GraphProjection, Orientation, Result,
    buffer::Buffer,
    meter::Meter,
    random,
    table::{NodeColumn, NodeTable, TableScalar},
};
use grust_procedures::ExecutionContext;

/// Louvain controls.
#[derive(Clone, Copy, Debug)]
pub struct LouvainOptions {
    /// Resolution γ: finite and nonnegative. 1 is standard modularity; larger
    /// values favour smaller communities, and 0 merges each connected component.
    pub resolution: f64,
    /// Positive maximum number of coarsening levels.
    pub max_levels: usize,
    /// Positive maximum number of sweeps over the nodes within one level.
    pub max_iterations: usize,
    /// A sweep, or a level, that improves modularity by less than this ends its
    /// loop. Finite and nonnegative.
    pub tolerance: f64,
    /// Visit nodes in a seeded random order. `None` visits them in row order.
    /// Either way the result is a function of the projection and the options.
    pub seed: Option<u64>,
}

impl Default for LouvainOptions {
    fn default() -> Self {
        Self {
            resolution: 1.0,
            max_levels: 10,
            max_iterations: 10,
            tolerance: 1e-4,
            seed: None,
        }
    }
}

/// A community per node, with the evidence of how it was reached.
pub struct Louvain {
    graph: GraphProjection,
    communities: Buffer<usize>,
    modularity: f64,
    levels: usize,
    converged: bool,
}

impl Louvain {
    /// Projection supplying external ids and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        &self.graph
    }
    /// Per node, the row of its community's smallest member: canonical ids, as
    /// `wcc` reports components.
    pub fn communities(&self) -> &[usize] {
        &self.communities.values
    }
    /// Modularity of the returned partition, recomputed from the projection
    /// rather than accumulated from the moves.
    pub fn modularity(&self) -> f64 {
        self.modularity
    }
    /// Coarsening levels that moved at least one node.
    pub fn levels(&self) -> usize {
        self.levels
    }
    /// Whether the search ended because no move improved modularity, rather
    /// than because `max_levels` or `max_iterations` stopped it.
    pub fn converged(&self) -> bool {
        self.converged
    }
    /// `communityId`, then the `modularity`, `levels` and `converged` scalars.
    pub fn into_table(self) -> Result<NodeTable> {
        let levels = i64::try_from(self.levels)
            .map_err(|_| AlgorithmError::Numerical("level count exceeds Int64".into()))?;
        Ok(NodeTable::new(&self.graph)
            .column("communityId", NodeColumn::Node(self.communities))?
            .scalar("modularity", TableScalar::Number(self.modularity))
            .scalar("levels", TableScalar::Integer(levels))
            .scalar("converged", TableScalar::Boolean(self.converged)))
    }
}

/// The graph one level works on. Rows hold arcs to **other** nodes only; what a
/// node carries to itself — loops at the first level, a whole community's
/// internal weight after coarsening — is `inside`, already in `A_uu` units.
struct Level {
    offsets: Buffer<usize>,
    targets: Buffer<usize>,
    weights: Buffer<f64>,
    inside: Buffer<f64>,
    /// In-arcs, for directed graphs only; an undirected row is its own mirror.
    incoming: Option<(Buffer<usize>, Buffer<usize>, Buffer<f64>)>,
}

impl Level {
    fn nodes(&self) -> usize {
        self.inside.values.len()
    }
    fn row(&self, node: usize) -> std::ops::Range<usize> {
        self.offsets.values[node]..self.offsets.values[node + 1]
    }
}

/// Detect communities by modularity.
///
/// **Orientation.** An `Undirected` projection is optimized for Newman's
/// modularity; `Outgoing` and `Incoming` projections for Leicht and Newman's
/// directed modularity, which rewards arcs that are surprising given the
/// source's out-strength and the target's in-strength.
///
/// **Multigraphs.** Parallel edges add their weights. A self-loop of weight `w`
/// contributes `2w` to its node's strength and to its community's internal
/// weight on an undirected projection, and `w` on a directed one. Isolates, and
/// every node of a graph with no weight at all, stay singleton communities.
///
/// **Determinism.** Nodes are visited in row order, or in the order `seed`
/// fixes; ties go to staying put, then to the community whose current id is
/// smallest. Moves are applied one at a time, so the result does not depend on
/// the rayon pool: asynchronous parallel moves, which NetworKit's PLM uses, are
/// not reproducible, and reproducibility is the contract here.
pub fn louvain(graph: &GraphProjection, options: LouvainOptions) -> Result<Louvain> {
    let context = graph.execution();
    context.checkpoint()?;
    if !options.resolution.is_finite()
        || options.resolution < 0.0
        || !options.tolerance.is_finite()
        || options.tolerance < 0.0
        || options.max_levels == 0
        || options.max_iterations == 0
    {
        return Err(AlgorithmError::InvalidArguments(
            "Louvain requires finite nonnegative resolution and tolerance, and positive maxLevels and maxIterations".into(),
        ));
    }
    let n = graph.node_count();
    let directed = graph.orientation() != Orientation::Undirected;
    let mut level = first_level(graph, directed, context)?;

    // `assignment[v]` is v's node in the current level.
    let mut assignment = Buffer::capacity(n, context)?;
    assignment.values.extend(0..n);
    let mut levels = 0usize;
    let mut converged = false;

    for depth in 0..options.max_levels {
        let outcome = move_nodes(&level, directed, &options, depth as u64, context)?;
        if !outcome.moved {
            converged = outcome.settled;
            break;
        }
        levels += 1;
        let (dense, count) = renumber(&outcome.community, context)?;
        let mut meter = Meter::new(context);
        for slot in &mut assignment.values {
            meter.tick(1)?;
            *slot = dense.values[*slot];
        }
        meter.flush()?;
        if count == level.nodes() {
            // Every node moved into a community of one: nothing left to merge.
            converged = true;
            break;
        }
        if outcome.gain < options.tolerance {
            converged = true;
            break;
        }
        level = coarsen(&level, &dense, count, directed, context)?;
    }

    // Canonical ids: the smallest member's row.
    let mut smallest = Buffer::filled(n, usize::MAX, context)?;
    for (node, &community) in assignment.values.iter().enumerate() {
        if smallest.values[community] == usize::MAX {
            smallest.values[community] = node;
        }
    }
    let mut communities = Buffer::capacity(n, context)?;
    communities
        .values
        .extend(assignment.values.iter().map(|&c| smallest.values[c]));
    let modularity = modularity_of(graph, &communities.values, options.resolution, context)?;
    Ok(Louvain {
        graph: graph.clone(),
        communities,
        modularity,
        levels,
        converged,
    })
}

/// Modularity of `communities` (any labels below the node count) on `graph`,
/// by the formula at the top of this file. Independent of the search.
pub(crate) fn modularity_of(
    graph: &GraphProjection,
    communities: &[usize],
    resolution: f64,
    context: &ExecutionContext,
) -> Result<f64> {
    let n = graph.node_count();
    let directed = graph.orientation() != Orientation::Undirected;
    let adjacency = graph.outgoing();
    let mut inside = Buffer::filled(n, 0.0f64, context)?;
    let mut out = Buffer::filled(n, 0.0f64, context)?;
    let mut into = Buffer::filled(n, 0.0f64, context)?;
    let mut total = 0.0f64;
    let mut meter = Meter::new(context);
    for source in 0..n {
        let range = adjacency.range(source);
        meter.tick(1 + range.len())?;
        for arc in range {
            let target = adjacency.targets.values[arc];
            // An undirected loop occupies one arc but is two matrix entries' worth.
            let weight = if !directed && target == source {
                2.0 * adjacency.weight(arc)
            } else {
                adjacency.weight(arc)
            };
            total += weight;
            out.values[communities[source]] += weight;
            into.values[communities[target]] += weight;
            if communities[source] == communities[target] {
                inside.values[communities[source]] += weight;
            }
        }
    }
    meter.flush()?;
    if total <= 0.0 {
        return Ok(0.0);
    }
    let mut modularity = 0.0;
    for community in 0..n {
        modularity += inside.values[community] / total
            - resolution * (out.values[community] / total) * (into.values[community] / total);
    }
    if !modularity.is_finite() {
        return Err(AlgorithmError::Numerical("modularity is not finite".into()));
    }
    Ok(modularity)
}

fn first_level(
    graph: &GraphProjection,
    directed: bool,
    context: &ExecutionContext,
) -> Result<Level> {
    let n = graph.node_count();
    let adjacency = graph.outgoing();
    let arcs = adjacency.targets.values.len();
    let mut offsets = Buffer::filled(n + 1, 0usize, context)?;
    let mut targets = Buffer::capacity(arcs, context)?;
    let mut weights = Buffer::capacity(arcs, context)?;
    let mut inside = Buffer::filled(n, 0.0f64, context)?;
    let mut meter = Meter::new(context);
    for node in 0..n {
        let range = adjacency.range(node);
        meter.tick(1 + range.len())?;
        for arc in range {
            let target = adjacency.targets.values[arc];
            let weight = adjacency.weight(arc);
            if target == node {
                inside.values[node] += if directed { weight } else { 2.0 * weight };
            } else {
                targets.values.push(target);
                weights.values.push(weight);
            }
        }
        offsets.values[node + 1] = targets.values.len();
    }
    meter.flush()?;
    let incoming = directed
        .then(|| transpose(&offsets, &targets, &weights, context))
        .transpose()?;
    Ok(Level {
        offsets,
        targets,
        weights,
        inside,
        incoming,
    })
}

type Csr = (Buffer<usize>, Buffer<usize>, Buffer<f64>);

fn transpose(
    offsets: &Buffer<usize>,
    targets: &Buffer<usize>,
    weights: &Buffer<f64>,
    context: &ExecutionContext,
) -> Result<Csr> {
    let n = offsets.values.len() - 1;
    let arcs = targets.values.len();
    let mut meter = Meter::new(context);
    let mut reversed = Buffer::filled(n + 1, 0usize, context)?;
    for &target in &targets.values {
        reversed.values[target + 1] += 1;
    }
    for node in 0..n {
        reversed.values[node + 1] += reversed.values[node];
    }
    let mut next = Buffer::capacity(n, context)?;
    next.values.extend_from_slice(&reversed.values[..n]);
    let mut sources = Buffer::filled(arcs, 0usize, context)?;
    let mut carried = Buffer::filled(arcs, 0.0f64, context)?;
    for source in 0..n {
        let range = offsets.values[source]..offsets.values[source + 1];
        meter.tick(1 + range.len())?;
        for arc in range {
            let slot = next.values[targets.values[arc]];
            next.values[targets.values[arc]] += 1;
            sources.values[slot] = source;
            carried.values[slot] = weights.values[arc];
        }
    }
    meter.flush()?;
    Ok((reversed, sources, carried))
}

struct Moves {
    community: Buffer<usize>,
    /// Any node changed community in this level.
    moved: bool,
    /// The last sweep moved nothing: a local optimum, not a limit.
    settled: bool,
    /// Modularity gained in this level.
    gain: f64,
}

fn move_nodes(
    level: &Level,
    directed: bool,
    options: &LouvainOptions,
    depth: u64,
    context: &ExecutionContext,
) -> Result<Moves> {
    let n = level.nodes();
    let mut meter = Meter::new(context);

    // Strengths, and the total M they sum to.
    let mut k_out = Buffer::capacity(n, context)?;
    let mut k_in = Buffer::capacity(n, context)?;
    for node in 0..n {
        let row = level.row(node);
        meter.tick(1 + row.len())?;
        let own = level.inside.values[node];
        k_out
            .values
            .push(own + level.weights.values[row].iter().sum::<f64>());
        k_in.values.push(match &level.incoming {
            Some((offsets, _, weights)) => {
                own + weights.values[offsets.values[node]..offsets.values[node + 1]]
                    .iter()
                    .sum::<f64>()
            }
            None => k_out.values[node],
        });
    }
    let total: f64 = k_out.values.iter().sum();
    let mut community = Buffer::capacity(n, context)?;
    community.values.extend(0..n);
    if !total.is_finite() {
        return Err(AlgorithmError::Numerical(
            "total edge weight is not finite".into(),
        ));
    }
    if total <= 0.0 {
        return Ok(Moves {
            community,
            moved: false,
            settled: true,
            gain: 0.0,
        });
    }

    let mut out_of = Buffer::capacity(n, context)?;
    out_of.values.extend_from_slice(&k_out.values);
    let mut into = Buffer::capacity(n, context)?;
    into.values.extend_from_slice(&k_in.values);
    let mut order = Buffer::capacity(n, context)?;
    order.values.extend(0..n);
    if let Some(seed) = options.seed {
        random::shuffle(&mut order.values, seed, depth);
    }

    // Weight between the node under consideration and each nearby community;
    // `touched` lists the communities to reset, so a sweep never clears O(n).
    let mut affinity = Buffer::filled(n, 0.0f64, context)?;
    let mut seen = Buffer::filled(n, false, context)?;
    let mut touched = Buffer::capacity(n, context)?;
    let gamma = options.resolution;
    let mut moved = false;
    let mut settled = false;
    let mut level_gain = 0.0f64;

    for _ in 0..options.max_iterations {
        let mut sweep_moves = 0usize;
        let mut sweep_gain = 0.0f64;
        for &node in &order.values {
            let home = community.values[node];
            touched.values.clear();
            seen.values[home] = true;
            touched.values.push(home);
            let row = level.row(node);
            meter.tick(1 + row.len())?;
            for arc in row {
                let other = community.values[level.targets.values[arc]];
                if !seen.values[other] {
                    seen.values[other] = true;
                    touched.values.push(other);
                }
                // An undirected arc stands for both matrix entries.
                affinity.values[other] +=
                    level.weights.values[arc] * if directed { 1.0 } else { 2.0 };
            }
            if let Some((offsets, sources, weights)) = &level.incoming {
                let row = offsets.values[node]..offsets.values[node + 1];
                meter.tick(row.len())?;
                for arc in row {
                    let other = community.values[sources.values[arc]];
                    if !seen.values[other] {
                        seen.values[other] = true;
                        touched.values.push(other);
                    }
                    affinity.values[other] += weights.values[arc];
                }
            }

            // Lift the node out, then score every candidate the same way.
            out_of.values[home] -= k_out.values[node];
            into.values[home] -= k_in.values[node];
            let score = |candidate: usize| {
                affinity.values[candidate]
                    - gamma
                        * (k_out.values[node] * into.values[candidate]
                            + k_in.values[node] * out_of.values[candidate])
                        / total
            };
            let stay = score(home);
            let mut best = home;
            let mut best_score = stay;
            for &candidate in &touched.values {
                let value = score(candidate);
                if value > best_score || (value == best_score && best != home && candidate < best) {
                    best = candidate;
                    best_score = value;
                }
            }
            out_of.values[best] += k_out.values[node];
            into.values[best] += k_in.values[node];
            if best != home {
                community.values[node] = best;
                sweep_moves += 1;
                sweep_gain += (best_score - stay) / total;
            }
            for &candidate in &touched.values {
                affinity.values[candidate] = 0.0;
                seen.values[candidate] = false;
            }
        }
        level_gain += sweep_gain;
        if sweep_moves == 0 {
            settled = true;
            break;
        }
        moved = true;
        if sweep_gain < options.tolerance {
            settled = true;
            break;
        }
    }
    meter.flush()?;
    Ok(Moves {
        community,
        moved,
        settled,
        gain: level_gain,
    })
}

/// Dense ids in order of each community's smallest member.
fn renumber(
    community: &Buffer<usize>,
    context: &ExecutionContext,
) -> Result<(Buffer<usize>, usize)> {
    let n = community.values.len();
    let mut id = Buffer::filled(n, usize::MAX, context)?;
    let mut dense = Buffer::capacity(n, context)?;
    let mut count = 0;
    for &label in &community.values {
        if id.values[label] == usize::MAX {
            id.values[label] = count;
            count += 1;
        }
        dense.values.push(id.values[label]);
    }
    Ok((dense, count))
}

fn coarsen(
    level: &Level,
    dense: &Buffer<usize>,
    count: usize,
    directed: bool,
    context: &ExecutionContext,
) -> Result<Level> {
    let n = level.nodes();
    let mut meter = Meter::new(context);

    // Members grouped by community, by counting sort.
    let mut start = Buffer::filled(count + 1, 0usize, context)?;
    for &community in &dense.values {
        start.values[community + 1] += 1;
    }
    for community in 0..count {
        start.values[community + 1] += start.values[community];
    }
    let mut next = Buffer::capacity(count, context)?;
    next.values.extend_from_slice(&start.values[..count]);
    let mut members = Buffer::filled(n, 0usize, context)?;
    for node in 0..n {
        let community = dense.values[node];
        members.values[next.values[community]] = node;
        next.values[community] += 1;
    }
    meter.tick(n)?;

    let mut offsets = Buffer::filled(count + 1, 0usize, context)?;
    let mut targets = Buffer::capacity(level.targets.values.len(), context)?;
    let mut weights = Buffer::capacity(level.targets.values.len(), context)?;
    let mut inside = Buffer::filled(count, 0.0f64, context)?;
    let mut sum = Buffer::filled(count, 0.0f64, context)?;
    let mut seen = Buffer::filled(count, false, context)?;
    let mut touched = Buffer::capacity(count, context)?;
    for community in 0..count {
        touched.values.clear();
        for &node in &members.values[start.values[community]..start.values[community + 1]] {
            inside.values[community] += level.inside.values[node];
            let row = level.row(node);
            meter.tick(1 + row.len())?;
            for arc in row {
                let other = dense.values[level.targets.values[arc]];
                let weight = level.weights.values[arc];
                if other == community {
                    // Both arcs of an undirected internal edge pass through here.
                    inside.values[community] += weight;
                    continue;
                }
                if !seen.values[other] {
                    seen.values[other] = true;
                    touched.values.push(other);
                }
                sum.values[other] += weight;
            }
        }
        // Sorted so the coarse rows do not depend on member order.
        touched.values.sort_unstable();
        for &other in &touched.values {
            targets.values.push(other);
            weights.values.push(sum.values[other]);
            sum.values[other] = 0.0;
            seen.values[other] = false;
        }
        offsets.values[community + 1] = targets.values.len();
    }
    meter.flush()?;
    let incoming = directed
        .then(|| transpose(&offsets, &targets, &weights, context))
        .transpose()?;
    Ok(Level {
        offsets,
        targets,
        weights,
        inside,
        incoming,
    })
}
