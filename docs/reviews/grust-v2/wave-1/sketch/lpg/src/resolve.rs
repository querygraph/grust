//! Resolving a pattern against the schema graph.
//!
//! The pattern is a chain `N0 E0 N1 E1 ... Nk`. Each node step admits a set of
//! vertex groups (its label expression), and each edge step admits schema hops
//! (its type expression and direction), taken between `hops.min` and
//! `hops.max` times. A *schema path* picks one vertex group per node step and a
//! sequence of hops per edge step that connects them.
//!
//! Two phases, both over the product of pattern positions and vertex groups:
//!
//! 1. **Feasibility, backwards.** `finish[i]` is the set of groups at node `i`
//!    from which the rest of the pattern can be completed. For edge `i`, the
//!    groups that reach `finish[i+1]` in exactly `k` hops form layer `B_k`;
//!    `finish[i]` is node `i`'s candidates intersected with the union of `B_k`
//!    for `k` in the step's range. Unbounded ranges iterate to a fixpoint,
//!    which is reached within `|VPG|` further layers. Cost:
//!    `O(sum over edges of layers * (|VPG| + |EPG|))`.
//! 2. **Enumeration, forwards.** A depth-first walk that only steps where
//!    phase 1 says completion is still possible, so no walk is a dead end. It
//!    is output-sensitive and capped by [`ResolveOptions`].
//!
//! The path list, and the per-position sets derived from it, are complete
//! unless [`Resolution::truncated`] says a cap was hit.

use std::collections::{BTreeSet, VecDeque};

use crate::pattern::{EdgeStep, Pattern, PatternDirection};
use crate::types::Direction;
use crate::{EdgeGroup, EpgId, Lpg, VpgId};

/// One schema hop: an edge group, traversed forwards (source to target) or backwards.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct Hop {
    pub edge: EpgId,
    pub forward: bool,
    /// The vertex group the hop arrives at.
    pub to: VpgId,
}

/// A valid path: one vertex group per node step, and the hops of each edge step.
#[derive(Clone, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct SchemaPath {
    pub nodes: Vec<VpgId>,
    /// `segments[i]` is the hops taken for edge step `i`; its length is in that step's range.
    pub segments: Vec<Vec<Hop>>,
}

#[derive(Clone, Debug)]
pub struct ResolveOptions {
    /// Stop enumerating after this many paths.
    pub max_paths: usize,
    /// Hops an unbounded edge step (`{n,}`) may take while enumerating.
    pub unbounded_limit: usize,
}

impl Default for ResolveOptions {
    fn default() -> Self {
        Self {
            max_paths: 10_000,
            unbounded_limit: 8,
        }
    }
}

#[derive(Clone, Debug, Default, PartialEq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct Resolution {
    /// For each node step, the groups it binds to in some valid path. Exact when
    /// the enumeration completed; when truncated, the groups from which the rest
    /// of the pattern can be completed (a superset).
    pub node_groups: Vec<Vec<VpgId>>,
    /// For each edge step, the edge groups it uses in some valid path. Exact when
    /// the enumeration completed; when truncated, those of the paths enumerated.
    pub edge_groups: Vec<Vec<EpgId>>,
    /// The valid paths, in a deterministic order.
    pub paths: Vec<SchemaPath>,
    /// Whether a cap in [`ResolveOptions`] stopped the enumeration.
    pub truncated: bool,
}

impl Resolution {
    pub fn is_empty(&self) -> bool {
        self.node_groups.first().is_none_or(|g| g.is_empty())
    }
}

/// The hops leaving group `from` that `step` admits.
fn steps<L: Lpg>(lpg: &L, from: VpgId, step: &EdgeStep) -> Vec<Hop> {
    let mut out = Vec::new();
    for e in lpg.edge_groups() {
        if !step
            .types
            .matches(std::slice::from_ref(&e.edge_type().to_string()))
        {
            continue;
        }
        let either =
            step.direction == PatternDirection::Either || e.direction() == Direction::Undirected;
        let forward_ok = either || step.direction == PatternDirection::Outgoing;
        let backward_ok = either || step.direction == PatternDirection::Incoming;
        if forward_ok && e.source() == from {
            out.push(Hop {
                edge: e.id(),
                forward: true,
                to: e.target(),
            });
        }
        // A self-loop group traversed either way is one hop, not two.
        if backward_ok && e.target() == from && !(forward_ok && e.source() == e.target()) {
            out.push(Hop {
                edge: e.id(),
                forward: false,
                to: e.source(),
            });
        }
    }
    out.sort();
    out
}

