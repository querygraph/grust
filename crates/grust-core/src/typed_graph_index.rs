//! Snapshot-owned, typed adjacency for compact read execution.

use std::{
    borrow::Cow,
    collections::HashMap,
    io,
    sync::{Arc, OnceLock},
};

use crate::{
    Edge, Graph, GraphSnapshotSource, GrustError, Label, Node, NodeId, Props, Result, Value,
    graph_source::OwnedGraphSource,
};

/// One adjacency entry. Parallel edges remain distinct through `edge`.
#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct TypedNeighbor {
    pub vertex: u32,
    pub edge: u32,
}

#[derive(Debug)]
struct Csr {
    offsets: CsrOffsets,
    neighbors: Vec<TypedNeighbor>,
}

#[derive(Debug)]
enum CsrOffsets {
    Dense(Vec<u32>),
    Sparse {
        sources: Vec<u32>,
        offsets: Vec<u32>,
    },
}

impl Csr {
    fn build(vertices: usize, edges: &[(u32, u32, u32)], reverse: bool) -> Self {
        // Every nonempty dense type pays at most 4E + 1 <= 5E offsets.
        // Sparse types must never allocate or initialize a V-sized scratch array.
        if edges.len() >= vertices.div_ceil(4)
            && let Some(offset_count) = vertices.checked_add(1)
        {
            Self::build_dense(offset_count, edges, reverse)
        } else {
            Self::build_sparse(edges, reverse)
        }
    }

    fn build_dense(offset_count: usize, edges: &[(u32, u32, u32)], reverse: bool) -> Self {
        // Bucket edges by source in linear time, then sort only each vertex's
        // neighbors. Avoid sorting the complete edge relation in both directions.
        let mut offsets = vec![0; offset_count];
        for &(from, to, _) in edges {
            offsets[if reverse { to } else { from } as usize] += 1;
        }
        let mut end = 0;
        for offset in &mut offsets {
            end += *offset;
            *offset = end;
        }
        let mut neighbors = vec![TypedNeighbor { vertex: 0, edge: 0 }; edges.len()];
        // Exclusive ends double as descending insertion cursors. Once filled,
        // they are exactly the CSR starts, with the final sentinel untouched.
        for &(from, to, edge) in edges {
            let (source, vertex) = if reverse { (to, from) } else { (from, to) };
            offsets[source as usize] -= 1;
            neighbors[offsets[source as usize] as usize] = TypedNeighbor { vertex, edge };
        }
        for bounds in offsets.windows(2) {
            neighbors[bounds[0] as usize..bounds[1] as usize].sort_unstable();
        }
        Self {
            offsets: CsrOffsets::Dense(offsets),
            neighbors,
        }
    }

    fn build_sparse(edges: &[(u32, u32, u32)], reverse: bool) -> Self {
        let mut ordered: Vec<_> = edges
            .iter()
            .map(|&(from, to, edge)| {
                if reverse {
                    (to, from, edge)
                } else {
                    (from, to, edge)
                }
            })
            .collect();
        ordered.sort_unstable();
        let mut sources = Vec::new();
        let mut offsets = Vec::new();
        let mut neighbors = Vec::with_capacity(edges.len());
        for (source, vertex, edge) in ordered {
            if sources.last() != Some(&source) {
                sources.push(source);
                offsets.push(neighbors.len() as u32);
            }
            neighbors.push(TypedNeighbor { vertex, edge });
        }
        offsets.push(neighbors.len() as u32);
        Self {
            offsets: CsrOffsets::Sparse { sources, offsets },
            neighbors,
        }
    }

    fn at(&self, vertex: u32) -> &[TypedNeighbor] {
        let (offsets, slot) = match &self.offsets {
            CsrOffsets::Dense(offsets) => (offsets, vertex as usize),
            CsrOffsets::Sparse { sources, offsets } => {
                let Ok(slot) = sources.binary_search(&vertex) else {
                    return &[];
                };
                (offsets, slot)
            }
        };
        // Never compute vertex + 1: u32::MAX must also be safe on 32-bit hosts.
        let Some(bounds) = offsets.get(slot..).and_then(|tail| tail.get(..2)) else {
            return &[];
        };
        &self.neighbors[bounds[0] as usize..bounds[1] as usize]
    }

    #[inline]
    fn sparse_sources(&self) -> Option<&[u32]> {
        match &self.offsets {
            CsrOffsets::Dense(_) => None,
            CsrOffsets::Sparse { sources, .. } => Some(sources),
        }
    }
}

#[derive(Debug)]
struct TypedAdjacency {
    forward: Csr,
    reverse: Csr,
}

