//! External provider proof through the ordinary Cypher parser and read executor.

use std::sync::{Arc, Mutex};

use grust_core::{Graph, Value};
use grust_cypher::procedures::*;
use grust_cypher::{CypherParameters, run_read_query_with_registry};

struct Echo {
    seen: Mutex<Vec<i64>>,
}

impl ProcedureProvider for Echo {
    fn open<'a>(
        &'a self,
        args: ValidatedArguments,
        invocation: Invocation<'a>,
    ) -> Result<Box<dyn ProcedureCursor + 'a>> {
        assert!(
            invocation.snapshot.is_none(),
            "graph-free provider has no graph capability"
        );
        let [Value::Int(value)] = args.positional() else {
            panic!("registered signature validates one integer");
        };
        self.seen.lock().expect("counter").push(*value);
        let reservation = invocation
            .execution
            .reserve(size_of::<Vec<Value>>() + size_of::<Value>())?;
        Ok(Box::new(One(Some(ProcedureBatch::new(
            vec![vec![Value::Int(*value)]],
            reservation,
        )))))
    }
}

struct One(Option<ProcedureBatch>);
impl ProcedureCursor for One {
    fn next_batch(&mut self) -> Result<Option<ProcedureBatch>> {
        Ok(self.0.take())
    }
}

struct SnapshotProbe(Mutex<Vec<SnapshotIdentity>>);

impl ProcedureProvider for SnapshotProbe {
    fn open<'a>(
        &'a self,
        _args: ValidatedArguments,
        invocation: Invocation<'a>,
    ) -> Result<Box<dyn ProcedureCursor + 'a>> {
        let snapshot = invocation.snapshot.expect("declared graph requirement");
        self.0.lock().unwrap().push(snapshot.identity().clone());
        Ok(Box::new(One(None)))
    }
}

#[test]
fn prepared_execution_preserves_authorized_snapshot_identity() {
    let (base, _) = registry();
    let mut definition = base.resolve("example.echo").unwrap().definition().clone();
    definition.name = "example.snapshot".into();
    definition.aliases.clear();
    definition.arguments.clear();
    definition.graph = GraphRequirement::LocalSnapshot;
    definition.mode = ProcedureMode::Read;
    let probe = Arc::new(SnapshotProbe(Mutex::new(Vec::new())));
    let mut builder = RegistryBuilder::default();
    builder.register(definition, probe.clone()).unwrap();
    let registry = builder.build();
    let query = grust_cypher::PreparedProcedureQuery::prepare(
        "analytics",
        "USE analytics CALL example.snapshot() YIELD value RETURN value",
        &registry,
    )
    .unwrap();
    let graph = Graph::default();
    let identity = SnapshotIdentity::new(
        "analytics".into(),
        "transaction-7".into(),
        "tenant-reader".into(),
    )
    .unwrap();
    query
        .execute_snapshot(
            LocalSnapshot::new(&graph, &identity),
            &CypherParameters::new(),
        )
        .unwrap();
    assert_eq!(probe.0.lock().unwrap().as_slice(), &[identity]);
    let wrong = SnapshotIdentity::new(
        "other".into(),
        "transaction-8".into(),
        "tenant-reader".into(),
    )
    .unwrap();
    assert!(
        query
            .execute_snapshot(LocalSnapshot::new(&graph, &wrong), &CypherParameters::new())
            .is_err()
    );
    assert_eq!(probe.0.lock().unwrap().len(), 1);
    query.execute(&graph, &CypherParameters::new()).unwrap();
    let identities = probe.0.lock().unwrap();
    assert_eq!(identities[1].graph(), "analytics");
    assert_eq!(identities[1].principal(), "local-caller");
    assert_ne!(identities[1].revision(), identities[0].revision());
}

