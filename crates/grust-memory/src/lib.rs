use std::{
    borrow::Cow,
    cmp::Ordering,
    collections::{BTreeMap, HashMap},
    fmt,
    hash::BuildHasher,
    sync::{Arc, Mutex, RwLock},
};

use async_trait::async_trait;
use grust_core::{TypedGraphIndex, TypedNeighbor, UniqueValueIndex, prelude::*};
use hashbrown::{DefaultHashBuilder, HashTable, hash_table::Entry};

mod indexed_reads;
mod indexed_snapshot;
mod snapshot_source;

type UniqueValueIndexes<Owner> = BTreeMap<Label, BTreeMap<String, UniqueValueIndex<Owner, Value>>>;

/// Index of an interned node id (a vertex), a label, a stored edge, or an
/// edge's out-of-line id and properties.
type Handle = u32;

/// The absent handle: a vertex with no stored node, a free edge slot, an edge
/// with no id and no properties.
const NONE: Handle = Handle::MAX;

static EMPTY_PROPS: Props = Props::new();

#[derive(Clone, Debug, Default)]
pub struct MemoryGraphStore {
    /// The graph, shared copy-on-write with the snapshots indexed from it:
    /// a write clones it only while a caller still holds such a snapshot.
    inner: Arc<RwLock<Arc<MemoryGraph>>>,
    index_cache: Arc<Mutex<Option<Arc<TypedGraphIndex>>>>,
}

/// The stored graph, laid out for footprint.
///
/// Every node id that names a stored node or an edge endpoint is interned
/// once as a vertex, and every node and edge label once in `labels`; edges
/// refer to both by `u32` handle. An edge is one 16-byte `EdgeRec`, listed by
/// slot in its source's outgoing and its target's incoming adjacency, and
/// found by key through `edge_index`. Its id and properties live out of line
/// in `edge_extras` and cost nothing when it has neither.
///
/// Edge identity is the key `(from, label, to, id)`: edges with distinct ids
/// between the same endpoints are all kept, an edge without an id replaces the
/// earlier id-less edge with the same `(from, label, to)`, and re-putting a key
/// updates its properties in place.
///
/// Storage order is insertion order; every read that returns several nodes
/// or edges sorts them by node id or by edge key, the order of the ordered
/// maps this layout replaced.
#[derive(Clone, Default)]
struct MemoryGraph {
    vertices: Vec<Vertex>,
    /// Vertex handles, hashed by id.
    vertex_index: HashTable<Handle>,
    labels: Vec<Label>,
    label_index: HashMap<Label, Handle>,
    edges: Vec<EdgeRec>,
    free_edges: Vec<Handle>,
    edge_extras: Vec<EdgeExtra>,
    free_extras: Vec<Handle>,
    /// Live edge slots, hashed by key.
    edge_index: HashTable<Handle>,
    hasher: DefaultHashBuilder,
    node_count: usize,
    edge_count: usize,
    node_unique_values: UniqueValueIndexes<NodeId>,
    edge_unique_values: UniqueValueIndexes<Handle>,
    schema: Option<GraphSchema>,
    native_constraints: Vec<GraphConstraint>,
}

impl fmt::Debug for MemoryGraph {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("MemoryGraph")
            .field("nodes", &self.node_count)
            .field("edges", &self.edge_count)
            .field("vertices", &self.vertices.len())
            .field("labels", &self.labels)
            .field("schema", &self.schema)
            .field("native_constraints", &self.native_constraints)
            .finish_non_exhaustive()
    }
}

#[derive(Clone, Debug)]
struct Vertex {
    id: NodeId,
    /// Label of the stored node; `NONE` while no node with this id is stored
    /// and the vertex exists only as an edge endpoint.
    label: Handle,
    /// The stored node's `id` property is a string equal to its id. It is
    /// kept implicitly rather than in `props`, so a node whose only property
    /// is the one `Node::new` adds allocates no property map.
    id_prop: bool,
    props: Option<Box<Props>>,
    outgoing: Vec<Handle>,
    incoming: Vec<Handle>,
}

#[derive(Clone, Copy, Debug)]
struct EdgeRec {
    /// `NONE` marks a free slot.
    from: Handle,
    label: Handle,
    to: Handle,
    /// Slot in `edge_extras`, `NONE` for an edge with no id and no properties.
    extra: Handle,
}

#[derive(Clone, Debug, Default)]
struct EdgeExtra {
    id: Option<EdgeId>,
    props: Props,
}

/// A stored node, borrowed from the graph.
#[derive(Clone, Copy)]
struct NodeRef<'a> {
    id: &'a NodeId,
    label: &'a Label,
    id_prop: bool,
    props: &'a Props,
}

impl<'a> NodeRef<'a> {
    fn prop(&self, key: &str) -> Option<Cow<'a, Value>> {
        if let Some(value) = self.props.get(key) {
            return Some(Cow::Borrowed(value));
        }
        (self.id_prop && key == "id").then(|| Cow::Owned(Value::String(self.id.as_str().into())))
    }

    fn has_prop(&self, key: &str) -> bool {
        self.props.contains_key(key) || (self.id_prop && key == "id")
    }

    fn to_node(self) -> Node {
        let mut props = self.props.clone();
        if self.id_prop {
            props.insert("id".to_string(), Value::String(self.id.as_str().into()));
        }
        Node {
            id: self.id.clone(),
            label: self.label.clone(),
            props,
        }
    }
}

/// Owned edge key, ordered as reads return edges.
#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd)]
struct MemoryEdgeKey {
    from: NodeId,
    label: Label,
    to: NodeId,
    id: Option<EdgeId>,
}

impl MemoryEdgeKey {
    fn from_edge(edge: &Edge) -> Self {
        Self {
            from: edge.from.clone(),
            label: edge.label.clone(),
            to: edge.to.clone(),
            id: edge.id.clone(),
        }
    }
}

/// Split a node's properties into the implicit `id` flag and the rest.
fn pack_node_props(id: &NodeId, props: &Props) -> (bool, Option<Box<Props>>) {
    let id_prop = matches!(props.get("id"), Some(Value::String(value)) if value == id.as_str());
    if props.len() == usize::from(id_prop) {
        return (id_prop, None);
    }
    let mut stored = props.clone();
    if id_prop {
        stored.remove("id");
    }
    (id_prop, Some(Box::new(stored)))
}

fn to_handle(len: usize) -> Handle {
    Handle::try_from(len)
        .ok()
        .filter(|&handle| handle != NONE)
        .expect("memory graph exceeds u32 handle capacity")
}

impl MemoryGraph {
    // ---- vertices and labels ------------------------------------------------

    fn vertex(&self, id: &NodeId) -> Option<Handle> {
        self.vertex_str(id.as_str())
    }

    fn vertex_str(&self, id: &str) -> Option<Handle> {
        let hash = self.hasher.hash_one(id);
        self.vertex_index
            .find(hash, |&h| self.vertices[h as usize].id.as_str() == id)
            .copied()
    }

    fn intern_vertex(&mut self, id: &NodeId) -> Handle {
        let hash = self.hasher.hash_one(id.as_str());
        let Self {
            vertices,
            vertex_index,
            hasher,
            ..
        } = self;
        match vertex_index.entry(
            hash,
            |&h| vertices[h as usize].id == *id,
            |&h| hasher.hash_one(vertices[h as usize].id.as_str()),
        ) {
            Entry::Occupied(entry) => *entry.get(),
            Entry::Vacant(entry) => {
                let handle = to_handle(vertices.len());
                entry.insert(handle);
                vertices.push(Vertex {
                    id: id.clone(),
                    label: NONE,
                    id_prop: false,
                    props: None,
                    outgoing: Vec::new(),
                    incoming: Vec::new(),
                });
                handle
            }
        }
    }

    fn label(&self, label: &Label) -> Option<Handle> {
        self.label_index.get(label).copied()
    }

    fn intern_label(&mut self, label: &Label) -> Handle {
        if let Some(&handle) = self.label_index.get(label) {
            return handle;
        }
        let handle = to_handle(self.labels.len());
        self.labels.push(label.clone());
        self.label_index.insert(label.clone(), handle);
        handle
    }