/// `layers[k]` = groups that reach `goal` in exactly `k` admitted hops, for `k` up to `limit`.
fn backward_layers<L: Lpg>(
    lpg: &L,
    goal: &BTreeSet<VpgId>,
    step: &EdgeStep,
    limit: usize,
) -> Vec<BTreeSet<VpgId>> {
    let mut layers = vec![goal.clone()];
    for _ in 0..limit {
        let previous = layers.last().unwrap();
        let next: BTreeSet<VpgId> = lpg
            .vertex_groups()
            .iter()
            .map(crate::VertexGroup::id)
            .filter(|&v| steps(lpg, v, step).iter().any(|h| previous.contains(&h.to)))
            .collect();
        layers.push(next);
    }
    layers
}

struct Plan {
    /// finish[i]: groups at node i from which the pattern can be completed.
    finish: Vec<BTreeSet<VpgId>>,
    /// layers[i][k]: groups that reach finish[i+1] in exactly k hops of edge step i.
    layers: Vec<Vec<BTreeSet<VpgId>>>,
    /// Hops each edge step may take: [min, max] with unbounded steps capped.
    ranges: Vec<(usize, usize)>,
}

fn plan<L: Lpg>(lpg: &L, pattern: &Pattern, unbounded_limit: usize) -> Option<Plan> {
    if !pattern.is_well_formed() {
        return None;
    }
    let groups = lpg.vertex_groups().len();
    let candidates: Vec<BTreeSet<VpgId>> = pattern
        .nodes
        .iter()
        .map(|n| lpg.vertices_matching(&n.labels).into_iter().collect())
        .collect();
    let k = pattern.edges.len();
    let mut finish = vec![BTreeSet::new(); k + 1];
    let mut layers = vec![Vec::new(); k];
    let mut ranges = vec![(0, 0); k];
    finish[k] = candidates[k].clone();
    for i in (0..k).rev() {
        let step = &pattern.edges[i];
        // An unbounded step reaches its fixpoint within `groups` more layers;
        // enumeration is capped separately by `unbounded_limit`.
        let max = step
            .hops
            .max
            .unwrap_or(step.hops.min + groups.max(unbounded_limit));
        layers[i] = backward_layers(lpg, &finish[i + 1], step, max);
        let reach: BTreeSet<VpgId> = layers[i][step.hops.min..=max]
            .iter()
            .flatten()
            .copied()
            .collect();
        finish[i] = candidates[i].intersection(&reach).copied().collect();
        ranges[i] = (
            step.hops.min,
            step.hops.max.unwrap_or(step.hops.min + unbounded_limit),
        );
    }
    Some(Plan {
        finish,
        layers,
        ranges,
    })
}

pub fn is_feasible<L: Lpg>(lpg: &L, pattern: &Pattern) -> bool {
    plan(lpg, pattern, 0).is_some_and(|p| !p.finish[0].is_empty())
}

pub fn is_feasible_from<L: Lpg>(lpg: &L, from: VpgId, pattern: &Pattern) -> bool {
    plan(lpg, pattern, 0).is_some_and(|p| p.finish[0].contains(&from))
}

pub fn resolve<L: Lpg>(lpg: &L, pattern: &Pattern, options: &ResolveOptions) -> Resolution {
    let Some(plan) = plan(lpg, pattern, options.unbounded_limit) else {
        return Resolution::default();
    };
    let mut resolution = Resolution {
        node_groups: vec![Vec::new(); pattern.nodes.len()],
        edge_groups: vec![Vec::new(); pattern.edges.len()],
        ..Default::default()
    };
    let mut nodes = Vec::new();
    let mut segments: Vec<Vec<Hop>> = Vec::new();
    for &start in &plan.finish[0] {
        nodes.push(start);
        walk(
            lpg,
            pattern,
            &plan,
            options,
            0,
            start,
            &mut nodes,
            &mut segments,
            &mut resolution,
        );
        nodes.pop();
        if resolution.truncated {
            break;
        }
    }
    // The exact feasible sets come from the paths when enumeration completed,
    // and otherwise from the plan (nodes) and the steps between feasible groups (edges).
    let mut node_sets: Vec<BTreeSet<VpgId>> = vec![BTreeSet::new(); pattern.nodes.len()];
    let mut edge_sets: Vec<BTreeSet<EpgId>> = vec![BTreeSet::new(); pattern.edges.len()];
    for path in &resolution.paths {
        for (i, n) in path.nodes.iter().enumerate() {
            node_sets[i].insert(*n);
        }
        for (i, segment) in path.segments.iter().enumerate() {
            edge_sets[i].extend(segment.iter().map(|h| h.edge));
        }
    }
    if resolution.truncated {
        node_sets = plan.finish.clone();
    }
    resolution.node_groups = node_sets
        .into_iter()
        .map(|s| s.into_iter().collect())
        .collect();
    resolution.edge_groups = edge_sets
        .into_iter()
        .map(|s| s.into_iter().collect())
        .collect();
    resolution
}