#[test]
fn cypher_catalog_tracks_the_final_registry_and_pins_prepared_generations() {
    let (registry, echo) = registry();
    let query =
        "CALL db.procedures() YIELD name WHERE name STARTS WITH 'example.' RETURN count(name)";
    let prepared =
        grust_cypher::PreparedProcedureQuery::prepare("default", query, &registry).unwrap();
    let mut extension = registry.extend();
    let mut definition = registry
        .resolve("example.echo")
        .unwrap()
        .definition()
        .clone();
    definition.name = "example.second".into();
    definition.aliases.clear();
    extension.register(definition, echo).unwrap();
    let extended = extension.build();
    assert_eq!(
        prepared
            .execute(&Graph::default(), &CypherParameters::new())
            .unwrap()
            .rows,
        vec![vec![Value::Int(1)]]
    );
    assert_eq!(
        run_read_query_with_registry(
            &Graph::default(),
            "default",
            query,
            &CypherParameters::new(),
            &extended
        )
        .unwrap()
        .rows,
        vec![vec![Value::Int(2)]]
    );
    let metadata = run_read_query_with_registry(&Graph::default(), "default", "CALL db.procedures() YIELD name, inputs, outputs, graph WHERE name = 'example.echo' RETURN inputs, outputs, graph", &CypherParameters::new(), &registry).unwrap();
    assert_eq!(
        metadata.rows,
        vec![vec![
            Value::StringArray(vec!["input:Integer default=None".into()]),
            Value::StringArray(vec!["value:Integer".into()]),
            Value::String("None".into())
        ]]
    );
}

#[test]
fn explain_uses_pinned_metadata_and_native_requests_do_not_fallback() {
    use grust_cypher::{PreparedProcedureQuery, ProcedureExecutionTarget, ProcedureRowExecution};
    let (registry, echo) = registry();
    let prepared = PreparedProcedureQuery::prepare(
        "default",
        "CALL example.echo(1) YIELD value RETURN value LIMIT 1",
        &registry,
    )
    .unwrap();
    let plan = prepared.explain().unwrap();
    assert_eq!(plan.target, ProcedureExecutionTarget::LocalSnapshot);
    assert_eq!(plan.pipelines, vec![ProcedureRowExecution::Incremental]);
    assert_eq!(plan.calls[0].definition.provider, "external.integration");
    assert_eq!(plan.calls[0].definition.name, "example.echo");
    assert_eq!(plan.calls[0].yields, vec![("value".into(), None)]);
    assert!(plan.snapshot.is_none());
    let graph = Graph::default();
    let identity = grust_cypher::procedures::SnapshotIdentity::new(
        "default".into(),
        "revision-one".into(),
        "reader-one".into(),
    )
    .unwrap();
    let bound = prepared
        .explain_snapshot(grust_cypher::procedures::LocalSnapshot::new(
            &graph, &identity,
        ))
        .unwrap();
    assert_eq!(bound.snapshot.as_ref(), Some(&identity));
    let blocking = PreparedProcedureQuery::prepare(
        "default",
        "CALL example.echo(1) YIELD value RETURN collect(value)",
        &registry,
    )
    .unwrap()
    .explain()
    .unwrap();
    assert_eq!(
        blocking.pipelines,
        vec![ProcedureRowExecution::Materializing]
    );
    assert!(
        PreparedProcedureQuery::prepare_for_target(
            "default",
            "CALL example.echo(1) YIELD value RETURN value",
            &registry,
            ProcedureExecutionTarget::BackendNative
        )
        .is_err()
    );
    assert!(echo.seen.lock().unwrap().is_empty());
}

fn registry() -> (ProcedureRegistry, Arc<Echo>) {
    registry_with_mode(ProcedureMode::Table)
}

fn registry_with_mode(mode: ProcedureMode) -> (ProcedureRegistry, Arc<Echo>) {
    let echo = Arc::new(Echo {
        seen: Mutex::new(Vec::new()),
    });
    let mut builder = RegistryBuilder::default();
    register_builtins(&mut builder).expect("builtins");
    builder
        .register(
            ProcedureDefinition {
                name: "example.echo".into(),
                aliases: vec!["example.identity".into()],
                version: 1,
                provider: "external.integration".into(),
                arguments: vec![Argument {
                    field: Field {
                        name: "input".into(),
                        value_type: ValueType::Integer,
                        nullable: false,
                    },
                    default: None,
                }],
                options_argument: None,
                options: vec![],
                outputs: vec![Field {
                    name: "value".into(),
                    value_type: ValueType::Integer,
                    nullable: false,
                }],
                mode,
                determinism: Determinism::Deterministic,
                correlation: Correlation::PerRow,
                graph: GraphRequirement::None,
                streaming: Streaming::Incremental,
            },
            echo.clone(),
        )
        .expect("external provider");
    (builder.build(), echo)
}

