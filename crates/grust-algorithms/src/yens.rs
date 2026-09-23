//! Yen's algorithm: the k shortest loopless paths from one node to another.

use std::cmp::Ordering;

use grust_procedures::WorkMeter;

use crate::{
    AlgorithmError, ExecutionContext, GraphProjection, PathView, Result,
    buffer::Buffer,
    projection::{Adjacency, InArcs},
    shortest::MinHeap,
};

/// No node: `spur` before the first deviation, where no arc is suppressed.
const NONE: usize = usize::MAX;

/// How many paths [`yens`] is asked for.
pub struct YensOptions {
    /// An upper bound, not a demand. Returning fewer paths than `k` because
    /// fewer exist is the correct answer, not an error; a graph with one route
    /// between two nodes has one loopless path however large `k` is. Zero is
    /// rejected: it asks for no answer at all.
    pub k: usize,
}

impl Default for YensOptions {
    fn default() -> Self {
        Self { k: 1 }
    }
}

/// The paths [`yens`] found, ranked from cheapest, concatenated into one set of
/// buffers so that a result of many paths is a few allocations rather than one
/// per path.
pub struct KShortestPaths {
    graph: GraphProjection,
    source: usize,
    target: usize,
    nodes: Buffer<usize>,
    costs: Buffer<f64>,
    edges: Buffer<usize>,
    /// Exclusive end of each path in `nodes`/`costs` and in `edges`.
    bounds: Buffer<(usize, usize)>,
}

impl KShortestPaths {
    /// Projection supplying external ids and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        &self.graph
    }
    /// Source and destination rows.
    pub fn endpoints(&self) -> (usize, usize) {
        (self.source, self.target)
    }
    /// How many paths were found: at most `k`, and fewer when fewer exist.
    pub fn len(&self) -> usize {
        self.bounds.values.len()
    }
    /// Whether the destination is unreachable from the source.
    pub fn is_empty(&self) -> bool {
        self.bounds.values.is_empty()
    }
    /// The path of rank `index`, counting from zero, in the order documented on
    /// [`yens`]. The view has the shape `shortestPaths` produces for one target.
    pub fn path(&self, index: usize) -> Option<PathView<'_>> {
        let &(node_end, edge_end) = self.bounds.values.get(index)?;
        let (node_start, edge_start) = match index {
            0 => (0, 0),
            _ => self.bounds.values[index - 1],
        };
        Some(PathView {
            target: self.target,
            nodes: &self.nodes.values[node_start..node_end],
            costs: &self.costs.values[node_start..node_end],
            edges: &self.edges.values[edge_start..edge_end],
        })
    }
    /// Total cost of the path of rank `index`.
    pub fn total_cost(&self, index: usize) -> Option<f64> {
        self.path(index).and_then(|path| path.costs.last().copied())
    }
}

/// One path while it is being built: node rows, the cumulative cost at each,
/// and the edge slot of each hop. Every buffer is admitted.
struct Route {
    nodes: Buffer<usize>,
    costs: Buffer<f64>,
    edges: Buffer<usize>,
}

impl Route {
    fn cost(&self) -> f64 {
        self.costs.values.last().copied().unwrap_or(0.0)
    }
}

/// The documented order: total cost first, then the node rows read from the
/// source. Two distinct loopless paths between the same pair never have the
/// same node sequence, so this is a strict total order and the rank of a path
/// never depends on the order candidates happened to be generated in.
fn ranks_before(left: &Route, right: &Route) -> bool {
    match left.cost().total_cmp(&right.cost()) {
        Ordering::Less => true,
        Ordering::Greater => false,
        Ordering::Equal => left.nodes.values < right.nodes.values,
    }
}

