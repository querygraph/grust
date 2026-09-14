//! A resident read snapshot of the universal node and edge tables.
//!
//! LanceDB keeps no index on `from_id`/`to_id`, so every anchored read was a
//! filtered scan of the whole edge table, and a traversal step paid one such
//! scan per frontier node plus two scans of the node table. The snapshot
//! mirrors the two tables once per pair of table versions: node ids interned
//! to `u32`, the edge endpoints as compressed out- and in-adjacency in scan
//! order, and props and explicit edge ids kept as the Arrow strings the scan
//! returned. Reads return rows in the order the filtered scans returned them,
//! so answers are unchanged. LanceDB stays the source of truth: a snapshot is
//! only used while both tables still report the versions it was built from.

use std::collections::BTreeSet;
use std::hash::BuildHasher;

use arrow::array::{Array as _, StringArray};
use arrow::record_batch::RecordBatch;
use futures::TryStreamExt;
use grust_core::prelude::*;
use hashbrown::{DefaultHashBuilder, HashTable};
use lancedb::Table;
use lancedb::query::{ExecutableQuery, QueryBase, Select};

use super::{parse_props, string_column};

const ABSENT: u32 = u32::MAX;

/// Interned strings in one arena, looked up through a table of indices.
#[derive(Default)]
struct Interner {
    bytes: String,
    ends: Vec<usize>,
    table: HashTable<u32>,
    hasher: DefaultHashBuilder,
}

fn arena_str<'a>(bytes: &'a str, ends: &[usize], index: u32) -> &'a str {
    let index = index as usize;
    let start = if index == 0 { 0 } else { ends[index - 1] };
    &bytes[start..ends[index]]
}

impl Interner {
    fn resolve(&self, index: u32) -> &str {
        arena_str(&self.bytes, &self.ends, index)
    }

    fn len(&self) -> usize {
        self.ends.len()
    }

    fn get(&self, value: &str) -> Option<u32> {
        let hash = self.hasher.hash_one(value);
        self.table
            .find(hash, |&index| {
                arena_str(&self.bytes, &self.ends, index) == value
            })
            .copied()
    }

    fn intern(&mut self, value: &str) -> u32 {
        let hash = self.hasher.hash_one(value);
        let Self {
            bytes,
            ends,
            table,
            hasher,
        } = self;
        if let Some(&index) = table.find(hash, |&index| arena_str(bytes, ends, index) == value) {
            return index;
        }
        let index = ends.len() as u32;
        bytes.push_str(value);
        ends.push(bytes.len());
        table.insert_unique(hash, index, |&other| {
            hasher.hash_one(arena_str(bytes, ends, other))
        });
        index
    }
}

/// A label per row, stored once when every row carries the same label.
enum LabelColumn {
    Uniform { label: u32, rows: usize },
    PerRow(Vec<u32>),
}

impl LabelColumn {
    fn new() -> Self {
        Self::Uniform {
            label: ABSENT,
            rows: 0,
        }
    }

    fn push(&mut self, value: u32) {
        match self {
            Self::Uniform { label, rows } if *rows == 0 || *label == value => {
                *label = value;
                *rows += 1;
            }
            Self::Uniform { label, rows } => {
                let mut values = vec![*label; *rows];
                values.push(value);
                *self = Self::PerRow(values);
            }
            Self::PerRow(values) => values.push(value),
        }
    }

    fn get(&self, row: u32) -> u32 {
        match self {
            Self::Uniform { label, .. } => *label,
            Self::PerRow(values) => values[row as usize],
        }
    }
}

/// A string per row, kept as the scan's own Arrow arrays. A batch whose rows
/// all hold the column's trivial value (null ids, `{}` props) keeps nothing.
#[derive(Default)]
struct StringColumn {
    /// First row of each batch, ascending.
    starts: Vec<u32>,
    arrays: Vec<Option<StringArray>>,
}

impl StringColumn {
    fn push(&mut self, start: u32, array: Option<StringArray>) {
        self.starts.push(start);
        self.arrays.push(array);
    }

    /// The row's value, `None` when null or when its batch was trivial.
    fn get(&self, row: u32) -> Option<&str> {
        let batch = self.starts.partition_point(|start| *start <= row) - 1;
        let array = self.arrays[batch].as_ref()?;
        let offset = (row - self.starts[batch]) as usize;
        (!array.is_null(offset)).then(|| array.value(offset))
    }
}

