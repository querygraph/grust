//! Projection identity and topology validation. Property extraction lives at adapters.

use std::collections::HashMap;
use std::sync::{Arc, Mutex};

use grust_core::{EdgeId, NodeId};
pub use grust_procedures::SnapshotIdentity;
use grust_procedures::{ExecutionContext, MemoryReservation, ProcedureError, Result};

use crate::buffer::Buffer;

mod adjacency;
mod origin;
pub(crate) use adjacency::Adjacency;
pub use origin::{ProjectionRepresentation, ProjectionSelection};

/// Explicit orientation applied once while preparing topology.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Orientation {
    /// Follow source-to-target edges.
    Outgoing,
    /// Follow target-to-source edges.
    Incoming,
    /// Traverse each non-loop edge in both directions; loops occur once.
    Undirected,
}

/// Topology-only input edge. Dense endpoints refer to the supplied node table.
/// An original ordinal distinguishes parallel edges and nonunique/missing IDs.
#[derive(Clone, Debug)]
pub struct ProjectionEdge {
    /// Source row in the supplied external-ID mapping.
    pub source: usize,
    /// Target row in the supplied external-ID mapping.
    pub target: usize,
    /// Original snapshot edge position, unique within this projection.
    pub ordinal: usize,
    /// Optional external edge identity, preserved without reinterpretation.
    pub id: Option<EdgeId>,
}

/// A validated immutable topology and external identity mapping.
///
/// Input vectors transfer ownership. Their retained storage is charged upon
/// entry; the caller remains responsible for allocating those input vectors
/// under its ingestion envelope. CSR and scratch are reserved before allocation.
/// No property maps enter adjacency loops. Reverse CSR is constructed lazily.
#[derive(Clone)]
pub struct GraphProjection {
    inner: Arc<ProjectionData>,
}

struct ProjectionData {
    identity: SnapshotIdentity,
    representation: ProjectionRepresentation,
    selection: Option<ProjectionSelection>,
    orientation: Orientation,
    /// Weights may be negative; see [`GraphProjection::require_nonnegative`].
    signed: bool,
    nodes: Buffer<NodeId>,
    node_by_id: HashMap<NodeId, usize>,
    edges: Buffer<ProjectionEdge>,
    outgoing: Adjacency,
    incoming: Mutex<Option<Arc<Adjacency>>>,
    context: ExecutionContext,
    _retained: MemoryReservation,
}

impl GraphProjection {
    /// Validate and prepare topology. Weights are either absent (all unit
    /// weights, with no weight buffer) or one finite nonnegative value per edge.
    /// Duplicate node IDs, ordinals and missing endpoints are errors. External
    /// edge IDs may repeat; the original ordinal remains the disambiguator.
    pub fn from_topology(
        identity: SnapshotIdentity,
        nodes: Vec<NodeId>,
        edges: Vec<ProjectionEdge>,
        weights: Option<Vec<f64>>,
        orientation: Orientation,
        context: &ExecutionContext,
    ) -> Result<Self> {
        Self::from_buffers(
            identity,
            Buffer::adopt(nodes, context)?,
            Buffer::adopt(edges, context)?,
            weights
                .map(|values| Buffer::adopt(values, context))
                .transpose()?,
            false,
            orientation,
            context,
        )
    }

    /// As [`Self::from_topology`], admitting negative weights. The projection is
    /// then *signed*: [`crate::bellman_ford`] runs on it, and every other kernel
    /// refuses it, because each of them assumes what a negative weight breaks —
    /// that a settled distance is final, that a strength is a total, that a
    /// capacity can be filled.
    pub fn from_signed_topology(
        identity: SnapshotIdentity,
        nodes: Vec<NodeId>,
        edges: Vec<ProjectionEdge>,
        weights: Vec<f64>,
        orientation: Orientation,
        context: &ExecutionContext,
    ) -> Result<Self> {
        Self::from_buffers(
            identity,
            Buffer::adopt(nodes, context)?,
            Buffer::adopt(edges, context)?,
            Some(Buffer::adopt(weights, context)?),
            true,
            orientation,
            context,
        )
    }