/// The k shortest **loopless** paths from `source` to `target`, cheapest first.
///
/// Yen's 1971 construction on top of Dijkstra: having accepted a path, every
/// node of it but the last is used as a *spur*. The prefix up to the spur is
/// kept, the arcs by which accepted paths sharing that prefix left the spur are
/// suppressed, the prefix's earlier nodes are removed so the remainder cannot
/// turn back through them, and a shortest path is computed from the spur to the
/// target. Each such path is a candidate; the cheapest candidate is the next
/// answer, and the rest stay for later rounds.
///
/// **Fewer than `k` is a correct answer.** The paths are simple, so there are
/// finitely many, and a graph that has three loopless routes returns three for
/// any larger `k`. Nothing is padded and nothing is an error.
///
/// **A path is a sequence of nodes.** Parallel edges collapse: a hop is
/// reported with the cheapest edge joining its two nodes, ties among equal
/// weights going to the earliest arc, and two routes that differ only in which
/// parallel edge they use are one path. A self-loop can never appear in a
/// loopless path. Orientation is the projection's, so an undirected projection
/// walks each edge either way.
///
/// **Ties break toward the smaller node sequence.** Paths are ranked by total
/// cost compared with [`f64::total_cmp`]; paths of equal cost are ranked by
/// their node rows, read from the source, lexicographically, smaller first.
/// That is a total order, and the kernel reaches it rather than approximating
/// it: each spur search returns the lexicographically smallest of the
/// minimum-cost paths available to it, which makes the cheapest candidate the
/// next path under the whole order, not merely one path of the next cost. A
/// nondeterministic choice here would be a defect, not a detail: the same
/// projection and the same `k` produce the same paths in the same order.
///
/// **Costs are summed along the path from the source**, so a reported cost is
/// exactly the sum of its hop weights in that order. Two paths that are equal
/// in exact arithmetic but differ in the last bit of that sum rank in the order
/// of the sums, which is what a caller can reproduce from the output.
///
/// `source == target` is one path: the source alone, of zero cost, as
/// `shortestPaths` reports the zero-hop path. An unreachable target is no paths
/// at all. Weights must be nonnegative, as for Dijkstra, on which this is
/// built; `bellmanFord` is the kernel that admits negative ones.
pub fn yens(
    graph: &GraphProjection,
    source: &str,
    target: &str,
    options: YensOptions,
) -> Result<KShortestPaths> {
    graph.require_nonnegative("yens")?;
    let context = graph.execution();
    context.checkpoint()?;
    if options.k == 0 {
        return Err(AlgorithmError::InvalidArguments(
            "k must be at least 1: yens returns the k shortest paths".into(),
        ));
    }
    let source = graph.source(source)?;
    let target = graph.source(target)?;
    let n = graph.node_count();
    let mut meter = context.work_meter();
    let mut search = Search {
        graph,
        out: graph.outgoing(),
        incoming: graph.incoming()?,
        distance: Buffer::filled(n, f64::INFINITY, context)?,
        banned: Buffer::filled(n, false, context)?,
        visited: Buffer::filled(n, false, context)?,
        seen: Buffer::filled(n, false, context)?,
        touched: Buffer::capacity(n, context)?,
        stack: Buffer::capacity(n, context)?,
        banned_next: Buffer::capacity(options.k, context)?,
        walk_nodes: Buffer::capacity(n, context)?,
        walk_edges: Buffer::capacity(n, context)?,
        walk_weights: Buffer::capacity(n, context)?,
        spur: NONE,
    };

    // The spine of these two lists is fallibly reserved and every path it holds
    // owns admitted buffers; a candidate that is never accepted releases them
    // when the list is dropped.
    let mut accepted: Vec<Route> = Vec::new();
    let mut candidates: Vec<Route> = Vec::new();
    search.distances_to_target(target, &mut meter)?;
    if search.walk(source, target, &mut meter)? {
        let first = search.route(&[], &[], &[], &mut meter)?;
        accepted.try_reserve(1)?;
        accepted.push(first);
    }
    while !accepted.is_empty() && accepted.len() < options.k {
        let previous = &accepted[accepted.len() - 1];
        for spur_index in 0..previous.nodes.values.len() - 1 {
            let spur = previous.nodes.values[spur_index];
            search.prepare(&accepted, previous, spur_index, &mut meter)?;
            search.distances_to_target(target, &mut meter)?;
            if search.walk(spur, target, &mut meter)? {
                let route = search.route(
                    &previous.nodes.values[..=spur_index],
                    &previous.costs.values[..=spur_index],
                    &previous.edges.values[..spur_index],
                    &mut meter,
                )?;
                if !known(&accepted, &route) && !known(&candidates, &route) {
                    candidates.try_reserve(1)?;
                    candidates.push(route);
                }
            }
            search.restore(&previous.nodes.values[..spur_index], &mut meter)?;
        }
        let Some(best) = cheapest(&candidates, &mut meter)? else {
            break;
        };
        let route = candidates.swap_remove(best);
        accepted.try_reserve(1)?;
        accepted.push(route);
    }
    drop(candidates);
    drop(search);
    meter.finish();
    collect(graph, source, target, accepted, context)
}

