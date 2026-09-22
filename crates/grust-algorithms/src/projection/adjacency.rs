//! Packed CSR with stable original-edge order and optional contiguous weights.
//!
//! Both builds here — a projection's own adjacency from its edges, and the
//! transpose from that adjacency — count and fill in parallel above the floor,
//! produce the same bytes as their sequential forms at every width, and admit
//! exactly the memory the sequential forms admit, in the same order. How the
//! count stays exact is on [`Counts`]; how the fill does is on [`RowRange`].

use std::ops::Range;

use grust_procedures::WorkMeter;

use super::*;

pub(crate) struct Adjacency {
    pub(crate) offsets: Buffer<usize>,
    pub(crate) targets: Buffer<usize>,
    /// Original edge position per arc. Present on a projection's own adjacency,
    /// absent on a transpose, whose callers identify arcs by endpoint rather
    /// than by edge and would otherwise pay eight bytes an arc to ignore.
    edge_slots: Option<Buffer<usize>>,
    pub(crate) weights: Option<Buffer<f64>>,
}

/// Which code a build ran. Only tests read it: a determinism test whose fixture
/// never reached the parallel build would pass while verifying nothing, so
/// they assert this instead of trusting the fixture's size.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum BuildPath {
    /// Below the floor, no concurrency asked for, or a budget that would not
    /// have covered the parallel passes.
    Sequential,
    /// Counted in parallel, in `chunks`; filled sequentially.
    CountedInParallel { chunks: usize },
    /// Filled in `ranges` in parallel, counted in `chunks` in parallel, or
    /// sequentially when `chunks` is zero (the table did not fit).
    Parallel { chunks: usize, ranges: usize },
}

impl BuildPath {
    fn filled_sequentially(counted: Option<usize>) -> Self {
        counted.map_or(Self::Sequential, |chunks| Self::CountedInParallel {
            chunks,
        })
    }
}

/// Most chunks a parallel count divides its input into. Its table is four
/// bytes a node a chunk, so this bounds it on a machine with many cores; the
/// density bound in [`Counts::plan`] bounds it on a sparse graph.
const MAX_COUNT_CHUNKS: usize = 64;

impl Adjacency {
    pub(crate) fn build(
        n: usize,
        edges: &[ProjectionEdge],
        weights: Option<&[f64]>,
        orientation: Orientation,
        context: &ExecutionContext,
    ) -> Result<Self> {
        Ok(Self::build_traced(n, edges, weights, orientation, context)?.0)
    }

