//! The store's own storage as the snapshot a `TypedGraphIndex` reads.
//!
//! `indexed_snapshot` used to copy every stored node and edge into an owned
//! `Graph` and index that copy, so the read path held the graph twice. A
//! `StoreSnapshot` instead shares the frozen `MemoryGraph` through the store's
//! copy-on-write `Arc` and adds only three `u32` permutations that give its
//! nodes and edges the slot order `graph_snapshot` would: nodes by id, edges by
//! edge key. Elements are built on demand, one at a time, when a reader asks
//! for a whole node or edge; ids, labels and edge properties are borrowed.

use grust_core::GraphSnapshotSource;

use super::*;

pub(super) struct StoreSnapshot {
    graph: Arc<MemoryGraph>,
    /// Node slot -> vertex handle.
    nodes: Vec<Handle>,
    /// Vertex handle -> node slot; `NONE` for a vertex with no stored node.
    slots: Vec<u32>,
    /// Edge slot -> stored edge slot.
    edges: Vec<Handle>,
}

impl StoreSnapshot {
    pub(super) fn new(graph: Arc<MemoryGraph>) -> Self {
        let nodes = graph.sorted_nodes_where(|_| true);
        let mut slots = vec![NONE; graph.vertices.len()];
        for (slot, &vertex) in nodes.iter().enumerate() {
            slots[vertex as usize] = slot as u32;
        }
        let edges = graph.sorted_edge_slots();
        Self {
            graph,
            nodes,
            slots,
            edges,
        }
    }

    fn handle(&self, slot: u32) -> Handle {
        self.nodes[slot as usize]
    }

    fn node_ref(&self, slot: u32) -> NodeRef<'_> {
        self.graph
            .node_ref(self.handle(slot))
            .expect("snapshot slots name stored nodes")
    }

    fn stored_edge(&self, slot: u32) -> Handle {
        self.edges[slot as usize]
    }

    /// The node slot of an edge endpoint, or the error `TypedGraphIndex::new`
    /// gives for an endpoint that is not a stored node.
    fn endpoint(&self, vertex: Handle, what: &str) -> Result<u32> {
        match self.slots[vertex as usize] {
            NONE => Err(GrustError::Schema(format!(
                "edge {what} '{}' is not present in vertices",
                self.graph.vertices[vertex as usize].id
            ))),
            slot => Ok(slot),
        }
    }
}

impl fmt::Debug for StoreSnapshot {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("StoreSnapshot")
            .field("nodes", &self.nodes.len())
            .field("edges", &self.edges.len())
            .finish_non_exhaustive()
    }
}

impl GraphSnapshotSource for StoreSnapshot {
    fn node_count(&self) -> usize {
        self.nodes.len()
    }

    fn edge_count(&self) -> usize {
        self.edges.len()
    }

    fn node(&self, slot: u32) -> Cow<'_, Node> {
        Cow::Owned(self.node_ref(slot).to_node())
    }

    fn node_id(&self, slot: u32) -> &NodeId {
        &self.graph.vertices[self.handle(slot) as usize].id
    }

    fn node_label(&self, slot: u32) -> &Label {
        self.node_ref(slot).label
    }

    fn node_property(&self, slot: u32, key: &str) -> Option<Cow<'_, Value>> {
        self.node_ref(slot).prop(key)
    }

    fn edge(&self, slot: u32) -> Cow<'_, Edge> {
        Cow::Owned(self.graph.edge(self.stored_edge(slot)))
    }

    fn edge_label(&self, slot: u32) -> &Label {
        self.graph.edge_label(self.stored_edge(slot))
    }

    fn edge_props(&self, slot: u32) -> &Props {
        self.graph.edge_props(self.stored_edge(slot))
    }

    fn edge_endpoints(&self, slot: u32) -> Result<(u32, u32)> {
        let rec = self.graph.edges[self.stored_edge(slot) as usize];
        Ok((
            self.endpoint(rec.from, "source")?,
            self.endpoint(rec.to, "destination")?,
        ))
    }

    fn vertex_index(&self, id: &str) -> Option<u32> {
        self.graph
            .vertex_str(id)
            .map(|vertex| self.slots[vertex as usize])
            .filter(|&slot| slot != NONE)
    }
}