/// Whether a path with these node rows was already found.
fn known(routes: &[Route], route: &Route) -> bool {
    routes
        .iter()
        .any(|other| other.nodes.values == route.nodes.values)
}

/// The position of the candidate that ranks first. The order is strict, so this
/// does not depend on the order the candidates are held in.
fn cheapest(candidates: &[Route], meter: &mut WorkMeter) -> Result<Option<usize>> {
    let mut best: Option<usize> = None;
    for (index, candidate) in candidates.iter().enumerate() {
        meter.charge(1)?;
        match best {
            Some(current) if !ranks_before(candidate, &candidates[current]) => {}
            _ => best = Some(index),
        }
    }
    Ok(best)
}

/// Pack the accepted paths into one set of buffers, in rank order.
fn collect(
    graph: &GraphProjection,
    source: usize,
    target: usize,
    accepted: Vec<Route>,
    context: &ExecutionContext,
) -> Result<KShortestPaths> {
    let node_total = accepted.iter().map(|r| r.nodes.values.len()).sum();
    let edge_total = accepted.iter().map(|r| r.edges.values.len()).sum();
    let mut nodes = Buffer::capacity(node_total, context)?;
    let mut costs = Buffer::capacity(node_total, context)?;
    let mut edges = Buffer::capacity(edge_total, context)?;
    let mut bounds = Buffer::capacity(accepted.len(), context)?;
    for route in &accepted {
        context.charge_work(route.nodes.values.len() + route.edges.values.len())?;
        nodes.values.extend_from_slice(&route.nodes.values);
        costs.values.extend_from_slice(&route.costs.values);
        edges.values.extend_from_slice(&route.edges.values);
        bounds.values.push((nodes.values.len(), edges.values.len()));
    }
    Ok(KShortestPaths {
        graph: graph.clone(),
        source,
        target,
        nodes,
        costs,
        edges,
        bounds,
    })
}

/// Everything one spur search needs: the two adjacencies, the distances to the
/// target in the restricted graph, what is suppressed, and the walk it writes.
struct Search<'a> {
    graph: &'a GraphProjection,
    out: &'a Adjacency,
    incoming: InArcs<'a>,
    /// Cost from each node to the target, in the restricted graph.
    distance: Buffer<f64>,
    /// Nodes of the root path before the spur: removed, so the remainder of the
    /// path cannot turn back through them and stop being loopless.
    banned: Buffer<bool>,
    visited: Buffer<bool>,
    seen: Buffer<bool>,
    touched: Buffer<usize>,
    stack: Buffer<usize>,
    /// Nodes an accepted path left the spur for: those arcs are suppressed, so
    /// this search must deviate rather than rediscover an answer already given.
    banned_next: Buffer<usize>,
    walk_nodes: Buffer<usize>,
    walk_edges: Buffer<usize>,
    walk_weights: Buffer<f64>,
    spur: usize,
}

