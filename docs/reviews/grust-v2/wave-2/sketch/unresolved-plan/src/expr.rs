//! Expressions retain logical names; plugin binding is a resolver operation.
use crate::Binding;
use grust_functions::{FunctionKind, FunctionName};
#[derive(Clone, Debug, PartialEq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum Literal {
    Null,
    Boolean(bool),
    Integer(i64),
    /// IEEE-754 bits preserve NaNs and signed zero through portable JSON.
    FloatBits(u64),
    String(String),
    Binary(Vec<u8>),
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum BinaryOp {
    Eq,
    NotEq,
    Lt,
    Le,
    Gt,
    Ge,
    Add,
    Subtract,
    Multiply,
    Divide,
    And,
    Or,
    In,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum UnaryOp {
    Not,
    Negate,
    IsNull,
    IsNotNull,
}
#[derive(Clone, Debug, PartialEq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct FunctionCall {
    pub name: FunctionName,
    pub kind: FunctionKind,
    pub arguments: Vec<Expr>,
    pub distinct: bool,
    pub filter: Option<Box<Expr>>,
}
#[derive(Clone, Debug, PartialEq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum Expr {
    /// Relative subject of a predicate inside a vertex or edge pattern.
    CurrentElement,
    Literal(Literal),
    Parameter(String),
    Binding(Binding),
    Property {
        object: Box<Expr>,
        name: String,
    },
    Binary {
        op: BinaryOp,
        left: Box<Expr>,
        right: Box<Expr>,
    },
    Unary {
        op: UnaryOp,
        argument: Box<Expr>,
    },
    Call(FunctionCall),
    List(Vec<Expr>),
    Map(Vec<(String, Expr)>),
    Case {
        branches: Vec<(Expr, Expr)>,
        otherwise: Box<Expr>,
    },
}
impl Expr {
    pub fn float(value: f64) -> Self {
        Self::Literal(Literal::FloatBits(value.to_bits()))
    }
    pub fn variable(name: impl Into<String>) -> Self {
        Self::Binding(Binding::Named(name.into()))
    }
    pub fn property(self, name: impl Into<String>) -> Self {
        Self::Property {
            object: Box::new(self),
            name: name.into(),
        }
    }
    pub fn binary(self, op: BinaryOp, right: Expr) -> Self {
        Self::Binary {
            op,
            left: Box::new(self),
            right: Box::new(right),
        }
    }
    pub fn scalar(name: FunctionName, arguments: Vec<Expr>) -> Self {
        Self::Call(FunctionCall {
            name,
            kind: FunctionKind::Scalar,
            arguments,
            distinct: false,
            filter: None,
        })
    }
    pub fn aggregate(name: FunctionName, arguments: Vec<Expr>, distinct: bool) -> Self {
        Self::Call(FunctionCall {
            name,
            kind: FunctionKind::Aggregate,
            arguments,
            distinct,
            filter: None,
        })
    }
}
impl From<&str> for Expr {
    fn from(s: &str) -> Self {
        Self::Literal(Literal::String(s.into()))
    }
}
impl From<i64> for Expr {
    fn from(v: i64) -> Self {
        Self::Literal(Literal::Integer(v))
    }
}
impl From<bool> for Expr {
    fn from(v: bool) -> Self {
        Self::Literal(Literal::Boolean(v))
    }
}
