//! Immutable name resolution, validated invocation and checked result batches.

use std::collections::{BTreeMap, BTreeSet};
use std::sync::Arc;

use grust_core::Value;

use crate::{ExecutionContext, MemoryReservation, ProcedureDefinition, ProcedureError, Result};

mod validation;
use validation::{validate_arguments, validate_definition};

/// Owned, normalized arguments. Construction is restricted to signature validation.
#[derive(Debug)]
pub struct ValidatedArguments {
    pub(super) positional: Vec<Value>,
    pub(super) options: BTreeMap<String, Value>,
    pub(super) reservation: Option<MemoryReservation>,
}

impl ValidatedArguments {
    /// Positional values with missing defaults filled in.
    pub fn positional(&self) -> &[Value] {
        &self.positional
    }
    /// Validated configuration with defaults filled in.
    pub fn options(&self) -> &BTreeMap<String, Value> {
        &self.options
    }
}

/// Inputs owned by the caller for one provider invocation.
///
/// The immutable borrow pins the graph for the cursor lifetime. Named snapshot
/// capabilities and backend admission are supplied by the query adapter.
pub struct Invocation<'a> {
    /// Explicit local graph, if the provider requires it.
    pub snapshot: Option<crate::LocalSnapshot<'a>>,
    /// Optional query-scoped preparation reuse. Graph-free providers receive none.
    pub cache: Option<&'a crate::InvocationCache>,
    /// Shared query resource and cancellation state.
    pub execution: &'a ExecutionContext,
}

/// Open extension point. Providers contain no Cypher parser or executor types.
pub trait ProcedureProvider: Send + Sync {
    /// Open a bounded cursor after signature and admission validation.
    /// Implementations charge allocations before creating them and poll during
    /// long loops. Errors must retain their original provider cause.
    fn open<'a>(
        &'a self,
        args: ValidatedArguments,
        invocation: Invocation<'a>,
    ) -> Result<Box<dyn ProcedureCursor + 'a>>;
}

/// Synchronous demand-driven cursor; no prefetch or implicit task spawning.
pub trait ProcedureCursor {
    /// Return a nonempty bounded owned batch or end of stream. Any error is
    /// terminal; consumers must not report preceding partial output as complete.
    fn next_batch(&mut self) -> Result<Option<ProcedureBatch>>;
}

/// Immutable owned rows whose memory admission survives cursor destruction.
#[derive(Clone, Debug)]
pub struct ProcedureBatch {
    rows: Arc<Vec<Vec<Value>>>,
    reservation: MemoryReservation,
}

impl ProcedureBatch {
    /// Attach a reservation acquired **before** constructing the rows. The
    /// reservation must include outer/inner vector capacity and nested payloads.
    /// Consumers validate its minimum size, schema, and query ownership.
    pub fn new(rows: Vec<Vec<Value>>, reservation: MemoryReservation) -> Self {
        Self {
            rows: Arc::new(rows),
            reservation,
        }
    }

    /// Borrow ordered rows. Cloning a batch shares rows and their reservation.
    pub fn rows(&self) -> &[Vec<Value>] {
        &self.rows
    }

    /// Accounted bytes retained with this batch.
    pub fn reserved_bytes(&self) -> usize {
        self.reservation.bytes()
    }
}

struct Registered {
    definition: ProcedureDefinition,
    provider: Arc<dyn ProcedureProvider>,
    registry_catalog: bool,
}

/// Handle pinning a definition and implementation together across registry changes.
#[derive(Clone)]
pub struct ResolvedProcedure(Arc<Registered>);

impl ResolvedProcedure {
    /// Immutable authoritative metadata, also used for introspection and planning.
    pub fn definition(&self) -> &ProcedureDefinition {
        &self.0.definition
    }

    /// Validate arity before executing any incoming row.
    pub fn validate_arity(&self, count: usize) -> Result<()> {
        let args = &self.0.definition.arguments;
        let required = args.iter().take_while(|arg| arg.default.is_none()).count();
        if !(required..=args.len()).contains(&count) {
            if args.is_empty() {
                return Err(ProcedureError::InvalidArguments(format!(
                    "{} expects no arguments",
                    self.0.definition.name
                )));
            }
            return Err(ProcedureError::InvalidArguments(format!(
                "{} expects {required}..={} arguments, got {count}",
                self.0.definition.name,
                args.len()
            )));
        }
        Ok(())
    }

