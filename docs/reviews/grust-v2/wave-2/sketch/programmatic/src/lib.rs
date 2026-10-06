//! A parser-free Gremlin-like draft which constructs the shared unresolved IR.
use grust_unresolved_plan::{
    BinaryOp, Binding, EdgePattern, Expr, GraphRef, Hops, JoinKind, LabelExpr, NamedExpr, PathMode,
    PathPattern, PathSelector, PatternDirection, Plan, Relation, SortKey, VertexPattern,
};
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum BuildError {
    EmptyBinding,
    AlreadyBound,
    InvalidHopRange,
}

pub trait PlanBuilder {
    fn finish(self) -> Plan;
}
#[derive(Clone, Debug)]
pub struct Graph {
    reference: GraphRef,
}
impl Graph {
    pub fn new(reference: GraphRef) -> Self {
        Self { reference }
    }
    pub fn vertices(self) -> Traversal {
        Traversal {
            graph: self.reference,
            path: PathPattern {
                binding: None,
                vertices: vec![VertexPattern {
                    binding: Binding::Anonymous(0),
                    labels: LabelExpr::Any,
                    predicates: Vec::new(),
                }],
                edges: Vec::new(),
                mode: PathMode::Walk,
                selector: PathSelector::All,
            },
            optional: false,
        }
    }
}
#[derive(Clone, Debug)]
pub struct Traversal {
    graph: GraphRef,
    path: PathPattern,
    optional: bool,
}
impl Traversal {
    pub fn has_label(mut self, label: impl Into<String>) -> Self {
        let node = self
            .path
            .vertices
            .last_mut()
            .expect("traversal always has a vertex");
        let next = LabelExpr::label(label);
        node.labels = match std::mem::replace(&mut node.labels, LabelExpr::Any) {
            LabelExpr::Any => next,
            old => LabelExpr::And(vec![old, next]),
        };
        self
    }
    pub fn as_(mut self, name: impl Into<String>) -> Result<Self, BuildError> {
        let name = name.into();
        if name.is_empty() {
            return Err(BuildError::EmptyBinding);
        }
        let current = self
            .path
            .vertices
            .last_mut()
            .expect("traversal always has a vertex");
        if matches!(current.binding, Binding::Named(_)) {
            return Err(BuildError::AlreadyBound);
        }
        current.binding = Binding::Named(name);
        Ok(self)
    }
    /// The predicate is local to this element, so binding it later is safe.
    pub fn has(mut self, name: impl Into<String>, op: BinaryOp, value: Expr) -> Self {
        let predicate = Expr::CurrentElement.property(name).binary(op, value);
        self.path
            .vertices
            .last_mut()
            .expect("traversal always has a vertex")
            .predicates
            .push(predicate);
        self
    }
    pub fn out(self, label: impl Into<String>) -> Self {
        self.step(label, PatternDirection::Outgoing)
    }
    pub fn incoming(self, label: impl Into<String>) -> Self {
        self.step(label, PatternDirection::Incoming)
    }
    pub fn both(self, label: impl Into<String>) -> Self {
        self.step(label, PatternDirection::Either)
    }
    pub fn step(mut self, label: impl Into<String>, direction: PatternDirection) -> Self {
        let index = self.path.edges.len() as u64;
        self.path.edges.push(EdgePattern {
            binding: Binding::Anonymous(2 * index + 1),
            labels: LabelExpr::label(label),
            direction,
            hops: Hops::ONE,
            predicates: Vec::new(),
        });
        self.path.vertices.push(VertexPattern {
            binding: Binding::Anonymous(2 * index + 2),
            labels: LabelExpr::Any,
            predicates: Vec::new(),
        });
        self
    }
    pub fn hops(mut self, hops: Hops) -> Result<Self, BuildError> {
        if !hops.is_valid() || self.path.edges.is_empty() {
            return Err(BuildError::InvalidHopRange);
        }
        self.path.edges.last_mut().expect("checked above").hops = hops;
        Ok(self)
    }
    pub fn mode(mut self, mode: PathMode) -> Self {
        self.path.mode = mode;
        self
    }
    pub fn selector(mut self, selector: PathSelector) -> Self {
        self.path.selector = selector;
        self
    }
    pub fn optional(mut self) -> Self {
        self.optional = true;
        self
    }
    pub fn query(self) -> Query {
        Query {
            root: Relation::Match {
                input: Box::new(Relation::Unit),
                graph: self.graph,
                patterns: vec![self.path],
                optional: self.optional,
            },
        }
    }
    pub fn select(self, items: Vec<NamedExpr>) -> Query {
        self.query().select(items)
    }
}
impl PlanBuilder for Traversal {
    fn finish(self) -> Plan {
        self.query().finish()
    }
}
#[derive(Clone, Debug)]
pub struct Query {
    root: Relation,
}
impl Query {
    pub fn from_plan(plan: Plan) -> Self {
        Self { root: plan.root }
    }
    pub fn filter(self, predicate: Expr) -> Self {
        Self {
            root: Relation::Filter {
                input: Box::new(self.root),
                predicate,
            },
        }
    }
    pub fn select(self, items: Vec<NamedExpr>) -> Self {
        Self {
            root: Relation::Project {
                input: Box::new(self.root),
                items,
                distinct: false,
            },
        }
    }
    pub fn select_distinct(self, items: Vec<NamedExpr>) -> Self {
        Self {
            root: Relation::Project {
                input: Box::new(self.root),
                items,
                distinct: true,
            },
        }
    }
    pub fn aggregate(self, groups: Vec<NamedExpr>, aggregates: Vec<NamedExpr>) -> Self {
        Self {
            root: Relation::Aggregate {
                input: Box::new(self.root),
                groups,
                aggregates,
            },
        }
    }
    pub fn order_by(self, keys: Vec<SortKey>) -> Self {
        Self {
            root: Relation::Sort {
                input: Box::new(self.root),
                keys,
            },
        }
    }
    pub fn slice(self, offset: Option<Expr>, limit: Option<Expr>) -> Self {
        Self {
            root: Relation::Slice {
                input: Box::new(self.root),
                offset,
                limit,
            },
        }
    }
    pub fn limit(self, count: u32) -> Self {
        self.slice(None, Some(i64::from(count).into()))
    }
    pub fn union(self, other: Self, all: bool) -> Self {
        Self {
            root: Relation::Union {
                inputs: vec![self.root, other.root],
                all,
            },
        }
    }
    pub fn join(self, other: Self, kind: JoinKind, condition: Option<Expr>) -> Self {
        Self {
            root: Relation::Join {
                left: Box::new(self.root),
                right: Box::new(other.root),
                kind,
                condition,
            },
        }
    }
}
impl PlanBuilder for Query {
    fn finish(self) -> Plan {
        Plan { root: self.root }
    }
}
#[cfg(test)]
mod tests;