/// Borrowed adjacency for one relationship type in an immutable index.
///
/// Obtain a view with [`TypedGraphIndex::adjacency`] to resolve the type once.
/// Copying the view neither allocates nor clones the graph or its `Arc`.
/// Row access performs no type hashing: dense rows use O(1) offset lookup,
/// while sparse rows use O(log(active sources)) lookup. An absent type has
/// empty rows, as do invalid vertex slots, including `u32::MAX`.
///
/// Slices retain physical edge multiplicity and are sorted by the other vertex
/// slot, then edge slot. A self-loop appears once in each direction; callers
/// combining both directions must avoid double-counting it when appropriate.
/// Sparse-source accessors borrow the CSR's sorted, unique nonempty row slots;
/// they return `None` for dense storage and `Some(&[])` for an absent type.
/// Views do not execute queries or exempt callers from read budgets.
///
/// The view and its slices borrow the index, not the relationship string, and
/// cannot outlive the index even if another owner retains the graph snapshot:
///
/// ```compile_fail
/// use grust_core::{Graph, TypedGraphIndex};
/// use std::sync::Arc;
/// let snapshot = Arc::new(Graph::default());
/// let view = {
///     let index = TypedGraphIndex::new(snapshot.clone()).unwrap();
///     index.adjacency("T")
/// };
/// assert!(view.outgoing(0).is_empty());
/// ```
#[derive(Clone, Copy, Debug)]
pub struct TypedAdjacencyView<'index> {
    adjacency: Option<&'index TypedAdjacency>,
}

impl<'index> TypedAdjacencyView<'index> {
    /// Outgoing neighbors, borrowed for the lifetime of the indexed snapshot.
    #[inline]
    pub fn outgoing(&self, vertex: u32) -> &'index [TypedNeighbor] {
        self.adjacency
            .map(|adjacency| adjacency.forward.at(vertex))
            .unwrap_or(&[])
    }

    /// Incoming neighbors, borrowed for the lifetime of the indexed snapshot.
    #[inline]
    pub fn incoming(&self, vertex: u32) -> &'index [TypedNeighbor] {
        self.adjacency
            .map(|adjacency| adjacency.reverse.at(vertex))
            .unwrap_or(&[])
    }

    /// Sorted, unique outgoing slots with nonempty rows when storage is sparse.
    ///
    /// Dense storage returns `None`, because enumerating only its nonempty rows
    /// would require a scan. An absent relationship type returns `Some(&[])`.
    #[inline]
    pub fn sparse_outgoing_sources(&self) -> Option<&'index [u32]> {
        match self.adjacency {
            Some(adjacency) => adjacency.forward.sparse_sources(),
            None => Some(&[]),
        }
    }

    /// Sorted, unique incoming slots with nonempty rows when storage is sparse.
    ///
    /// Dense storage returns `None`, because enumerating only its nonempty rows
    /// would require a scan. An absent relationship type returns `Some(&[])`.
    #[inline]
    pub fn sparse_incoming_sources(&self) -> Option<&'index [u32]> {
        match self.adjacency {
            Some(adjacency) => adjacency.reverse.sparse_sources(),
            None => Some(&[]),
        }
    }
}

/// A reusable index over an immutable graph snapshot.
///
/// The snapshot is either an owned [`Graph`] ([`TypedGraphIndex::new`]) or any
/// [`GraphSnapshotSource`] ([`TypedGraphIndex::from_source`]), such as a view
/// of a store's own frozen storage; the index shares it through an `Arc` and
/// never copies its nodes or edges. Vertex and edge slots are the source's
/// slots, the positions of its materialized graph, not property values.
/// Holding the snapshot prevents mutation from invalidating the index.
/// Construction validates endpoints (and, for an owned graph, node identities)
/// and preserves edge multiplicity. It does not execute queries or exempt them
/// from read budgets.
///
/// Read elements through the slot accessors (`node`, `edge`, `node_label`,
/// `edge_props`, ...). [`TypedGraphIndex::graph`] returns an owned `Graph`;
/// for a source that is not one, the first call materializes and keeps a full
/// copy, which is exactly the cost a borrowed source exists to avoid.
///
/// Auxiliary slot storage is O(V + E), not O(V times relationship types): a
/// nonempty type uses dense offsets only when it has at least ceil(V / 4)
/// edges, otherwise it stores sorted active sources and sparse offsets. Dense
/// source lookup is O(1); sparse lookup is O(log(active sources)). Each returned
/// neighbor slice is sorted by destination slot and then edge slot.
///
/// Construction sorts neighbors (worst-case O(V + E log E) structural work)
/// and traverses the serialized graph once to cache its exact compact JSON
/// byte length, without allocating a graph-sized encoding buffer. That cached
/// length measures the graph, not this index's allocations. Variable-length
/// identifiers, labels, and property data additionally contribute their byte
/// costs; the graph snapshot is shared with, not copied into, the index.
#[derive(Debug)]
pub struct TypedGraphIndex {
    source: Arc<dyn GraphSnapshotSource>,
    /// Owned copy for `graph()` when the source is not a `Graph`.
    materialized: OnceLock<Graph>,
    serialized_graph_bytes: OnceLock<usize>,
    vertices_by_label: HashMap<Label, Vec<u32>>,
    adjacency: HashMap<Label, TypedAdjacency>,
}

