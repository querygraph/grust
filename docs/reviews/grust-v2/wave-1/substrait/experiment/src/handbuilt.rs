//! A Substrait plan built directly from protobuf structs, the way a Grust
//! emitter would build one: no SQL text and no DataFusion planner involved.
//!
//! Shape: Grust's fixed-segment pushdown for `(n0)-[e0]->(n1)-[e1]->(n2)`,
//! that is `n0 JOIN e0 ON e0.source = n0.id JOIN n1 ON n1.id = e0.target
//! JOIN e1 ON e1.source = n1.id JOIN n2 ON n2.id = e1.target`.

use substrait::proto::{
    AggregateFunction, AggregateRel, AggregationPhase, Expression, FilterRel, FunctionArgument,
    JoinRel, NamedStruct, Plan, PlanRel, ProjectRel, ReadRel, Rel, RelCommon, RelRoot, Type,
    aggregate_function::AggregationInvocation,
    aggregate_rel::Measure,
    expression::{
        FieldReference, Literal, ReferenceSegment, RexType, ScalarFunction, field_reference,
        literal::LiteralType, reference_segment,
    },
    extensions::{
        SimpleExtensionDeclaration, SimpleExtensionUrn,
        simple_extension_declaration::{ExtensionFunction, MappingType},
    },
    function_argument::ArgType,
    join_rel::JoinType,
    plan_rel, read_rel,
    rel::RelType,
    rel_common::{Emit, EmitKind},
    r#type::{self, Kind, Nullability},
};

// Function anchors. Names follow the Substrait standard extension YAML
// (compound names `name:arg_types`); URNs follow the spec's URN scheme.
const EQUAL: u32 = 1;
const AND: u32 = 2;
const GTE: u32 = 3;
const LT: u32 = 4;
const COUNT: u32 = 5;
const SUM: u32 = 6;

fn i64_type(nullable: bool) -> Type {
    Type {
        kind: Some(Kind::I64(r#type::I64 {
            type_variation_reference: 0,
            nullability: if nullable {
                Nullability::Nullable
            } else {
                Nullability::Required
            } as i32,
        })),
    }
}

fn bool_type() -> Type {
    Type {
        kind: Some(Kind::Bool(r#type::Boolean {
            type_variation_reference: 0,
            nullability: Nullability::Nullable as i32,
        })),
    }
}

fn field(i: i32) -> Expression {
    Expression {
        rex_type: Some(RexType::Selection(Box::new(FieldReference {
            reference_type: Some(field_reference::ReferenceType::DirectReference(
                ReferenceSegment {
                    reference_type: Some(reference_segment::ReferenceType::StructField(
                        Box::new(reference_segment::StructField {
                            field: i,
                            child: None,
                        }),
                    )),
                },
            )),
            root_type: Some(field_reference::RootType::RootReference(
                field_reference::RootReference {},
            )),
        }))),
    }
}

fn lit_i64(v: i64) -> Expression {
    Expression {
        rex_type: Some(RexType::Literal(Literal {
            nullable: false,
            type_variation_reference: 0,
            literal_type: Some(LiteralType::I64(v)),
        })),
    }
}

fn call(anchor: u32, args: Vec<Expression>, out: Type) -> Expression {
    Expression {
        rex_type: Some(RexType::ScalarFunction(ScalarFunction {
            function_reference: anchor,
            arguments: args
                .into_iter()
                .map(|e| FunctionArgument {
                    arg_type: Some(ArgType::Value(e)),
                })
                .collect(),
            output_type: Some(out),
            ..Default::default()
        })),
    }
}

fn eq(a: i32, b: i32) -> Expression {
    call(EQUAL, vec![field(a), field(b)], bool_type())
}

fn read(table: &str, cols: &[&str]) -> Rel {
    Rel {
        rel_type: Some(RelType::Read(Box::new(ReadRel {
            base_schema: Some(NamedStruct {
                names: cols.iter().map(|c| c.to_string()).collect(),
                r#struct: Some(r#type::Struct {
                    types: cols.iter().map(|_| i64_type(true)).collect(),
                    type_variation_reference: 0,
                    nullability: Nullability::Required as i32,
                }),
            }),
            read_type: Some(read_rel::ReadType::NamedTable(read_rel::NamedTable {
                names: vec![table.to_string()],
                advanced_extension: None,
            })),
            ..Default::default()
        }))),
    }
}

fn join(left: Rel, right: Rel, on: Expression) -> Rel {
    Rel {
        rel_type: Some(RelType::Join(Box::new(JoinRel {
            left: Some(Box::new(left)),
            right: Some(Box::new(right)),
            expression: Some(Box::new(on)),
            r#type: JoinType::Inner as i32,
            ..Default::default()
        }))),
    }
}

fn filter(input: Rel, cond: Expression) -> Rel {
    Rel {
        rel_type: Some(RelType::Filter(Box::new(FilterRel {
            input: Some(Box::new(input)),
            condition: Some(Box::new(cond)),
            ..Default::default()
        }))),
    }
}

