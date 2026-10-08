//! Relational operators refer to graph names and expressions, never file paths.
use crate::{Expr, PathPattern};
use grust_functions::FunctionName;
#[derive(Clone, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum GraphRef {
    Default,
    Named {
        namespace: Vec<String>,
        name: String,
    },
    Parameter(String),
}
#[derive(Clone, Debug, PartialEq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct NamedExpr {
    pub name: String,
    pub expression: Expr,
}
#[derive(Clone, Debug, PartialEq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct SortKey {
    pub expression: Expr,
    pub descending: bool,
    pub nulls_first: bool,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum JoinKind {
    Inner,
    Left,
    Right,
    Full,
    Cross,
    Semi,
    Anti,
}
#[derive(Clone, Debug, PartialEq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum Relation {
    Unit,
    /// One logical input row inside an Apply body; populated by the resolver.
    Argument,
    Apply {
        input: Box<Relation>,
        body: Box<Relation>,
    },
    Match {
        input: Box<Relation>,
        graph: GraphRef,
        patterns: Vec<PathPattern>,
        optional: bool,
    },
    Filter {
        input: Box<Relation>,
        predicate: Expr,
    },
    Project {
        input: Box<Relation>,
        items: Vec<NamedExpr>,
        distinct: bool,
    },
    Aggregate {
        input: Box<Relation>,
        groups: Vec<NamedExpr>,
        aggregates: Vec<NamedExpr>,
    },
    Join {
        left: Box<Relation>,
        right: Box<Relation>,
        kind: JoinKind,
        condition: Option<Expr>,
    },
    Union {
        inputs: Vec<Relation>,
        all: bool,
    },
    Unwind {
        input: Box<Relation>,
        list: Expr,
        binding: String,
    },
    Sort {
        input: Box<Relation>,
        keys: Vec<SortKey>,
    },
    Slice {
        input: Box<Relation>,
        offset: Option<Expr>,
        limit: Option<Expr>,
    },
    /// An extension's schema and semantics are supplied by a resolver/provider.
    Extension {
        name: FunctionName,
        inputs: Vec<Relation>,
        arguments: Vec<Expr>,
    },
}
#[derive(Clone, Debug, PartialEq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct Plan {
    pub root: Relation,
}