#[allow(clippy::too_many_arguments)]
fn walk<L: Lpg>(
    lpg: &L,
    pattern: &Pattern,
    plan: &Plan,
    options: &ResolveOptions,
    edge: usize,
    at: VpgId,
    nodes: &mut Vec<VpgId>,
    segments: &mut Vec<Vec<Hop>>,
    out: &mut Resolution,
) {
    if out.truncated {
        return;
    }
    if edge == pattern.edges.len() {
        if out.paths.len() >= options.max_paths {
            out.truncated = true;
            return;
        }
        out.paths.push(SchemaPath {
            nodes: nodes.clone(),
            segments: segments.clone(),
        });
        return;
    }
    segments.push(Vec::new());
    hop(lpg, pattern, plan, options, edge, at, nodes, segments, out);
    segments.pop();
}

/// Extend the current segment of edge step `edge` from group `at`.
#[allow(clippy::too_many_arguments)]
fn hop<L: Lpg>(
    lpg: &L,
    pattern: &Pattern,
    plan: &Plan,
    options: &ResolveOptions,
    edge: usize,
    at: VpgId,
    nodes: &mut Vec<VpgId>,
    segments: &mut Vec<Vec<Hop>>,
    out: &mut Resolution,
) {
    let (min, max) = plan.ranges[edge];
    let taken = segments.last().unwrap().len();
    // Stop here and bind the next node step, if the range allows and the rest can complete.
    if taken >= min && plan.finish[edge + 1].contains(&at) {
        nodes.push(at);
        walk(
            lpg,
            pattern,
            plan,
            options,
            edge + 1,
            at,
            nodes,
            segments,
            out,
        );
        nodes.pop();
    }
    if taken >= max || out.truncated {
        return;
    }
    let layers = &plan.layers[edge];
    for h in steps(lpg, at, &pattern.edges[edge]) {
        // Step only if `h.to` can still reach finish[edge+1] within the remaining range.
        let lo = min.saturating_sub(taken + 1);
        let hi = (max - taken - 1).min(layers.len() - 1);
        if lo > hi || !layers[lo..=hi].iter().any(|layer| layer.contains(&h.to)) {
            continue;
        }
        segments.last_mut().unwrap().push(h);
        hop(
            lpg, pattern, plan, options, edge, h.to, nodes, segments, out,
        );
        segments.last_mut().unwrap().pop();
    }
}

/// Breadth-first over the schema graph, either direction, any edge type.
pub fn find_path<L: Lpg>(lpg: &L, from: VpgId, to: VpgId, max_hops: usize) -> Option<Vec<Hop>> {
    let any = EdgeStep {
        types: crate::LabelExpr::Any,
        direction: PatternDirection::Either,
        hops: crate::Hops::ONE,
    };
    let mut previous: std::collections::HashMap<VpgId, (VpgId, Hop)> = Default::default();
    let mut queue = VecDeque::from([(from, 0usize)]);
    let mut seen = BTreeSet::from([from]);
    while let Some((v, depth)) = queue.pop_front() {
        if v == to {
            let mut path = Vec::new();
            let mut cursor = to;
            while cursor != from {
                let (back, h) = previous[&cursor];
                path.push(h);
                cursor = back;
            }
            path.reverse();
            return Some(path);
        }
        if depth == max_hops {
            continue;
        }
        for h in steps(lpg, v, &any) {
            if seen.insert(h.to) {
                previous.insert(h.to, (v, h));
                queue.push_back((h.to, depth + 1));
            }
        }
    }
    None
}
