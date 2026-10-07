//! Draft resolved IR: metadata only, no catalog handles or engine plans.
use grust_functions::FunctionDescriptor;
use grust_lpg::{GroupId, LogicalType};
use grust_unresolved_plan::{BinaryOp, Binding, Literal};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct Slot(pub u32);
#[derive(Clone, Debug, PartialEq)]
pub struct Field {
    pub slot: Slot,
    pub name: String,
    pub ty: LogicalType,
    pub nullable: bool,
}
#[derive(Clone, Debug, PartialEq)]
pub enum Expr {
    Slot(Slot),
    Literal(Literal),
    Parameter {
        name: String,
        ty: LogicalType,
    },
    Binary {
        op: BinaryOp,
        left: Box<Expr>,
        right: Box<Expr>,
    },
    Call {
        function: Box<FunctionDescriptor>,
        arguments: Vec<Expr>,
    },
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Orientation {
    Stored,
    Reversed,
}
/// One feasible schema path; alternatives are separate bag-preserving branches.
#[derive(Clone, Debug, PartialEq)]
pub struct SchemaPath {
    pub vertices: Vec<GroupId>,
    pub edges: Vec<(GroupId, Orientation)>,
}
#[derive(Clone, Debug, PartialEq)]
pub struct EntityBinding {
    pub binding: Binding,
    pub groups: Vec<GroupId>,
}
#[derive(Clone, Debug, PartialEq)]
pub enum Relation {
    Unit,
    Scan {
        graph: String,
        group: GroupId,
        fields: Vec<Field>,
    },
    Match {
        input: Box<Relation>,
        graph: String,
        alternatives: Vec<SchemaPath>,
        bindings: Vec<EntityBinding>,
        predicates: Vec<Expr>,
        optional: bool,
    },
    Filter {
        input: Box<Relation>,
        predicate: Expr,
    },
    Project {
        input: Box<Relation>,
        items: Vec<(Field, Expr)>,
        distinct: bool,
    },
    /// Kept explicit: a backend must not replace recursion with a single join.
    GraphOperator {
        name: String,
        input: Box<Relation>,
        arguments: Vec<Expr>,
    },
}
pub trait ResolvedPlan {
    fn root(&self) -> &Relation;
    fn output(&self) -> &[Field];
}
#[derive(Clone, Debug, PartialEq)]
pub struct Plan {
    pub root: Relation,
    pub output: Vec<Field>,
}
impl ResolvedPlan for Plan {
    fn root(&self) -> &Relation {
        &self.root
    }
    fn output(&self) -> &[Field] {
        &self.output
    }
}
