//! Graph-pattern semantics independent of a language grammar or storage layout.
use crate::Expr;
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum Binding {
    Named(String),
    Anonymous(u64),
}
#[derive(Clone, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum LabelExpr {
    Any,
    Label(String),
    And(Vec<LabelExpr>),
    Or(Vec<LabelExpr>),
    Not(Box<LabelExpr>),
}
impl LabelExpr {
    pub fn label(name: impl Into<String>) -> Self {
        Self::Label(name.into())
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum PatternDirection {
    Outgoing,
    Incoming,
    Either,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct Hops {
    pub min: u64,
    pub max: Option<u64>,
}
impl Hops {
    pub const ONE: Self = Self {
        min: 1,
        max: Some(1),
    };
    pub fn is_valid(self) -> bool {
        self.max.is_none_or(|max| max >= self.min)
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum PathMode {
    Walk,
    Trail,
    Simple,
    Acyclic,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum PathSelector {
    All,
    Any,
    Shortest,
    AllShortest,
}
#[derive(Clone, Debug, PartialEq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct VertexPattern {
    pub binding: Binding,
    pub labels: LabelExpr,
    pub predicates: Vec<Expr>,
}
#[derive(Clone, Debug, PartialEq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct EdgePattern {
    /// Explicit ranged syntax binds a list even when its range is exactly one hop.
    #[cfg_attr(feature = "serde", serde(default))]
    pub binding_list: bool,
    pub binding: Binding,
    pub labels: LabelExpr,
    pub direction: PatternDirection,
    pub hops: Hops,
    pub predicates: Vec<Expr>,
}
#[derive(Clone, Debug, PartialEq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct PathPattern {
    pub binding: Option<Binding>,
    pub vertices: Vec<VertexPattern>,
    pub edges: Vec<EdgePattern>,
    pub mode: PathMode,
    pub selector: PathSelector,
}
impl PathPattern {
    pub fn is_well_formed(&self) -> bool {
        !self.vertices.is_empty()
            && self.vertices.len() == self.edges.len() + 1
            && self.edges.iter().all(|e| e.hops.is_valid())
    }
}
