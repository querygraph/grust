//! Leiden community detection: Louvain with a refinement phase that keeps
//! every community connected.

use crate::{
    GraphProjection, Orientation, Result,
    buffer::Buffer,
    louvain::{self, Level, Louvain, LouvainOptions},
    random,
};
use grust_procedures::ExecutionContext;

/// Leiden takes Louvain's controls.
pub type LeidenOptions = LouvainOptions;
/// Leiden returns Louvain's result shape.
pub type Leiden = Louvain;

/// Detect communities by modularity, guaranteeing each one is **connected**.
///
/// Louvain can leave a community in two pieces: a node that held it together
/// moves away and nothing looks back. Leiden (Traag, Waltman and van Eck, 2019)
/// adds a refinement between moving and coarsening. Inside each community found
/// by the move phase, nodes start alone again and merge only with a neighbour's
/// group, only while still alone, and only when the merge does not lower
/// modularity. A group is therefore grown one attached node at a time and is
/// connected; the next level coarsens these groups, not the move phase's
/// communities, and starts its move phase from those communities.
///
/// **The result is always the refined partition**, so it is connected however
/// the run ends, including at `max_levels`. Communities follow arcs in either
/// direction: connected means weakly connected on a directed projection. An arc
/// of zero weight attaches nothing.
///
/// **Refinement is greedy here.** The paper picks among the admissible merges at
/// random, with a temperature `theta`; this picks the best one, ties to the
/// smallest group, which is that rule's limit as `theta` goes to zero. It keeps
/// the connectivity guarantee and makes the run reproducible, and it gives up
/// the paper's guarantee of eventually reaching every optimal partition.
///
/// Orientation, multigraph and self-loop semantics, options and determinism are
/// Louvain's. Its modularity is often, but not always, higher than Louvain's.
pub fn leiden(graph: &GraphProjection, options: LeidenOptions) -> Result<Leiden> {
    graph.require_nonnegative("leiden")?;
    let context = graph.execution();
    context.checkpoint()?;
    louvain::validate(&options)?;
    let n = graph.node_count();
    let directed = graph.orientation() != Orientation::Undirected;
    let mut level = louvain::first_level(graph, directed, context)?;

    // `assignment[v]` is v's node in the current level: the refined groups.
    let mut assignment = Buffer::capacity(n, context)?;
    assignment.values.extend(0..n);
    let mut initial: Option<Buffer<usize>> = None;
    let mut levels = 0usize;
    let mut converged = false;

    for depth in 0..options.max_levels {
        let outcome = louvain::move_nodes(
            &level,
            directed,
            &options,
            depth as u64,
            initial.as_ref().map(|labels| labels.values.as_slice()),
            context,
        )?;
        let refined = refine(
            &level,
            &outcome.community,
            directed,
            &options,
            depth as u64,
            context,
        )?;
        let (dense, count) = louvain::renumber(&refined, context)?;
        if count == level.nodes() {
            // Nothing merged: the groups carried so far are the answer.
            converged = outcome.settled;
            break;
        }
        levels += 1;
        let mut meter = context.work_meter();
        for slot in &mut assignment.values {
            meter.charge(1)?;
            *slot = dense.values[*slot];
        }
        // The next level's nodes are these groups; each starts in the community
        // the move phase gave its members, named by that community's first group.
        let mut first_group = Buffer::filled(level.nodes(), usize::MAX, context)?;
        let mut next_initial = Buffer::filled(count, 0usize, context)?;
        for node in 0..level.nodes() {
            meter.charge(1)?;
            let community = outcome.community.values[node];
            let group = dense.values[node];
            if first_group.values[community] == usize::MAX {
                first_group.values[community] = group;
            }
            next_initial.values[group] = first_group.values[community];
        }
        level = louvain::coarsen(&level, &dense, count, directed, context)?;
        initial = Some(next_initial);
    }
    louvain::finish(
        graph,
        &assignment.values,
        levels,
        converged,
        options.resolution,
    )
}

