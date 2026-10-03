//! The labeled property graph as a graph of property groups.
//!
//! A *vertex property group* (VPG) is a set of vertices with the same labels,
//! the same properties and one key. An *edge property group* (EPG) is a set of
//! edges of one type between one source VPG and one target VPG. The schema is
//! itself a small graph: VPGs are its nodes and EPGs its edges.
//!
//! This crate holds that schema and answers questions about it. It never
//! executes a query, never reads data and knows no backend. Its one algorithm
//! is [`Lpg::resolve`]: the valid paths through the schema for a pattern such as
//! `(a:Person)-[]-(b:Person)-[:KNOWS]{1,5}-()`.
//!
//! Sketch status: the traits are the proposal; [`Schema`] is a plain
//! implementation so that the traits can be exercised.

pub mod pattern;
pub mod resolve;
pub mod schema;
pub mod types;

pub use pattern::{EdgeStep, Hops, LabelExpr, NodeStep, Pattern, PatternDirection};
pub use resolve::{Hop, Resolution, ResolveOptions, SchemaPath};
pub use schema::{EdgeGroupDef, LpgError, Schema, SchemaBuilder, VertexGroupDef};
pub use types::{Constraint, Direction, EdgeCardinality, LogicalType, Property, TimeUnit};

/// Identity of a vertex property group within one schema. Sixteen bits: at
/// most 65,536 groups, the convention of a `(group, dense id)` global id.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct VpgId(pub u16);

/// Identity of an edge property group within one schema.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct EpgId(pub u16);

/// A vertex property group, as seen by planners.
pub trait VertexGroup {
    fn id(&self) -> VpgId;
    fn name(&self) -> &str;
    /// All labels a vertex of this group carries. An LPG vertex may have several.
    fn labels(&self) -> &[String];
    fn properties(&self) -> &[Property];
    /// The columns that identify a vertex of this group. Never empty.
    fn key(&self) -> &[String];
    fn constraints(&self) -> &[Constraint];

    fn property(&self, name: &str) -> Option<&Property> {
        self.properties().iter().find(|p| p.name == name)
    }
    fn has_label(&self, label: &str) -> bool {
        self.labels().iter().any(|l| l == label)
    }
}

/// An edge property group: edges of one type from one VPG to one VPG.
pub trait EdgeGroup {
    fn id(&self) -> EpgId;
    fn name(&self) -> &str;
    /// The edge type (the relationship label).
    fn edge_type(&self) -> &str;
    fn source(&self) -> VpgId;
    fn target(&self) -> VpgId;
    fn direction(&self) -> Direction;
    fn properties(&self) -> &[Property];
    /// Columns of the edge rows that hold the source vertex's key, in key order.
    fn source_key(&self) -> &[String];
    /// Columns of the edge rows that hold the target vertex's key, in key order.
    fn target_key(&self) -> &[String];
    fn constraints(&self) -> &[Constraint];

    fn property(&self, name: &str) -> Option<&Property> {
        self.properties().iter().find(|p| p.name == name)
    }
}

/// A schema of property groups. Implement it over any catalog; [`Schema`] is
/// the in-memory one.
pub trait Lpg {
    type Vertex: VertexGroup;
    type Edge: EdgeGroup;

    fn vertex_groups(&self) -> &[Self::Vertex];
    fn edge_groups(&self) -> &[Self::Edge];

    fn vertex(&self, id: VpgId) -> Option<&Self::Vertex> {
        self.vertex_groups().iter().find(|v| v.id() == id)
    }
    fn edge(&self, id: EpgId) -> Option<&Self::Edge> {
        self.edge_groups().iter().find(|e| e.id() == id)
    }
    fn vertex_by_name(&self, name: &str) -> Option<&Self::Vertex> {
        self.vertex_groups().iter().find(|v| v.name() == name)
    }
    fn edge_by_name(&self, name: &str) -> Option<&Self::Edge> {
        self.edge_groups().iter().find(|e| e.name() == name)
    }
    /// The groups whose labels satisfy `labels`.
    fn vertices_matching(&self, labels: &LabelExpr) -> Vec<VpgId> {
        self.vertex_groups()
            .iter()
            .filter(|v| labels.matches(v.labels()))
            .map(|v| v.id())
            .collect()
    }

    /// All valid paths through the schema for `pattern`. See [`resolve`].
    fn resolve(&self, pattern: &Pattern, options: &ResolveOptions) -> Resolution
    where
        Self: Sized,
    {
        resolve::resolve(self, pattern, options)
    }
    /// Whether any path through the schema satisfies `pattern`.
    fn is_feasible(&self, pattern: &Pattern) -> bool
    where
        Self: Sized,
    {
        resolve::is_feasible(self, pattern)
    }
    /// Whether `pattern` can start at a vertex of group `from`.
    fn is_feasible_from(&self, from: VpgId, pattern: &Pattern) -> bool
    where
        Self: Sized,
    {
        resolve::is_feasible_from(self, from, pattern)
    }
    /// A shortest path of at most `max_hops` group-to-group hops, in either direction.
    fn find_path(&self, from: VpgId, to: VpgId, max_hops: usize) -> Option<Vec<Hop>>
    where
        Self: Sized,
    {
        resolve::find_path(self, from, to, max_hops)
    }
}