    // ---- nodes ---------------------------------------------------------------

    fn node_ref(&self, vertex: Handle) -> Option<NodeRef<'_>> {
        let v = &self.vertices[vertex as usize];
        (v.label != NONE).then(|| NodeRef {
            id: &v.id,
            label: &self.labels[v.label as usize],
            id_prop: v.id_prop,
            props: v.props.as_deref().unwrap_or(&EMPTY_PROPS),
        })
    }

    fn find_node(&self, id: &NodeId) -> Option<NodeRef<'_>> {
        self.vertex(id).and_then(|vertex| self.node_ref(vertex))
    }

    fn node_label(&self, id: &NodeId) -> Option<&Label> {
        self.find_node(id).map(|node| node.label)
    }

    fn node_handles(&self) -> impl Iterator<Item = Handle> + '_ {
        self.vertices
            .iter()
            .enumerate()
            .filter(|(_, v)| v.label != NONE)
            .map(|(h, _)| h as Handle)
    }

    /// Stored nodes accepted by `keep`, in node-id order.
    fn sorted_nodes_where(&self, keep: impl Fn(&NodeRef<'_>) -> bool) -> Vec<Handle> {
        let mut handles = self
            .node_handles()
            .filter(|&h| self.node_ref(h).is_some_and(|node| keep(&node)))
            .collect::<Vec<_>>();
        handles.sort_unstable_by(|&a, &b| {
            self.vertices[a as usize]
                .id
                .cmp(&self.vertices[b as usize].id)
        });
        handles
    }

    fn store_node(&mut self, node: &Node) -> bool {
        let vertex = self.intern_vertex(&node.id);
        let label = self.intern_label(&node.label);
        let (id_prop, props) = pack_node_props(&node.id, &node.props);
        let v = &mut self.vertices[vertex as usize];
        let existed = v.label != NONE;
        v.label = label;
        v.id_prop = id_prop;
        v.props = props;
        if !existed {
            self.node_count += 1;
        }
        existed
    }

    fn index_node_unique_values(indexes: &mut UniqueValueIndexes<NodeId>, node: &Node) {
        let Some(properties) = indexes.get_mut(&node.label) else {
            return;
        };
        for (key, values) in properties {
            if let Some(value) = node.props.get(key) {
                values.insert(node.id.clone(), value.clone());
            }
        }
    }

    fn remove_node_unique_values(indexes: &mut UniqueValueIndexes<NodeId>, node: &Node) {
        let Some(properties) = indexes.get_mut(&node.label) else {
            return;
        };
        for (key, values) in properties {
            if let Some(value) = node.props.get(key) {
                values.remove(&node.id, value);
            }
        }
    }

    /// Insert or replace `node`; true when a node with its id was stored.
    fn upsert_node(&mut self, node: &Node) -> bool {
        if self.node_unique_values.is_empty() {
            return self.store_node(node);
        }
        let previous = self.find_node(&node.id).map(NodeRef::to_node);
        Self::index_node_unique_values(&mut self.node_unique_values, node);
        self.store_node(node);
        if let Some(existing) = &previous {
            Self::remove_node_unique_values(&mut self.node_unique_values, existing);
        }
        previous.is_some()
    }

    fn upsert_nodes(&mut self, nodes: &[Node]) {
        for node in nodes {
            self.upsert_node(node);
        }
    }

    /// Remove the node, leaving its incident edges; true when one was stored.
    fn remove_node(&mut self, id: &NodeId) -> bool {
        let Some(vertex) = self.vertex(id) else {
            return false;
        };
        let Some(node) = self.node_ref(vertex) else {
            return false;
        };
        if !self.node_unique_values.is_empty() {
            let removed = node.to_node();
            Self::remove_node_unique_values(&mut self.node_unique_values, &removed);
        }
        let v = &mut self.vertices[vertex as usize];
        v.label = NONE;
        v.id_prop = false;
        v.props = None;
        self.node_count -= 1;
        true
    }

    // ---- edges ---------------------------------------------------------------

    fn edge_id(&self, slot: Handle) -> Option<&str> {
        let extra = self.edges[slot as usize].extra;
        if extra == NONE {
            None
        } else {
            self.edge_extras[extra as usize]
                .id
                .as_ref()
                .map(EdgeId::as_str)
        }
    }

    fn edge_props(&self, slot: Handle) -> &Props {
        let extra = self.edges[slot as usize].extra;
        if extra == NONE {
            &EMPTY_PROPS
        } else {
            &self.edge_extras[extra as usize].props
        }
    }

    fn edge_label(&self, slot: Handle) -> &Label {
        &self.labels[self.edges[slot as usize].label as usize]
    }

    fn edge(&self, slot: Handle) -> Edge {
        let rec = self.edges[slot as usize];
        let (id, props) = if rec.extra == NONE {
            (None, Props::new())
        } else {
            let extra = &self.edge_extras[rec.extra as usize];
            (extra.id.clone(), extra.props.clone())
        };
        Edge {
            id,
            from: self.vertices[rec.from as usize].id.clone(),
            to: self.vertices[rec.to as usize].id.clone(),
            label: self.labels[rec.label as usize].clone(),
            props,
        }
    }

    fn edge_handles(&self) -> impl Iterator<Item = Handle> + '_ {
        self.edges
            .iter()
            .enumerate()
            .filter(|(_, rec)| rec.from != NONE)
            .map(|(slot, _)| slot as Handle)
    }

    fn key_hash(hasher: &DefaultHashBuilder, rec: EdgeRec, id: Option<&str>) -> u64 {
        hasher.hash_one((rec.from, rec.label, rec.to, id))
    }

    fn slot_hash(&self, slot: Handle) -> u64 {
        Self::key_hash(&self.hasher, self.edges[slot as usize], self.edge_id(slot))
    }

    fn key_matches(&self, slot: Handle, key: EdgeRec, id: Option<&str>) -> bool {
        let rec = self.edges[slot as usize];
        rec.from == key.from
            && rec.label == key.label
            && rec.to == key.to
            && self.edge_id(slot) == id
    }

    fn find_edge(&self, key: EdgeRec, id: Option<&str>) -> Option<Handle> {
        let hash = Self::key_hash(&self.hasher, key, id);
        self.edge_index
            .find(hash, |&slot| self.key_matches(slot, key, id))
            .copied()
    }

    /// The slot storing an edge with `edge`'s key, if any.
    fn lookup_edge(&self, edge: &Edge) -> Option<Handle> {
        let key = EdgeRec {
            from: self.vertex(&edge.from)?,
            label: self.label(&edge.label)?,
            to: self.vertex(&edge.to)?,
            extra: NONE,
        };
        self.find_edge(key, edge.id.as_ref().map(EdgeId::as_str))
    }

    fn alloc_extra(&mut self, extra: EdgeExtra) -> Handle {
        if let Some(slot) = self.free_extras.pop() {
            self.edge_extras[slot as usize] = extra;
            slot
        } else {
            let slot = to_handle(self.edge_extras.len());
            self.edge_extras.push(extra);
            slot
        }
    }

    fn free_extra(&mut self, slot: Handle) {
        self.edge_extras[slot as usize] = EdgeExtra::default();
        self.free_extras.push(slot);
    }

    fn set_edge_props(&mut self, slot: Handle, props: &Props) {
        let extra = self.edges[slot as usize].extra;
        if extra == NONE {
            if !props.is_empty() {
                let extra = self.alloc_extra(EdgeExtra {
                    id: None,
                    props: props.clone(),
                });
                self.edges[slot as usize].extra = extra;
            }
            return;
        }
        let stored = &mut self.edge_extras[extra as usize];
        stored.props.clone_from(props);
        if stored.id.is_none() && stored.props.is_empty() {
            self.free_extra(extra);
            self.edges[slot as usize].extra = NONE;
        }
    }

    /// Insert `edge` or update the stored edge with its key; returns the slot
    /// and whether an edge with that key was stored.
    fn store_edge(&mut self, edge: &Edge) -> (Handle, bool) {
        let from = self.intern_vertex(&edge.from);
        let to = self.intern_vertex(&edge.to);
        let label = self.intern_label(&edge.label);
        let id = edge.id.as_ref().map(EdgeId::as_str);
        let key = EdgeRec {
            from,
            label,
            to,
            extra: NONE,
        };
        let hash = Self::key_hash(&self.hasher, key, id);
        if let Some(&slot) = self
            .edge_index
            .find(hash, |&slot| self.key_matches(slot, key, id))
        {
            self.set_edge_props(slot, &edge.props);
            return (slot, true);
        }

        let extra = if edge.id.is_some() || !edge.props.is_empty() {
            self.alloc_extra(EdgeExtra {
                id: edge.id.clone(),
                props: edge.props.clone(),
            })
        } else {
            NONE
        };
        let rec = EdgeRec { extra, ..key };
        let slot = if let Some(slot) = self.free_edges.pop() {
            self.edges[slot as usize] = rec;
            slot
        } else {
            let slot = to_handle(self.edges.len());
            self.edges.push(rec);
            slot
        };
        self.vertices[from as usize].outgoing.push(slot);
        self.vertices[to as usize].incoming.push(slot);
        let Self {
            edge_index,
            edges,
            edge_extras,
            hasher,
            ..
        } = self;
        edge_index.insert_unique(hash, slot, |&other| {
            let rec = edges[other as usize];
            let id = (rec.extra != NONE)
                .then(|| edge_extras[rec.extra as usize].id.as_ref())
                .flatten()
                .map(EdgeId::as_str);
            Self::key_hash(hasher, rec, id)
        });
        self.edge_count += 1;
        (slot, false)
    }

    fn index_edge_unique_values(
        indexes: &mut UniqueValueIndexes<Handle>,
        owner: Handle,
        label: &Label,
        props: &Props,
    ) {
        let Some(properties) = indexes.get_mut(label) else {
            return;
        };
        for (key, values) in properties {
            if let Some(value) = props.get(key) {
                values.insert(owner, value.clone());
            }
        }
    }

    fn remove_edge_unique_values(
        indexes: &mut UniqueValueIndexes<Handle>,
        owner: Handle,
        label: &Label,
        props: &Props,
    ) {
        let Some(properties) = indexes.get_mut(label) else {
            return;
        };
        for (key, values) in properties {
            if let Some(value) = props.get(key) {
                values.remove(&owner, value);
            }
        }
    }

    /// Insert or update `edge`; true when an edge with its key was stored.
    fn upsert_edge(&mut self, edge: &Edge) -> bool {
        if self.edge_unique_values.is_empty() {
            return self.store_edge(edge).1;
        }
        let previous = self
            .lookup_edge(edge)
            .map(|slot| self.edge_props(slot).clone());
        let (slot, existed) = self.store_edge(edge);
        if let Some(previous) = &previous {
            Self::remove_edge_unique_values(
                &mut self.edge_unique_values,
                slot,
                &edge.label,
                previous,
            );
        }
        Self::index_edge_unique_values(
            &mut self.edge_unique_values,
            slot,
            &edge.label,
            &edge.props,
        );
        existed
    }

    fn upsert_edges(&mut self, edges: &[Edge]) {
        for edge in edges {
            self.upsert_edge(edge);
        }
    }

    fn remove_edge_slot(&mut self, slot: Handle) {
        let rec = self.edges[slot as usize];
        if rec.from == NONE {
            return;
        }
        if !self.edge_unique_values.is_empty() {
            let props = if rec.extra == NONE {
                &EMPTY_PROPS
            } else {
                &self.edge_extras[rec.extra as usize].props
            };
            Self::remove_edge_unique_values(
                &mut self.edge_unique_values,
                slot,
                &self.labels[rec.label as usize],
                props,
            );
        }
        let hash = self.slot_hash(slot);
        if let Ok(entry) = self.edge_index.find_entry(hash, |&other| other == slot) {
            entry.remove();
        }
        let remove_from = |list: &mut Vec<Handle>| {
            if let Some(position) = list.iter().position(|&other| other == slot) {
                list.swap_remove(position);
            }
        };
        remove_from(&mut self.vertices[rec.from as usize].outgoing);
        remove_from(&mut self.vertices[rec.to as usize].incoming);
        if rec.extra != NONE {
            self.free_extra(rec.extra);
        }
        self.edges[slot as usize] = EdgeRec {
            from: NONE,
            label: NONE,
            to: NONE,
            extra: NONE,
        };
        self.free_edges.push(slot);
        self.edge_count -= 1;
    }

    /// Edges leaving or entering `id`, each once, in edge-key order.
    fn incident_edge_slots(&self, id: &NodeId) -> Vec<Handle> {
        let Some(vertex) = self.vertex(id) else {
            return Vec::new();
        };
        let v = &self.vertices[vertex as usize];
        let mut slots = v
            .outgoing
            .iter()
            .chain(&v.incoming)
            .copied()
            .collect::<Vec<_>>();
        self.sort_edge_slots(&mut slots);
        slots.dedup();
        slots
    }

    fn remove_incident_edges(&mut self, id: &NodeId) -> usize {
        let slots = self.incident_edge_slots(id);
        for &slot in &slots {
            self.remove_edge_slot(slot);
        }
        slots.len()
    }

    fn remove_edges_between(&mut self, from: &NodeId, label: &Label, to: &NodeId) -> usize {
        let (Some(from), Some(label), Some(to)) =
            (self.vertex(from), self.label(label), self.vertex(to))
        else {
            return 0;
        };
        let slots = self.vertices[from as usize]
            .outgoing
            .iter()
            .copied()
            .filter(|&slot| {
                let rec = self.edges[slot as usize];
                rec.label == label && rec.to == to
            })
            .collect::<Vec<_>>();
        for &slot in &slots {
            self.remove_edge_slot(slot);
        }
        slots.len()
    }

    fn has_conflicting_edge(&self, candidate: &Edge, directed: bool) -> bool {
        let (Some(from), Some(label), Some(to)) = (
            self.vertex(&candidate.from),
            self.label(&candidate.label),
            self.vertex(&candidate.to),
        ) else {
            // An endpoint or the label is unknown, so no stored edge joins
            // the endpoints with this label.
            return false;
        };
        let own = self.find_edge(
            EdgeRec {
                from,
                label,
                to,
                extra: NONE,
            },
            candidate.id.as_ref().map(EdgeId::as_str),
        );
        let conflicts = |&slot: &Handle| {
            let rec = self.edges[slot as usize];
            Some(slot) != own
                && rec.label == label
                && if directed {
                    rec.from == from && rec.to == to
                } else {
                    (rec.from == from && rec.to == to) || (rec.from == to && rec.to == from)
                }
        };
        let v = &self.vertices[from as usize];
        if directed {
            v.outgoing.iter().any(conflicts)
        } else {
            v.outgoing.iter().chain(&v.incoming).any(conflicts)
        }
    }

    // ---- ordering ------------------------------------------------------------

    fn cmp_edges(&self, a: Handle, b: Handle) -> Ordering {
        let (x, y) = (self.edges[a as usize], self.edges[b as usize]);
        let id = |vertex: Handle| &self.vertices[vertex as usize].id;
        id(x.from)
            .cmp(id(y.from))
            .then_with(|| self.labels[x.label as usize].cmp(&self.labels[y.label as usize]))
            .then_with(|| id(x.to).cmp(id(y.to)))
            .then_with(|| self.edge_id(a).cmp(&self.edge_id(b)))
    }

    /// Sort a handful of edge slots into edge-key order.
    fn sort_edge_slots(&self, slots: &mut [Handle]) {
        slots.sort_unstable_by(|&a, &b| self.cmp_edges(a, b));
    }

    /// Every stored edge in edge-key order, ranking vertices and labels once
    /// so the sort compares integers rather than strings.
    fn sorted_edge_slots(&self) -> Vec<Handle> {
        let mut order = (0..self.vertices.len() as Handle).collect::<Vec<_>>();
        order.sort_unstable_by(|&a, &b| {
            self.vertices[a as usize]
                .id
                .cmp(&self.vertices[b as usize].id)
        });
        let mut vertex_rank = vec![0 as Handle; order.len()];
        for (rank, &vertex) in order.iter().enumerate() {
            vertex_rank[vertex as usize] = rank as Handle;
        }
        drop(order);
        let mut labels = (0..self.labels.len() as Handle).collect::<Vec<_>>();
        labels.sort_unstable_by(|&a, &b| self.labels[a as usize].cmp(&self.labels[b as usize]));
        let mut label_rank = vec![0 as Handle; labels.len()];
        for (rank, &label) in labels.iter().enumerate() {
            label_rank[label as usize] = rank as Handle;
        }

        let mut keyed = self
            .edge_handles()
            .map(|slot| {
                let rec = self.edges[slot as usize];
                (
                    vertex_rank[rec.from as usize],
                    label_rank[rec.label as usize],
                    vertex_rank[rec.to as usize],
                    slot,
                )
            })
            .collect::<Vec<_>>();
        keyed.sort_unstable_by(|a, b| {
            (a.0, a.1, a.2)
                .cmp(&(b.0, b.1, b.2))
                .then_with(|| self.edge_id(a.3).cmp(&self.edge_id(b.3)))
        });
        keyed.into_iter().map(|(_, _, _, slot)| slot).collect()
    }

    // ---- unique-value indexes ------------------------------------------------

    fn rebuild_unique_value_indexes(&mut self) {
        let mut node_indexes = UniqueValueIndexes::new();
        let mut edge_indexes = UniqueValueIndexes::new();
        let constraints = self
            .schema
            .iter()
            .flat_map(|schema| schema.constraints.iter())
            .chain(&self.native_constraints);

        for constraint in constraints {
            match constraint {
                GraphConstraint::NodePropertyUnique { label, key } => {
                    node_indexes
                        .entry(label.clone())
                        .or_default()
                        .entry(key.clone())
                        .or_insert_with(|| UniqueValueIndex::with_capacity(self.node_count));
                }
                GraphConstraint::EdgePropertyUnique { label, key } => {
                    edge_indexes
                        .entry(label.clone())
                        .or_default()
                        .entry(key.clone())
                        .or_insert_with(|| UniqueValueIndex::with_capacity(self.edge_count));
                }
                GraphConstraint::NodePropertyRequired { .. }
                | GraphConstraint::EdgePropertyRequired { .. } => {}
            }
        }

        if !node_indexes.is_empty() {
            for vertex in self.node_handles() {
                let node = self.node_ref(vertex).expect("stored node");
                if node_indexes.contains_key(node.label) {
                    Self::index_node_unique_values(&mut node_indexes, &node.to_node());
                }
            }
        }
        if !edge_indexes.is_empty() {
            for slot in self.edge_handles() {
                Self::index_edge_unique_values(
                    &mut edge_indexes,
                    slot,
                    self.edge_label(slot),
                    self.edge_props(slot),
                );
            }
        }
        self.node_unique_values = node_indexes;
        self.edge_unique_values = edge_indexes;
    }
}