    pub(crate) fn from_buffers(
        identity: SnapshotIdentity,
        nodes: Buffer<NodeId>,
        edges: Buffer<ProjectionEdge>,
        weights: Option<Buffer<f64>>,
        signed: bool,
        orientation: Orientation,
        context: &ExecutionContext,
    ) -> Result<Self> {
        context.checkpoint()?;
        let mut bytes = size_of::<ProjectionData>()
            .saturating_add(2 * size_of::<usize>())
            .saturating_add(
                nodes
                    .len()
                    .saturating_add(4)
                    .saturating_mul(2 * (size_of::<NodeId>() + size_of::<usize>() + 1)),
            )
            .saturating_add(identity.owned_bytes());
        for id in nodes.iter() {
            context.charge_work(1)?;
            bytes = bytes
                .saturating_add(id.as_str().len())
                .saturating_add(2 * size_of::<usize>());
        }
        for edge in edges.iter() {
            context.charge_work(1)?;
            if let Some(id) = &edge.id {
                bytes = bytes
                    .saturating_add(id.as_str().len())
                    .saturating_add(2 * size_of::<usize>());
            }
        }
        let retained = context.reserve(bytes)?;
        let mut node_by_id = HashMap::new();
        node_by_id.try_reserve(nodes.len())?;
        for (index, id) in nodes.iter().enumerate() {
            context.charge_work(1)?;
            if node_by_id.insert(id.clone(), index).is_some() {
                return Err(ProcedureError::InvalidArguments(format!(
                    "duplicate node ID: {id}"
                )));
            }
        }
        if weights
            .as_ref()
            .is_some_and(|weights| weights.len() != edges.len())
        {
            return Err(ProcedureError::InvalidArguments(
                "weight count must equal edge count".into(),
            ));
        }
        validate_edges(&edges, weights.as_deref(), nodes.len(), signed, context)?;
        let outgoing = Adjacency::build(
            nodes.len(),
            &edges,
            weights.as_deref(),
            orientation,
            context,
        )?;
        drop(weights);
        Ok(Self {
            inner: Arc::new(ProjectionData {
                identity,
                representation: ProjectionRepresentation::Topology,
                selection: None,
                orientation,
                signed,
                nodes,
                node_by_id,
                edges,
                outgoing,
                incoming: Mutex::new(None),
                context: context.clone(),
                _retained: retained,
            }),
        })
    }

    /// Snapshot and principal to which this projection belongs.
    pub fn identity(&self) -> &SnapshotIdentity {
        &self.inner.identity
    }
    /// Adapter representation used to construct the owned topology.
    pub fn representation(&self) -> ProjectionRepresentation {
        self.inner.representation
    }
    /// Retained label and property policy; absent for raw topology input.
    pub fn selection(&self) -> Option<&ProjectionSelection> {
        self.inner.selection.as_ref()
    }
    /// Orientation used by directed kernels.
    pub fn orientation(&self) -> Orientation {
        self.inner.orientation
    }
    /// External IDs in result row order, including isolates.
    pub fn node_ids(&self) -> &[NodeId] {
        &self.inner.nodes
    }
    /// Original edge identity mapping. Kernel edge slots index this slice.
    pub fn edges(&self) -> &[ProjectionEdge] {
        &self.inner.edges
    }
    /// Shared resource context for preparation, kernels and consumers.
    pub fn execution(&self) -> &ExecutionContext {
        &self.inner.context
    }
    /// Number of selected vertices.
    pub fn node_count(&self) -> usize {
        self.inner.nodes.len()
    }
    /// Number of original selected edges; undirected traversal may have more arcs.
    pub fn edge_count(&self) -> usize {
        self.inner.edges.len()
    }
    /// Whether the projection was built to admit negative weights.
    pub fn is_signed(&self) -> bool {
        self.inner.signed
    }

    /// Refuse a signed projection on behalf of `kernel`. Every kernel but
    /// `bellman_ford` calls this first. Without it a negative weight would not
    /// fail: Dijkstra would settle a node too early, PageRank would divide by a
    /// strength that is no longer a total, max flow would fill a negative
    /// capacity — each a confident wrong answer.
    pub(crate) fn require_nonnegative(&self, kernel: &str) -> Result<()> {
        if self.inner.signed {
            return Err(ProcedureError::InvalidArguments(format!(
                "{kernel} does not accept a signed projection: it was built to admit negative weights, which only bellmanFord handles"
            )));
        }
        Ok(())
    }

    /// Whether a weight buffer was explicitly supplied.
    pub fn is_weighted(&self) -> bool {
        self.inner.outgoing.weights.is_some()
    }