impl TypedGraphIndex {
    pub fn new(graph: Arc<Graph>) -> Result<Self> {
        Self::check_capacity(graph.nodes.len(), graph.edges.len())?;
        Self::build(Arc::new(OwnedGraphSource::new(graph)?))
    }

    /// Index a snapshot the caller already holds in its own layout, sharing
    /// it instead of copying it into a [`Graph`]. The source must uphold the
    /// [`GraphSnapshotSource`] contract, unique node ids included; dangling
    /// endpoints are rejected here as [`TypedGraphIndex::new`] rejects them.
    pub fn from_source(source: Arc<dyn GraphSnapshotSource>) -> Result<Self> {
        Self::check_capacity(source.node_count(), source.edge_count())?;
        Self::build(source)
    }

    fn check_capacity(nodes: usize, edges: usize) -> Result<()> {
        u32::try_from(nodes).map_err(|_| {
            GrustError::Schema("typed graph index exceeds u32 vertex capacity".into())
        })?;
        u32::try_from(edges).map_err(|_| {
            GrustError::Schema("typed graph index exceeds u32 edge capacity".into())
        })?;
        Ok(())
    }

    fn build(source: Arc<dyn GraphSnapshotSource>) -> Result<Self> {
        let nodes = source.node_count();
        let mut vertices_by_label: HashMap<Label, Vec<u32>> = HashMap::new();
        for vertex in 0..nodes as u32 {
            let label = source.node_label(vertex);
            match vertices_by_label.get_mut(label.as_str()) {
                Some(vertices) => vertices.push(vertex),
                None => {
                    vertices_by_label.insert(label.clone(), vec![vertex]);
                }
            }
        }
        let mut typed_edges: HashMap<Label, Vec<(u32, u32, u32)>> = HashMap::new();
        for edge in 0..source.edge_count() as u32 {
            let (from, to) = source.edge_endpoints(edge)?;
            let label = source.edge_label(edge);
            match typed_edges.get_mut(label.as_str()) {
                Some(edges) => edges.push((from, to, edge)),
                None => {
                    typed_edges.insert(label.clone(), vec![(from, to, edge)]);
                }
            }
        }
        let mut adjacency = HashMap::with_capacity(typed_edges.len());
        for (label, edges) in typed_edges {
            let forward = Csr::build(nodes, &edges, false);
            let reverse = Csr::build(nodes, &edges, true);
            // Free each type's scratch triples before building the next.
            drop(edges);
            adjacency.insert(label, TypedAdjacency { forward, reverse });
        }
        Ok(Self {
            source,
            materialized: OnceLock::new(),
            serialized_graph_bytes: OnceLock::new(),
            vertices_by_label,
            adjacency,
        })
    }

    /// The snapshot as an owned [`Graph`].
    ///
    /// Free for an index built by [`TypedGraphIndex::new`]. For any other
    /// source the first call materializes a full copy and keeps it for the
    /// index's lifetime; query paths read through the slot accessors instead.
    pub fn graph(&self) -> &Graph {
        match self.source.as_graph() {
            Some(graph) => graph,
            None => self.materialized.get_or_init(|| self.source.materialize()),
        }
    }

    /// The snapshot this index reads.
    pub fn source(&self) -> &dyn GraphSnapshotSource {
        self.source.as_ref()
    }

    pub fn node_count(&self) -> usize {
        self.source.node_count()
    }

    pub fn edge_count(&self) -> usize {
        self.source.edge_count()
    }

