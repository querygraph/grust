use grust_backend::query::QueryStorage;
use grust_functions::*;
use grust_lpg::*;
use grust_optimized_plan::Estimate;
use grust_optimizer::{DegreeSummary, Statistics};
use grust_resolution::{Catalog, ParameterTypes, ResolveError};
use grust_resolved_plan::query::{Column, Expr};
use grust_unresolved_plan::{self as u, Expr as E, Relation as R};
use std::collections::HashMap;
pub struct FixtureCatalog {
    pub schema: Schema,
}
impl Default for FixtureCatalog {
    fn default() -> Self {
        let ty = |id, name: &str, parents, properties| ElementType {
            id: TypeId(id),
            name: name.into(),
            labels: vec![name.into()],
            supertypes: parents,
            properties,
        };
        let vertex = |id, t| Vertex {
            id: GroupId(id),
            element_type: TypeId(t),
            identity: Identity::Opaque,
            constraints: vec![],
        };
        let edge = |id, t, src, dst| Edge {
            id: GroupId(id),
            element_type: TypeId(t),
            source: GroupId(src),
            target: GroupId(dst),
            direction: Direction::Directed,
            identity: Identity::Opaque,
        };
        let schema = Schema::new(
            vec![
                ty(
                    1,
                    "Person",
                    vec![],
                    vec![
                        Property::required("id", LogicalType::Int64),
                        Property::required("name", LogicalType::String),
                        Property::new("age", LogicalType::Int64),
                    ],
                ),
                ty(
                    2,
                    "Employee",
                    vec![TypeId(1)],
                    vec![Property::required("salary", LogicalType::Int64)],
                ),
                ty(
                    3,
                    "Company",
                    vec![],
                    vec![
                        Property::required("id", LogicalType::Int64),
                        Property::required("name", LogicalType::String),
                    ],
                ),
                ty(10, "KNOWS", vec![], vec![]),
                ty(11, "WORKS", vec![], vec![]),
            ],
            vec![vertex(1, 1), vertex(2, 2), vertex(3, 3)],
            vec![edge(10, 10, 1, 1), edge(11, 11, 1, 3)],
        )
        .unwrap();
        Self { schema }
    }
}
impl Catalog for FixtureCatalog {
    fn graph(&self, graph: &u::GraphRef) -> Result<(&str, &Schema), ResolveError> {
        match graph {
            u::GraphRef::Default => Ok(("fixture", &self.schema)),
            _ => Err(ResolveError::UnknownGraph(graph.clone())),
        }
    }
}
pub struct Parameters;
impl ParameterTypes for Parameters {
    fn parameter(&self, name: &str) -> Option<(LogicalType, bool)> {
        (name == "minimum").then_some((LogicalType::Int64, false))
    }
}
pub struct Storage;
impl QueryStorage for Storage {
    fn table(&self, _: &str, group: GroupId) -> Option<Vec<String>> {
        Some(vec![match group.0 {
            1 => "people",
            2 => "employees",
            3 => "companies",
            10 => "knows",
            11 => "works",
            _ => return None,
        }
        .into()])
    }
    fn column(&self, _: &str, _: GroupId, column: &Column) -> Option<String> {
        Some(match column {
            Column::Identity => "id".into(),
            Column::Source => "src".into(),
            Column::Target => "dst".into(),
            Column::Property(name) => name.clone(),
        })
    }
    fn function(&self, function: &FunctionDescriptor) -> Option<Vec<String>> {
        (function.provider == "fixture-builtins").then(|| vec![function.name.name.clone()])
    }
}
pub struct Stats;
impl Statistics for Stats {
    fn revision(&self) -> Option<&str> {
        Some("fixture-metadata-v1")
    }
    fn rows(&self, _: &str, g: GroupId) -> Estimate<u64> {
        Estimate::Known(match g.0 {
            1 => 4,
            2 | 3 => 1,
            10 => 5,
            11 => 2,
            _ => 0,
        })
    }
    fn distinct(&self, _: &str, g: GroupId, name: &str) -> Estimate<u64> {
        if name == "id" || name == "name" {
            self.rows("", g)
        } else {
            Estimate::Unknown
        }
    }
    fn endpoint_distinct(&self, _: &str, g: GroupId, source: bool) -> Estimate<u64> {
        Estimate::Known(match (g.0, source) {
            (10, true) | (10, false) => 3,
            (11, true) => 2,
            (11, false) => 1,
            _ => 0,
        })
    }
    fn degree(&self, _: &str, _: GroupId) -> Estimate<DegreeSummary> {
        Estimate::Unknown
    }
}
pub fn registry() -> Registry {
    let mut registry = Registry::default();
    for (name, kind, args, result, nulls) in [
        (
            "count",
            FunctionKind::Aggregate,
            vec![ArgumentType::Any],
            ReturnType::Exact(LogicalType::Int64),
            NullSemantics::NonNull,
        ),
        (
            "sum",
            FunctionKind::Aggregate,
            vec![ArgumentType::Exact(LogicalType::Int64)],
            ReturnType::Exact(LogicalType::Int64),
            NullSemantics::ProviderDefined,
        ),
        (
            "upper",
            FunctionKind::Scalar,
            vec![ArgumentType::Exact(LogicalType::String)],
            ReturnType::Exact(LogicalType::String),
            NullSemantics::Strict,
        ),
    ] {
        registry
            .register(FunctionDescriptor {
                name: FunctionName::new(name),
                kind,
                signature: Signature {
                    arguments: args,
                    variadic: None,
                    result,
                },
                nulls,
                backends: BackendSupport::Named(vec!["sail".into()]),
                volatility: Volatility::Immutable,
                provider: "fixture-builtins".into(),
            })
            .unwrap();
    }
    registry
}
pub fn p(binding: &str, name: &str) -> E {
    E::variable(binding).property(name)
}
pub fn item(name: &str, expression: E) -> u::NamedExpr {
    u::NamedExpr {
        name: name.into(),
        expression,
    }
}
pub fn vertex(name: &str, label: u::LabelExpr) -> u::VertexPattern {
    u::VertexPattern {
        binding: u::Binding::Named(name.into()),
        labels: label,
        predicates: vec![],
    }
}
pub fn path(source: &str, target: &str, direction: u::PatternDirection) -> u::PathPattern {
    u::PathPattern {
        binding: None,
        vertices: vec![
            vertex(source, u::LabelExpr::label("Person")),
            vertex(target, u::LabelExpr::label("Person")),
        ],
        edges: vec![u::EdgePattern {
            binding: u::Binding::Named("e".into()),
            labels: u::LabelExpr::label("KNOWS"),
            direction,
            hops: u::Hops::ONE,
            predicates: vec![],
        }],
        mode: u::PathMode::Walk,
        selector: u::PathSelector::All,
    }
}
pub fn scan(binding: &str, label: u::LabelExpr) -> R {
    R::Match {
        input: Box::new(R::Unit),
        graph: u::GraphRef::Default,
        patterns: vec![u::PathPattern {
            binding: None,
            vertices: vec![vertex(binding, label)],
            edges: vec![],
            mode: u::PathMode::Walk,
            selector: u::PathSelector::All,
        }],
        optional: false,
    }
}
pub fn project(input: R, items: Vec<u::NamedExpr>) -> R {
    R::Project {
        input: Box::new(input),
        items,
        distinct: false,
    }
}
pub struct Case {
    pub name: &'static str,
    pub plan: u::Plan,
    pub expected: serde_json::Value,
    pub ordered: bool,
}
pub fn cases() -> Vec<Case> {
    let mut cases = crate::basic_cases::cases();
    cases.extend(crate::path_cases::cases());
    cases
}
pub fn values() -> HashMap<String, Expr> {
    HashMap::from([(
        "minimum".into(),
        Expr {
            kind: grust_resolved_plan::query::Value::Literal(u::Literal::Integer(30)),
            ty: Some(LogicalType::Int64),
            nullable: false,
        },
    )])
}

/// Qualification plugin, lowered without introducing storage or engine pointers.
pub struct RelationPlugins;
impl grust_resolution::query::providers::RelationProviders for RelationPlugins {
    fn lower(
        &self,
        name: &FunctionName,
        inputs: &[R],
        arguments: &[E],
    ) -> Result<Option<R>, ResolveError> {
        if name.name != "keep_above" {
            return Ok(None);
        }
        if inputs.len() != 1 || arguments.len() != 1 {
            return Err(ResolveError::Unsupported {
                operator: "keep_above".into(),
                reason: "one relation and threshold required".into(),
            });
        }
        Ok(Some(R::Filter {
            input: Box::new(inputs[0].clone()),
            predicate: E::variable("value").binary(u::BinaryOp::Gt, arguments[0].clone()),
        }))
    }
}