    pub(crate) fn source(&self, id: &str) -> Result<usize> {
        self.inner.node_by_id.get(id).copied().ok_or_else(|| {
            ProcedureError::InvalidArguments(format!("source is not selected: {id}"))
        })
    }
    pub(crate) fn outgoing(&self) -> &Adjacency {
        &self.inner.outgoing
    }
    /// Build the incoming adjacency now, instead of inside the first kernel that
    /// needs it. The first such kernel otherwise pays for the transpose: for an
    /// embedder that caches projections, that cost lands in a user's query
    /// rather than at staging, and a timing that wants the kernel alone sees a
    /// one-off build folded into it. Admitted and charged here, exactly as it
    /// would be there; the result is shared by every later kernel. Idempotent,
    /// and free on an undirected projection, whose rows already mirror.
    pub fn prepare_incoming(&self) -> Result<()> {
        self.incoming().map(|_| ())
    }
    /// Arcs by target, with weights and edge slots: what `reverse` omits. On an
    /// undirected projection every row already mirrors itself, so this is the
    /// outgoing adjacency and nothing is built. Otherwise it is built once,
    /// admitted and charged, and shared by every kernel on this projection.
    pub(crate) fn incoming(&self) -> Result<InArcs<'_>> {
        self.inner.context.checkpoint()?;
        if self.inner.orientation == Orientation::Undirected {
            return Ok(InArcs::Mirror(&self.inner.outgoing));
        }
        let mut cached = self
            .inner
            .incoming
            .lock()
            .map_err(|_| ProcedureError::ResourceStatePoisoned)?;
        if let Some(incoming) = &*cached {
            return Ok(InArcs::Built(Arc::clone(incoming)));
        }
        let incoming = Arc::new(self.inner.outgoing.transposed(&self.inner.context)?);
        *cached = Some(Arc::clone(&incoming));
        Ok(InArcs::Built(incoming))
    }
}

/// In-arcs of a projection: its own rows when undirected, else a built transpose.
pub(crate) enum InArcs<'a> {
    Mirror(&'a Adjacency),
    Built(Arc<Adjacency>),
}

impl std::ops::Deref for InArcs<'_> {
    type Target = Adjacency;
    fn deref(&self) -> &Adjacency {
        match self {
            Self::Mirror(adjacency) => adjacency,
            Self::Built(adjacency) => adjacency,
        }
    }
}

