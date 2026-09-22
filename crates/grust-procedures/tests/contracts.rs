use std::sync::{Arc, Mutex};

use grust_core::Value;
use grust_procedures::*;

#[path = "contracts/accounting.rs"]
mod accounting;
#[path = "contracts/failures.rs"]
mod failures;

#[path = "contracts/builtins.rs"]
mod builtins;
#[path = "contracts/cache.rs"]
mod cache;
#[path = "contracts/cancellation.rs"]
mod cancellation;
#[path = "contracts/children.rs"]
mod children;
#[path = "contracts/memory.rs"]
mod memory;
#[path = "contracts/parallel.rs"]
mod parallel;

#[test]
fn temporary_memory_accounts_release_only_their_own_admission() {
    let execution = context(100);
    let retained = execution.reserve(30).unwrap();
    let peak = execution.usage().unwrap().peak_bytes;
    execution.check_memory_available(70).unwrap();
    assert_eq!(execution.usage().unwrap().peak_bytes, peak);
    {
        let mut account = execution.memory_account();
        account.charge(40).unwrap();
        assert!(account.charge(31).is_err());
        assert_eq!(account.bytes(), 40);
        assert_eq!(execution.usage().unwrap().live_bytes, 70);
    }
    assert_eq!(execution.usage().unwrap().live_bytes, 30);
    drop(retained);
    assert_eq!(execution.usage().unwrap().live_bytes, 0);
}

fn context(bytes: usize) -> ExecutionContext {
    ExecutionContext::new(ExecutionLimits {
        memory_bytes: bytes,
        work_units: 100,
        batch_rows: 2,
        deadline: None,
    })
    .expect("valid limits")
}

fn definition() -> ProcedureDefinition {
    ProcedureDefinition {
        name: "test.echo".into(),
        aliases: vec!["test.alias".into()],
        version: 1,
        provider: "external-test".into(),
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
        mode: ProcedureMode::Table,
        determinism: Determinism::Deterministic,
        correlation: Correlation::PerRow,
        graph: GraphRequirement::None,
        streaming: Streaming::Incremental,
    }
}

#[derive(Default)]
struct Echo {
    calls: Mutex<usize>,
}

impl ProcedureProvider for Echo {
    fn open<'a>(
        &'a self,
        args: ValidatedArguments,
        invocation: Invocation<'a>,
    ) -> Result<Box<dyn ProcedureCursor + 'a>> {
        *self.calls.lock().expect("test counter") += 1;
        let reservation = invocation
            .execution
            .reserve(size_of::<Vec<Value>>() + size_of::<Value>())?;
        let batch = ProcedureBatch::new(vec![vec![args.positional()[0].clone()]], reservation);
        Ok(Box::new(Once { batch: Some(batch) }))
    }
}

struct Once {
    batch: Option<ProcedureBatch>,
}
impl ProcedureCursor for Once {
    fn next_batch(&mut self) -> Result<Option<ProcedureBatch>> {
        Ok(self.batch.take())
    }
}

#[test]
fn external_provider_is_pinned_and_alias_resolution_is_case_insensitive() {
    let provider = Arc::new(Echo::default());
    let mut builder = RegistryBuilder::default();
    builder
        .register(definition(), provider.clone())
        .expect("valid provider");
    let registry = builder.build();
    let procedure = registry
        .resolve("TEST.ALIAS")
        .expect("case-insensitive alias");
    drop(registry);
    let execution = context(4096);
    let mut cursor = procedure
        .open(
            vec![Value::Int(42)],
            Invocation {
                snapshot: None,
                cache: None,
                execution: &execution,
            },
        )
        .expect("open external provider");
    let batch = cursor
        .next_batch()
        .expect("valid schema")
        .expect("one batch");
    assert_eq!(batch.rows(), &[vec![Value::Int(42)]]);
    assert!(cursor.next_batch().expect("end").is_none());
    assert_eq!(*provider.calls.lock().expect("counter"), 1);
}

#[test]
fn duplicate_alias_registration_is_atomic() {
    let mut builder = RegistryBuilder::default();
    builder
        .register(definition(), Arc::new(Echo::default()))
        .expect("first provider");
    let mut second = definition();
    second.name = "test.second".into();
    second.aliases = vec!["TEST.ALIAS".into()];
    assert!(
        matches!(builder.register(second, Arc::new(Echo::default())), Err(ProcedureError::DuplicateName(name)) if name == "test.alias")
    );
    let registry = builder.build();
    assert!(matches!(
        registry.resolve("test.second"),
        Err(ProcedureError::UnknownProcedure(_))
    ));
    assert_eq!(registry.definitions().count(), 1);
}

