//! Unweighted traversal and canonical connected components.

use crate::{GraphProjection, Result, buffer::Buffer};

/// One distance per selected node, in projection row order.
/// Positive infinity denotes an unreachable node. The result shares its immutable
/// projection so external IDs and their memory admission remain alive.
pub struct Distances {
    graph: GraphProjection,
    pub(crate) distances: Buffer<f64>,
}

impl Distances {
    pub(crate) fn new(graph: &GraphProjection, distances: Buffer<f64>) -> Self {
        Self {
            graph: graph.clone(),
            distances,
        }
    }
    /// Projection supplying external IDs and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        &self.graph
    }
    /// Distances, including infinity for unreachable nodes.
    pub fn values(&self) -> &[f64] {
        &self.distances.values
    }
}

/// A partition whose component labels are the minimum node row in each set.
/// Labels are deterministic for a fixed node table, independent of edge order.
pub struct Components {
    graph: GraphProjection,
    labels: Buffer<usize>,
}

impl Components {
    /// Projection supplying external IDs and snapshot identity.
    pub fn projection(&self) -> &GraphProjection {
        &self.graph
    }
    /// Canonical component row for every selected vertex, including isolates.
    pub fn values(&self) -> &[usize] {
        &self.labels.values
    }
}

/// Minimum hop counts following the projection orientation. Weights are ignored.
pub fn bfs(graph: &GraphProjection, source: &str) -> Result<Distances> {
    graph.require_nonnegative("bfs")?;
    bfs_sources(graph, std::iter::once(source))
}

/// Minimum hop distance from any supplied external source ID. Duplicate sources
/// are harmless, source order breaks discovery ties, and an empty set is invalid.
pub fn multi_source_bfs(graph: &GraphProjection, sources: &[String]) -> Result<Distances> {
    graph.require_nonnegative("multiSourceBfs")?;
    if sources.is_empty() {
        return Err(crate::AlgorithmError::InvalidArguments(
            "at least one BFS source is required".into(),
        ));
    }
    bfs_sources(graph, sources.iter().map(String::as_str))
}

fn bfs_sources<'a>(
    graph: &GraphProjection,
    sources: impl Iterator<Item = &'a str>,
) -> Result<Distances> {
    let context = graph.execution();
    let mut meter = context.work_meter();
    context.checkpoint()?;
    let adjacency = graph.outgoing();
    let workers = crate::parallel::workers_above(
        context,
        graph.node_count().saturating_add(adjacency.arc_count()),
        crate::parallel::BREADTH_FIRST_SEQUENTIAL_BELOW_UNITS,
    );
    let mut roots = Vec::new();
    {
        let mut seen = Buffer::filled(graph.node_count(), false, context)?;
        for source in sources {
            meter.charge(1)?;
            let source = graph.source(source)?;
            if !seen.values[source] {
                seen.values[source] = true;
                roots.push(source);
            }
        }
    }
    if let Some(workers) = workers {
        return levels(graph, &roots, workers);
    }
    let mut distances = Buffer::filled(graph.node_count(), f64::INFINITY, context)?;
    let mut queue = Buffer::capacity(graph.node_count(), context)?;
    for &source in &roots {
        distances.values[source] = 0.0;
        queue.values.push(source);
    }
    let mut head = 0;
    while head < queue.values.len() {
        meter.charge(1)?;
        let node = queue.values[head];
        head += 1;
        for arc in adjacency.range(node) {
            meter.charge(1)?;
            let next = adjacency.target(arc);
            if distances.values[next].is_infinite() {
                distances.values[next] = distances.values[node] + 1.0;
                queue.values.push(next);
            }
        }
    }
    Ok(Distances::new(graph, distances))
}

