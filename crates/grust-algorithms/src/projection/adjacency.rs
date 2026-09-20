//! Packed CSR with stable original-edge order and optional contiguous weights.

use super::*;

pub(crate) struct Adjacency {
    pub(crate) offsets: Buffer<usize>,
    pub(crate) targets: Buffer<usize>,
    pub(crate) edge_slots: Buffer<usize>,
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
        prefix(&mut offsets.values, context)?;
        let count = offsets.values[n];
        let mut result = Self {
            offsets,
            targets: Buffer::filled(count, 0, context)?,
            edge_slots: Buffer::filled(count, 0, context)?,
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
        self.edge_slots.values[index] = edge;
        if let (Some(weights), Some(weight)) = (&mut self.weights, weight) {
            weights.values[index] = weight;
        }
        positions[source] += 1;
    }

    pub(crate) fn range(&self, node: usize) -> std::ops::Range<usize> {
        self.offsets.values[node]..self.offsets.values[node + 1]
    }
    pub(crate) fn weight(&self, arc: usize) -> f64 {
        self.weights
            .as_ref()
            .map_or(1.0, |weights| weights.values[arc])
    }

    pub(crate) fn reversed(&self, context: &ExecutionContext) -> Result<ReverseTopology> {
        let n = self.offsets.values.len() - 1;
        let mut offsets = Buffer::filled(n + 1, 0usize, context)?;
        for &target in &self.targets.values {
            context.charge_work(1)?;
            offsets.values[target + 1] += 1;
        }
        prefix(&mut offsets.values, context)?;
        let mut reverse = ReverseTopology {
            offsets,
            targets: Buffer::filled(self.targets.values.len(), 0, context)?,
        };
        let mut positions = Buffer::capacity(n, context)?;
        for chunk in reverse.offsets.values[..n].chunks(1024) {
            context.charge_work(chunk.len())?;
            positions.values.extend_from_slice(chunk);
        }
        for source in 0..n {
            context.charge_work(1)?;
            for arc in self.range(source) {
                context.charge_work(1)?;
                let target = self.targets.values[arc];
                reverse.targets.values[positions.values[target]] = source;
                positions.values[target] += 1;
            }
        }
        Ok(reverse)
    }
}

impl Adjacency {
    /// The same arcs grouped by target: row `v` lists the sources of arcs into
    /// `v`, each with its weight and original edge slot. Within a row, arcs keep
    /// the order of their sources, so the result is a function of this CSR alone.
    #[allow(dead_code)] // first used by the eigenvector, Katz and HITS kernels
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
        let mut edge_slots = Buffer::filled(arcs, 0usize, context)?;
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
                edge_slots.values[slot] = self.edge_slots.values[arc];
                if let (Some(into), Some(from)) = (&mut weights, &self.weights) {
                    into.values[slot] = from.values[arc];
                }
            }
        }
        Ok(Adjacency {
            offsets,
            targets,
            edge_slots,
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

/// SCC needs reverse reachability only. No duplicated weights or edge IDs.
pub(crate) struct ReverseTopology {
    offsets: Buffer<usize>,
    pub(crate) targets: Buffer<usize>,
}

impl ReverseTopology {
    pub(crate) fn range(&self, node: usize) -> std::ops::Range<usize> {
        self.offsets.values[node]..self.offsets.values[node + 1]
    }
}
