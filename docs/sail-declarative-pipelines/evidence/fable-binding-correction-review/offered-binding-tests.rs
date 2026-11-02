//! Unit tests for pre-resolution read binding, plus checks of the
//! classifier against the actual `PlanResolver` for CTE handling.

use std::collections::HashMap;

use datafusion::arrow::datatypes::{DataType, Field, Schema};
use datafusion::datasource::MemTable;
use datafusion::prelude::SessionContext;
use sail_plan::config::PlanConfig;
use sail_plan::resolver::PlanResolver;

use super::*;
use crate::pipelines::graph::Output;
use crate::spark::connect::OutputType;
use crate::spark::connect::pipeline_command::DefineOutput;

fn name(parts: &[&str]) -> Name {
    parts.iter().map(|part| part.to_string()).collect()
}

fn output(parts: &[&str]) -> Output {
    Output {
        name: name(parts),
        kind: OutputType::Table,
        definition: DefineOutput::default(),
        schema: None,
        view: None,
    }
}

fn read(table: &str, streaming: bool) -> spec::QueryPlan {
    spec::QueryPlan::new(spec::QueryNode::Read {
        read_type: spec::ReadType::NamedTable(Box::new(spec::ReadNamedTable {
            name: spec::ObjectName::bare(table),
            temporal: None,
            sample: None,
            options: vec![],
        })),
        is_streaming: streaming,
    })
}

fn graph() -> GraphDefinition {
    GraphDefinition {
        catalog: "c".into(),
        database: "d".into(),
        sql_conf: HashMap::new(),
        outputs: vec![output(&["c", "d", "events"]), output(&["c", "d", "target"])],
        flows: vec![],
    }
}

fn flow(query: spec::QueryPlan) -> Flow {
    Flow {
        name: name(&["c", "d", "target"]),
        target: name(&["c", "d", "target"]),
        query,
        sql_conf: HashMap::new(),
        catalog: "c".into(),
        database: "d".into(),
        auto_cdc: None,
    }
}

type TestResult = Result<(), Box<dyn std::error::Error>>;

fn provider() -> Result<Arc<dyn TableProvider>, Box<dyn std::error::Error>> {
    let schema = Arc::new(Schema::new(vec![Field::new("id", DataType::Int64, false)]));
    Ok(Arc::new(MemTable::try_new(schema, vec![vec![]])?))
}

fn source(parts: &[&str]) -> SourceBinding {
    SourceBinding {
        name: name(parts),
        schema: Arc::new(Schema::new(vec![Field::new("id", DataType::Int64, false)])),
        descriptor: SourceDescriptor {
            kind: "test".into(),
            descriptor: serde_json::json!({}),
            partitions: vec![],
        },
        intent: BatchIntent { ranges: vec![] },
        scans: vec![],
    }
}

fn statik(parts: &[&str]) -> StaticBinding {
    StaticBinding {
        name: name(parts),
        identity: "version:7".into(),
    }
}

fn validate(
    plan: spec::QueryPlan,
    sources: &[SourceBinding],
    statics: &[StaticBinding],
) -> Result<ReadSet, BindingError> {
    let ctx = SessionContext::new();
    let graph = graph();
    let flow = flow(plan.clone());
    validate_reads(&ctx, &graph, &flow, &plan, sources, statics)
}

#[test]
fn a_bound_streaming_read_and_a_local_batch_read_are_accepted_and_qualified() -> TestResult {
    let plan = spec::QueryPlan::new(spec::QueryNode::Join(spec::Join {
        left: Box::new(read("Clicks", true)),
        right: Box::new(read("EVENTS", false)),
        join_type: spec::JoinType::Inner,
        join_criteria: None,
        join_data_type: None,
    }));
    let reads = validate(plan, &[source(&["c", "d", "clicks"])], &[])?;
    assert_eq!(
        reads.streaming,
        BTreeSet::from([name(&["c", "d", "clicks"])])
    );
    assert_eq!(reads.local, BTreeSet::from([name(&["c", "d", "events"])]));
    assert!(reads.statics.is_empty());
    Ok(())
}