/// Level-synchronous breadth-first search.
///
/// Each level expands the whole frontier in parallel. A node is claimed by the
/// one worker whose compare-exchange on its level succeeds, so it enters the
/// next frontier exactly once, and its distance is the level that claimed it.
/// Distances therefore do not depend on the order arcs were examined, which is
/// what makes the parallel result identical to the sequential queue's. The next
/// frontier is assembled from per-chunk lists in chunk order, so even the
/// frontier itself is reproducible.
fn levels(graph: &GraphProjection, roots: &[usize], workers: usize) -> Result<Distances> {
    use std::sync::atomic::{AtomicU32, Ordering};

    const UNVISITED: u32 = u32::MAX;
    let context = graph.execution();
    let n = graph.node_count();
    let adjacency = graph.outgoing();
    let targets = adjacency.targets();
    let level_of = Buffer::indexed_with(n, || AtomicU32::new(UNVISITED), context)?;
    // Every node is claimed at most once, so the frontiers together hold at most
    // one entry per node. Admit that once rather than per level or per worker.
    let _frontiers = context.reserve(n.saturating_mul(2 * size_of::<usize>()))?;
    let mut frontier: Vec<usize> = Vec::new();
    frontier.try_reserve(roots.len())?;
    for &root in roots {
        level_of.values[root].store(0, Ordering::Relaxed);
        frontier.push(root);
    }
    let mut level: u32 = 0;
    while !frontier.is_empty() {
        context.checkpoint()?;
        let next_level = level.saturating_add(1);
        // A level with a small frontier is expanded in place: spreading a few
        // hundred nodes over sixteen workers costs more than it saves, which is
        // what the measurements on road networks showed.
        let level_workers = if frontier.len() < crate::parallel::SEQUENTIAL_FRONTIER_BELOW {
            1
        } else {
            workers
        };
        // A frontier's expansion writes each discovered node once, so its
        // chunking cannot change the answer and may follow the worker count.
        let chunk = crate::parallel::chunk_len(frontier.len(), level_workers);
        let lists = crate::parallel::map_chunks_sized(
            context,
            level_workers,
            &frontier,
            chunk,
            |_, slice, meter| {
                let mut discovered: Vec<usize> = Vec::new();
                for &node in slice {
                    let arcs = adjacency.range(node);
                    meter.charge(1 + arcs.len())?;
                    for arc in arcs {
                        let next = targets[arc] as usize;
                        if level_of.values[next]
                            .compare_exchange(
                                UNVISITED,
                                next_level,
                                Ordering::Relaxed,
                                Ordering::Relaxed,
                            )
                            .is_ok()
                        {
                            discovered.try_reserve(1)?;
                            discovered.push(next);
                        }
                    }
                }
                Ok(discovered)
            },
        )?;
        frontier.clear();
        for list in &lists {
            frontier.try_reserve(list.len())?;
            frontier.extend_from_slice(list);
        }
        level = next_level;
    }
    let mut distances = Buffer::indexed(n, f64::INFINITY, context)?;
    crate::parallel::for_each_chunk(
        context,
        workers,
        &mut distances.values,
        |first, slice, meter| {
            meter.charge(slice.len())?;
            for (index, distance) in slice.iter_mut().enumerate() {
                let claimed = level_of.values[first + index].load(Ordering::Relaxed);
                *distance = if claimed == UNVISITED {
                    f64::INFINITY
                } else {
                    claimed as f64
                };
            }
            Ok(())
        },
    )?;
    Ok(Distances::new(graph, distances))
}

/// Connected components after ignoring edge direction. Union by size and path
/// halving use O(V) scratch and never require reverse adjacency.
pub fn weakly_connected_components(graph: &GraphProjection) -> Result<Components> {
    graph.require_nonnegative("wcc")?;
    let context = graph.execution();
    let mut meter = context.work_meter();
    let n = graph.node_count();
    let workers = crate::parallel::workers(
        context,
        n.saturating_add(graph.edge_count().saturating_mul(2)),
    );
    if let Some(workers) = workers {
        return union_find(graph, workers);
    }
    let mut parents = Buffer::capacity(n, context)?;
    for node in 0..n {
        meter.charge(1)?;
        parents.values.push(node);
    }
    let mut sizes = Buffer::filled(n, 1usize, context)?;
    for edge in graph.edges() {
        meter.charge(1)?;
        let mut left = root(&mut parents.values, edge.source, &mut meter)?;
        let mut right = root(&mut parents.values, edge.target, &mut meter)?;
        if left == right {
            continue;
        }
        if sizes.values[left] < sizes.values[right] {
            std::mem::swap(&mut left, &mut right);
        }
        parents.values[right] = left;
        sizes.values[left] += sizes.values[right];
    }
    // Reuse the size buffer for each root's canonical minimum row.
    sizes.values.fill(usize::MAX);
    for node in 0..n {
        meter.charge(1)?;
        let representative = root(&mut parents.values, node, &mut meter)?;
        parents.values[node] = representative;
        sizes.values[representative] = sizes.values[representative].min(node);
    }
    for representative in &mut parents.values {
        meter.charge(1)?;
        *representative = sizes.values[*representative];
    }
    Ok(Components {
        graph: graph.clone(),
        labels: parents,
    })
}

/// Called on both endpoints of every edge, so a call here is paid twice per
/// edge. v0.22.0 inlined it by default; when `charge` grew, it stopped being
/// inlined, and `#[inline]` alone did not restore that. `always` does.
#[inline(always)]
fn root(
    parents: &mut [usize],
    mut node: usize,
    meter: &mut grust_procedures::WorkMeter,
) -> Result<usize> {
    while parents[node] != node {
        meter.charge(1)?;
        parents[node] = parents[parents[node]];
        node = parents[node];
    }
    Ok(node)
}