    pub(crate) fn build_traced(
        n: usize,
        edges: &[ProjectionEdge],
        weights: Option<&[f64]>,
        orientation: Orientation,
        context: &ExecutionContext,
    ) -> Result<(Self, BuildPath)> {
        let mut offsets = Buffer::filled(
            n.checked_add(1)
                .ok_or_else(|| ProcedureError::Numerical("node count overflow".into()))?,
            0usize,
            context,
        )?;
        // Row and other end of an edge's first arc; an undirected non-loop
        // edge also has the mirrored arc. Counting and both fills read these,
        // so they cannot disagree about which rows an edge lands in.
        let ends = |edge: &ProjectionEdge| match orientation {
            Orientation::Outgoing | Orientation::Undirected => (edge.source, edge.target),
            Orientation::Incoming => (edge.target, edge.source),
        };
        let mirrored =
            |row: usize, other: usize| orientation == Orientation::Undirected && row != other;

        let counted = match Counts::plan(context, context, n, edges.len(), edges.len())? {
            Some(mut table) => {
                let len = edges.len().div_ceil(table.chunks).max(1);
                table.count(context, |index, row, meter| {
                    let start = (index * len).min(edges.len());
                    let slice = &edges[start..(start + len).min(edges.len())];
                    meter.charge(slice.len())?;
                    for edge in slice {
                        let (source, target) = ends(edge);
                        row[source] += 1;
                        if mirrored(source, target) {
                            row[target] += 1;
                        }
                    }
                    Ok(())
                })?;
                Some(table.sum_into(context, &mut offsets.values[1..])?)
            }
            None => {
                for edge in edges {
                    context.charge_work(1)?;
                    let (source, target) = ends(edge);
                    offsets.values[source + 1] = offsets.values[source + 1]
                        .checked_add(1)
                        .ok_or_else(|| ProcedureError::Numerical("degree overflow".into()))?;
                    if mirrored(source, target) {
                        offsets.values[target + 1] = offsets.values[target + 1]
                            .checked_add(1)
                            .ok_or_else(|| ProcedureError::Numerical("degree overflow".into()))?;
                    }
                }
                None
            }
        };
        prefix(&mut offsets.values, context)?;
        let count = offsets.values[n];
        let mut result = Self {
            offsets,
            targets: Buffer::filled(count, 0, context)?,
            edge_slots: Some(Buffer::filled(count, 0, context)?),
            weights: weights
                .map(|_| Buffer::filled(count, 0.0, context))
                .transpose()?,
        };
        let mut positions = Buffer::capacity(n, context)?;
        for chunk in result.offsets.values[..n].chunks(1024) {
            context.charge_work(chunk.len())?;
            positions.values.extend_from_slice(chunk);
        }

        if let Some(workers) = fill_workers(context, n, edges.len(), edges.len())? {
            let parts = result.row_ranges(&mut positions.values, workers);
            let ranges = parts.len();
            // The sequential fill charges one unit per edge. Here each range
            // pays up front — the whole fill was found to fit — its share of
            // the edges in proportion to the arcs it holds, cut at cumulative
            // arc counts so the shares add up to the edge count exactly.
            // Directed, a range's share is exactly its arcs. Paying as it went,
            // a unit per edge through the meter, cost more than the fill.
            let share = |arc: usize| -> usize {
                if count == 0 {
                    return 0;
                }
                (edges.len() as u128 * arc as u128 / count as u128) as usize
            };
            crate::parallel::for_each_owned(workers, parts, |_, mut part| {
                let mut meter = context.work_meter();
                let end = part.first_arc + part.targets.len();
                meter.charge(share(end) - share(part.first_arc))?;
                for (slot, edge) in edges.iter().enumerate() {
                    part.poll(slot, &meter)?;
                    let (source, target) = ends(edge);
                    let weight = weights.map(|values| values[slot]);
                    if part.holds(source) {
                        part.put(source, target, Some(slot), weight);
                    }
                    if mirrored(source, target) && part.holds(target) {
                        part.put(target, source, Some(slot), weight);
                    }
                }
                Ok(())
            })?;
            let chunks = counted.unwrap_or(0);
            return Ok((result, BuildPath::Parallel { chunks, ranges }));
        }
        for (slot, edge) in edges.iter().enumerate() {
            context.charge_work(1)?;
            let (source, target) = ends(edge);
            let weight = weights.map(|values| values[slot]);
            result.put(&mut positions.values, source, target, slot, weight);
            if mirrored(source, target) {
                result.put(&mut positions.values, target, source, slot, weight);
            }
        }
        Ok((result, BuildPath::filled_sequentially(counted)))
    }

    fn put(
        &mut self,
        positions: &mut [usize],
        source: usize,
        target: usize,
        edge: usize,
        weight: Option<f64>,
    ) {
        let index = positions[source];
        self.targets.values[index] = target;
        if let Some(slots) = &mut self.edge_slots {
            slots.values[index] = edge;
        }
        if let (Some(weights), Some(weight)) = (&mut self.weights, weight) {
            weights.values[index] = weight;
        }
        positions[source] += 1;
    }

    /// Cut the rows into at most `parts` contiguous ranges of similar arc
    /// counts, each with its own slices of every array and of the positions.
    /// Ranges are cut from the offsets alone, so which rows a range holds does
    /// not depend on anything but the graph and the width.
    fn row_ranges<'a>(&'a mut self, positions: &'a mut [usize], parts: usize) -> Vec<RowRange<'a>> {
        let n = positions.len();
        let offsets = &self.offsets.values;
        let arcs = offsets[n];
        let parts = parts.clamp(1, n.max(1));
        let bound = |index: usize| -> usize {
            if index >= parts {
                return n;
            }
            let share = (index as u128 * arcs as u128 / parts as u128) as usize;
            offsets[..n].partition_point(|&start| start < share)
        };
        let mut targets = &mut self.targets.values[..];
        let mut slots = self.edge_slots.as_mut().map(|slots| &mut slots.values[..]);
        let mut weights = self.weights.as_mut().map(|weights| &mut weights.values[..]);
        let mut positions = positions;
        let mut ranges = Vec::with_capacity(parts);
        for index in 0..parts {
            let rows = bound(index)..bound(index + 1);
            let first_arc = offsets[rows.start];
            let len = offsets[rows.end] - first_arc;
            let (own, rest) = std::mem::take(&mut targets).split_at_mut(len);
            targets = rest;
            let (own_slots, rest) = split_option(slots.take(), len);
            slots = rest;
            let (own_weights, rest) = split_option(weights.take(), len);
            weights = rest;
            let (own_positions, rest) = std::mem::take(&mut positions).split_at_mut(rows.len());
            positions = rest;
            ranges.push(RowRange {
                rows,
                first_arc,
                targets: own,
                slots: own_slots,
                weights: own_weights,
                positions: own_positions,
            });
        }
        ranges
    }

