//! Executable backend-neutral relational IR. Slots have query-wide identity.
use crate::{Field, Slot};
use grust_functions::FunctionDescriptor;
use grust_lpg::{GroupId, LogicalType};
use grust_unresolved_plan::{BinaryOp, JoinKind, Literal, UnaryOp};
#[derive(Clone, Debug, PartialEq)]
pub struct Expr {
    pub kind: Value,
    pub ty: Option<LogicalType>,
    pub nullable: bool,
}
#[derive(Clone, Debug, PartialEq)]
pub enum Value {
    Slot(Slot),
    Literal(Literal),
    Parameter(String),
    Binary {
        op: BinaryOp,
        left: Box<Expr>,
        right: Box<Expr>,
    },
    Unary {
        op: UnaryOp,
        argument: Box<Expr>,
    },
    Call {
        function: Box<FunctionDescriptor>,
        arguments: Vec<Expr>,
        distinct: bool,
        filter: Option<Box<Expr>>,
    },
    List(Vec<Expr>),
    Struct(Vec<(String, Expr)>),
    Property {
        object: Box<Expr>,
        name: String,
    },
    Case {
        branches: Vec<(Expr, Expr)>,
        otherwise: Box<Expr>,
    },
}
impl Expr {
    pub fn slot(field: &Field) -> Self {
        Self {
            kind: Value::Slot(field.slot),
            ty: Some(field.ty.clone()),
            nullable: field.nullable,
        }
    }
    pub fn boolean(value: bool) -> Self {
        Self {
            kind: Value::Literal(Literal::Boolean(value)),
            ty: Some(LogicalType::Boolean),
            nullable: false,
        }
    }
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Column {
    Identity,
    Source,
    Target,
    Property(String),
}
#[derive(Clone, Debug, PartialEq)]
pub struct SortKey {
    pub expression: Expr,
    pub descending: bool,
    pub nulls_first: bool,
}
#[derive(Clone, Debug, PartialEq)]
pub struct Node {
    pub op: Op,
    pub fields: Vec<Field>,
}
#[derive(Clone, Debug, PartialEq)]
pub enum Op {
    Unit,
    Empty,
    Scan {
        graph: String,
        group: GroupId,
        columns: Vec<(Slot, Column)>,
    },
    Filter {
        input: Box<Node>,
        predicate: Expr,
    },
    Project {
        input: Box<Node>,
        items: Vec<(Slot, Expr)>,
        distinct: bool,
    },
    Aggregate {
        input: Box<Node>,
        groups: Vec<(Slot, Expr)>,
        aggregates: Vec<(Slot, Expr)>,
    },
    Join {
        left: Box<Node>,
        right: Box<Node>,
        kind: JoinKind,
        condition: Option<Expr>,
    },
    Union {
        inputs: Vec<Node>,
        all: bool,
    },
    Unwind {
        input: Box<Node>,
        list: Expr,
        slot: Slot,
    },
    Sort {
        input: Box<Node>,
        keys: Vec<SortKey>,
    },
    Slice {
        input: Box<Node>,
        offset: Option<Expr>,
        limit: Option<Expr>,
    },
}
#[derive(Clone, Debug, PartialEq)]
pub struct Plan {
    pub root: Node,
}
impl Plan {
    pub fn output(&self) -> &[Field] {
        &self.root.fields
    }
}

/// The NULL-only logical type uses the LPG extension namespace without changing Wave 2.
pub fn null_type() -> LogicalType {
    LogicalType::Extension {
        namespace: "grust".into(),
        name: "null".into(),
        parameters: vec![],
    }
}
pub fn is_null_type(ty: &LogicalType) -> bool {
    *ty == null_type()
}