    /// Resolve a YIELD name before invocation. Output names are case-sensitive.
    pub fn output_index(&self, name: &str) -> Result<usize> {
        self.0
            .definition
            .outputs
            .iter()
            .position(|field| field.name == name)
            .ok_or_else(|| ProcedureError::UnknownOutput(name.to_owned()))
    }

    /// Validate dynamic values and options without invoking the provider.
    pub fn validate_arguments(&self, args: Vec<Value>) -> Result<ValidatedArguments> {
        self.validate_arity(args.len())?;
        validate_arguments(&self.0.definition, args)
    }

    /// Validate one statically known argument even when other arguments are
    /// correlated. A configuration map is checked against the option schema.
    pub fn validate_argument(&self, index: usize, value: &Value) -> Result<()> {
        validation::validate_argument(&self.0.definition, index, value).map(drop)
    }

    /// Validate input and open a schema-checking cursor. Read-only execution
    /// adapters must additionally admit the definition's mode and graph scope.
    pub fn open<'a>(
        &'a self,
        args: Vec<Value>,
        mut invocation: Invocation<'a>,
    ) -> Result<Box<dyn ProcedureCursor + 'a>> {
        invocation.execution.checkpoint()?;
        self.validate_arity(args.len())?;
        let reservation = invocation
            .execution
            .reserve(validation::argument_memory_bytes(&self.0.definition, &args))?;
        let mut args = self.validate_arguments(args)?;
        args.reservation = Some(reservation);
        if self.0.definition.graph == crate::GraphRequirement::None {
            invocation.snapshot = None;
            invocation.cache = None;
        }
        if invocation
            .cache
            .is_some_and(|cache| !cache.belongs_to(invocation.execution))
        {
            return Err(ProcedureError::OutputContract(
                "preparation cache belongs to another query".into(),
            ));
        }
        if self.0.definition.graph == crate::GraphRequirement::LocalSnapshot
            && invocation.snapshot.is_none()
        {
            return Err(ProcedureError::Unsupported(
                "local snapshot required".into(),
            ));
        }
        let execution = invocation.execution;
        let cursor = self.0.provider.open(args, invocation)?;
        Ok(Box::new(CheckedCursor {
            state: CursorState::Active(cursor),
            definition: &self.0.definition,
            execution,
        }))
    }
}

struct CheckedCursor<'a> {
    state: CursorState<'a>,
    definition: &'a ProcedureDefinition,
    execution: &'a ExecutionContext,
}

enum CursorState<'a> {
    Active(Box<dyn ProcedureCursor + 'a>),
    Complete,
    Failed,
}

impl ProcedureCursor for CheckedCursor<'_> {
    fn next_batch(&mut self) -> Result<Option<ProcedureBatch>> {
        let cursor = match &mut self.state {
            CursorState::Active(cursor) => cursor,
            CursorState::Complete => return Ok(None),
            CursorState::Failed => return Err(ProcedureError::CursorFailed),
        };
        let result = (|| {
            self.execution.checkpoint()?;
            let Some(batch) = cursor.next_batch()? else {
                return Ok(None);
            };
            if batch.rows.is_empty() || batch.rows.len() > self.execution.limits().batch_rows {
                return Err(ProcedureError::OutputContract(
                    "empty or oversized batch".into(),
                ));
            }
            if !batch.reservation.belongs_to(self.execution) {
                return Err(ProcedureError::OutputContract(
                    "batch charged to another query".into(),
                ));
            }
            let mut bytes = batch
                .rows
                .capacity()
                .saturating_mul(size_of::<Vec<Value>>());
            for row in batch.rows.iter() {
                self.execution.charge_work(1)?;
                if row.len() != self.definition.outputs.len()
                    || !row
                        .iter()
                        .zip(&self.definition.outputs)
                        .all(|(value, field)| field.accepts(value))
                {
                    return Err(ProcedureError::OutputContract(
                        "row differs from registered schema".into(),
                    ));
                }
                bytes = bytes.saturating_add(row.capacity().saturating_mul(size_of::<Value>()));
                for value in row {
                    bytes = bytes.saturating_add(validation::value_payload_bytes(value));
                }
            }
            if bytes > batch.reserved_bytes() {
                return Err(ProcedureError::OutputContract(
                    "batch reservation does not cover owned rows".into(),
                ));
            }
            Ok(Some(batch))
        })();
        match &result {
            Ok(Some(_)) => {}
            Ok(None) => self.state = CursorState::Complete,
            Err(_) => self.state = CursorState::Failed,
        }
        result
    }
}