    pub(crate) fn range(&self, node: usize) -> std::ops::Range<usize> {
        self.offsets.values[node]..self.offsets.values[node + 1]
    }
    /// Original edge position of an arc, on an adjacency that carries them.
    ///
    /// # Panics
    /// A transpose carries no edge slots. Every construction that a kernel
    /// reaches through `outgoing()` fills them, so a panic here would mean a
    /// kernel read a transpose as if it were the projection's own adjacency.
    #[track_caller]
    pub(crate) fn edge_slot(&self, arc: usize) -> usize {
        self.edge_slots
            .as_ref()
            .expect("arc slots belong to a projection's own adjacency, not a transpose")
            .values[arc]
    }

    pub(crate) fn weight(&self, arc: usize) -> f64 {
        self.weights
            .as_ref()
            .map_or(1.0, |weights| weights.values[arc])
    }

    /// The same arcs grouped by target: row `v` lists the sources of arcs into
    /// `v`, each with its weight. Within a row, arcs keep the order of their
    /// sources, so the result is a function of this CSR alone.
    ///
    /// This is the projection's only reverse index. Reachability alone once had
    /// a second, narrower one; one build that carries weights costs less than
    /// two builds over the same arcs, and no caller of a transpose reads edge
    /// slots, so those are left out rather than duplicated.
    ///
    /// Counted and filled in parallel above the floor, as [`Self::build`] is,
    /// with this CSR's arcs, in source order, standing for the edges.
    ///
    /// The projection builds its transpose with [`Self::transposed_split`];
    /// these, with one execution for both roles, are what the tests measure.
    #[cfg(all(test, feature = "parallel"))]
    pub(crate) fn transposed(&self, context: &ExecutionContext) -> Result<Adjacency> {
        Ok(self.transposed_traced(context)?.0)
    }

    #[cfg(all(test, feature = "parallel"))]
    pub(crate) fn transposed_traced(
        &self,
        context: &ExecutionContext,
    ) -> Result<(Adjacency, BuildPath)> {
        self.transposed_split(context, context)
    }

    /// The transpose with every byte it admits, kept or scratch, admitted by
    /// `memory`, and everything else — work, cancellation, the deadline and
    /// the worker count — taken from `context`. A projection's cached
    /// transpose outlives the query that happens to build it, so it is
    /// admitted by the projection's owner while that query pays for, and can
    /// stop, the build. With one execution for both this is
    /// [`Self::transposed_traced`], unchanged.
    pub(crate) fn transposed_split(
        &self,
        memory: &ExecutionContext,
        context: &ExecutionContext,
    ) -> Result<(Adjacency, BuildPath)> {
        let n = self.offsets.values.len() - 1;
        let arcs = self.targets.values.len();
        let mut offsets = Buffer::filled_split(n + 1, 0usize, memory, context)?;
        let counted = match Counts::plan(context, memory, n, arcs, arcs)? {
            Some(mut table) => {
                let len = arcs.div_ceil(table.chunks).max(1);
                table.count(context, |index, row, meter| {
                    let start = (index * len).min(arcs);
                    let slice = &self.targets.values[start..(start + len).min(arcs)];
                    meter.charge(slice.len())?;
                    for &target in slice {
                        row[target] += 1;
                    }
                    Ok(())
                })?;
                Some(table.sum_into(context, &mut offsets.values[1..])?)
            }
            None => {
                for chunk in self.targets.values.chunks(1024) {
                    context.charge_work(chunk.len())?;
                    for &target in chunk {
                        offsets.values[target + 1] += 1;
                    }
                }
                None
            }
        };
        prefix(&mut offsets.values, context)?;
        let mut positions = Buffer::capacity(n, memory)?;
        positions.values.extend_from_slice(&offsets.values[..n]);
        let mut result = Adjacency {
            offsets,
            targets: Buffer::filled_split(arcs, 0usize, memory, context)?,
            edge_slots: None,
            weights: self
                .weights
                .as_ref()
                .map(|_| Buffer::filled_split(arcs, 0.0f64, memory, context))
                .transpose()?,
        };

        // The fill charges one unit per source and one per arc.
        if let Some(workers) = fill_workers(context, n, arcs, n.saturating_add(arcs))? {
            let parts = result.row_ranges(&mut positions.values, workers);
            let ranges = parts.len();
            crate::parallel::for_each_owned(workers, parts, |_, mut part| {
                let mut meter = context.work_meter();
                // A range pays for its own sources and for the arcs into its
                // rows, which its slice of the targets counts: together, one
                // unit per source and one per arc, as sequentially. Paid up
                // front, because the whole fill was found to fit.
                meter.charge(part.rows.len() + part.targets.len())?;
                for source in 0..n {
                    part.poll(source, &meter)?;
                    for arc in self.range(source) {
                        let target = self.targets.values[arc];
                        if part.holds(target) {
                            let weight = self.weights.as_ref().map(|from| from.values[arc]);
                            part.put(target, source, None, weight);
                        }
                    }
                }
                Ok(())
            })?;
            let chunks = counted.unwrap_or(0);
            return Ok((result, BuildPath::Parallel { chunks, ranges }));
        }
        for source in 0..n {
            let range = self.range(source);
            context.charge_work(1 + range.len())?;
            for arc in range {
                let slot = positions.values[self.targets.values[arc]];
                positions.values[self.targets.values[arc]] += 1;
                result.targets.values[slot] = source;
                if let (Some(into), Some(from)) = (&mut result.weights, &self.weights) {
                    into.values[slot] = from.values[arc];
                }
            }
        }
        Ok((result, BuildPath::filled_sequentially(counted)))
    }
}

