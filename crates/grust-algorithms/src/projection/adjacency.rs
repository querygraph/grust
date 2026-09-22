//! Packed CSR with stable original-edge order and optional contiguous weights.

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

impl Adjacency {
    pub(crate) fn build(
        n: usize,
        edges: &[ProjectionEdge],
        weights: Option<&[f64]>,
        orientation: Orientation,
        context: &ExecutionContext,
    ) -> Result<Self> {
        let mut offsets = Buffer::filled(
            n.checked_add(1)
                .ok_or_else(|| ProcedureError::Numerical("node count overflow".into()))?,
            0usize,
            context,
        )?;
        // Counting is a sum per node, so it parallelises without touching the
        // order anything ends up in. Each worker counts its own edge range into
        // its own row, and the rows are added up afterwards: no atomics, and the
        // totals cannot depend on how the edges were divided.
        let workers = crate::parallel::workers(context, n.saturating_add(edges.len()));
        let counted = match workers {
            // A chunk contributes at most one arc per edge to any one node, so
            // a count fits `u32` whenever the edge list does; above that the
            // sequential path, which carries its own overflow check, takes over.
            Some(workers) if n > 0 && edges.len() <= u32::MAX as usize => {
                let chunk = crate::parallel::chunk_len(edges.len(), workers);
                let rows = edges.len().div_ceil(chunk.max(1));
                // A row of counts per chunk. Four bytes a node a chunk, admitted
                // before it is allocated: on a graph of three million nodes with
                // sixteen chunks that is under two hundred megabytes, and it is
                // released before the CSR arrays are filled.
                let _admission =
                    context.reserve_for_workers(rows, n.saturating_mul(size_of::<u32>()))?;
                let mut counts: Vec<u32> = Vec::new();
                counts.try_reserve_exact(rows.saturating_mul(n))?;
                counts.resize(rows.saturating_mul(n), 0);
                crate::parallel::for_each_chunk_sized(
                    context,
                    workers,
                    &mut counts,
                    n,
                    |first, row, meter| {
                        let index = first / n;
                        let start = index * chunk;
                        let slice = &edges[start..(start + chunk).min(edges.len())];
                        meter.charge(slice.len())?;
                        for edge in slice {
                            let source = match orientation {
                                Orientation::Outgoing | Orientation::Undirected => edge.source,
                                Orientation::Incoming => edge.target,
                            };
                            row[source] += 1;
                            if orientation == Orientation::Undirected && edge.source != edge.target
                            {
                                row[edge.target] += 1;
                            }
                        }
                        Ok(())
                    },
                )?;
                // Sum the rows into the degrees. A node's arcs are counted at
                // most twice per edge, so the total cannot exceed the arc count,
                // which the sequential path already proved fits a usize.
                for node in 0..n {
                    context.charge_work(1)?;
                    let mut total = 0usize;
                    for row in 0..rows {
                        total = total
                            .checked_add(counts[row * n + node] as usize)
                            .ok_or_else(|| ProcedureError::Numerical("degree overflow".into()))?;
                    }
                    offsets.values[node + 1] = total;
                }
                true
            }
            _ => false,
        };
        if !counted {
            for edge in edges {
                context.charge_work(1)?;
                let source = match orientation {
                    Orientation::Outgoing | Orientation::Undirected => edge.source,
                    Orientation::Incoming => edge.target,
                };
                offsets.values[source + 1] = offsets.values[source + 1]
                    .checked_add(1)
                    .ok_or_else(|| ProcedureError::Numerical("degree overflow".into()))?;
                if orientation == Orientation::Undirected && edge.source != edge.target {
                    offsets.values[edge.target + 1] = offsets.values[edge.target + 1]
                        .checked_add(1)
                        .ok_or_else(|| ProcedureError::Numerical("degree overflow".into()))?;
                }
            }
        }
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
        for (slot, edge) in edges.iter().enumerate() {
            context.charge_work(1)?;
            let (source, target) = match orientation {
                Orientation::Outgoing | Orientation::Undirected => (edge.source, edge.target),
                Orientation::Incoming => (edge.target, edge.source),
            };
            result.put(
                &mut positions.values,
                source,
                target,
                slot,
                weights.map(|values| values[slot]),
            );
            if orientation == Orientation::Undirected && source != target {
                result.put(
                    &mut positions.values,
                    target,
                    source,
                    slot,
                    weights.map(|values| values[slot]),
                );
            }
        }
        Ok(result)
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
    pub(crate) fn transposed(&self, context: &ExecutionContext) -> Result<Adjacency> {
        let n = self.offsets.values.len() - 1;
        let arcs = self.targets.values.len();
        let mut offsets = Buffer::filled(n + 1, 0usize, context)?;
        for chunk in self.targets.values.chunks(1024) {
            context.charge_work(chunk.len())?;
            for &target in chunk {
                offsets.values[target + 1] += 1;
            }
        }
        prefix(&mut offsets.values, context)?;
        let mut positions = Buffer::capacity(n, context)?;
        positions.values.extend_from_slice(&offsets.values[..n]);
        let mut targets = Buffer::filled(arcs, 0usize, context)?;
        let mut weights = self
            .weights
            .as_ref()
            .map(|_| Buffer::filled(arcs, 0.0f64, context))
            .transpose()?;
        for source in 0..n {
            let range = self.range(source);
            context.charge_work(1 + range.len())?;
            for arc in range {
                let slot = positions.values[self.targets.values[arc]];
                positions.values[self.targets.values[arc]] += 1;
                targets.values[slot] = source;
                if let (Some(into), Some(from)) = (&mut weights, &self.weights) {
                    into.values[slot] = from.values[arc];
                }
            }
        }
        Ok(Adjacency {
            offsets,
            targets,
            edge_slots: None,
            weights,
        })
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