impl MemoryGraphStore {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn graph(&self) -> Graph {
        let inner = self.inner.read().expect("memory graph lock poisoned");
        Self::graph_snapshot(&inner)
    }

    fn node_matches(
        node: &NodeRef<'_>,
        label: Option<&Label>,
        props: &Props,
        predicates: &[GraphPropertyPredicate],
    ) -> bool {
        label.is_none_or(|label| node.label == label)
            && props.iter().all(|(key, value)| {
                if key == "id" {
                    value.as_str().is_some_and(|id| node.id.as_str() == id)
                } else {
                    node.prop(key).as_deref() == Some(value)
                }
            })
            && predicates
                .iter()
                .all(|predicate| predicate.matches(node.prop(&predicate.key).as_deref()))
    }

    fn matching_node_ids(
        inner: &MemoryGraph,
        label: Option<&Label>,
        props: &Props,
        predicates: &[GraphPropertyPredicate],
    ) -> Vec<NodeId> {
        inner
            .sorted_nodes_where(|node| Self::node_matches(node, label, props, predicates))
            .into_iter()
            .map(|vertex| inner.vertices[vertex as usize].id.clone())
            .collect()
    }

    fn relationship_matches(
        inner: &MemoryGraph,
        slot: Handle,
        relationship: &GraphRelationshipMatch,
    ) -> bool {
        if relationship
            .id
            .as_ref()
            .is_some_and(|id| inner.edge_id(slot) != Some(id.as_str()))
        {
            return false;
        }
        let props = inner.edge_props(slot);
        if !relationship
            .props
            .iter()
            .all(|(key, value)| props.get(key) == Some(value))
        {
            return false;
        }
        if !relationship
            .predicates
            .iter()
            .all(|predicate| predicate.matches(props.get(&predicate.key)))
        {
            return false;
        }
        let rec = inner.edges[slot as usize];
        let Some(from) = inner.node_ref(rec.from) else {
            return false;
        };
        let Some(to) = inner.node_ref(rec.to) else {
            return false;
        };
        Self::node_matches(
            &from,
            relationship.from.label.as_ref(),
            &relationship.from.props,
            &relationship.from.predicates,
        ) && Self::node_matches(
            &to,
            relationship.to.label.as_ref(),
            &relationship.to.props,
            &relationship.to.predicates,
        )
    }