/// Components by concurrent union-find.
///
/// Workers union the endpoints of disjoint edge ranges into a shared parent
/// array. A link always points from the larger root to the smaller one, so the
/// root that survives in each component is its minimum node row: the same
/// canonical label the sequential kernel produces, arrived at without depending
/// on the order edges were merged. A losing compare-exchange re-reads the roots
/// and retries, which is why one pass over the edges is enough.
fn union_find(graph: &GraphProjection, workers: usize) -> Result<Components> {
    use std::sync::atomic::{AtomicUsize, Ordering};

    fn root(parents: &[AtomicUsize], mut node: usize) -> usize {
        loop {
            let parent = parents[node].load(Ordering::Relaxed);
            if parent == node {
                return node;
            }
            node = parent;
        }
    }

    let context = graph.execution();
    let n = graph.node_count();
    let mut row = 0;
    let parents = Buffer::indexed_with(
        n,
        || {
            let node = row;
            row += 1;
            AtomicUsize::new(node)
        },
        context,
    )?;
    let parents = &parents.values;
    // Unions are applied to shared atomics, not summed, so the grouping cannot
    // change the partition and the chunks may follow the worker count.
    let chunk = crate::parallel::chunk_len(graph.edge_count(), workers);
    crate::parallel::map_chunks_sized(
        context,
        workers,
        graph.edges(),
        chunk,
        |_, slice, meter| {
            for edge in slice {
                meter.charge(1)?;
                let mut left = root(parents, edge.source);
                let mut right = root(parents, edge.target);
                while left != right {
                    meter.charge(1)?;
                    let (larger, smaller) = if left > right {
                        (left, right)
                    } else {
                        (right, left)
                    };
                    match parents[larger].compare_exchange(
                        larger,
                        smaller,
                        Ordering::Relaxed,
                        Ordering::Relaxed,
                    ) {
                        Ok(_) => break,
                        // Another worker linked this root first; follow where it went.
                        Err(observed) => {
                            left = root(parents, observed);
                            right = root(parents, smaller);
                        }
                    }
                }
            }
            Ok(())
        },
    )?;
    let mut labels = Buffer::indexed(n, 0usize, context)?;
    crate::parallel::for_each_chunk(
        context,
        workers,
        &mut labels.values,
        |first, slice, meter| {
            meter.charge(slice.len())?;
            for (index, label) in slice.iter_mut().enumerate() {
                *label = root(parents, first + index);
            }
            Ok(())
        },
    )?;
    Ok(Components {
        graph: graph.clone(),
        labels,
    })
}

/// Strong components via two iterative depth-first passes. Stack usage is O(V)
/// in admitted heap buffers, including on chains with millions of vertices.
pub fn strongly_connected_components(graph: &GraphProjection) -> Result<Components> {
    graph.require_nonnegative("scc")?;
    let context = graph.execution();
    let mut meter = context.work_meter();
    let n = graph.node_count();
    let adjacency = graph.outgoing();
    let mut seen = Buffer::filled(n, false, context)?;
    let mut order = Buffer::capacity(n, context)?;
    let mut stack = Buffer::capacity(n, context)?;
    for seed in 0..n {
        meter.charge(1)?;
        if seen.values[seed] {
            continue;
        }
        seen.values[seed] = true;
        stack.values.push((seed, adjacency.range(seed).start));
        while let Some(&mut (node, ref mut next_arc)) = stack.values.last_mut() {
            meter.charge(1)?;
            if *next_arc == adjacency.range(node).end {
                order.values.push(node);
                stack.values.pop();
            } else {
                let next = adjacency.target(*next_arc);
                *next_arc += 1;
                if !seen.values[next] {
                    seen.values[next] = true;
                    stack.values.push((next, adjacency.range(next).start));
                }
            }
        }
    }
    drop(stack);
    drop(seen);
    // In-arcs, the projection's one reverse index, shared with every other
    // kernel that needs them rather than built again here.
    let reverse = graph.incoming()?;
    let mut labels = Buffer::filled(n, usize::MAX, context)?;
    let mut members = Buffer::capacity(n, context)?;
    for &seed in order.values.iter().rev() {
        meter.charge(1)?;
        if labels.values[seed] != usize::MAX {
            continue;
        }
        members.values.clear();
        members.values.push(seed);
        labels.values[seed] = seed;
        let mut minimum = seed;
        let mut head = 0;
        while head < members.values.len() {
            meter.charge(1)?;
            let node = members.values[head];
            head += 1;
            for arc in reverse.range(node) {
                meter.charge(1)?;
                let next = reverse.target(arc);
                if labels.values[next] == usize::MAX {
                    labels.values[next] = seed;
                    minimum = minimum.min(next);
                    members.values.push(next);
                }
            }
        }
        for &node in &members.values {
            meter.charge(1)?;
            labels.values[node] = minimum;
        }
    }
    Ok(Components {
        graph: graph.clone(),
        labels,
    })
}