fn split_option<T>(values: Option<&mut [T]>, at: usize) -> (Option<&mut [T]>, Option<&mut [T]>) {
    match values {
        Some(values) => {
            let (own, rest) = values.split_at_mut(at);
            (Some(own), Some(rest))
        }
        None => (None, None),
    }
}

/// Workers for a parallel fill, or `None` for the sequential one: below the
/// floor, no concurrency asked for, no rows, or a budget that cannot pay for
/// the whole fill. The last keeps exhaustion exact: the sequential fill then
/// runs and is refused at the unit it always was, with the same count left.
fn fill_workers(
    context: &ExecutionContext,
    nodes: usize,
    items: usize,
    work: usize,
) -> Result<Option<usize>> {
    let Some(workers) = crate::parallel::workers(context, nodes.saturating_add(items)) else {
        return Ok(None);
    };
    if nodes == 0 || !crate::parallel::work_fits(context, work)? {
        return Ok(None);
    }
    Ok(Some(workers))
}

/// One worker's share of a parallel fill: a contiguous range of rows, and the
/// slices of every array those rows own.
///
/// **Why the result is the sequential one, byte for byte.** The sequential fill
/// walks its input once, in order, and appends each arc to its row, so a row
/// lists its arcs in input order. Here every worker walks the whole input, in
/// the same order, and appends only the arcs whose rows it holds, through the
/// same positions, which start where the sequential fill's do. Each row is
/// therefore written by exactly one worker, in exactly the sequential order,
/// into exactly the sequential slots. Nothing about the result depends on how
/// many ranges there are or where they were cut.
///
/// Rows are contiguous and so are their arcs, so each worker's slices come from
/// `split_at_mut`: no atomics, no `unsafe`, and not one byte more than the
/// sequential fill holds. The price is that every worker reads every edge,
/// which is a streaming read, while the random writes — what the sequential
/// fill spends its time on — are divided among the workers and each lands in a
/// region a worker's cache can hold more of.
struct RowRange<'a> {
    rows: Range<usize>,
    /// Arc index where `rows.start`'s row begins: the slices are relative to it.
    first_arc: usize,
    targets: &'a mut [usize],
    slots: Option<&'a mut [usize]>,
    weights: Option<&'a mut [f64]>,
    /// Absolute next-arc index per row in `rows`, as the sequential fill's.
    positions: &'a mut [usize],
}

impl RowRange<'_> {
    #[inline]
    fn holds(&self, row: usize) -> bool {
        self.rows.contains(&row)
    }

    /// Poll cancellation and the deadline every so often. A range that holds
    /// few rows charges little while it scans everything, so charging alone
    /// would leave it deaf for a whole pass.
    #[inline]
    fn poll(&self, item: usize, meter: &WorkMeter) -> Result<()> {
        if item.is_multiple_of(1 << 16) {
            meter.checkpoint()?;
        }
        Ok(())
    }

    #[inline]
    fn put(&mut self, row: usize, target: usize, slot: Option<usize>, weight: Option<f64>) {
        let local = row - self.rows.start;
        let index = self.positions[local] - self.first_arc;
        self.positions[local] += 1;
        self.targets[index] = target;
        if let (Some(slots), Some(slot)) = (&mut self.slots, slot) {
            slots[index] = slot;
        }
        if let (Some(weights), Some(weight)) = (&mut self.weights, weight) {
            weights[index] = weight;
        }
    }
}