/// Out- or in-adjacency: the edge rows of each interned node, ascending.
struct Adjacency {
    offsets: Vec<u32>,
    rows: Vec<u32>,
}

impl Adjacency {
    fn build(nodes: usize, endpoints: &[u32]) -> Self {
        let mut offsets = vec![0u32; nodes + 1];
        for &endpoint in endpoints {
            offsets[endpoint as usize + 1] += 1;
        }
        for index in 0..nodes {
            offsets[index + 1] += offsets[index];
        }
        let mut next = offsets.clone();
        let mut rows = vec![0u32; endpoints.len()];
        for (row, &endpoint) in endpoints.iter().enumerate() {
            let slot = &mut next[endpoint as usize];
            rows[*slot as usize] = row as u32;
            *slot += 1;
        }
        Self { offsets, rows }
    }

    fn rows(&self, node: u32) -> &[u32] {
        let node = node as usize;
        &self.rows[self.offsets[node] as usize..self.offsets[node + 1] as usize]
    }
}

pub(crate) struct ReadSnapshot {
    /// `(nodes table version, edges table version)` the rows were read at.
    pub(crate) versions: (u64, u64),
    ids: Interner,
    labels: Interner,
    /// Node-table row of each interned id, `ABSENT` for ids only edges name.
    node_row: Vec<u32>,
    node_id: Vec<u32>,
    node_label: LabelColumn,
    node_props: StringColumn,
    edge_from: Vec<u32>,
    edge_to: Vec<u32>,
    edge_label: LabelColumn,
    edge_ids: StringColumn,
    edge_props: StringColumn,
    out: Adjacency,
    incoming: Adjacency,
}

fn row_count(total: usize, what: &str) -> Result<u32> {
    u32::try_from(total)
        .ok()
        .filter(|rows| *rows < ABSENT)
        .ok_or_else(|| {
            GrustError::Backend(format!(
                "LanceDB read snapshot supports fewer than {ABSENT} {what}"
            ))
        })
}

async fn scan(
    table: &Table,
    columns: &[&str],
) -> Result<lancedb::arrow::SendableRecordBatchStream> {
    table
        .query()
        .select(Select::columns(columns))
        .execute()
        .await
        .map_err(|err| GrustError::Backend(format!("LanceDB snapshot scan failed: {err}")))
}

fn trivial_or(
    array: &StringArray,
    trivial: impl Fn(&StringArray, usize) -> bool,
) -> Option<StringArray> {
    (0..array.len())
        .any(|row| !trivial(array, row))
        .then(|| array.clone())
}

impl ReadSnapshot {
    /// Read both tables at (at least) `versions`. The versions are taken
    /// before the scans, so a write that lands during the build can only make
    /// the snapshot look older than its rows, never newer: the next read sees
    /// a newer version and does not use it.
    pub(crate) async fn build(nodes: &Table, edges: &Table, versions: (u64, u64)) -> Result<Self> {
        let mut ids = Interner::default();
        let mut labels = Interner::default();

        let mut node_id = Vec::new();
        let mut node_label = LabelColumn::new();
        let mut node_props = StringColumn::default();
        let mut stream = scan(nodes, &["id", "label", "props"]).await?;
        while let Some(batch) = next_batch(&mut stream).await? {
            let start = row_count(node_id.len(), "nodes")?;
            let (id_col, label_col, props_col) = (
                string_column(&batch, "id")?,
                string_column(&batch, "label")?,
                string_column(&batch, "props")?,
            );
            for row in 0..batch.num_rows() {
                node_id.push(ids.intern(id_col.value(row)));
                node_label.push(labels.intern(label_col.value(row)));
            }
            node_props.push(
                start,
                trivial_or(props_col, |array, row| array.value(row) == "{}"),
            );
        }
        row_count(node_id.len(), "nodes")?;

        let mut edge_from = Vec::new();
        let mut edge_to = Vec::new();
        let mut edge_label = LabelColumn::new();
        let mut edge_ids = StringColumn::default();
        let mut edge_props = StringColumn::default();
        let mut stream = scan(edges, &["id", "from_id", "to_id", "label", "props"]).await?;
        while let Some(batch) = next_batch(&mut stream).await? {
            let start = row_count(edge_from.len(), "edges")?;
            let (id_col, from_col, to_col, label_col, props_col) = (
                string_column(&batch, "id")?,
                string_column(&batch, "from_id")?,
                string_column(&batch, "to_id")?,
                string_column(&batch, "label")?,
                string_column(&batch, "props")?,
            );
            for row in 0..batch.num_rows() {
                edge_from.push(ids.intern(from_col.value(row)));
                edge_to.push(ids.intern(to_col.value(row)));
                edge_label.push(labels.intern(label_col.value(row)));
            }
            edge_ids.push(start, trivial_or(id_col, |array, row| array.is_null(row)));
            edge_props.push(
                start,
                trivial_or(props_col, |array, row| array.value(row) == "{}"),
            );
        }
        row_count(edge_from.len(), "edges")?;

        let mut node_row = vec![ABSENT; ids.len()];
        for (row, &id) in node_id.iter().enumerate() {
            // Ids are unique in the table (`merge_insert` on `id`); keep the
            // first row regardless, as `get_node`'s `LIMIT 1` scan did.
            if node_row[id as usize] == ABSENT {
                node_row[id as usize] = row as u32;
            }
        }
        let out = Adjacency::build(ids.len(), &edge_from);
        let incoming = Adjacency::build(ids.len(), &edge_to);
        Ok(Self {
            versions,
            ids,
            labels,
            node_row,
            node_id,
            node_label,
            node_props,
            edge_from,
            edge_to,
            edge_label,
            edge_ids,
            edge_props,
            out,
            incoming,
        })
    }