/// The five-way join of the two-hop pattern. Output columns, in Substrait's
/// left-then-right order: 0 n0.id, 1 e0.source, 2 e0.target, 3 n1.id,
/// 4 e1.source, 5 e1.target, 6 n2.id.
fn two_hop(n0_range: Option<(i64, i64)>) -> Rel {
    let mut n0 = read("v", &["id"]);
    if let Some((lo, hi)) = n0_range {
        let cond = call(
            AND,
            vec![
                call(GTE, vec![field(0), lit_i64(lo)], bool_type()),
                call(LT, vec![field(0), lit_i64(hi)], bool_type()),
            ],
            bool_type(),
        );
        n0 = filter(n0, cond);
    }
    let j1 = join(n0, read("e", &["source", "target"]), eq(1, 0)); // e0.source = n0.id
    let j2 = join(j1, read("v", &["id"]), eq(3, 2)); // n1.id = e0.target
    let j3 = join(j2, read("e", &["source", "target"]), eq(4, 3)); // e1.source = n1.id
    join(j3, read("v", &["id"]), eq(6, 5)) // n2.id = e1.target
}

fn extensions() -> (Vec<SimpleExtensionUrn>, Vec<SimpleExtensionDeclaration>) {
    let urns = vec![
        (1, "extension:io.substrait:functions_comparison"),
        (2, "extension:io.substrait:functions_boolean"),
        (3, "extension:io.substrait:functions_aggregate_generic"),
        (4, "extension:io.substrait:functions_arithmetic"),
    ]
    .into_iter()
    .map(|(anchor, urn)| SimpleExtensionUrn {
        extension_urn_anchor: anchor,
        urn: urn.to_string(),
    })
    .collect();
    let funcs = vec![
        (1, EQUAL, "equal:any_any"),
        (2, AND, "and:bool"),
        (1, GTE, "gte:any_any"),
        (1, LT, "lt:any_any"),
        (3, COUNT, "count:"),
        (4, SUM, "sum:i64"),
    ]
    .into_iter()
    .map(|(urn, anchor, name)| SimpleExtensionDeclaration {
        mapping_type: Some(MappingType::ExtensionFunction(ExtensionFunction {
            extension_urn_reference: urn,
            function_anchor: anchor,
            name: name.to_string(),
        })),
    })
    .collect();
    (urns, funcs)
}

fn plan(root: Rel, names: &[&str]) -> Plan {
    let (extension_urns, extensions) = extensions();
    Plan {
        version: Some(substrait::version::version_with_producer("grust-substrait-experiment")),
        extension_urns,
        extensions,
        relations: vec![PlanRel {
            rel_type: Some(plan_rel::RelType::Root(RelRoot {
                input: Some(root),
                names: names.iter().map(|n| n.to_string()).collect(),
            })),
        }],
        ..Default::default()
    }
}

/// `MATCH (a)-[]->(b)-[]->(c) WHERE lo <= a.id < hi RETURN a, b, c` as rows.
pub fn two_hop_rows(lo: i64, hi: i64) -> Plan {
    let joined = two_hop(Some((lo, hi)));
    // Project appends field references 7, 8, 9; Emit keeps only those.
    let project = Rel {
        rel_type: Some(RelType::Project(Box::new(ProjectRel {
            common: Some(RelCommon {
                emit_kind: Some(EmitKind::Emit(Emit {
                    output_mapping: vec![7, 8, 9],
                })),
                ..Default::default()
            }),
            input: Some(Box::new(joined)),
            expressions: vec![field(0), field(3), field(6)],
            ..Default::default()
        }))),
    };
    plan(project, &["a", "b", "c"])
}

/// The same query with the range filter placed above the joins, as SQL's
/// `WHERE` is, instead of directly on the `n0` read.
pub fn two_hop_rows_filter_on_top(lo: i64, hi: i64) -> Plan {
    let cond = call(
        AND,
        vec![
            call(GTE, vec![field(0), lit_i64(lo)], bool_type()),
            call(LT, vec![field(0), lit_i64(hi)], bool_type()),
        ],
        bool_type(),
    );
    let joined = filter(two_hop(None), cond);
    let project = Rel {
        rel_type: Some(RelType::Project(Box::new(ProjectRel {
            common: Some(RelCommon {
                emit_kind: Some(EmitKind::Emit(Emit {
                    output_mapping: vec![7, 8, 9],
                })),
                ..Default::default()
            }),
            input: Some(Box::new(joined)),
            expressions: vec![field(0), field(3), field(6)],
            ..Default::default()
        }))),
    };
    plan(project, &["a", "b", "c"])
}

/// `MATCH (a)-[]->(b)-[]->(c) RETURN count(*), sum(a.id), sum(b.id), sum(c.id)`
/// over the whole graph: a full-scale check without moving every row.
pub fn two_hop_aggregate() -> Plan {
    let joined = two_hop(None);
    let measure = |anchor: u32, args: Vec<Expression>, nullable: bool| Measure {
        measure: Some(AggregateFunction {
            function_reference: anchor,
            arguments: args
                .into_iter()
                .map(|e| FunctionArgument {
                    arg_type: Some(ArgType::Value(e)),
                })
                .collect(),
            output_type: Some(i64_type(nullable)),
            phase: AggregationPhase::InitialToResult as i32,
            invocation: AggregationInvocation::All as i32,
            ..Default::default()
        }),
        filter: None,
    };
    let agg = Rel {
        rel_type: Some(RelType::Aggregate(Box::new(AggregateRel {
            input: Some(Box::new(joined)),
            groupings: vec![],
            measures: vec![
                measure(COUNT, vec![], false),
                measure(SUM, vec![field(0)], true),
                measure(SUM, vec![field(3)], true),
                measure(SUM, vec![field(6)], true),
            ],
            ..Default::default()
        }))),
    };
    plan(agg, &["paths", "sum_a", "sum_b", "sum_c"])
}