/// Mutable construction phase. Duplicate registration leaves it unchanged.
#[derive(Default)]
pub struct RegistryBuilder {
    entries: BTreeMap<String, ResolvedProcedure>,
}

impl RegistryBuilder {
    /// Register a definition and all aliases as one atomic operation.
    pub fn register(
        &mut self,
        definition: ProcedureDefinition,
        provider: Arc<dyn ProcedureProvider>,
    ) -> Result<()> {
        self.register_inner(definition, provider, false)
    }

    /// Register `db.procedures`. Its rows bind to the final immutable generation
    /// at build time, including providers registered after this call. Extending
    /// a registry rebuilds the new catalog without changing old prepared plans.
    pub fn register_catalog(&mut self) -> Result<()> {
        self.register_inner(
            crate::catalog::definition(),
            Arc::new(crate::catalog::Catalog::new(std::iter::empty())),
            true,
        )
    }

    fn register_inner(
        &mut self,
        mut definition: ProcedureDefinition,
        provider: Arc<dyn ProcedureProvider>,
        registry_catalog: bool,
    ) -> Result<()> {
        validate_definition(&definition)?;
        definition.name.make_ascii_lowercase();
        for alias in &mut definition.aliases {
            alias.make_ascii_lowercase();
        }
        let mut names = BTreeSet::new();
        for name in std::iter::once(&definition.name).chain(&definition.aliases) {
            if self.entries.contains_key(name) || !names.insert(name.clone()) {
                return Err(ProcedureError::DuplicateName(name.clone()));
            }
        }
        let registered = ResolvedProcedure(Arc::new(Registered {
            definition,
            provider,
            registry_catalog,
        }));
        for name in names {
            self.entries.insert(name, registered.clone());
        }
        Ok(())
    }

    /// Freeze the registry. Prepared plans retain this immutable generation.
    pub fn build(mut self) -> ProcedureRegistry {
        if self.entries.values().any(|entry| entry.0.registry_catalog) {
            let catalog = Arc::new(crate::catalog::Catalog::new(
                self.entries
                    .iter()
                    .filter(|(name, entry)| **name == entry.definition().name)
                    .map(|(_, entry)| entry.definition()),
            ));
            for entry in self
                .entries
                .values_mut()
                .filter(|entry| entry.0.registry_catalog)
            {
                *entry = ResolvedProcedure(Arc::new(Registered {
                    definition: entry.definition().clone(),
                    provider: catalog.clone(),
                    registry_catalog: true,
                }));
            }
        }
        ProcedureRegistry {
            entries: Arc::new(self.entries),
        }
    }
}

pub(crate) fn owned_row_bytes(row: &Vec<Value>) -> usize {
    row.iter().fold(
        row.capacity().saturating_mul(size_of::<Value>()),
        |bytes, value| bytes.saturating_add(validation::value_payload_bytes(value)),
    )
}

/// Immutable registry generation, cheaply shared by prepared plans.
#[derive(Clone, Default)]
pub struct ProcedureRegistry {
    entries: Arc<BTreeMap<String, ResolvedProcedure>>,
}

impl ProcedureRegistry {
    /// Resolve case-insensitively, retaining the provider and schema together.
    pub fn resolve(&self, name: &str) -> Result<ResolvedProcedure> {
        self.entries
            .get(&name.to_ascii_lowercase())
            .cloned()
            .ok_or_else(|| ProcedureError::UnknownProcedure(name.to_owned()))
    }

    /// Introspect each canonical definition once, in name order.
    pub fn definitions(&self) -> impl Iterator<Item = &ProcedureDefinition> {
        self.entries
            .iter()
            .filter(|(name, entry)| **name == entry.definition().name)
            .map(|(_, entry)| entry.definition())
    }

    /// Start an independent generation while leaving existing plans pinned.
    pub fn extend(&self) -> RegistryBuilder {
        RegistryBuilder {
            entries: (*self.entries).clone(),
        }
    }
}