    fn node(&self, row: u32) -> Result<Node> {
        Ok(Node {
            id: NodeId::new(self.ids.resolve(self.node_id[row as usize])),
            label: Label::new(self.labels.resolve(self.node_label.get(row))),
            props: parse_props(self.node_props.get(row).unwrap_or("{}"))?,
        })
    }

    fn edge(&self, row: u32) -> Result<Edge> {
        let index = row as usize;
        let props = match self.edge_props.get(row) {
            Some(props) => parse_props(props)?,
            None => Props::new(),
        };
        let mut edge = Edge::new(
            self.labels.resolve(self.edge_label.get(row)),
            self.ids.resolve(self.edge_from[index]),
            self.ids.resolve(self.edge_to[index]),
            props,
        );
        if let Some(id) = self.edge_ids.get(row) {
            edge.id = Some(EdgeId::new(id));
        }
        Ok(edge)
    }

    fn node_row_of(&self, id: &str) -> Option<u32> {
        let index = self.ids.get(id)?;
        let row = self.node_row[index as usize];
        (row != ABSENT).then_some(row)
    }

    pub(crate) fn get_node(&self, id: &NodeId) -> Result<Option<Node>> {
        self.node_row_of(id.as_str())
            .map(|row| self.node(row))
            .transpose()
    }