#[test]
fn unbound_reads_are_refused_before_resolution() -> TestResult {
    assert_eq!(
        validate(read("clicks", true), &[], &[]),
        Err(BindingError::UnboundStreamingRead(name(&[
            "c", "d", "clicks"
        ])))
    );
    assert_eq!(
        validate(read("dim", false), &[], &[]),
        Err(BindingError::UnboundCatalogRead(name(&["c", "d", "dim"])))
    );
    let reads = validate(read("dim", false), &[], &[statik(&["c", "d", "dim"])])?;
    assert_eq!(reads.statics, BTreeSet::from([name(&["c", "d", "dim"])]));
    Ok(())
}

#[test]
fn one_name_in_both_modes_is_refused_instead_of_renamed() -> TestResult {
    let plan = spec::QueryPlan::new(spec::QueryNode::Join(spec::Join {
        left: Box::new(read("events", true)),
        right: Box::new(read("events", false)),
        join_type: spec::JoinType::Inner,
        join_criteria: None,
        join_data_type: None,
    }));
    assert_eq!(
        validate(plan, &[source(&["c", "d", "events"])], &[]),
        Err(BindingError::MixedReadModes(name(&["c", "d", "events"])))
    );
    Ok(())
}

#[test]
fn helper_executing_constructs_are_refused() -> TestResult {
    let streaming = || read("clicks", true);
    let sources = [source(&["c", "d", "clicks"])];
    let mut temporal = read("clicks", true);
    if let spec::QueryNode::Read {
        read_type: spec::ReadType::NamedTable(table),
        ..
    } = &mut temporal.node
    {
        table.temporal = Some(spec::TableTemporal::Version {
            value: spec::Expr::Literal(spec::Literal::Int64 { value: Some(3) }),
        });
    }
    assert_eq!(
        validate(temporal, &sources, &[]),
        Err(BindingError::TimeTravel(name(&["c", "d", "clicks"])))
    );
    let pivot = spec::QueryPlan::new(spec::QueryNode::Pivot(spec::Pivot {
        input: Box::new(streaming()),
        grouping: None,
        aggregate: vec![],
        columns: vec![],
        values: vec![],
    }));
    assert_eq!(
        validate(pivot, &sources, &[]),
        Err(BindingError::PivotInference)
    );
    let tail = spec::QueryPlan::new(spec::QueryNode::Tail {
        input: Box::new(streaming()),
        limit: spec::Expr::Literal(spec::Literal::Int32 { value: Some(1) }),
    });
    assert_eq!(validate(tail, &sources, &[]), Err(BindingError::Tail));
    let describe = spec::QueryPlan::new(spec::QueryNode::StatDescribe {
        input: Box::new(streaming()),
        columns: vec![],
    });
    assert_eq!(
        validate(describe, &sources, &[]),
        Err(BindingError::StatHelper("describe"))
    );
    Ok(())
}

#[test]
fn a_cte_name_is_not_a_table_read_and_its_definition_is_walked() -> TestResult {
    let plan = spec::QueryPlan::new(spec::QueryNode::WithCtes {
        input: Box::new(read("staged", false)),
        recursive: false,
        ctes: vec![("staged".into(), read("clicks", true))],
    });
    let reads = validate(plan, &[source(&["c", "d", "clicks"])], &[])?;
    assert_eq!(
        reads.streaming,
        BTreeSet::from([name(&["c", "d", "clicks"])])
    );
    assert!(reads.local.is_empty());
    let unbound = spec::QueryPlan::new(spec::QueryNode::WithCtes {
        input: Box::new(read("staged", false)),
        recursive: false,
        ctes: vec![("staged".into(), read("missing", true))],
    });
    assert_eq!(
        validate(unbound, &[], &[]),
        Err(BindingError::UnboundStreamingRead(name(&[
            "c", "d", "missing"
        ])))
    );
    Ok(())
}