    /// Slots of the edges `relationship` matches, in edge-key order.
    fn matching_edge_slots(
        inner: &MemoryGraph,
        relationship: &GraphRelationshipMatch,
    ) -> Vec<Handle> {
        let Some(label) = inner.label(&relationship.label) else {
            return Vec::new();
        };
        let mut slots = inner
            .edge_handles()
            .filter(|&slot| {
                inner.edges[slot as usize].label == label
                    && Self::relationship_matches(inner, slot, relationship)
            })
            .collect::<Vec<_>>();
        inner.sort_edge_slots(&mut slots);
        slots
    }

    fn matching_edges(inner: &MemoryGraph, relationship: &GraphRelationshipMatch) -> Vec<Edge> {
        Self::matching_edge_slots(inner, relationship)
            .into_iter()
            .map(|slot| inner.edge(slot))
            .collect()
    }

    /// The stored graph: nodes in id order, edges in edge-key order.
    fn graph_snapshot(inner: &MemoryGraph) -> Graph {
        let nodes = inner
            .sorted_nodes_where(|_| true)
            .into_iter()
            .map(|vertex| inner.node_ref(vertex).expect("stored node").to_node())
            .collect();
        let edges = inner
            .sorted_edge_slots()
            .into_iter()
            .map(|slot| inner.edge(slot))
            .collect();
        Graph { nodes, edges }
    }

    fn graph_snapshot_with_graph(inner: &MemoryGraph, input: &Graph) -> Graph {
        let current = Self::graph_snapshot(inner);
        let mut nodes = current
            .nodes
            .into_iter()
            .map(|node| (node.id.clone(), node))
            .collect::<BTreeMap<_, _>>();
        let mut edges = current
            .edges
            .into_iter()
            .map(|edge| (MemoryEdgeKey::from_edge(&edge), edge))
            .collect::<BTreeMap<_, _>>();
        for node in &input.nodes {
            nodes.insert(node.id.clone(), node.clone());
        }
        for edge in &input.edges {
            edges.insert(MemoryEdgeKey::from_edge(edge), edge.clone());
        }
        Graph {
            nodes: nodes.into_values().collect(),
            edges: edges.into_values().collect(),
        }
    }