#[test]
fn external_provider_is_correlated_and_supports_aliases_and_yield_filtering() {
    let (registry, echo) = registry();
    let result = run_read_query_with_registry(&Graph::default(), "default",
        "UNWIND [3, 1, 3] AS input CALL EXAMPLE.IDENTITY(input) YIELD value AS output WHERE output > 1 RETURN output",
        &CypherParameters::new(), &registry).expect("ordinary Cypher dispatches external provider");
    assert_eq!(result.columns, ["output"]);
    assert_eq!(result.rows, vec![vec![Value::Int(3)], vec![Value::Int(3)]]);
    assert_eq!(*echo.seen.lock().expect("calls"), [3, 1, 3]);
}

#[test]
fn whole_query_signature_validation_precedes_every_invocation() {
    for query in [
        "CALL example.echo(1) YIELD value WITH value CALL example.echo(2) YIELD missing RETURN missing",
        "UNWIND [] AS input CALL example.echo(null) YIELD value RETURN value",
        "CALL example.missing() YIELD value RETURN value",
        "CALL example.echo() YIELD value RETURN value",
    ] {
        let (registry, echo) = registry();
        let error = run_read_query_with_registry(
            &Graph::default(),
            "default",
            query,
            &CypherParameters::new(),
            &registry,
        )
        .expect_err("invalid metadata/arguments");
        assert!(matches!(
            error,
            grust_core::GrustError::CypherUnresolvedIdentity(_)
                | grust_core::GrustError::CypherExecution(_)
                | grust_core::GrustError::Unsupported(_)
        ));
        assert!(
            echo.seen.lock().expect("calls").is_empty(),
            "no provider may run before preflight completes"
        );
    }
}

#[test]
fn call_subqueries_keep_the_same_registry_and_per_row_correlation() {
    let (registry, echo) = registry();
    let result = run_read_query_with_registry(&Graph::default(), "default",
        "UNWIND [1, 2] AS input CALL { CALL example.echo(input) YIELD value RETURN value } RETURN input, value",
        &CypherParameters::new(), &registry).expect("nested CALL uses caller registry");
    assert_eq!(
        result.rows,
        vec![
            vec![Value::Int(1), Value::Int(1)],
            vec![Value::Int(2), Value::Int(2)]
        ]
    );
    assert_eq!(*echo.seen.lock().expect("calls"), [1, 2]);
}

#[test]
fn named_graph_mismatch_is_rejected_before_external_invocation() {
    let (registry, echo) = registry();
    run_read_query_with_registry(
        &Graph::default(),
        "selected",
        "USE other CALL example.echo(1) YIELD value RETURN value",
        &CypherParameters::new(),
        &registry,
    )
    .expect_err("cannot change the selected graph");
    assert!(echo.seen.lock().expect("calls").is_empty());
}

#[test]
fn prepared_query_pins_its_provider_generation_and_revalidates_parameters() {
    use grust_cypher::PreparedProcedureQuery;
    let (mut registry, echo) = registry();
    let prepared = PreparedProcedureQuery::prepare(
        "selected",
        "CALL example.echo($input) RETURN value",
        &registry,
    )
    .expect("schema resolves implicit YIELD without parameters");
    registry = ProcedureRegistry::default();
    assert!(matches!(
        registry.resolve("example.echo"),
        Err(ProcedureError::UnknownProcedure(_))
    ));
    assert_eq!(prepared.graph_name(), "selected");
    assert!(
        prepared
            .definitions()
            .any(|definition| definition.provider == "external.integration"
                && definition.version == 1)
    );
    let result = prepared
        .execute(
            &Graph::default(),
            &CypherParameters::from([("input".into(), Value::Int(42))]),
        )
        .expect("old generation remains owned by the plan");
    assert_eq!(result.rows, vec![vec![Value::Int(42)]]);
    let error = prepared
        .execute(
            &Graph::default(),
            &CypherParameters::from([("input".into(), Value::Null)]),
        )
        .expect_err("parameter types are checked per execution");
    assert!(matches!(error, grust_core::GrustError::CypherExecution(_)));
    assert_eq!(*echo.seen.lock().expect("counter"), [42]);
}