/// Per-chunk degree counts for a parallel count.
///
/// The input is cut into `chunks` contiguous pieces, and each piece counts its
/// own arcs per row into its own row of this table. The rows are disjoint
/// slices, so this needs no atomics, and a node's degree — the sum down its
/// column — is an integer sum, so it does not depend on where the pieces were
/// cut. The pieces follow the worker count, which the crate's rule allows for
/// integers: no float is ever summed in a width-dependent grouping.
///
/// **Memory.** The table is `chunks × nodes × 4` bytes, admitted before it is
/// allocated and released before the adjacency's arrays are, so it never adds
/// to a build's peak. The chunks are at most the worker count, at most
/// [`MAX_COUNT_CHUNKS`], and at most twice the input per node, so the table is
/// at most eight bytes per input item and four per node: never more than the
/// target array and positions the build allocates next, which the sequential
/// build allocates too.
struct Counts {
    workers: usize,
    chunks: usize,
    nodes: usize,
    /// Row-major, one row of `nodes` per chunk.
    table: Vec<u32>,
    _admission: MemoryReservation,
}

impl Counts {
    /// A table for a parallel count, or `None` for the sequential one.
    ///
    /// `items` is the input the count walks, charging one unit each. Two
    /// refusals keep a budget's outcome independent of the width. If the
    /// count's work does not fit what is left of the budget, the sequential
    /// count runs and exhausts it at the unit it always did. If the table's
    /// memory is refused, the sequential count runs, and the build meets
    /// whatever memory limit it would have met, where it would have met it.
    fn plan(
        context: &ExecutionContext,
        memory: &ExecutionContext,
        nodes: usize,
        items: usize,
        counting: usize,
    ) -> Result<Option<Self>> {
        let Some(workers) = crate::parallel::workers(context, nodes.saturating_add(items)) else {
            return Ok(None);
        };
        // One chunk counts at most its own length at any node, which must fit
        // a u32; past four billion items the count stays sequential.
        if nodes == 0 || items == 0 || u32::try_from(items).is_err() {
            return Ok(None);
        }
        if !crate::parallel::work_fits(context, counting)? {
            return Ok(None);
        }
        let chunks = workers
            .min(MAX_COUNT_CHUNKS)
            .min(items.saturating_mul(2) / nodes)
            .max(1);
        let cells = chunks.saturating_mul(nodes);
        let admission = match memory.reserve(cells.saturating_mul(size_of::<u32>())) {
            Ok(admission) => admission,
            Err(ProcedureError::BudgetExceeded {
                resource: "memory", ..
            }) => return Ok(None),
            Err(error) => return Err(error),
        };
        let mut table = Vec::new();
        table.try_reserve_exact(cells)?;
        table.resize(cells, 0u32);
        Ok(Some(Self {
            workers,
            chunks,
            nodes,
            table,
            _admission: admission,
        }))
    }

    /// Each chunk counts into its own row.
    fn count(
        &mut self,
        context: &ExecutionContext,
        body: impl Fn(usize, &mut [u32], &mut WorkMeter) -> Result<()> + Send + Sync,
    ) -> Result<()> {
        let nodes = self.nodes;
        crate::parallel::for_each_chunk_sized(
            context,
            self.workers,
            &mut self.table,
            nodes,
            |first, row, meter| body(first / nodes, row, meter),
        )
    }

    /// Add each column into `degrees` — `offsets[1..]`, still zero — and
    /// release the table. Charges no work, as the sequential build has no such
    /// pass; it polls instead. Returns the chunk count, for [`BuildPath`].
    fn sum_into(self, context: &ExecutionContext, degrees: &mut [usize]) -> Result<usize> {
        let nodes = self.nodes;
        let block = nodes.div_ceil(self.workers.saturating_mul(4)).max(4096);
        let mut columns: Vec<(Vec<&[u32]>, &mut [usize])> = degrees
            .chunks_mut(block)
            .map(|degrees| (Vec::with_capacity(self.chunks), degrees))
            .collect();
        for row in self.table.chunks(nodes) {
            for (column, cells) in columns.iter_mut().zip(row.chunks(block)) {
                column.0.push(cells);
            }
        }
        crate::parallel::for_each_owned(self.workers, columns, |_, (rows, degrees)| {
            context.checkpoint()?;
            // Row by row, so each pass reads memory in order.
            for row in rows {
                for (&cell, degree) in row.iter().zip(degrees.iter_mut()) {
                    *degree += cell as usize;
                }
            }
            Ok(())
        })?;
        Ok(self.chunks)
    }
}