    fn validate_native_constraints(constraints: &[GraphConstraint], graph: &Graph) -> Result<()> {
        for constraint in constraints {
            match constraint {
                GraphConstraint::NodePropertyRequired { label, key } => {
                    for node in graph.nodes.iter().filter(|node| &node.label == label) {
                        if !node.props.contains_key(key) {
                            return Err(GrustError::Schema(format!(
                                "node '{}' with label '{}' is missing native required constrained property '{}'",
                                node.id.as_str(),
                                label.as_str(),
                                key
                            )));
                        }
                    }
                }
                GraphConstraint::EdgePropertyRequired { label, key } => {
                    for edge in graph.edges.iter().filter(|edge| &edge.label == label) {
                        if !edge.props.contains_key(key) {
                            return Err(GrustError::Schema(format!(
                                "edge '{}' from '{}' to '{}' is missing native required constrained property '{}'",
                                edge.label.as_str(),
                                edge.from.as_str(),
                                edge.to.as_str(),
                                key
                            )));
                        }
                    }
                }
                GraphConstraint::NodePropertyUnique { label, key } => {
                    let mut seen = UniqueValueIndex::with_capacity(graph.nodes.len());
                    for node in graph.nodes.iter().filter(|node| &node.label == label) {
                        let Some(value) = node.props.get(key) else {
                            continue;
                        };
                        if let Some(existing_id) = seen.insert(&node.id, value) {
                            return Err(GrustError::Schema(format!(
                                "node '{}' with label '{}' duplicates native unique constrained property '{}' from node '{}'",
                                node.id.as_str(),
                                label.as_str(),
                                key,
                                existing_id.as_str()
                            )));
                        }
                    }
                }
                GraphConstraint::EdgePropertyUnique { label, key } => {
                    let mut seen = UniqueValueIndex::with_capacity(graph.edges.len());
                    for edge in graph.edges.iter().filter(|edge| &edge.label == label) {
                        let Some(value) = edge.props.get(key) else {
                            continue;
                        };
                        if let Some(existing) = seen.insert(edge, value) {
                            return Err(GrustError::Schema(format!(
                                "edge '{}' duplicates native unique constrained property '{}' from edge '{}'",
                                edge_key(edge),
                                key,
                                edge_key(existing)
                            )));
                        }
                    }
                }
            }
        }
        Ok(())
    }

    fn validate_write_snapshot(inner: &MemoryGraph, graph: &Graph) -> Result<()> {
        if let Some(schema) = &inner.schema {
            schema.validate_graph(graph)?;
        }
        Self::validate_native_constraints(&inner.native_constraints, graph)
    }

    fn requires_write_validation(inner: &MemoryGraph) -> bool {
        inner.schema.is_some() || !inner.native_constraints.is_empty()
    }

    fn validate_node_write(inner: &MemoryGraph, node: &Node) -> Result<()> {
        if let Some(schema) = &inner.schema {
            schema.validate_node(node)?;
            Self::validate_node_constraints(inner, node, &schema.constraints, false)?;

            let validate_incident = |slot: Handle| {
                let edge = inner.edge(slot);
                schema.validate_edge_with(&edge, |id| {
                    if id == &node.id {
                        Some(&node.label)
                    } else {
                        inner.node_label(id)
                    }
                })
            };
            if let Some(vertex) = inner.vertex(&node.id) {
                let v = &inner.vertices[vertex as usize];
                for &slot in &v.outgoing {
                    validate_incident(slot)?;
                }
                for &slot in &v.incoming {
                    // Self-loops are listed in both directions and need only
                    // one endpoint validation.
                    let rec = inner.edges[slot as usize];
                    if rec.from != rec.to {
                        validate_incident(slot)?;
                    }
                }
            }
        }
        Self::validate_node_constraints(inner, node, &inner.native_constraints, true)
    }

    fn validate_edge_write(inner: &MemoryGraph, edge: &Edge) -> Result<()> {
        // The slot the edge would overwrite; `NONE` never owns an indexed value.
        let candidate = inner.lookup_edge(edge).unwrap_or(NONE);
        if let Some(schema) = &inner.schema {
            schema.validate_edge_with(edge, |id| inner.node_label(id))?;

            let edge_type = schema.edge_type(&edge.label).expect("validated edge type");
            if edge_type.uniqueness != EdgeUniqueness::None
                && inner.has_conflicting_edge(edge, edge_type.directed)
            {
                let (from, to) = if edge_type.directed || edge.from <= edge.to {
                    (&edge.from, &edge.to)
                } else {
                    (&edge.to, &edge.from)
                };
                return Err(GrustError::Schema(format!(
                    "duplicate edge '{}' between '{}' and '{}' violates {:?} uniqueness",
                    edge.label.as_str(),
                    from.as_str(),
                    to.as_str(),
                    edge_type.uniqueness
                )));
            }
            Self::validate_edge_constraints(inner, edge, candidate, &schema.constraints, false)?;
        }
        Self::validate_edge_constraints(inner, edge, candidate, &inner.native_constraints, true)
    }

    fn validate_node_constraints(
        inner: &MemoryGraph,
        node: &Node,
        constraints: &[GraphConstraint],
        native: bool,
    ) -> Result<()> {
        let qualifier = if native { "native " } else { "" };
        for constraint in constraints {
            match constraint {
                GraphConstraint::NodePropertyRequired { label, key }
                    if label == &node.label && !node.props.contains_key(key) =>
                {
                    return Err(GrustError::Schema(format!(
                        "node '{}' with label '{}' is missing {qualifier}required constrained property '{}'",
                        node.id.as_str(),
                        label.as_str(),
                        key
                    )));
                }
                GraphConstraint::NodePropertyUnique { label, key }
                    if label == &node.label && node.props.contains_key(key) =>
                {
                    let value = &node.props[key];
                    if let Some(existing_id) = inner
                        .node_unique_values
                        .get(label)
                        .and_then(|properties| properties.get(key))
                        .and_then(|values| values.conflicting_owner(&node.id, value))
                    {
                        return Err(GrustError::Schema(format!(
                            "node '{}' with label '{}' duplicates {qualifier}unique constrained property '{}' from node '{}'",
                            node.id.as_str(),
                            label.as_str(),
                            key,
                            existing_id.as_str()
                        )));
                    }
                }
                _ => {}
            }
        }
        Ok(())
    }

    fn validate_edge_constraints(
        inner: &MemoryGraph,
        edge: &Edge,
        candidate: Handle,
        constraints: &[GraphConstraint],
        native: bool,
    ) -> Result<()> {
        let qualifier = if native { "native " } else { "" };
        for constraint in constraints {
            match constraint {
                GraphConstraint::EdgePropertyRequired { label, key }
                    if label == &edge.label && !edge.props.contains_key(key) =>
                {
                    return Err(GrustError::Schema(format!(
                        "edge '{}' from '{}' to '{}' is missing {qualifier}required constrained property '{}'",
                        edge.label.as_str(),
                        edge.from.as_str(),
                        edge.to.as_str(),
                        key
                    )));
                }
                GraphConstraint::EdgePropertyUnique { label, key }
                    if label == &edge.label && edge.props.contains_key(key) =>
                {
                    let value = &edge.props[key];
                    if let Some(&existing) = inner
                        .edge_unique_values
                        .get(label)
                        .and_then(|properties| properties.get(key))
                        .and_then(|values| values.conflicting_owner(&candidate, value))
                    {
                        if inner
                            .edges
                            .get(existing as usize)
                            .is_none_or(|rec| rec.from == NONE)
                        {
                            return Err(GrustError::Backend(
                                "memory unique-value index references a missing edge".into(),
                            ));
                        }
                        return Err(GrustError::Schema(format!(
                            "edge '{}' duplicates {qualifier}unique constrained property '{}' from edge '{}'",
                            edge_key(edge),
                            key,
                            edge_key(&inner.edge(existing))
                        )));
                    }
                }
                _ => {}
            }
        }
        Ok(())
    }
}

#[async_trait]
impl GraphStore for MemoryGraphStore {
    async fn apply_schema(&self, schema: &GraphSchema) -> Result<()> {
        let mut inner = self.write_inner();
        schema.validate_graph(&Self::graph_snapshot(&inner))?;
        inner.schema = Some(schema.clone());
        inner.rebuild_unique_value_indexes();
        Ok(())
    }