#[test]
fn implicit_yield_scopes_work_for_default_and_bounded_registry_entrypoints() {
    use grust_cypher::{ReadQueryPolicy, run_bounded_read_query_with_registry};
    let table = grust_cypher::read::run_read_query(
        &Graph::default(),
        "CALL tvf.range(1, 2) RETURN value",
        &CypherParameters::new(),
    )
    .expect("default registry supplies CALL output scope");
    assert_eq!(table.rows, vec![vec![Value::Int(1)], vec![Value::Int(2)]]);
    let (registry, _) = registry();
    let policy = ReadQueryPolicy {
        require_match: false,
        allow_catalog_procedures: true,
        ..ReadQueryPolicy::default()
    };
    let table = run_bounded_read_query_with_registry(
        &Graph::default(),
        "default",
        "CALL example.echo(7) RETURN value LIMIT 1",
        &CypherParameters::new(),
        &policy,
        &registry,
    )
    .expect("bounded scope comes from the same metadata");
    assert_eq!(table.rows, vec![vec![Value::Int(7)]]);
}

#[test]
fn bounded_admission_keeps_catalog_and_graph_reads_separate() {
    use grust_cypher::{ReadQueryPolicy, run_bounded_read_query_with_registry};
    for (mode, catalog, reads, allowed) in [
        (ProcedureMode::Table, true, false, true),
        (ProcedureMode::Table, false, true, false),
        (ProcedureMode::Read, false, true, true),
        (ProcedureMode::Read, true, false, false),
        (ProcedureMode::Write, true, true, false),
    ] {
        let (registry, echo) = registry_with_mode(mode);
        let policy = ReadQueryPolicy {
            require_match: false,
            allow_catalog_procedures: catalog,
            allow_read_procedures: reads,
            ..ReadQueryPolicy::default()
        };
        let result = run_bounded_read_query_with_registry(
            &Graph::default(),
            "default",
            "CALL example.echo(7) YIELD value RETURN value LIMIT 1",
            &CypherParameters::new(),
            &policy,
            &registry,
        );
        if allowed {
            assert_eq!(
                result.expect("admitted mode").rows,
                vec![vec![Value::Int(7)]]
            );
            assert_eq!(*echo.seen.lock().expect("counter"), [7]);
        } else {
            assert!(matches!(
                result,
                Err(grust_core::GrustError::CypherSyntax(_))
            ));
            assert!(echo.seen.lock().expect("counter").is_empty());
        }
    }
}

#[test]
fn provider_batch_and_downstream_copies_consume_one_memory_allowance() {
    use grust_cypher::{ReadQueryPolicy, run_bounded_read_query_with_registry};
    let (registry, _) = registry();
    let policy = ReadQueryPolicy {
        require_match: false,
        allow_catalog_procedures: true,
        // The batch alone fits exactly. Copying it into the legacy binding
        // pipeline must fail while the provider's reservation is still live.
        max_intermediate_bytes: size_of::<Vec<Value>>() + size_of::<Value>(),
        ..ReadQueryPolicy::default()
    };
    let result = run_bounded_read_query_with_registry(
        &Graph::default(),
        "default",
        "CALL example.echo(7) YIELD value RETURN value LIMIT 1",
        &CypherParameters::new(),
        &policy,
        &registry,
    );
    let Err(grust_core::GrustError::CypherExecution(message)) = result else {
        panic!("provider allocation and legacy copies cannot receive separate allowances");
    };
    assert!(
        message.contains("cumulative intermediate bytes"),
        "{message}"
    );
}