fn prefix(offsets: &mut [usize], context: &ExecutionContext) -> Result<()> {
    for index in 1..offsets.len() {
        context.charge_work(1)?;
        offsets[index] = offsets[index]
            .checked_add(offsets[index - 1])
            .ok_or_else(|| ProcedureError::Numerical("arc count overflow".into()))?;
    }
    Ok(())
}

/// Without the `parallel` feature there is only the sequential build, which the
/// rest of the crate's tests already cover.
#[cfg(all(test, feature = "parallel"))]
mod tests {
    use grust_procedures::{Accounting, ExecutionLimits};

    use super::*;

    const WIDTHS: [usize; 5] = [1, 2, 3, 8, 16];

    const ORIENTATIONS: [Orientation; 3] = [
        Orientation::Outgoing,
        Orientation::Incoming,
        Orientation::Undirected,
    ];

    fn limits(memory_bytes: usize, work_units: usize) -> ExecutionLimits {
        ExecutionLimits {
            memory_bytes,
            work_units,
            batch_rows: 1024,
            deadline: None,
        }
    }

    /// No concurrency asked for: the sequential build, the oracle.
    fn sequential(memory: usize, work: usize) -> ExecutionContext {
        ExecutionContext::new(limits(memory, work)).unwrap()
    }

    fn parallel(workers: usize, memory: usize, work: usize) -> ExecutionContext {
        sequential(memory, work).with_concurrency(workers).unwrap()
    }

    fn xorshift(mut state: u64) -> impl FnMut() -> u64 {
        move || {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            state
        }
    }

    /// Skewed endpoints (a quarter of sources on a sixteenth of the nodes),
    /// a self-loop every 37th edge, a repeat of the previous edge every 23rd,
    /// and weights that include negatives and both zeros, so a weight that
    /// moved or was rounded would show in its bits.
    fn fixture(nodes: usize, edges: usize, seed: u64) -> (Vec<ProjectionEdge>, Vec<f64>) {
        let mut random = xorshift(seed);
        let mut list: Vec<ProjectionEdge> = Vec::with_capacity(edges);
        for ordinal in 0..edges {
            let (source, target) = if ordinal % 23 == 22 {
                let previous = &list[ordinal - 1];
                (previous.source, previous.target)
            } else {
                let source = if random().is_multiple_of(4) {
                    (random() % (nodes as u64 / 16)) as usize
                } else {
                    (random() % nodes as u64) as usize
                };
                let target = if ordinal % 37 == 0 {
                    source
                } else {
                    (random() % nodes as u64) as usize
                };
                (source, target)
            };
            list.push(ProjectionEdge {
                source,
                target,
                ordinal,
                id: None,
            });
        }
        let weights = (0..edges)
            .map(|index| match index % 11 {
                0 => 0.0,
                1 => -0.0,
                2 => -((random() % 1000) as f64) / 7.0,
                _ => (random() % 1_000_000) as f64 / 3.0,
            })
            .collect();
        (list, weights)
    }

    type Bytes = (Vec<usize>, Vec<usize>, Option<Vec<usize>>, Option<Vec<u64>>);

    /// Every array, weights as bits.
    fn bytes(adjacency: &Adjacency) -> Bytes {
        (
            adjacency.offsets.values.clone(),
            adjacency.targets.values.clone(),
            adjacency
                .edge_slots
                .as_ref()
                .map(|slots| slots.values.clone()),
            adjacency.weights.as_ref().map(|weights| {
                weights
                    .values
                    .iter()
                    .map(|weight| weight.to_bits())
                    .collect()
            }),
        )
    }

    fn work(context: &ExecutionContext) -> Option<usize> {
        context.usage().unwrap().counted_work()
    }

