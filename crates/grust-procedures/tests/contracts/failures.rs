use super::*;

enum Fault {
    WrongType,
    WrongWidth,
    EmptyBatch,
    TooManyRows,
    Undercharged,
    ForeignReservation,
    ProviderFailure,
}

struct FaultyProvider(Fault);

impl ProcedureProvider for FaultyProvider {
    fn open<'a>(
        &'a self,
        _args: ValidatedArguments,
        invocation: Invocation<'a>,
    ) -> Result<Box<dyn ProcedureCursor + 'a>> {
        let scratch = invocation.execution.reserve(32)?;
        Ok(Box::new(FaultyCursor {
            fault: &self.0,
            execution: invocation.execution,
            _scratch: scratch,
        }))
    }
}

struct FaultyCursor<'a> {
    fault: &'a Fault,
    execution: &'a ExecutionContext,
    _scratch: MemoryReservation,
}

impl ProcedureCursor for FaultyCursor<'_> {
    fn next_batch(&mut self) -> Result<Option<ProcedureBatch>> {
        // Deliberate provider violations. Production providers reserve before
        // allocation; these fixtures exercise rejection at the cursor boundary.
        let rows = match self.fault {
            Fault::WrongType => vec![vec![Value::Null]],
            Fault::WrongWidth => vec![vec![]],
            Fault::EmptyBatch => vec![],
            Fault::TooManyRows => vec![vec![Value::Int(1)]; 3],
            Fault::Undercharged | Fault::ForeignReservation => vec![vec![Value::Int(1)]],
            Fault::ProviderFailure => {
                return Err(ProcedureError::Provider(Box::new(std::io::Error::other(
                    "fixture failure",
                ))));
            }
        };
        let reservation = match self.fault {
            Fault::Undercharged => self.execution.reserve(0)?,
            Fault::ForeignReservation => context(4096).reserve(1024)?,
            Fault::WrongType
            | Fault::WrongWidth
            | Fault::EmptyBatch
            | Fault::TooManyRows
            | Fault::ProviderFailure => self.execution.reserve(1024)?,
        };
        Ok(Some(ProcedureBatch::new(rows, reservation)))
    }
}

#[test]
fn malformed_batches_fail_and_immediately_release_provider_scratch() {
    for fault in [
        Fault::WrongType,
        Fault::WrongWidth,
        Fault::EmptyBatch,
        Fault::TooManyRows,
        Fault::Undercharged,
        Fault::ForeignReservation,
    ] {
        let mut builder = RegistryBuilder::default();
        builder
            .register(definition(), Arc::new(FaultyProvider(fault)))
            .expect("registered");
        let procedure = builder.build().resolve("test.echo").expect("resolve");
        let execution = context(4096);
        let mut cursor = procedure
            .open(
                vec![Value::Int(1)],
                Invocation {
                    snapshot: None,
                    cache: None,
                    execution: &execution,
                },
            )
            .expect("open");
        assert_eq!(execution.usage().expect("usage").live_bytes, 32);
        assert!(matches!(
            cursor.next_batch(),
            Err(ProcedureError::OutputContract(_))
        ));
        assert_eq!(execution.usage().expect("usage").live_bytes, 0);
        assert!(matches!(
            cursor.next_batch(),
            Err(ProcedureError::CursorFailed)
        ));
    }
}

#[test]
fn provider_failure_preserves_the_original_cause_and_never_becomes_success() {
    let mut builder = RegistryBuilder::default();
    builder
        .register(
            definition(),
            Arc::new(FaultyProvider(Fault::ProviderFailure)),
        )
        .expect("registered");
    let procedure = builder.build().resolve("test.echo").expect("resolve");
    let execution = context(4096);
    let mut cursor = procedure
        .open(
            vec![Value::Int(1)],
            Invocation {
                snapshot: None,
                cache: None,
                execution: &execution,
            },
        )
        .expect("open");
    let Err(ProcedureError::Provider(source)) = cursor.next_batch() else {
        panic!("provider source must survive");
    };
    assert_eq!(
        source
            .downcast_ref::<std::io::Error>()
            .expect("typed source")
            .kind(),
        std::io::ErrorKind::Other
    );
    assert_eq!(execution.usage().expect("usage").live_bytes, 0);
    assert!(matches!(
        cursor.next_batch(),
        Err(ProcedureError::CursorFailed)
    ));
}

#[test]
fn cancellation_during_consumption_releases_cursor_state() {
    let mut builder = RegistryBuilder::default();
    builder
        .register(definition(), Arc::new(FaultyProvider(Fault::WrongType)))
        .expect("registered");
    let procedure = builder.build().resolve("test.echo").expect("resolve");
    let execution = context(4096);
    let mut cursor = procedure
        .open(
            vec![Value::Int(1)],
            Invocation {
                snapshot: None,
                cache: None,
                execution: &execution,
            },
        )
        .expect("open");
    execution.cancel().expect("cancel");
    assert!(matches!(
        cursor.next_batch(),
        Err(ProcedureError::Cancelled)
    ));
    assert_eq!(execution.usage().expect("usage").live_bytes, 0);
    assert!(matches!(
        cursor.next_batch(),
        Err(ProcedureError::CursorFailed)
    ));
}

#[test]
fn expired_deadline_rejects_before_provider_invocation() {
    let provider = Arc::new(Echo::default());
    let mut builder = RegistryBuilder::default();
    builder
        .register(definition(), provider.clone())
        .expect("registered");
    let procedure = builder.build().resolve("test.echo").expect("resolve");
    let execution = ExecutionContext::new(ExecutionLimits {
        memory_bytes: 4096,
        work_units: 100,
        batch_rows: 1,
        deadline: Some(std::time::Instant::now()),
    })
    .expect("valid limits");
    assert!(matches!(
        procedure.open(
            vec![Value::Int(1)],
            Invocation {
                snapshot: None,
                cache: None,
                execution: &execution
            }
        ),
        Err(ProcedureError::DeadlineExceeded)
    ));
    assert_eq!(*provider.calls.lock().expect("counter"), 0);
}