    /// Node rows for `ids`, each once, in table order (the `id IN (...)` scan).
    fn node_rows_of<'a>(&self, ids: impl Iterator<Item = &'a str>) -> Vec<u32> {
        let rows = ids
            .filter_map(|id| self.node_row_of(id))
            .collect::<BTreeSet<_>>();
        rows.into_iter().collect()
    }

    pub(crate) fn get_nodes(&self, ids: &[NodeId]) -> Result<Vec<Node>> {
        self.node_rows_of(ids.iter().map(NodeId::as_str))
            .into_iter()
            .map(|row| self.node(row))
            .collect()
    }

    /// `Some(None)`: the filter names a label or node no row carries.
    fn label_filter(&self, label: Option<&Label>) -> Option<Option<u32>> {
        match label {
            None => Some(None),
            Some(label) => self.labels.get(label.as_str()).map(Some),
        }
    }

    pub(crate) fn get_edges(&self, query: &EdgeQuery) -> Result<Vec<Edge>> {
        let Some(label) = self.label_filter(query.label.as_ref()) else {
            return Ok(Vec::new());
        };
        let lookup = |id: &Option<NodeId>| id.as_ref().map(|id| self.ids.get(id.as_str()));
        let (from, to) = (lookup(&query.from), lookup(&query.to));
        if matches!(from, Some(None)) || matches!(to, Some(None)) {
            return Ok(Vec::new());
        }
        let (from, to) = (from.flatten(), to.flatten());
        let keep = |row: u32| {
            label.is_none_or(|label| self.edge_label.get(row) == label)
                && from.is_none_or(|from| self.edge_from[row as usize] == from)
                && to.is_none_or(|to| self.edge_to[row as usize] == to)
        };
        let rows: Box<dyn Iterator<Item = u32>> = match (from, to) {
            (Some(from), _) => Box::new(self.out.rows(from).iter().copied()),
            (None, Some(to)) => Box::new(self.incoming.rows(to).iter().copied()),
            (None, None) => Box::new(0..self.edge_from.len() as u32),
        };
        rows.filter(|row| keep(*row))
            .map(|row| self.edge(row))
            .collect()
    }

    /// The node rows `LanceDbGraphStore::traverse` returns, in its order.
    pub(crate) fn traverse_rows(&self, traversal: &Traversal) -> Result<Vec<u32>> {
        let limit = traversal.limit.map(|limit| limit as usize);
        let mut current = match &traversal.start {
            Start::Node(id) => self.node_row_of(id.as_str()).into_iter().collect(),
            Start::NodesByLabel(label) => match self.labels.get(label.as_str()) {
                Some(label) => self.rows_labelled(label).collect(),
                None => Vec::new(),
            },
            Start::NodesByProperty { label, key, value } => {
                let mut rows = Vec::new();
                if let Some(label) = self.labels.get(label.as_str()) {
                    for row in self.rows_labelled(label) {
                        let props = parse_props(self.node_props.get(row).unwrap_or("{}"))?;
                        if props.get(key) == Some(value) {
                            rows.push(row);
                        }
                    }
                }
                rows
            }
        };
        if !matches!(traversal.start, Start::NodesByProperty { .. })
            && let Some(limit) = limit
        {
            current.truncate(limit);
        }

        for step in &traversal.steps {
            let Some(edge_label) = self.label_filter(step.edge.as_ref()) else {
                current.clear();
                continue;
            };
            let node_label = match &step.node {
                None => None,
                Some(label) => match self.labels.get(label.as_str()) {
                    Some(label) => Some(label),
                    None => {
                        current.clear();
                        continue;
                    }
                },
            };
            let mut next = BTreeSet::new();
            let matches =
                |row: u32| edge_label.is_none_or(|label| self.edge_label.get(row) == label);
            for &node_row in &current {
                let node = self.node_id[node_row as usize];
                if matches!(step.direction, Direction::Out | Direction::Both) {
                    for &row in self.out.rows(node) {
                        if matches(row) {
                            next.insert(self.edge_to[row as usize]);
                        }
                    }
                }
                if matches!(step.direction, Direction::In | Direction::Both) {
                    for &row in self.incoming.rows(node) {
                        if matches(row) {
                            next.insert(self.edge_from[row as usize]);
                        }
                    }
                }
            }
            let mut rows = next
                .into_iter()
                .filter_map(|id| {
                    let row = self.node_row[id as usize];
                    (row != ABSENT).then_some(row)
                })
                .filter(|row| node_label.is_none_or(|label| self.node_label.get(*row) == label))
                .collect::<Vec<_>>();
            rows.sort_unstable();
            if let Some(limit) = limit {
                rows.truncate(limit);
            }
            current = rows;
        }
        if let Some(limit) = limit {
            current.truncate(limit);
        }
        Ok(current)
    }

    fn rows_labelled(&self, label: u32) -> impl Iterator<Item = u32> + '_ {
        (0..self.node_id.len() as u32).filter(move |row| self.node_label.get(*row) == label)
    }

    pub(crate) fn nodes_at(&self, rows: &[u32]) -> Result<Vec<Node>> {
        rows.iter().map(|row| self.node(*row)).collect()
    }

    pub(crate) fn ids_at(&self, rows: &[u32]) -> Vec<NodeId> {
        rows.iter()
            .map(|row| NodeId::new(self.ids.resolve(self.node_id[*row as usize])))
            .collect()
    }
}

async fn next_batch(
    stream: &mut lancedb::arrow::SendableRecordBatchStream,
) -> Result<Option<RecordBatch>> {
    stream
        .try_next()
        .await
        .map_err(|err| GrustError::Backend(format!("LanceDB snapshot stream failed: {err}")))
}

#[cfg(test)]
#[path = "snapshot_tests.rs"]
mod tests;