    #[test]
    fn the_parallel_build_and_transpose_are_the_sequential_bytes_at_every_width() {
        const NODES: usize = 3000;
        const EDGES: usize = 60_000;
        let (edges, weights) = fixture(NODES, EDGES, 0x9E37_79B9_7F4A_7C15);
        assert!(edges.iter().any(|edge| edge.source == edge.target));
        assert!(
            edges.windows(2).any(|pair| {
                (pair[0].source, pair[0].target) == (pair[1].source, pair[1].target)
            })
        );
        // Well above the floor, and dense enough for sixteen chunks. The path
        // each build reports below is the proof; these say why to expect it.
        const { assert!(NODES + EDGES >= 2 * crate::parallel::SEQUENTIAL_BELOW_UNITS) };
        const { assert!(2 * EDGES / NODES >= 16) };
        for orientation in ORIENTATIONS {
            for weights in [None, Some(weights.as_slice())] {
                let oracle = sequential(1 << 30, usize::MAX);
                let (expected, path) =
                    Adjacency::build_traced(NODES, &edges, weights, orientation, &oracle).unwrap();
                assert_eq!(path, BuildPath::Sequential);
                let (expected_in, path) = expected.transposed_traced(&oracle).unwrap();
                assert_eq!(path, BuildPath::Sequential);
                let expected_usage = oracle.usage().unwrap();
                for workers in WIDTHS {
                    let context = parallel(workers, 1 << 30, usize::MAX);
                    let label = format!(
                        "{orientation:?}, weighted {}, {workers} workers",
                        weights.is_some()
                    );
                    // The parallel code ran, cut as many ways as there are workers.
                    let cut = BuildPath::Parallel {
                        chunks: workers,
                        ranges: workers,
                    };
                    let (built, path) =
                        Adjacency::build_traced(NODES, &edges, weights, orientation, &context)
                            .unwrap();
                    assert_eq!(path, cut, "{label}");
                    assert!(bytes(&built) == bytes(&expected), "build, {label}");
                    let (transposed, path) = built.transposed_traced(&context).unwrap();
                    assert_eq!(path, cut, "{label}");
                    assert!(
                        bytes(&transposed) == bytes(&expected_in),
                        "transpose, {label}"
                    );
                    // The same work, and not a byte more memory at any moment.
                    let usage = context.usage().unwrap();
                    assert_eq!(usage.work_units, expected_usage.work_units, "{label}");
                    assert_eq!(usage.peak_bytes, expected_usage.peak_bytes, "{label}");
                }
            }
        }
    }

    #[test]
    fn a_sparse_graph_is_counted_in_fewer_chunks_and_still_matches() {
        const NODES: usize = 20_000;
        const EDGES: usize = 30_000;
        let (edges, weights) = fixture(NODES, EDGES, 0xD1B5_4A32_D192_ED03);
        for orientation in ORIENTATIONS {
            let oracle = sequential(1 << 30, usize::MAX);
            let expected =
                Adjacency::build(NODES, &edges, Some(&weights), orientation, &oracle).unwrap();
            let expected_in = expected.transposed(&oracle).unwrap();
            let context = parallel(16, 1 << 30, usize::MAX);
            let (built, path) =
                Adjacency::build_traced(NODES, &edges, Some(&weights), orientation, &context)
                    .unwrap();
            // Three edges per two nodes: three counting chunks, not sixteen.
            assert_eq!(
                path,
                BuildPath::Parallel {
                    chunks: 3,
                    ranges: 16
                }
            );
            assert!(bytes(&built) == bytes(&expected));
            let (transposed, path) = built.transposed_traced(&context).unwrap();
            assert!(matches!(
                path,
                BuildPath::Parallel {
                    chunks: 2..=5,
                    ranges: 16
                }
            ));
            assert!(bytes(&transposed) == bytes(&expected_in));
        }
    }

    #[test]
    fn an_uncounted_execution_builds_the_same_bytes() {
        const NODES: usize = 3000;
        let (edges, weights) = fixture(NODES, 60_000, 7);
        let oracle = sequential(1 << 30, usize::MAX);
        let expected = Adjacency::build(
            NODES,
            &edges,
            Some(&weights),
            Orientation::Undirected,
            &oracle,
        )
        .unwrap();
        for accounting in [Accounting::WORK_UNCOUNTED, Accounting::UNCHECKED] {
            let context =
                ExecutionContext::with_accounting(limits(1 << 30, usize::MAX), accounting)
                    .unwrap()
                    .with_concurrency(8)
                    .unwrap();
            let (built, path) = Adjacency::build_traced(
                NODES,
                &edges,
                Some(&weights),
                Orientation::Undirected,
                &context,
            )
            .unwrap();
            assert_eq!(
                path,
                BuildPath::Parallel {
                    chunks: 8,
                    ranges: 8
                }
            );
            assert!(bytes(&built) == bytes(&expected));
        }
    }

    /// Whether a budget succeeds, and the work counted when it stops.
    fn outcome<T>(result: &Result<T>, context: &ExecutionContext) -> (bool, Option<usize>) {
        match result {
            Ok(_) => (true, work(context)),
            Err(ProcedureError::BudgetExceeded {
                resource: "work", ..
            }) => (false, work(context)),
            Err(other) => panic!("unexpected error: {other}"),
        }
    }

