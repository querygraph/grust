//! Slot-addressed element access to an immutable graph snapshot.
//!
//! A [`TypedGraphIndex`](crate::TypedGraphIndex) reads its graph through this
//! trait instead of owning a [`Graph`], so a store can hand the index a view of
//! its own frozen storage and no second copy of every node and edge exists.
//! [`Graph`] itself is one source; a store with a compact layout is another.

use std::{borrow::Cow, collections::HashMap, fmt, sync::Arc};

use crate::{Edge, Graph, GrustError, Label, Node, NodeId, Props, Result, Value};

/// Read access to an immutable graph snapshot by node and edge slot.
///
/// Node slots `0..node_count()` and edge slots `0..edge_count()` are the
/// positions the snapshot's nodes and edges hold in [`materialize`]'s
/// [`Graph`], so every slot-ordered walk visits elements in the order a walk of
/// that graph would. Answers never change for the lifetime of the source:
/// holders rely on it as a snapshot. Node ids are unique.
///
/// Accessors that return [`Cow`] let a source build an element on demand
/// rather than keep an owned copy of each; the scalar accessors (`node_id`,
/// `node_label`, `edge_label`, `edge_props`, `node_property`) never build a
/// whole element. Out-of-range slots may panic.
///
/// [`materialize`]: GraphSnapshotSource::materialize
pub trait GraphSnapshotSource: Send + Sync + fmt::Debug {
    fn node_count(&self) -> usize;
    fn edge_count(&self) -> usize;
    fn node(&self, slot: u32) -> Cow<'_, Node>;
    fn node_id(&self, slot: u32) -> &NodeId;
    fn node_label(&self, slot: u32) -> &Label;
    /// The node's property `key`, as `node(slot).props.get(key)` would return it.
    fn node_property(&self, slot: u32, key: &str) -> Option<Cow<'_, Value>>;
    fn edge(&self, slot: u32) -> Cow<'_, Edge>;
    fn edge_label(&self, slot: u32) -> &Label;
    fn edge_props(&self, slot: u32) -> &Props;
    /// Node slots of the edge's source and destination, or a schema error
    /// naming the endpoint that is not a node of the snapshot.
    fn edge_endpoints(&self, slot: u32) -> Result<(u32, u32)>;
    /// The slot of the node with this id.
    fn vertex_index(&self, id: &str) -> Option<u32>;

    /// The snapshot as an owned [`Graph`] when the source already holds one.
    fn as_graph(&self) -> Option<&Graph> {
        None
    }

    /// A full owned copy of the snapshot, nodes and edges in slot order.
    fn materialize(&self) -> Graph {
        if let Some(graph) = self.as_graph() {
            return graph.clone();
        }
        let nodes = (0..self.node_count() as u32)
            .map(|slot| self.node(slot).into_owned())
            .collect();
        let edges = (0..self.edge_count() as u32)
            .map(|slot| self.edge(slot).into_owned())
            .collect();
        Graph::new(nodes, edges)
    }
}

pub(crate) fn missing_source(id: &NodeId) -> GrustError {
    GrustError::Schema(format!("edge source '{id}' is not present in vertices"))
}

pub(crate) fn missing_destination(id: &NodeId) -> GrustError {
    GrustError::Schema(format!(
        "edge destination '{id}' is not present in vertices"
    ))
}

/// An owned [`Graph`] as a snapshot source: slots are vector positions.
#[derive(Debug)]
pub(crate) struct OwnedGraphSource {
    graph: Arc<Graph>,
    vertex_by_id: HashMap<NodeId, u32>,
}

impl OwnedGraphSource {
    /// Index node ids, rejecting a graph that repeats one. The caller has
    /// checked that slots fit in `u32`.
    pub(crate) fn new(graph: Arc<Graph>) -> Result<Self> {
        let mut vertex_by_id = HashMap::with_capacity(graph.nodes.len());
        for (vertex, node) in graph.nodes.iter().enumerate() {
            if vertex_by_id
                .insert(node.id.clone(), vertex as u32)
                .is_some()
            {
                return Err(GrustError::Schema(format!(
                    "duplicate vertex id '{}'",
                    node.id
                )));
            }
        }
        Ok(Self {
            graph,
            vertex_by_id,
        })
    }
}

impl GraphSnapshotSource for OwnedGraphSource {
    fn node_count(&self) -> usize {
        self.graph.nodes.len()
    }

    fn edge_count(&self) -> usize {
        self.graph.edges.len()
    }

    fn node(&self, slot: u32) -> Cow<'_, Node> {
        Cow::Borrowed(&self.graph.nodes[slot as usize])
    }

    fn node_id(&self, slot: u32) -> &NodeId {
        &self.graph.nodes[slot as usize].id
    }

    fn node_label(&self, slot: u32) -> &Label {
        &self.graph.nodes[slot as usize].label
    }

    fn node_property(&self, slot: u32, key: &str) -> Option<Cow<'_, Value>> {
        self.graph.nodes[slot as usize]
            .props
            .get(key)
            .map(Cow::Borrowed)
    }

    fn edge(&self, slot: u32) -> Cow<'_, Edge> {
        Cow::Borrowed(&self.graph.edges[slot as usize])
    }

    fn edge_label(&self, slot: u32) -> &Label {
        &self.graph.edges[slot as usize].label
    }

    fn edge_props(&self, slot: u32) -> &Props {
        &self.graph.edges[slot as usize].props
    }

    fn edge_endpoints(&self, slot: u32) -> Result<(u32, u32)> {
        let edge = &self.graph.edges[slot as usize];
        let from = self
            .vertex_index(edge.from.as_str())
            .ok_or_else(|| missing_source(&edge.from))?;
        let to = self
            .vertex_index(edge.to.as_str())
            .ok_or_else(|| missing_destination(&edge.to))?;
        Ok((from, to))
    }

    fn vertex_index(&self, id: &str) -> Option<u32> {
        self.vertex_by_id.get(id).copied()
    }

    fn as_graph(&self) -> Option<&Graph> {
        Some(&self.graph)
    }
}