#[test]
fn invalid_arguments_never_invoke_provider() {
    let provider = Arc::new(Echo::default());
    let mut builder = RegistryBuilder::default();
    builder
        .register(definition(), provider.clone())
        .expect("provider");
    let procedure = builder.build().resolve("test.echo").expect("registered");
    let execution = context(4096);
    for args in [
        vec![],
        vec![Value::Null],
        vec![Value::Float(1.0)],
        vec![Value::Int(1), Value::Int(2)],
    ] {
        assert!(matches!(
            procedure.open(
                args,
                Invocation {
                    snapshot: None,
                    cache: None,
                    execution: &execution
                }
            ),
            Err(ProcedureError::InvalidArguments(_))
        ));
    }
    assert!(matches!(
        procedure.output_index("VALUE"),
        Err(ProcedureError::UnknownOutput(_))
    ));
    assert_eq!(*provider.calls.lock().expect("counter"), 0);
}

#[test]
fn options_reject_unknown_keys_and_fill_defaults_without_float_coercion() {
    let mut metadata = definition();
    metadata.arguments[0] = Argument {
        field: Field {
            name: "config".into(),
            value_type: ValueType::Map,
            nullable: false,
        },
        default: Some(Value::Json(serde_json::json!({}))),
    };
    metadata.options_argument = Some(0);
    metadata.options = vec![OptionField {
        field: Field {
            name: "iterations".into(),
            value_type: ValueType::Integer,
            nullable: false,
        },
        default: Some(Value::Int(20)),
    }];
    let mut builder = RegistryBuilder::default();
    builder
        .register(metadata, Arc::new(Echo::default()))
        .expect("options schema");
    let procedure = builder.build().resolve("test.echo").expect("registered");
    assert_eq!(
        procedure
            .validate_arguments(vec![])
            .expect("defaults")
            .options()["iterations"],
        Value::Int(20)
    );
    assert!(
        matches!(procedure.validate_arguments(vec![Value::Json(serde_json::json!({"typo": 1}))]), Err(ProcedureError::UnknownOption(key)) if key == "typo")
    );
    assert!(matches!(
        procedure.validate_arguments(vec![Value::Json(serde_json::json!({"iterations": 1.5}))]),
        Err(ProcedureError::InvalidArguments(_))
    ));
}

#[test]
fn reservations_survive_cursor_drop_and_batch_cloning() {
    let mut builder = RegistryBuilder::default();
    builder
        .register(definition(), Arc::new(Echo::default()))
        .expect("provider");
    let procedure = builder.build().resolve("test.echo").expect("registered");
    let execution = context(4096);
    let mut cursor = procedure
        .open(
            vec![Value::Int(3)],
            Invocation {
                snapshot: None,
                cache: None,
                execution: &execution,
            },
        )
        .expect("open");
    let batch = cursor.next_batch().expect("read").expect("batch");
    let retained = batch.clone();
    drop(cursor);
    drop(batch);
    assert_eq!(
        execution.usage().expect("usage").live_bytes,
        retained.reserved_bytes()
    );
    drop(retained);
    assert_eq!(execution.usage().expect("usage").live_bytes, 0);
}

#[test]
fn budget_failure_and_cancellation_release_owned_reservations() {
    let execution = context(64);
    let first = execution.reserve(64).expect("fits");
    assert!(matches!(
        execution.reserve(1),
        Err(ProcedureError::BudgetExceeded {
            resource: "memory",
            limit: 64
        })
    ));
    assert!(matches!(
        execution.charge_work(101),
        Err(ProcedureError::BudgetExceeded {
            resource: "work",
            limit: 100
        })
    ));
    assert_eq!(
        execution
            .usage()
            .expect("usage")
            .counted_work()
            .expect("counted"),
        0
    );
    execution.cancel().expect("cancel");
    assert!(matches!(
        execution.checkpoint(),
        Err(ProcedureError::Cancelled)
    ));
    drop(first);
    assert_eq!(execution.usage().expect("usage").live_bytes, 0);
}

#[test]
fn separate_queries_do_not_share_reservations_or_cancellation() {
    let first = context(1);
    let second = context(1);
    let reservation = first.reserve(1).expect("fits first");
    first.cancel().expect("cancel first");
    second.charge_work(1).expect("second not cancelled");
    let other = second.reserve(1).expect("second has own allowance");
    drop(reservation);
    assert_eq!(second.usage().expect("usage").live_bytes, other.bytes());
}

#[test]
fn cumulative_copies_and_live_reservations_share_one_envelope() {
    let execution = context(100);
    execution
        .charge_cumulative_memory(40)
        .expect("legacy copies");
    let retained = execution.reserve(60).expect("remaining allowance");
    assert!(matches!(
        execution.charge_cumulative_memory(1),
        Err(ProcedureError::BudgetExceeded {
            resource: "memory",
            limit: 100
        })
    ));
    drop(retained);
    assert_eq!(execution.usage().expect("usage").live_bytes, 40);
    execution
        .charge_cumulative_memory(60)
        .expect("released live allowance is reusable");
    assert_eq!(execution.usage().expect("usage").live_bytes, 100);
}