impl Search<'_> {
    /// Remove the root path's earlier nodes and suppress the arcs by which
    /// accepted paths with this root prefix left the spur.
    fn prepare(
        &mut self,
        accepted: &[Route],
        previous: &Route,
        spur_index: usize,
        meter: &mut WorkMeter,
    ) -> Result<()> {
        let root = &previous.nodes.values[..spur_index];
        meter.charge(root.len())?;
        for &node in root {
            self.banned.values[node] = true;
        }
        self.banned_next.values.clear();
        for path in accepted {
            meter.charge(spur_index + 1)?;
            if path.nodes.values.len() > spur_index + 1
                && path.nodes.values[..=spur_index] == previous.nodes.values[..=spur_index]
            {
                let next = path.nodes.values[spur_index + 1];
                if !self.banned_next.values.contains(&next) {
                    self.banned_next.values.push(next);
                }
            }
        }
        self.spur = previous.nodes.values[spur_index];
        Ok(())
    }

    /// Put back what [`Self::prepare`] removed.
    fn restore(&mut self, root: &[usize], meter: &mut WorkMeter) -> Result<()> {
        meter.charge(root.len())?;
        for &node in root {
            self.banned.values[node] = false;
        }
        self.spur = NONE;
        Ok(())
    }

    /// Whether this arc exists in the restricted graph.
    fn allowed(&self, from: usize, to: usize) -> bool {
        !self.banned.values[to] && !(from == self.spur && self.banned_next.values.contains(&to))
    }

    /// Cost from every node to the target, by Dijkstra over the in-arcs. The
    /// search runs backwards because what a spur needs is the distance *to* the
    /// target from everywhere, which one pass gives and n forward passes would
    /// not.
    fn distances_to_target(&mut self, target: usize, meter: &mut WorkMeter) -> Result<()> {
        let n = self.graph.node_count();
        reset(&mut self.distance.values, f64::INFINITY, meter)?;
        let mut heap = MinHeap::new(n, self.graph.execution())?;
        if self.banned.values[target] {
            return Ok(());
        }
        self.distance.values[target] = 0.0;
        heap.improve(target, 0.0, meter)?;
        while let Some((cost, node)) = heap.pop(meter)? {
            meter.charge(1)?;
            for arc in self.incoming.range(node) {
                meter.charge(1)?;
                let previous = self.incoming.target(arc);
                if !self.allowed(previous, node) {
                    continue;
                }
                let candidate = cost + self.incoming.weight(arc);
                if !candidate.is_finite() {
                    return Err(AlgorithmError::Numerical(
                        "k-shortest-path cost overflow".into(),
                    ));
                }
                if candidate < self.distance.values[previous] {
                    self.distance.values[previous] = candidate;
                    heap.improve(previous, candidate, meter)?;
                }
            }
        }
        Ok(())
    }

    /// Walk from `start` to the target along *tight* arcs — those where the
    /// hop's weight plus the distance still to come equals the distance from
    /// here — so every step stays on a minimum-cost path, taking the smallest
    /// node row at each choice. That yields the lexicographically smallest of
    /// the minimum-cost paths, which is what makes the tie-break on [`yens`]
    /// reachable rather than aspirational.
    ///
    /// A tight arc of positive weight always leads onward: the distances below
    /// it are strictly smaller than every distance already walked through, so
    /// nothing it reaches has been used. A tight arc of *zero* weight has no
    /// such guarantee — it is how a zero-weight cycle would be entered — so
    /// that one case asks [`Self::reaches`] whether the target is still
    /// reachable before committing, and takes the next smallest row if not.
    ///
    /// Returns whether a path exists at all.
    fn walk(&mut self, start: usize, target: usize, meter: &mut WorkMeter) -> Result<bool> {
        self.walk_nodes.values.clear();
        self.walk_edges.values.clear();
        self.walk_weights.values.clear();
        if !self.distance.values[start].is_finite() {
            return Ok(false);
        }
        reset(&mut self.visited.values, false, meter)?;
        self.visited.values[start] = true;
        self.walk_nodes.values.push(start);
        let mut node = start;
        while node != target {
            let mut floor = 0usize;
            let step = loop {
                let Some((next, arc, weight)) = self.tightest(node, floor, meter)? else {
                    break None;
                };
                if weight > 0.0 || self.reaches(next, target, meter)? {
                    break Some((next, arc, weight));
                }
                floor = next + 1;
            };
            let Some((next, arc, weight)) = step else {
                return Err(AlgorithmError::Numerical(
                    "k shortest paths lost a tight arc out of a node it had reached".into(),
                ));
            };
            self.visited.values[next] = true;
            self.walk_nodes.values.push(next);
            self.walk_edges.values.push(self.out.edge_slot(arc));
            self.walk_weights.values.push(weight);
            node = next;
        }
        Ok(true)
    }

    /// The tight arc out of `node` reaching the smallest usable row at or above
    /// `floor`, and among equal rows the earliest arc, which is the cheapest of
    /// any parallel edges because tightness fixes the weight.
    fn tightest(
        &self,
        node: usize,
        floor: usize,
        meter: &mut WorkMeter,
    ) -> Result<Option<(usize, usize, f64)>> {
        let mut best: Option<(usize, usize, f64)> = None;
        for arc in self.out.range(node) {
            meter.charge(1)?;
            let next = self.out.target(arc);
            if next < floor || self.visited.values[next] || !self.allowed(node, next) {
                continue;
            }
            let weight = self.out.weight(arc);
            if weight + self.distance.values[next] != self.distance.values[node] {
                continue;
            }
            match best {
                Some((row, _, _)) if row <= next => {}
                _ => best = Some((next, arc, weight)),
            }
        }
        Ok(best)
    }

    /// Whether the target is still reachable from `from` along tight arcs once
    /// the walk's own nodes are removed. Reachability is exactly the question:
    /// where a walk exists a loopless one exists, and the walk's nodes include
    /// the spur, so no suppressed arc can be taken from here.
    fn reaches(&mut self, from: usize, target: usize, meter: &mut WorkMeter) -> Result<bool> {
        self.stack.values.clear();
        self.touched.values.clear();
        self.stack.values.push(from);
        self.touched.values.push(from);
        self.seen.values[from] = true;
        let mut found = false;
        while let Some(node) = self.stack.values.pop() {
            if node == target {
                found = true;
                break;
            }
            for arc in self.out.range(node) {
                meter.charge(1)?;
                let next = self.out.target(arc);
                if self.seen.values[next] || self.visited.values[next] || self.banned.values[next] {
                    continue;
                }
                if self.out.weight(arc) + self.distance.values[next] != self.distance.values[node] {
                    continue;
                }
                self.seen.values[next] = true;
                self.touched.values.push(next);
                self.stack.values.push(next);
            }
        }
        meter.charge(self.touched.values.len())?;
        for &node in &self.touched.values {
            self.seen.values[node] = false;
        }
        Ok(found)
    }

    /// A full path: the root prefix as it was walked before, then the spur
    /// search's own nodes. Costs accumulate from the source in path order, so
    /// the prefix's costs carry over unchanged and the suffix continues them.
    fn route(
        &self,
        nodes: &[usize],
        costs: &[f64],
        edges: &[usize],
        meter: &mut WorkMeter,
    ) -> Result<Route> {
        let context = self.graph.execution();
        // With no prefix the walk supplies its own first node; with one, the
        // walk starts at the spur, which the prefix already holds.
        let skip = usize::from(!nodes.is_empty());
        let node_count = nodes.len() + self.walk_nodes.values.len() - skip;
        let edge_count = edges.len() + self.walk_edges.values.len();
        meter.charge(node_count + edge_count)?;
        let mut route = Route {
            nodes: Buffer::capacity(node_count, context)?,
            costs: Buffer::capacity(node_count, context)?,
            edges: Buffer::capacity(edge_count, context)?,
        };
        route.nodes.values.extend_from_slice(nodes);
        route.costs.values.extend_from_slice(costs);
        route.edges.values.extend_from_slice(edges);
        let mut running = costs.last().copied().unwrap_or(0.0);
        for (position, &node) in self.walk_nodes.values.iter().enumerate().skip(skip) {
            if position > 0 {
                running += self.walk_weights.values[position - 1];
            }
            route.nodes.values.push(node);
            route.costs.values.push(running);
        }
        route
            .edges
            .values
            .extend_from_slice(&self.walk_edges.values);
        Ok(route)
    }
}

/// Refill a scratch array, charging it in blocks: a per-element admit would
/// cost more than the element it guarded.
fn reset<T: Copy>(values: &mut [T], value: T, meter: &mut WorkMeter) -> Result<()> {
    for chunk in values.chunks_mut(1024) {
        meter.charge(chunk.len())?;
        chunk.fill(value);
    }
    Ok(())
}