#[test]
fn a_binding_must_be_compatible_with_its_own_intent_and_descriptor() -> TestResult {
    use super::super::source::{Cursor, Incarnation, Partition, PartitionId, Range};
    let range = |partition: &str, incarnation: &str| Range {
        partition: PartitionId(partition.into()),
        incarnation: Incarnation(incarnation.into()),
        start: Cursor("pos:0".into()),
        end: Cursor("pos:2".into()),
    };
    let mut binding = source(&["c", "d", "clicks"]);
    binding.descriptor.partitions = vec![Partition {
        id: PartitionId("p0".into()),
        incarnation: Incarnation("inc:1".into()),
    }];
    binding.intent.ranges = vec![range("p0", "inc:1")];
    assert_eq!(
        check_source(&binding),
        Err(BindingError::ScanCountMismatch {
            name: name(&["c", "d", "clicks"]),
            ranges: 1,
            scans: 0,
        })
    );
    binding.scans = vec![provider()?];
    assert_eq!(check_source(&binding), Ok(()));
    // A recreated partition is outside the captured descriptor.
    binding.intent.ranges = vec![range("p0", "inc:2")];
    assert_eq!(
        check_source(&binding),
        Err(BindingError::RangeOutsideDescriptor {
            name: name(&["c", "d", "clicks"]),
            range: 0,
        })
    );
    binding.intent.ranges = vec![range("p0", "inc:1")];
    let other = Arc::new(Schema::new(vec![Field::new("id", DataType::Utf8, true)]));
    binding.scans = vec![Arc::new(MemTable::try_new(other, vec![vec![]])?)];
    assert_eq!(
        check_source(&binding),
        Err(BindingError::ScanSchemaMismatch {
            name: name(&["c", "d", "clicks"]),
            range: 0,
        })
    );
    // An empty recorded intent is valid and distinct from an absent binding.
    binding.intent.ranges = vec![];
    binding.scans = vec![];
    assert_eq!(check_source(&binding), Ok(()));
    assert_eq!(
        validate(
            read("dim", false),
            &[],
            &[StaticBinding {
                name: name(&["c", "d", "dim"]),
                identity: String::new(),
            }]
        ),
        Err(BindingError::StaticIdentityMissing(name(&[
            "c", "d", "dim"
        ])))
    );
    Ok(())
}

#[test]
fn unsupported_read_kinds_are_refused() -> TestResult {
    let plan = spec::QueryPlan::new(spec::QueryNode::Read {
        read_type: spec::ReadType::DataSource(Box::new(spec::ReadDataSource {
            format: Some("parquet".into()),
            schema: None,
            options: vec![],
            paths: vec!["/tmp/x".into()],
            predicates: vec![],
        })),
        is_streaming: true,
    });
    assert_eq!(
        validate(plan, &[], &[]),
        Err(BindingError::UnsupportedRead("data source"))
    );
    Ok(())
}

fn scalar_subquery(plan: spec::QueryPlan) -> spec::Expr {
    spec::Expr::ScalarSubquery {
        subquery: Box::new(plan),
    }
}

fn exists(plan: spec::QueryPlan) -> spec::Expr {
    spec::Expr::Exists {
        subquery: Box::new(plan),
        negated: false,
    }
}

fn in_subquery(plan: spec::QueryPlan) -> spec::Expr {
    spec::Expr::InSubquery {
        expr: Box::new(spec::Expr::UnresolvedAttribute {
            name: spec::ObjectName::bare("id"),
            plan_id: None,
            is_metadata_column: false,
        }),
        subquery: Box::new(plan),
        negated: false,
    }
}

fn function(name: &str, arguments: Vec<spec::Expr>) -> spec::Expr {
    spec::Expr::UnresolvedFunction(spec::UnresolvedFunction {
        function_name: spec::ObjectName::bare(name),
        arguments,
        named_arguments: vec![],
        is_user_defined_function: false,
        is_distinct: false,
        is_internal: None,
        ignore_nulls: None,
        filter: None,
        order_by: None,
    })
}

fn project(input: Option<spec::QueryPlan>, expressions: Vec<spec::Expr>) -> spec::QueryPlan {
    spec::QueryPlan::new(spec::QueryNode::Project {
        input: input.map(Box::new),
        expressions,
    })
}

fn filter(input: spec::QueryPlan, condition: spec::Expr) -> spec::QueryPlan {
    spec::QueryPlan::new(spec::QueryNode::Filter {
        input: Box::new(input),
        condition,
    })
}

