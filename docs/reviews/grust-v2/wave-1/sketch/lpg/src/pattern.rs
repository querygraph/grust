//! The pattern this crate resolves: a chain of node steps joined by edge steps.
//!
//! It is the minimum the schema needs to answer "which paths are valid". The
//! unresolved logical plan (a separate crate) carries more: variables,
//! property predicates, path modes. It lowers each path pattern to this form
//! to ask the schema, and keeps its own variables beside the answer.

/// A label expression, as in GQL: `:A`, `:A&B`, `:A|B`, `:!A`, `:%` (any).
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
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
        LabelExpr::Label(name.into())
    }
    /// Whether an element carrying `labels` satisfies the expression.
    pub fn matches(&self, labels: &[String]) -> bool {
        match self {
            LabelExpr::Any => true,
            LabelExpr::Label(name) => labels.iter().any(|l| l == name),
            LabelExpr::And(all) => all.iter().all(|e| e.matches(labels)),
            LabelExpr::Or(any) => any.iter().any(|e| e.matches(labels)),
            LabelExpr::Not(inner) => !inner.matches(labels),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct NodeStep {
    pub labels: LabelExpr,
}

/// The direction written in the pattern: `->`, `<-`, or `-`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum PatternDirection {
    Outgoing,
    Incoming,
    Either,
}

/// How many schema hops one pattern edge may take: `{1}`, `{1,5}`, `{2,}`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct Hops {
    pub min: usize,
    /// `None` is unbounded.
    pub max: Option<usize>,
}

impl Hops {
    pub const ONE: Hops = Hops {
        min: 1,
        max: Some(1),
    };
    pub fn range(min: usize, max: usize) -> Self {
        Hops {
            min,
            max: Some(max),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct EdgeStep {
    /// The edge type expression. `Any` for an anonymous `-[]-`.
    pub types: LabelExpr,
    pub direction: PatternDirection,
    pub hops: Hops,
}

/// `nodes[0] edges[0] nodes[1] edges[1] ... nodes[k]`.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct Pattern {
    pub nodes: Vec<NodeStep>,
    pub edges: Vec<EdgeStep>,
}

impl Pattern {
    /// Start a pattern at a node step.
    pub fn node(labels: LabelExpr) -> Self {
        Pattern {
            nodes: vec![NodeStep { labels }],
            edges: Vec::new(),
        }
    }
    /// Append `-[types]-(labels)` in `direction`, taking `hops` schema hops.
    pub fn edge(
        mut self,
        types: LabelExpr,
        direction: PatternDirection,
        hops: Hops,
        labels: LabelExpr,
    ) -> Self {
        self.edges.push(EdgeStep {
            types,
            direction,
            hops,
        });
        self.nodes.push(NodeStep { labels });
        self
    }
    pub fn is_well_formed(&self) -> bool {
        !self.nodes.is_empty()
            && self.nodes.len() == self.edges.len() + 1
            && self
                .edges
                .iter()
                .all(|e| e.hops.max.is_none_or(|max| max >= e.hops.min))
    }
}