    #[test]
    fn a_work_budget_runs_out_at_the_same_unit_at_every_width() {
        const NODES: usize = 3000;
        let (edges, weights) = fixture(NODES, 40_000, 11);
        for orientation in ORIENTATIONS {
            let oracle = sequential(1 << 30, usize::MAX);
            let whole =
                Adjacency::build(NODES, &edges, Some(&weights), orientation, &oracle).unwrap();
            let needed = work(&oracle).unwrap();
            let transpose_needed = {
                let probe = sequential(1 << 30, usize::MAX);
                whole.transposed(&probe).unwrap();
                work(&probe).unwrap()
            };
            // Budgets across every phase of each build, and either side of enough.
            let budgets = |needed: usize| {
                (0..=64)
                    .map(move |step| needed * step / 64)
                    .chain([needed - 1, needed, needed + 1])
            };
            for budget in budgets(needed) {
                let context = sequential(1 << 30, budget);
                let expected = outcome(
                    &Adjacency::build(NODES, &edges, Some(&weights), orientation, &context),
                    &context,
                );
                for workers in WIDTHS {
                    let context = parallel(workers, 1 << 30, budget);
                    let result = Adjacency::build_traced(
                        NODES,
                        &edges,
                        Some(&weights),
                        orientation,
                        &context,
                    );
                    assert_eq!(
                        outcome(&result, &context),
                        expected,
                        "{orientation:?} build, budget {budget} of {needed}, {workers} workers"
                    );
                    if budget >= needed {
                        assert!(matches!(result.unwrap().1, BuildPath::Parallel { .. }));
                    }
                }
            }
            for budget in budgets(transpose_needed) {
                let context = sequential(1 << 30, budget);
                let expected = outcome(&whole.transposed(&context), &context);
                for workers in WIDTHS {
                    let context = parallel(workers, 1 << 30, budget);
                    let result = whole.transposed_traced(&context);
                    assert_eq!(
                        outcome(&result, &context),
                        expected,
                        "{orientation:?} transpose, budget {budget} of {transpose_needed}, \
                         {workers} workers"
                    );
                    if budget >= transpose_needed {
                        assert!(matches!(result.unwrap().1, BuildPath::Parallel { .. }));
                    }
                }
            }
        }
    }

    #[test]
    fn a_memory_limit_is_met_or_refused_as_it_is_sequentially() {
        const NODES: usize = 3000;
        let (edges, weights) = fixture(NODES, 60_000, 13);
        for orientation in ORIENTATIONS {
            let oracle = sequential(1 << 30, usize::MAX);
            let expected =
                Adjacency::build(NODES, &edges, Some(&weights), orientation, &oracle).unwrap();
            let peak = oracle.usage().unwrap().peak_bytes;
            let expected_in = expected.transposed(&oracle).unwrap();
            let transpose_peak = oracle.usage().unwrap().peak_bytes;

            // Exactly what the sequential build needs is enough for the
            // parallel one, which still runs in parallel.
            let context = parallel(16, peak, usize::MAX);
            let (built, path) =
                Adjacency::build_traced(NODES, &edges, Some(&weights), orientation, &context)
                    .unwrap();
            assert!(matches!(path, BuildPath::Parallel { chunks: 16, .. }));
            assert!(bytes(&built) == bytes(&expected));
            // One byte less refuses both.
            for context in [
                parallel(16, peak - 1, usize::MAX),
                sequential(peak - 1, usize::MAX),
            ] {
                assert!(matches!(
                    Adjacency::build(NODES, &edges, Some(&weights), orientation, &context),
                    Err(ProcedureError::BudgetExceeded {
                        resource: "memory",
                        ..
                    })
                ));
            }

            // The transpose, with the adjacency it reads held beside it.
            let context = parallel(16, transpose_peak, usize::MAX);
            let built =
                Adjacency::build(NODES, &edges, Some(&weights), orientation, &context).unwrap();
            let (transposed, path) = built.transposed_traced(&context).unwrap();
            assert!(matches!(path, BuildPath::Parallel { .. }));
            assert!(bytes(&transposed) == bytes(&expected_in));
            let context = parallel(16, transpose_peak - 1, usize::MAX);
            let built =
                Adjacency::build(NODES, &edges, Some(&weights), orientation, &context).unwrap();
            assert!(matches!(
                built.transposed(&context),
                Err(ProcedureError::BudgetExceeded {
                    resource: "memory",
                    ..
                })
            ));
        }
    }
}