    fn constraint_capability(&self, constraint: &GraphConstraint) -> GraphConstraintCapability {
        match constraint {
            GraphConstraint::NodePropertyRequired { .. }
            | GraphConstraint::EdgePropertyRequired { .. }
            | GraphConstraint::NodePropertyUnique { .. }
            | GraphConstraint::EdgePropertyUnique { .. } => {
                GraphConstraintCapability::ValidateBeforeWrite
            }
        }
    }

    fn native_constraint_capability(
        &self,
        constraint: &GraphConstraint,
    ) -> GraphNativeConstraintCapability {
        match constraint {
            GraphConstraint::NodePropertyRequired { .. }
            | GraphConstraint::EdgePropertyRequired { .. }
            | GraphConstraint::NodePropertyUnique { .. }
            | GraphConstraint::EdgePropertyUnique { .. } => {
                GraphNativeConstraintCapability::NativeConstraint
            }
        }
    }

    async fn apply_native_constraint(
        &self,
        request: GraphNativeConstraintRequest,
    ) -> Result<GraphNativeConstraintReport> {
        let mut inner = self.write_inner();
        if inner.native_constraints.contains(&request.constraint) {
            if request.if_not_exists {
                return Ok(GraphNativeConstraintReport {
                    applied: 0,
                    skipped: 1,
                });
            }
            return Err(GrustError::Schema(format!(
                "native graph constraint already exists: {:?}",
                request.constraint
            )));
        }

        let mut next = inner.native_constraints.clone();
        next.push(request.constraint);
        Self::validate_native_constraints(&next, &Self::graph_snapshot(&inner))?;
        inner.native_constraints = next;
        inner.rebuild_unique_value_indexes();
        Ok(GraphNativeConstraintReport {
            applied: 1,
            skipped: 0,
        })
    }

    async fn put_node(&self, node: &Node) -> Result<PutOutcome> {
        let mut inner = self.write_inner();
        if Self::requires_write_validation(&inner) {
            Self::validate_node_write(&inner, node)?;
        }
        Ok(if inner.upsert_node(node) {
            PutOutcome::Updated
        } else {
            PutOutcome::Inserted
        })
    }

    async fn put_edge(&self, edge: &Edge) -> Result<PutOutcome> {
        let mut inner = self.write_inner();
        if Self::requires_write_validation(&inner) {
            Self::validate_edge_write(&inner, edge)?;
        }
        Ok(if inner.upsert_edge(edge) {
            PutOutcome::Updated
        } else {
            PutOutcome::Inserted
        })
    }

    async fn put_graph(&self, graph: &Graph) -> Result<LoadReport> {
        let (report, was_empty) = {
            let mut inner = self.write_inner();
            if Self::requires_write_validation(&inner) {
                Self::validate_write_snapshot(
                    &inner,
                    &Self::graph_snapshot_with_graph(&inner, graph),
                )?;
            }
            let was_empty = inner.node_count == 0 && inner.edge_count == 0;
            let mut report = LoadReport::default();
            inner.upsert_nodes(&graph.nodes);
            report.nodes = graph.nodes.len();
            inner.upsert_edges(&graph.edges);
            report.edges = graph.edges.len();
            (report, was_empty)
        };
        self.warm_index_after_load(was_empty);
        Ok(report)
    }

    async fn get_node(&self, id: &NodeId) -> Result<Option<Node>> {
        let inner = self.inner.read().expect("memory graph lock poisoned");
        Ok(inner.find_node(id).map(NodeRef::to_node))
    }

    async fn get_nodes(&self, ids: &[NodeId]) -> Result<Vec<Node>> {
        let inner = self.inner.read().expect("memory graph lock poisoned");
        Ok(ids
            .iter()
            .filter_map(|id| inner.find_node(id).map(NodeRef::to_node))
            .collect())
    }

    async fn get_edges(&self, query: EdgeQuery) -> Result<Vec<Edge>> {
        let inner = self.inner.read().expect("memory graph lock poisoned");
        if let Some(edges) = self
            .cached_index()
            .and_then(|index| indexed_reads::edges_indexed(&index, &query))
        {
            return Ok(edges);
        }
        let resolve = |id: &Option<NodeId>| match id {
            Some(id) => inner.vertex(id).map(Some).ok_or(()),
            None => Ok(None),
        };
        let label = match &query.label {
            Some(label) => inner.label(label).map(Some).ok_or(()),
            None => Ok(None),
        };
        let (Ok(from), Ok(to), Ok(label)) = (resolve(&query.from), resolve(&query.to), label)
        else {
            return Ok(Vec::new());
        };
        let matches = |slot: &Handle| {
            let rec = inner.edges[*slot as usize];
            from.is_none_or(|from| rec.from == from)
                && to.is_none_or(|to| rec.to == to)
                && label.is_none_or(|label| rec.label == label)
        };
        let mut slots = if let Some(from) = from {
            inner.vertices[from as usize]
                .outgoing
                .iter()
                .copied()
                .filter(matches)
                .collect::<Vec<_>>()
        } else if let Some(to) = to {
            inner.vertices[to as usize]
                .incoming
                .iter()
                .copied()
                .filter(matches)
                .collect()
        } else {
            inner.edge_handles().filter(matches).collect()
        };
        inner.sort_edge_slots(&mut slots);
        Ok(slots.into_iter().map(|slot| inner.edge(slot)).collect())
    }

    async fn traverse(&self, traversal: Traversal) -> Result<Vec<Node>> {
        let inner = self.inner.read().expect("memory graph lock poisoned");
        if let Some(index) = self.cached_index() {
            return Ok(indexed_reads::traverse_indexed(&index, &traversal));
        }
        Ok(Self::traverse_maps(&inner, traversal)
            .into_iter()
            .map(|vertex| inner.node_ref(vertex).expect("stored node").to_node())
            .collect())
    }

    async fn traverse_ids(&self, traversal: Traversal) -> Result<Vec<NodeId>> {
        let inner = self.inner.read().expect("memory graph lock poisoned");
        if let Some(index) = self.cached_index() {
            return Ok(indexed_reads::traverse_ids_indexed(&index, &traversal));
        }
        Ok(Self::traverse_maps(&inner, traversal)
            .into_iter()
            .map(|vertex| inner.vertices[vertex as usize].id.clone())
            .collect())
    }
}

impl MemoryGraphStore {
    /// The vertices `traversal` reaches over the adjacency lists, the path
    /// taken when no snapshot is cached. Each step visits a node's incident
    /// edges in edge-key order.
    fn traverse_maps(inner: &MemoryGraph, traversal: Traversal) -> Vec<Handle> {
        let mut current = match traversal.start {
            Start::Node(id) => inner
                .vertex(&id)
                .filter(|&vertex| inner.node_ref(vertex).is_some())
                .into_iter()
                .collect::<Vec<_>>(),
            Start::NodesByLabel(label) => inner.sorted_nodes_where(|node| *node.label == label),
            Start::NodesByProperty { label, key, value } => inner.sorted_nodes_where(|node| {
                *node.label == label && node.prop(&key).as_deref() == Some(&value)
            }),
        };

        for step in traversal.steps {
            let edge_label = match &step.edge {
                Some(label) => match inner.label(label) {
                    Some(handle) => Some(handle),
                    None => {
                        current.clear();
                        continue;
                    }
                },
                None => None,
            };
            let (out, inc) = match step.direction {
                Direction::Out => (true, false),
                Direction::In => (false, true),
                Direction::Both => (true, true),
            };
            let mut next = Vec::new();
            let mut slots = Vec::new();
            for &node in &current {
                let v = &inner.vertices[node as usize];
                slots.clear();
                if out {
                    slots.extend_from_slice(&v.outgoing);
                }
                if inc {
                    slots.extend_from_slice(&v.incoming);
                }
                if let Some(label) = edge_label {
                    slots.retain(|&slot| inner.edges[slot as usize].label == label);
                }
                inner.sort_edge_slots(&mut slots);
                // A self-loop is listed in both directions but is one edge.
                slots.dedup();
                for &slot in &slots {
                    let rec = inner.edges[slot as usize];
                    let target = if out && rec.from == node {
                        rec.to
                    } else if inc && rec.to == node {
                        rec.from
                    } else {
                        continue;
                    };
                    if let Some(found) = inner.node_ref(target)
                        && step.node.as_ref().is_none_or(|label| label == found.label)
                    {
                        next.push(target);
                    }
                }
            }
            current = next;
        }

        if let Some(limit) = traversal.limit {
            current.truncate(limit as usize);
        }
        current
    }
}

