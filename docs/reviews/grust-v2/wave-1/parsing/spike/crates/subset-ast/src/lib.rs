//! The subset AST shared by the two alternative parsers.
//!
//! Subset: one or more `[OPTIONAL] MATCH pattern, ... [WHERE expr]` clauses,
//! then `RETURN [DISTINCT] expr [AS name], ... [ORDER BY expr [ASC|DESC], ...]
//! [SKIP n] [LIMIT n]`. Patterns: `[p =] (v:L {k: e})-[r:T|U *a..b {k: e}]->(...)`.
//! Expressions: OR, XOR, AND, NOT, comparisons, IS [NOT] NULL, IN, STARTS WITH,
//! ENDS WITH, CONTAINS, + - * / %, unary minus, property access, function calls
//! (with DISTINCT and count(*)), lists, maps, parameters and literals.

#[derive(Clone, Debug, PartialEq)]
pub struct Query {
    pub matches: Vec<Match>,
    pub ret: Return,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Match {
    pub optional: bool,
    pub patterns: Vec<Path>,
    pub filter: Option<Expr>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Path {
    pub var: Option<String>,
    pub start: Node,
    pub hops: Vec<(Rel, Node)>,
}

#[derive(Clone, Debug, PartialEq, Default)]
pub struct Node {
    pub var: Option<String>,
    pub labels: Vec<String>,
    pub props: Vec<(String, Expr)>,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Dir {
    Out,
    In,
    Both,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Rel {
    pub var: Option<String>,
    pub types: Vec<String>,
    pub range: Option<(Option<u64>, Option<u64>)>,
    pub props: Vec<(String, Expr)>,
    pub dir: Dir,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Return {
    pub distinct: bool,
    pub items: Vec<(Expr, Option<String>)>,
    pub order: Vec<(Expr, bool)>,
    pub skip: Option<i64>,
    pub limit: Option<i64>,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Op {
    Or,
    Xor,
    And,
    Eq,
    Ne,
    Lt,
    Le,
    Gt,
    Ge,
    In,
    StartsWith,
    EndsWith,
    Contains,
    Add,
    Sub,
    Mul,
    Div,
    Mod,
}

#[derive(Clone, Debug, PartialEq)]
pub enum Expr {
    Int(i64),
    Float(f64),
    Str(String),
    Bool(bool),
    Null,
    Param(String),
    Var(String),
    Prop(Box<Expr>, String),
    Call(String, bool, Vec<Expr>),
    CountStar,
    List(Vec<Expr>),
    Map(Vec<(String, Expr)>),
    Not(Box<Expr>),
    Neg(Box<Expr>),
    Bin(Op, Box<Expr>, Box<Expr>),
    IsNull(Box<Expr>, bool),
    /// Placeholder produced by error recovery (chumsky only).
    Error,
}

pub fn bin(op: Op, a: Expr, b: Expr) -> Expr {
    Expr::Bin(op, Box::new(a), Box::new(b))
}

/// Words that cannot be used as bare variables in the subset.
pub const RESERVED: &[&str] = &[
    "MATCH", "OPTIONAL", "WHERE", "RETURN", "DISTINCT", "AS", "ORDER", "BY", "SKIP", "LIMIT",
    "ASC", "DESC", "AND", "OR", "XOR", "NOT", "IN", "IS", "NULL", "TRUE", "FALSE", "STARTS",
    "ENDS", "CONTAINS", "WITH",
];

pub fn is_reserved(word: &str) -> bool {
    RESERVED.iter().any(|k| k.eq_ignore_ascii_case(word))
}