/// Check every edge: endpoints inside the node table, weights finite and, unless
/// the projection is signed, nonnegative, and original ordinals distinct.
///
/// This was a `HashSet` of every ordinal, which on a graph of a hundred million
/// edges is most of a projection's build time — 37.7s of 63s on com-Orkut,
/// measured before this changed. Ordinals are positions, so they are dense in
/// practice, and a bit per ordinal answers the same question in fourteen
/// megabytes instead of gigabytes of hash table. A sparse set of ordinals falls
/// back to sorting a copy, which is slower than the bitmap and still faster than
/// hashing.
fn validate_edges(
    edges: &[ProjectionEdge],
    weights: Option<&[f64]>,
    nodes: usize,
    signed: bool,
    context: &ExecutionContext,
) -> Result<()> {
    use std::sync::atomic::{AtomicU64, Ordering};

    let weight_message = || -> ProcedureError {
        ProcedureError::InvalidArguments(if signed {
            "weights must be finite".into()
        } else {
            "weights must be finite and nonnegative".into()
        })
    };
    // A budget that can pay for every edge is charged a chunk at a time. One
    // that cannot takes the sequential pass, charged an edge at a time as the
    // loop this replaced was, so it refuses at the same edge, with the same
    // work counted and the same error first, at every width. Chunks charged in
    // parallel would leave behind however many had got in first, and one
    // charge for the whole pass would count nothing at all.
    let fits = crate::parallel::work_fits(context, edges.len())?;
    let workers = if fits {
        crate::parallel::workers(context, edges.len())
    } else {
        None
    };
    // The endpoint, weight and range checks are independent per edge, and the
    // largest ordinal is a maximum, so one pass answers all of them. Work is
    // charged once per edge, as the sequential loop charged it.
    let largest = |first: usize,
                   slice: &[ProjectionEdge],
                   meter: &mut grust_procedures::WorkMeter|
     -> Result<usize> {
        if fits {
            meter.charge(slice.len())?;
        }
        let mut largest = 0usize;
        for (offset, edge) in slice.iter().enumerate() {
            if !fits {
                context.charge_work(1)?;
            }
            if edge.source >= nodes || edge.target >= nodes {
                return Err(ProcedureError::InvalidArguments(
                    "edge endpoint outside node table".into(),
                ));
            }
            if let Some(weights) = weights {
                let weight = weights[first + offset];
                if !weight.is_finite() || (!signed && weight < 0.0) {
                    return Err(weight_message());
                }
            }
            largest = largest.max(edge.ordinal);
        }
        Ok(largest)
    };
    let largest = match workers {
        Some(workers) => {
            let chunk = crate::parallel::chunk_len(edges.len(), workers);
            let parts = crate::parallel::map_chunks_sized(context, workers, edges, chunk, largest)?;
            crate::parallel::reduce_in_order(&parts, 0usize, usize::max)
        }
        None => {
            let mut meter = context.work_meter();
            largest(0, edges, &mut meter)?
        }
    };
    if edges.is_empty() {
        return Ok(());
    }

    // Dense ordinals, the ordinary case: one bit each. A word is claimed with a
    // fetch-or, so a duplicate is whoever finds the bit already set, and which
    // worker that is cannot change the answer: the error is the same either way.
    let dense = largest
        .checked_add(1)
        .is_some_and(|span| span <= edges.len().saturating_mul(4).max(1024));
    if dense {
        let words = (largest / 64) + 1;
        let _admission = context.reserve(words.saturating_mul(size_of::<u64>()))?;
        let mut seen = Vec::new();
        seen.try_reserve_exact(words)?;
        seen.resize_with(words, || AtomicU64::new(0));
        let claim = |_: usize,
                     slice: &[ProjectionEdge],
                     meter: &mut grust_procedures::WorkMeter|
         -> Result<()> {
            // The first pass charged these edges; this one polls rather than
            // charging again, so a projection's work total is what it was before
            // the check changed shape and a budget still means the same thing.
            meter.checkpoint()?;
            for edge in slice {
                let bit = 1u64 << (edge.ordinal % 64);
                if seen[edge.ordinal / 64].fetch_or(bit, Ordering::Relaxed) & bit != 0 {
                    return Err(ProcedureError::InvalidArguments(
                        "duplicate original edge ordinal".into(),
                    ));
                }
            }
            Ok(())
        };
        match workers {
            Some(workers) => {
                let chunk = crate::parallel::chunk_len(edges.len(), workers);
                crate::parallel::map_chunks_sized(context, workers, edges, chunk, claim)?;
            }
            None => {
                let mut meter = context.work_meter();
                claim(0, edges, &mut meter)?;
            }
        }
        return Ok(());
    }

    // Sparse ordinals: sort a copy and look at neighbours. Still linear in
    // memory rather than quadratic in cache misses.
    let _admission = context.reserve(edges.len().saturating_mul(size_of::<usize>()))?;
    let mut ordinals = Vec::new();
    ordinals.try_reserve_exact(edges.len())?;
    for chunk in edges.chunks(1024) {
        context.checkpoint()?;
        ordinals.extend(chunk.iter().map(|edge| edge.ordinal));
    }
    match workers {
        Some(workers) => crate::parallel::sort_total(workers, &mut ordinals, usize::cmp)?,
        None => ordinals.sort_unstable(),
    }
    for pair in ordinals.windows(2) {
        if pair[0] == pair[1] {
            return Err(ProcedureError::InvalidArguments(
                "duplicate original edge ordinal".into(),
            ));
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use grust_procedures::ExecutionLimits;

    #[test]
    fn in_arcs_carry_every_arc_with_its_weight_and_are_built_once() {
        let context = ExecutionContext::new(ExecutionLimits {
            memory_bytes: 1 << 20,
            work_units: 1 << 20,
            batch_rows: 1024,
            deadline: None,
        })
        .unwrap();
        let edges = [(0, 1), (2, 1), (0, 1), (1, 1), (3, 0)];
        let weights = vec![1.0, 2.0, 3.0, 4.0, 5.0];
        let build = |orientation| {
            GraphProjection::from_topology(
                SnapshotIdentity::new("g".into(), "r".into(), "reader".into()).unwrap(),
                (0..4).map(|i| format!("n{i}").into()).collect(),
                edges
                    .iter()
                    .enumerate()
                    .map(|(ordinal, &(source, target))| ProjectionEdge {
                        source,
                        target,
                        ordinal,
                        id: None,
                    })
                    .collect(),
                Some(weights.clone()),
                orientation,
                &context,
            )
            .unwrap()
        };
        let arcs = |adjacency: &Adjacency, flip: bool| {
            let mut arcs = Vec::new();
            for node in 0..4 {
                for arc in adjacency.range(node) {
                    let other = adjacency.targets.values[arc];
                    let (from, to) = if flip { (other, node) } else { (node, other) };
                    arcs.push((from, to, adjacency.weight(arc).to_bits()));
                }
            }
            arcs.sort_unstable();
            arcs
        };
        for orientation in [Orientation::Outgoing, Orientation::Incoming] {
            let graph = build(orientation);
            let incoming = graph.incoming().unwrap();
            assert_eq!(arcs(&incoming, true), arcs(graph.outgoing(), false));
            // Rows list their sources in ascending order.
            for node in 0..4 {
                let row = &incoming.targets.values[incoming.range(node)];
                assert!(row.windows(2).all(|pair| pair[0] <= pair[1]));
            }
            let held = context.usage().unwrap().live_bytes;
            drop(graph.incoming().unwrap());
            assert_eq!(context.usage().unwrap().live_bytes, held, "built once");
        }
        let graph = build(Orientation::Undirected);
        let held = context.usage().unwrap().live_bytes;
        assert!(matches!(graph.incoming().unwrap(), InArcs::Mirror(_)));
        assert_eq!(context.usage().unwrap().live_bytes, held, "nothing built");
    }
}