/// Split each community of `community` into connected groups. Returns a label
/// per node; a group is labelled by the node that founded it.
fn refine(
    level: &Level,
    community: &Buffer<usize>,
    directed: bool,
    options: &LouvainOptions,
    depth: u64,
    context: &ExecutionContext,
) -> Result<Buffer<usize>> {
    let n = level.nodes();
    let mut meter = context.work_meter();
    let gamma = options.resolution;
    // Both matrix entries of an undirected arc, as in the move phase.
    let scale = if directed { 1.0 } else { 2.0 };
    let in_rows = |node: usize| match &level.incoming {
        Some((offsets, _, _)) => offsets.values[node]..offsets.values[node + 1],
        None => 0..0,
    };

    // Strengths, per node and per community, and each node's weight to the
    // rest of its own community.
    let mut k_out = Buffer::capacity(n, context)?;
    let mut k_in = Buffer::capacity(n, context)?;
    let mut external = Buffer::filled(n, 0.0f64, context)?;
    let mut community_out = Buffer::filled(n, 0.0f64, context)?;
    let mut community_in = Buffer::filled(n, 0.0f64, context)?;
    for node in 0..n {
        let row = level.row(node);
        meter.charge(1 + row.len() + in_rows(node).len())?;
        let own = level.inside.values[node];
        let mut out = own;
        for arc in row {
            let weight = level.weights.values[arc];
            out += weight;
            if community.values[level.targets.values[arc]] == community.values[node] {
                external.values[node] += scale * weight;
            }
        }
        let mut into = own;
        match &level.incoming {
            Some((_, sources, weights)) => {
                for arc in in_rows(node) {
                    into += weights.values[arc];
                    if community.values[sources.values[arc]] == community.values[node] {
                        external.values[node] += weights.values[arc];
                    }
                }
            }
            None => into = out,
        }
        k_out.values.push(out);
        k_in.values.push(into);
        community_out.values[community.values[node]] += out;
        community_in.values[community.values[node]] += into;
    }
    let total: f64 = k_out.values.iter().sum();

    let mut group = Buffer::capacity(n, context)?;
    group.values.extend(0..n);
    if total <= 0.0 || !total.is_finite() {
        return Ok(group);
    }
    let mut group_out = Buffer::capacity(n, context)?;
    group_out.values.extend_from_slice(&k_out.values);
    let mut group_in = Buffer::capacity(n, context)?;
    group_in.values.extend_from_slice(&k_in.values);
    let mut alone = Buffer::filled(n, true, context)?;

    // A set S inside community C is well connected when its weight to the rest
    // of C is at least what the null model expects.
    let well_connected = |weight: f64, out: f64, into: f64, c: usize| {
        weight
            >= gamma
                * (out * (community_in.values[c] - into) + into * (community_out.values[c] - out))
                / total
    };

    let mut order = Buffer::capacity(n, context)?;
    order.values.extend(0..n);
    if let Some(seed) = options.seed {
        // A stream of its own, so refinement does not replay the move order.
        random::shuffle(&mut order.values, seed, depth ^ (1 << 63));
    }
    let mut affinity = Buffer::filled(n, 0.0f64, context)?;
    let mut touched = Buffer::<usize>::capacity(n, context)?;

    for &node in &order.values {
        let home = community.values[node];
        meter.charge(1 + level.row(node).len() + in_rows(node).len())?;
        if !alone.values[node]
            || !well_connected(
                external.values[node],
                k_out.values[node],
                k_in.values[node],
                home,
            )
        {
            continue;
        }
        let mut reach = |other: usize, weight: f64| {
            if community.values[other] == home && weight > 0.0 {
                let label = group.values[other];
                if affinity.values[label] == 0.0 {
                    touched.values.push(label);
                }
                affinity.values[label] += weight;
            }
        };
        for arc in level.row(node) {
            reach(level.targets.values[arc], scale * level.weights.values[arc]);
        }
        if let Some((_, sources, weights)) = &level.incoming {
            for arc in in_rows(node) {
                reach(sources.values[arc], weights.values[arc]);
            }
        }

        // The node is alone, so lifting it out leaves an empty group scoring 0.
        let mut best = None;
        let mut best_score = 0.0;
        for &label in &touched.values {
            if !well_connected(
                external.values[label],
                group_out.values[label],
                group_in.values[label],
                home,
            ) {
                continue;
            }
            let score = affinity.values[label]
                - gamma
                    * (k_out.values[node] * group_in.values[label]
                        + k_in.values[node] * group_out.values[label])
                    / total;
            let better = match best {
                None => score >= best_score,
                Some(current) => score > best_score || (score == best_score && label < current),
            };
            if better {
                best = Some(label);
                best_score = score;
            }
        }
        if let Some(label) = best {
            // `external` is kept per group under its label.
            external.values[label] =
                external.values[label] + external.values[node] - 2.0 * affinity.values[label];
            group_out.values[label] += k_out.values[node];
            group_in.values[label] += k_in.values[node];
            group.values[node] = label;
            alone.values[node] = false;
            alone.values[label] = false;
        }
        for &label in &touched.values {
            affinity.values[label] = 0.0;
        }
        touched.values.clear();
    }
    Ok(group)
}