#[test]
fn reads_embedded_in_expressions_are_classified_before_resolution() -> TestResult {
    let sources = [source(&["c", "d", "clicks"])];
    let missing = || name(&["c", "d", "missing"]);
    // CF-0143 counterexample 1: a projection without input whose expression
    // holds a scalar subquery over an unbound batch read.
    let projection = project(None, vec![scalar_subquery(read("missing", false))]);
    assert_eq!(
        validate(projection, &sources, &[]),
        Err(BindingError::UnboundCatalogRead(missing()))
    );
    // CF-0143 counterexample 2: a bound streaming input filtered by EXISTS
    // over an unbound batch read.
    let predicate = filter(read("clicks", true), exists(read("missing", false)));
    assert_eq!(
        validate(predicate, &sources, &[]),
        Err(BindingError::UnboundCatalogRead(missing()))
    );
    // Nested: IN subquery inside a function argument inside an alias.
    let nested = project(
        Some(read("clicks", true)),
        vec![spec::Expr::Alias {
            expr: Box::new(function(
                "coalesce",
                vec![in_subquery(read("missing", false))],
            )),
            name: vec!["x".into()],
            metadata: None,
        }],
    );
    assert_eq!(
        validate(nested, &sources, &[]),
        Err(BindingError::UnboundCatalogRead(missing()))
    );
    // Join condition carrying a subquery.
    let join = spec::QueryPlan::new(spec::QueryNode::Join(spec::Join {
        left: Box::new(read("clicks", true)),
        right: Box::new(read("events", false)),
        join_type: spec::JoinType::Inner,
        join_criteria: Some(spec::JoinCriteria::On(exists(read("missing", false)))),
        join_data_type: None,
    }));
    assert_eq!(
        validate(join, &sources, &[]),
        Err(BindingError::UnboundCatalogRead(missing()))
    );
    // Helper-executing constructs inside an expression subquery.
    let pivot = spec::QueryPlan::new(spec::QueryNode::Pivot(spec::Pivot {
        input: Box::new(read("events", false)),
        grouping: None,
        aggregate: vec![],
        columns: vec![],
        values: vec![],
    }));
    assert_eq!(
        validate(
            project(Some(read("clicks", true)), vec![scalar_subquery(pivot)]),
            &sources,
            &[]
        ),
        Err(BindingError::PivotInference)
    );
    let mut temporal = read("events", false);
    if let spec::QueryNode::Read {
        read_type: spec::ReadType::NamedTable(table),
        ..
    } = &mut temporal.node
    {
        table.temporal = Some(spec::TableTemporal::Version {
            value: spec::Expr::Literal(spec::Literal::Int64 { value: Some(1) }),
        });
    }
    assert_eq!(
        validate(
            filter(read("clicks", true), exists(temporal)),
            &sources,
            &[]
        ),
        Err(BindingError::TimeTravel(name(&["c", "d", "events"])))
    );
    // A bound read inside a subquery is accepted and recorded.
    let bound = filter(read("clicks", true), exists(read("events", false)));
    let reads = validate(bound, &sources, &[])?;
    assert_eq!(reads.local, BTreeSet::from([name(&["c", "d", "events"])]));
    Ok(())
}

#[test]
fn duplicate_and_ambiguous_bindings_are_refused() -> TestResult {
    let dup = [source(&["c", "d", "clicks"]), source(&["c", "d", "CLICKS"])];
    assert_eq!(
        validate(read("clicks", true), &dup, &[]),
        Err(BindingError::DuplicateBinding(name(&["c", "d", "CLICKS"])))
    );
    let ambiguous = [statik(&["c", "d", "clicks"])];
    assert_eq!(
        validate(
            read("clicks", true),
            &[source(&["c", "d", "clicks"])],
            &ambiguous
        ),
        Err(BindingError::AmbiguousBinding(name(&["c", "d", "clicks"])))
    );
    let dup_static = [statik(&["c", "d", "dim"]), statik(&["c", "d", "Dim"])];
    assert_eq!(
        validate(read("dim", false), &[], &dup_static),
        Err(BindingError::DuplicateBinding(name(&["c", "d", "Dim"])))
    );
    Ok(())
}

fn with_ctes(
    ctes: Vec<(&str, spec::QueryPlan)>,
    input: spec::QueryPlan,
    recursive: bool,
) -> spec::QueryPlan {
    spec::QueryPlan::new(spec::QueryNode::WithCtes {
        input: Box::new(input),
        recursive,
        ctes: ctes
            .into_iter()
            .map(|(name, plan)| (spec::Identifier::from(name), plan))
            .collect(),
    })
}