#[async_trait]
impl GraphMutationStore for MemoryGraphStore {
    async fn delete_node(&self, id: &NodeId) -> Result<()> {
        let mut inner = self.write_inner();
        inner.remove_node(id);
        inner.remove_incident_edges(id);
        Ok(())
    }

    async fn delete_edge(&self, from: &NodeId, label: &Label, to: &NodeId) -> Result<()> {
        let mut inner = self.write_inner();
        inner.remove_edges_between(from, label, to);
        Ok(())
    }
}

#[async_trait]
impl CypherMutationExecutor for MemoryGraphStore {
    async fn execute_cypher_mutation_plan(
        &self,
        plan: &GraphMutationPlan,
    ) -> Result<GraphMutationReport> {
        let mut report = plan.report();
        for operation in &plan.operations {
            match operation {
                GraphMutationPlanOp::PatchMatchingNodes {
                    label,
                    props,
                    predicates,
                    patch,
                    ..
                } => {
                    let mut inner = self.write_inner();
                    let ids = Self::matching_node_ids(&inner, label.as_ref(), props, predicates);
                    report.matched_rows += ids.len();
                    report.node_patches += ids.len();
                    report.changed_nodes += ids.len();

                    let mut patched = Vec::with_capacity(ids.len());
                    for id in &ids {
                        if let Some(node) = inner.find_node(id) {
                            let mut node = node.to_node();
                            for (key, value) in patch {
                                node.props.insert(key.clone(), value.clone());
                            }
                            if let Some(schema) = &inner.schema {
                                schema.validate_node(&node)?;
                            }
                            patched.push(node);
                        }
                    }
                    for node in &patched {
                        inner.upsert_node(node);
                    }
                }
                GraphMutationPlanOp::UpdateMatchingNodeProperty {
                    label,
                    props,
                    predicates,
                    target_key,
                    source_key,
                    op,
                    operand,
                    ..
                } => {
                    let mut inner = self.write_inner();
                    let ids = Self::matching_node_ids(&inner, label.as_ref(), props, predicates);
                    report.matched_rows += ids.len();
                    report.node_patches += ids.len();
                    report.changed_nodes += ids.len();

                    let mut updated = Vec::with_capacity(ids.len());
                    for id in &ids {
                        if let Some(node) = inner.find_node(id) {
                            let mut node = node.to_node();
                            let current = node.props.get(source_key).ok_or_else(|| {
                                GrustError::CypherExecution(format!(
                                    "numeric expression source property '{source_key}' is missing"
                                ))
                            })?;
                            let value = evaluate_numeric_update(current, *op, operand)?;
                            node.props.insert(target_key.clone(), value);
                            if let Some(schema) = &inner.schema {
                                schema.validate_node(&node)?;
                            }
                            updated.push(node);
                        }
                    }
                    for node in &updated {
                        inner.upsert_node(node);
                    }
                }
                GraphMutationPlanOp::RemoveMatchingNodeProps {
                    label,
                    props,
                    predicates,
                    keys,
                    ..
                } => {
                    let mut inner = self.write_inner();
                    let ids = Self::matching_node_ids(&inner, label.as_ref(), props, predicates);
                    report.matched_rows += ids.len();
                    report.node_property_removes += ids.len();
                    report.changed_nodes += ids.len();

                    let mut updated = Vec::with_capacity(ids.len());
                    for id in &ids {
                        if let Some(node) = inner.find_node(id) {
                            let mut node = node.to_node();
                            for key in keys {
                                node.props.remove(key);
                            }
                            if let Some(schema) = &inner.schema {
                                schema.validate_node(&node)?;
                            }
                            updated.push(node);
                        }
                    }
                    for node in &updated {
                        inner.upsert_node(node);
                    }
                }
                GraphMutationPlanOp::DeleteMatchingNodes {
                    label,
                    props,
                    predicates,
                    ..
                } => {
                    let mut inner = self.write_inner();
                    let ids = Self::matching_node_ids(&inner, label.as_ref(), props, predicates);
                    let incident_edges = ids
                        .iter()
                        .map(|id| inner.remove_incident_edges(id))
                        .sum::<usize>();

                    report.matched_rows += ids.len();
                    report.node_deletes += ids.len();
                    report.changed_nodes += ids.len();
                    report.edge_deletes += incident_edges;
                    report.changed_edges += incident_edges;

                    for id in &ids {
                        inner.remove_node(id);
                    }
                }
                GraphMutationPlanOp::PatchMatchingEdges {
                    relationship,
                    patch,
                    ..
                } => {
                    let mut inner = self.write_inner();
                    let edges = Self::matching_edges(&inner, relationship);
                    report.matched_rows += edges.len();
                    report.edge_patches += edges.len();
                    report.changed_edges += edges.len();

                    let mut patched = Vec::with_capacity(edges.len());
                    for mut edge in edges {
                        for (key, value) in patch {
                            edge.props.insert(key.clone(), value.clone());
                        }
                        if let Some(schema) = &inner.schema {
                            schema.validate_edge_with(&edge, |id| inner.node_label(id))?;
                        }
                        patched.push(edge);
                    }
                    for edge in &patched {
                        inner.upsert_edge(edge);
                    }
                }
                GraphMutationPlanOp::UpdateMatchingEdgeProperty {
                    relationship,
                    target_key,
                    source_key,
                    op,
                    operand,
                    ..
                } => {
                    let mut inner = self.write_inner();
                    let edges = Self::matching_edges(&inner, relationship);
                    report.matched_rows += edges.len();
                    report.edge_patches += edges.len();
                    report.changed_edges += edges.len();

                    let mut updated = Vec::with_capacity(edges.len());
                    for mut edge in edges {
                        let current = edge.props.get(source_key).ok_or_else(|| {
                            GrustError::CypherExecution(format!(
                                "numeric expression source property '{source_key}' is missing"
                            ))
                        })?;
                        let value = evaluate_numeric_update(current, *op, operand)?;
                        edge.props.insert(target_key.clone(), value);
                        if let Some(schema) = &inner.schema {
                            schema.validate_edge_with(&edge, |id| inner.node_label(id))?;
                        }
                        updated.push(edge);
                    }
                    for edge in &updated {
                        inner.upsert_edge(edge);
                    }
                }
                GraphMutationPlanOp::RemoveMatchingEdgeProps {
                    relationship, keys, ..
                } => {
                    let mut inner = self.write_inner();
                    let edges = Self::matching_edges(&inner, relationship);
                    report.matched_rows += edges.len();
                    report.edge_property_removes += edges.len();
                    report.changed_edges += edges.len();

                    let mut updated = Vec::with_capacity(edges.len());
                    for mut edge in edges {
                        for key in keys {
                            edge.props.remove(key);
                        }
                        if let Some(schema) = &inner.schema {
                            schema.validate_edge_with(&edge, |id| inner.node_label(id))?;
                        }
                        updated.push(edge);
                    }
                    for edge in &updated {
                        inner.upsert_edge(edge);
                    }
                }
                GraphMutationPlanOp::DeleteMatchingEdges { relationship, .. } => {
                    let mut inner = self.write_inner();
                    let slots = Self::matching_edge_slots(&inner, relationship);
                    report.matched_rows += slots.len();
                    report.edge_deletes += slots.len();
                    report.changed_edges += slots.len();
                    for slot in slots {
                        inner.remove_edge_slot(slot);
                    }
                }
                GraphMutationPlanOp::DeleteRelationshipRows {
                    relationship,
                    delete_edges,
                    endpoint_nodes,
                    ..
                } => {
                    let mut inner = self.write_inner();
                    let slots = Self::matching_edge_slots(&inner, relationship);
                    let mut ids = slots
                        .iter()
                        .flat_map(|&slot| {
                            let rec = inner.edges[slot as usize];
                            let inner = &inner;
                            endpoint_nodes.iter().map(move |endpoint| {
                                let vertex = match endpoint {
                                    GraphRelationshipEndpoint::From => rec.from,
                                    GraphRelationshipEndpoint::To => rec.to,
                                };
                                inner.vertices[vertex as usize].id.clone()
                            })
                        })
                        .collect::<Vec<_>>();
                    ids.sort();
                    ids.dedup();

                    let mut edge_slots = if *delete_edges {
                        slots.clone()
                    } else {
                        Vec::new()
                    };
                    edge_slots.extend(ids.iter().flat_map(|id| inner.incident_edge_slots(id)));
                    edge_slots.sort_unstable();
                    edge_slots.dedup();

                    report.matched_rows += slots.len();
                    report.node_deletes += ids.len();
                    report.changed_nodes += ids.len();
                    report.edge_deletes += edge_slots.len();
                    report.changed_edges += edge_slots.len();

                    for id in &ids {
                        inner.remove_node(id);
                    }
                    for slot in edge_slots {
                        inner.remove_edge_slot(slot);
                    }
                }
                GraphMutationPlanOp::UpsertEdgesFromNodeMatches {
                    kind,
                    from,
                    to,
                    label,
                    props,
                    edge_id_policy,
                    ..
                } => {
                    let mut inner = self.write_inner();
                    let from_ids = Self::matching_node_ids(
                        &inner,
                        from.label.as_ref(),
                        &from.props,
                        &from.predicates,
                    );
                    let to_ids = Self::matching_node_ids(
                        &inner,
                        to.label.as_ref(),
                        &to.props,
                        &to.predicates,
                    );
                    let matched_rows = from_ids.len().saturating_mul(to_ids.len());
                    report.matched_rows += matched_rows;
                    report.edge_upserts += matched_rows;
                    report.changed_edges += matched_rows;
                    let explicit_edge_id = explicit_edge_id_from_props(props)?;
                    if explicit_edge_id.is_some() && matched_rows > 1 {
                        return Err(GrustError::CypherUnsupportedCardinality(
                            "row-producing MATCH ... CREATE/MERGE with an explicit relationship id must produce exactly one edge".to_string(),
                        ));
                    }

                    let mut edges = Vec::with_capacity(matched_rows);
                    for from_id in &from_ids {
                        for to_id in &to_ids {
                            let mut edge = Edge::new(
                                label.clone(),
                                from_id.clone(),
                                to_id.clone(),
                                props.clone(),
                            );
                            if let Some(id) = explicit_edge_id.clone() {
                                edge = edge.with_id(id);
                            } else if row_edge_id_policy_generates(*kind, *edge_id_policy) {
                                edge = edge
                                    .with_id(generated_row_edge_id(from_id, label, to_id, props));
                            }
                            if let Some(schema) = &inner.schema {
                                schema.validate_edge_with(&edge, |id| inner.node_label(id))?;
                            }
                            edges.push(edge);
                        }
                    }
                    for edge in &edges {
                        if inner.upsert_edge(edge) {
                            report.edge_updates += 1;
                        } else {
                            report.edge_inserts += 1;
                        }
                    }
                }
                GraphMutationPlanOp::UpsertNode { node, .. } => {
                    classify_node_upsert(self.put_node(node).await?, &mut report);
                }
                GraphMutationPlanOp::UpsertEdge { edge, .. } => {
                    classify_edge_upsert(self.put_edge(edge).await?, &mut report);
                }
                GraphMutationPlanOp::SetMatchingNodeFromNode {
                    target_label,
                    target_props,
                    target_predicates,
                    target_key,
                    source_label,
                    source_props,
                    source_predicates,
                    source_key,
                    op,
                    operand,
                    correlation,
                    ..
                } => {
                    let mut inner = self.write_inner();
                    let target_ids = Self::matching_node_ids(
                        &inner,
                        target_label.as_ref(),
                        target_props,
                        target_predicates,
                    );
                    let source_ids = Self::matching_node_ids(
                        &inner,
                        source_label.as_ref(),
                        source_props,
                        source_predicates,
                    );
                    let target_set: std::collections::BTreeSet<NodeId> =
                        target_ids.iter().cloned().collect();
                    let source_set: std::collections::BTreeSet<NodeId> =
                        source_ids.iter().cloned().collect();
                    let related_pairs = |label: &Label, outgoing: bool| {
                        let Some(label) = inner.label(label) else {
                            return Vec::new();
                        };
                        let mut pairs: Vec<(NodeId, NodeId)> = inner
                            .edge_handles()
                            .filter_map(|slot| {
                                let rec = inner.edges[slot as usize];
                                if rec.label != label {
                                    return None;
                                }
                                let from = &inner.vertices[rec.from as usize].id;
                                let to = &inner.vertices[rec.to as usize].id;
                                let (target, source) =
                                    if outgoing { (from, to) } else { (to, from) };
                                (target_set.contains(target) && source_set.contains(source))
                                    .then(|| (target.clone(), source.clone()))
                            })
                            .collect();
                        pairs.sort();
                        pairs
                    };
                    // Build (target, source) pairs deterministically per correlation.
                    let pairs: Vec<(NodeId, NodeId)> = match correlation {
                        GraphWriteCorrelation::Cartesian => {
                            let mut pairs = Vec::new();
                            for t in &target_ids {
                                for s in &source_ids {
                                    pairs.push((t.clone(), s.clone()));
                                }
                            }
                            pairs
                        }
                        GraphWriteCorrelation::OutgoingRelationship { label } => {
                            related_pairs(label, true)
                        }
                        GraphWriteCorrelation::IncomingRelationship { label } => {
                            related_pairs(label, false)
                        }
                    };
                    // Apply target[target_key] = source[source_key] [op operand];
                    // for cartesian fan-out the last source (by id order) wins.
                    let mut changed: std::collections::BTreeSet<NodeId> = Default::default();
                    for (t, s) in pairs {
                        let value = {
                            let Some(source_node) = inner.find_node(&s) else {
                                continue;
                            };
                            if !source_node.has_prop(source_key) {
                                return Err(GrustError::CypherExecution(format!(
                                    "cross-variable update source property '{source_key}' is missing"
                                )));
                            }
                            let current = source_node.prop(source_key).expect("present property");
                            match op {
                                Some(op) => evaluate_numeric_update(&current, *op, operand)?,
                                None => current.into_owned(),
                            }
                        };
                        if let Some(node) = inner.find_node(&t) {
                            let mut node = node.to_node();
                            node.props.insert(target_key.clone(), value);
                            if let Some(schema) = &inner.schema {
                                schema.validate_node(&node)?;
                            }
                            inner.upsert_node(&node);
                            changed.insert(t);
                        }
                    }
                    report.matched_rows += changed.len();
                    report.node_patches += changed.len();
                    report.changed_nodes += changed.len();
                }
                _ => {
                    let mutation = GraphMutation::from(operation.clone());
                    self.apply_mutations(std::slice::from_ref(&mutation))
                        .await?;
                }
            }
        }
        Ok(report)
    }
}

fn explicit_edge_id_from_props(props: &Props) -> Result<Option<String>> {
    match props.get("id") {
        Some(Value::String(id)) => Ok(Some(id.clone())),
        Some(_) => Err(GrustError::CypherSyntax(
            "relationship id property must be a string literal".to_string(),
        )),
        None => Ok(None),
    }
}

fn row_edge_id_policy_generates(kind: GraphMutationPlanKind, policy: GraphRowEdgeIdPolicy) -> bool {
    matches!(
        (kind, policy),
        (
            GraphMutationPlanKind::Create,
            GraphRowEdgeIdPolicy::GenerateForCreate
                | GraphRowEdgeIdPolicy::GenerateForCreateAndMerge
        ) | (
            GraphMutationPlanKind::Merge,
            GraphRowEdgeIdPolicy::GenerateForCreateAndMerge
        )
    )
}

#[cfg(test)]
mod tests;
