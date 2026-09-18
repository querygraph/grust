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
fn a_deadline_that_expires_mid_run_is_observed_within_the_sampling_interval() {
    // Charges sample the clock, so expiry is observed within the interval rather
    // than on the first charge after it passes. It must still be observed.
    let execution = ExecutionContext::new(ExecutionLimits {
        memory_bytes: 4096,
        work_units: usize::MAX,
        batch_rows: 1,
        deadline: Some(std::time::Instant::now() + std::time::Duration::from_millis(50)),
    })
    .expect("valid limits");
    execution.charge_work(1).expect("before the deadline");
    std::thread::sleep(std::time::Duration::from_millis(80));
    let mut charges = 0usize;
    let outcome = loop {
        match execution.charge_work(1) {
            Ok(()) => charges += 1,
            Err(error) => break error,
        }
        assert!(charges <= 4096, "expiry was never observed");
    };
    assert!(matches!(outcome, ProcedureError::DeadlineExceeded));
    assert!(charges < 2048, "observed after {charges} charges");
}

#[test]
fn an_explicit_checkpoint_observes_expiry_without_waiting_for_a_sample() {
    let execution = ExecutionContext::new(ExecutionLimits {
        memory_bytes: 4096,
        work_units: usize::MAX,
        batch_rows: 1,
        deadline: Some(std::time::Instant::now() + std::time::Duration::from_millis(50)),
    })
    .expect("valid limits");
    // Land between samples, so only an exact check can observe the deadline.
    for _ in 0..8 {
        execution.charge_work(1).expect("before the deadline");
    }
    std::thread::sleep(std::time::Duration::from_millis(80));
    assert!(matches!(
        execution.checkpoint(),
        Err(ProcedureError::DeadlineExceeded)
    ));
}

#[test]
fn cancellation_and_budgets_are_never_sampled() {
    let execution = ExecutionContext::new(ExecutionLimits {
        memory_bytes: 4096,
        work_units: 10,
        batch_rows: 1,
        deadline: Some(std::time::Instant::now() + std::time::Duration::from_secs(3600)),
    })
    .expect("valid limits");
    // An exhausted budget fails exactly at its limit, at any sampling offset.
    for _ in 0..10 {
        execution.charge_work(1).expect("within budget");
    }
    assert!(matches!(
        execution.charge_work(1),
        Err(ProcedureError::BudgetExceeded { .. })
    ));
    let execution = ExecutionContext::new(ExecutionLimits {
        memory_bytes: 4096,
        work_units: usize::MAX,
        batch_rows: 1,
        deadline: Some(std::time::Instant::now() + std::time::Duration::from_secs(3600)),
    })
    .expect("valid limits");
    execution.charge_work(1).expect("before cancellation");
    execution.cancel().expect("cancel");
    // Immediately, not at the next sample.
    assert!(matches!(
        execution.charge_work(1),
        Err(ProcedureError::Cancelled)
    ));
    assert!(matches!(
        execution.checkpoint(),
        Err(ProcedureError::Cancelled)
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