/// Resolves `plan` with the actual `PlanResolver` over a `GraphScope` in
/// which `c.d.events` is an installed local output, returning the error
/// text if resolution fails. This is the behaviour the classifier is
/// aligned with; a catalog lookup of an unknown name errors here, which is
/// exactly the resolver I/O the pre-walk must prevent.
async fn resolve(plan: spec::QueryPlan) -> Result<(), String> {
    use datafusion::arrow::datatypes::Schema as ArrowSchema;
    use datafusion::common::DFSchema;
    use datafusion::logical_expr::{EmptyRelation, LogicalPlan};
    let ctx = SessionContext::new();
    let graph = graph();
    let flow = flow(plan.clone());
    let schema = ArrowSchema::new(vec![Field::new("id", DataType::Int64, false)]);
    let relation = LogicalPlan::EmptyRelation(EmptyRelation {
        produce_one_row: false,
        schema: Arc::new(DFSchema::try_from(schema).map_err(|e| e.to_string())?),
    });
    let resolved = BTreeMap::from([(name(&["c", "d", "events"]), relation)]);
    let scope = GraphScope::new(&graph, &resolved, &flow);
    PlanResolver::new(&ctx, Arc::new(PlanConfig::default()))
        .with_relation_scope(&scope)
        .resolve_named_plan(spec::Plan::Query(plan))
        .await
        .map(|_| ())
        .map_err(|e| e.to_string())
}

#[tokio::test]
async fn cte_handling_matches_the_resolver() -> TestResult {
    // Shadowing: the resolver keeps the last definition, so the earlier one
    // reading an unknown name is never resolved; the classifier does not
    // walk it either.
    let shadowed = with_ctes(
        vec![("t", read("missing", false)), ("t", read("events", false))],
        read("t", false),
        false,
    );
    assert_eq!(resolve(shadowed.clone()).await, Ok(()));
    assert!(validate(shadowed, &[], &[]).is_ok());
    // Case: the CTE scope is keyed by the literal bare name, so `T` is not
    // the CTE `t`; the resolver reaches the catalog for `c.d.t` (an error
    // here), and the classifier refuses it before resolution.
    let cased = with_ctes(vec![("t", read("events", false))], read("T", false), false);
    assert!(resolve(cased.clone()).await.is_err());
    assert_eq!(
        validate(cased, &[], &[]),
        Err(BindingError::UnboundCatalogRead(name(&["c", "d", "t"])))
    );
    // Time travel on a CTE name is refused by the resolver before any lookup
    // and by the classifier.
    let mut temporal = read("t", false);
    if let spec::QueryNode::Read {
        read_type: spec::ReadType::NamedTable(table),
        ..
    } = &mut temporal.node
    {
        table.temporal = Some(spec::TableTemporal::Version {
            value: spec::Expr::Literal(spec::Literal::Int64 { value: Some(1) }),
        });
    }
    let travelled = with_ctes(vec![("t", read("events", false))], temporal, false);
    let error = resolve(travelled.clone()).await.err().unwrap_or_default();
    assert!(error.contains("time travel"), "{error}");
    assert_eq!(
        validate(travelled, &[], &[]),
        Err(BindingError::TimeTravel(name(&["t"])))
    );
    // A streaming read of a CTE name is substituted by the resolver; the
    // classifier accepts it without requiring a source binding.
    let streamed = with_ctes(vec![("t", read("events", false))], read("t", true), false);
    assert_eq!(resolve(streamed.clone()).await, Ok(()));
    let reads = validate(streamed, &[], &[])?;
    assert!(reads.streaming.is_empty());
    assert_eq!(reads.local, BTreeSet::from([name(&["c", "d", "events"])]));
    Ok(())
}

// CF-0143 review fixtures, replayed verbatim from Codex's detached candidate
// 3e6ca3c34 on ebf631edd (where both failed with Ok(..)).
#[test]
fn codex_review_unbound_scalar_subquery_must_be_refused_before_resolution() {
    let plan = spec::QueryPlan::new(spec::QueryNode::Project {
        input: None,
        expressions: vec![spec::Expr::ScalarSubquery {
            subquery: Box::new(read("missing", false)),
        }],
    });
    let result = validate(plan, &[], &[]);
    assert!(
        matches!(result, Err(BindingError::UnboundCatalogRead(_))),
        "unbound scalar subquery passed: {result:?}"
    );
}

#[test]
fn codex_review_unbound_exists_predicate_must_be_refused_before_resolution() {
    let plan = spec::QueryPlan::new(spec::QueryNode::Filter {
        input: Box::new(read("clicks", true)),
        condition: spec::Expr::Exists {
            subquery: Box::new(read("missing", false)),
            negated: false,
        },
    });
    let result = validate(plan, &[source(&["c", "d", "clicks"])], &[]);
    assert!(
        matches!(result, Err(BindingError::UnboundCatalogRead(_))),
        "unbound predicate subquery passed: {result:?}"
    );
}