    /// The node in `vertex`'s slot; built on demand by a borrowed source.
    #[inline]
    pub fn node(&self, vertex: u32) -> Cow<'_, Node> {
        self.source.node(vertex)
    }

    #[inline]
    pub fn node_id(&self, vertex: u32) -> &NodeId {
        self.source.node_id(vertex)
    }

    #[inline]
    pub fn node_label(&self, vertex: u32) -> &Label {
        self.source.node_label(vertex)
    }

    #[inline]
    pub fn node_property(&self, vertex: u32, key: &str) -> Option<Cow<'_, Value>> {
        self.source.node_property(vertex, key)
    }

    /// The edge in slot `edge`; built on demand by a borrowed source.
    #[inline]
    pub fn edge(&self, edge: u32) -> Cow<'_, Edge> {
        self.source.edge(edge)
    }

    #[inline]
    pub fn edge_label(&self, edge: u32) -> &Label {
        self.source.edge_label(edge)
    }

    #[inline]
    pub fn edge_props(&self, edge: u32) -> &Props {
        self.source.edge_props(edge)
    }

    /// Exact compact JSON byte length of this immutable graph snapshot.
    ///
    /// Measured on first use through a counting writer, never with a
    /// graph-sized buffer, and cached for every later bounded reader. Plain
    /// traversals that never ask for it never pay for the measurement. A
    /// borrowed source is measured element by element, one element built at
    /// a time, never through `graph()`.
    pub fn serialized_graph_bytes(&self) -> usize {
        *self.serialized_graph_bytes.get_or_init(|| {
            let mut size = SerializedSize(0);
            match self.source.as_graph() {
                Some(graph) => size.measure(graph),
                None => self.measure_elements(&mut size),
            }
            size.0
        })
    }

    /// `{"nodes":[n,...],"edges":[e,...]}`, the derived `Graph` encoding,
    /// counted one element at a time.
    fn measure_elements(&self, size: &mut SerializedSize) {
        fn list<T: serde::Serialize>(
            size: &mut SerializedSize,
            count: usize,
            element: impl Fn(u32) -> T,
        ) {
            for slot in 0..count as u32 {
                if slot > 0 {
                    size.add(1);
                }
                size.measure(&element(slot));
            }
        }
        size.add(r#"{"nodes":["#.len());
        list(size, self.node_count(), |slot| self.node(slot));
        size.add(r#"],"edges":["#.len());
        list(size, self.edge_count(), |slot| self.edge(slot));
        size.add(r#"]}"#.len());
    }

    /// Every relationship type with at least one edge, in sorted order, so
    /// callers that walk all types produce the same neighbour order as the
    /// label-ordered edge maps they replace.
    pub fn relationship_types(&self) -> impl Iterator<Item = &Label> {
        let mut types: Vec<&Label> = self.adjacency.keys().collect();
        types.sort();
        types.into_iter()
    }

    pub fn vertex_index(&self, id: &str) -> Option<u32> {
        self.source.vertex_index(id)
    }

    pub fn vertices_with_label(&self, label: &str) -> &[u32] {
        self.vertices_by_label
            .get(label)
            .map(Vec::as_slice)
            .unwrap_or(&[])
    }

    /// Resolve a relationship type once without allocating or copying its name.
    ///
    /// The returned view borrows this index, not `relationship`. Missing types
    /// return an empty view with the same vertex-slot behavior as existing
    /// string-based adjacency methods.
    pub fn adjacency(&self, relationship: &str) -> TypedAdjacencyView<'_> {
        TypedAdjacencyView {
            adjacency: self.adjacency.get(relationship),
        }
    }

    pub fn outgoing(&self, vertex: u32, relationship: &str) -> &[TypedNeighbor] {
        self.adjacency(relationship).outgoing(vertex)
    }

    pub fn incoming(&self, vertex: u32, relationship: &str) -> &[TypedNeighbor] {
        self.adjacency(relationship).incoming(vertex)
    }

    pub fn has_relationship(&self, from: u32, to: u32, relationship: &str) -> bool {
        self.outgoing(from, relationship)
            .binary_search_by_key(&to, |n| n.vertex)
            .is_ok()
    }
}

struct SerializedSize(usize);

impl SerializedSize {
    fn add(&mut self, bytes: usize) {
        self.0 = self
            .0
            .checked_add(bytes)
            .expect("serialized graph size exceeds usize");
    }

    /// Add `value`'s compact JSON length: counted directly, or through the
    /// `serde_json` writer for an encoding the counter does not model.
    fn measure<T: serde::Serialize + ?Sized>(&mut self, value: &T) {
        match crate::json_byte_len(value) {
            Some(bytes) => self.add(bytes),
            None => serde_json::to_writer(&mut *self, value)
                .expect("measuring through a counting writer cannot fail"),
        }
    }
}

impl io::Write for SerializedSize {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        self.0 = self
            .0
            .checked_add(bytes.len())
            .ok_or_else(|| io::Error::other("serialized graph size exceeds usize"))?;
        Ok(bytes.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

#[cfg(test)]
#[path = "typed_graph_index_tests.rs"]
mod tests;

#[cfg(test)]
#[path = "typed_adjacency_view_tests.rs"]
mod view_tests;

#[cfg(test)]
#[path = "typed_adjacency_sparse_sources_tests.rs"]
mod sparse_source_tests;
