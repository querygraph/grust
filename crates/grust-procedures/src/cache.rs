//! Query-scoped preparation reuse; never a process-global result cache.

use crate::{ExecutionContext, MemoryReservation, ProcedureError, Result};
use std::{
    any::Any,
    collections::BTreeMap,
    sync::{Arc, Mutex},
};

struct Entry {
    value: Arc<dyn Any + Send + Sync>,
    _reservation: MemoryReservation,
}

struct CachedValue<T> {
    value: T,
    _reservation: MemoryReservation,
}

/// Shared prepared value whose inline storage admission outlives cache removal.
/// Any heap buffers inside T remain the responsibility of T's owning tokens.
pub struct CachedPreparation<T>(Arc<CachedValue<T>>);

impl<T> Clone for CachedPreparation<T> {
    fn clone(&self) -> Self {
        Self(self.0.clone())
    }
}
impl<T> AsRef<T> for CachedPreparation<T> {
    fn as_ref(&self) -> &T {
        &self.0.value
    }
}
impl<T> std::ops::Deref for CachedPreparation<T> {
    type Target = T;
    fn deref(&self) -> &T {
        &self.0.value
    }
}

/// Preparation cache owned by one invocation sequence. Cached values must own
/// their allocation reservations. Entry/key overhead consumes the same query
/// envelope. Keys must include provider namespace, immutable snapshot/principal
/// identity and every preparation option. Algorithm outputs are not cached.
pub struct InvocationCache {
    execution: ExecutionContext,
    entries: Mutex<BTreeMap<String, Entry>>,
}

impl InvocationCache {
    /// Create a cache for one query's execution context.
    pub fn new(execution: ExecutionContext) -> Self {
        Self {
            execution,
            entries: Mutex::new(BTreeMap::new()),
        }
    }

    /// Return existing preparation or initialize it exactly once. Initialization
    /// is serialized and must not reenter this cache. Failed initialization is
    /// not retained. A key reused for a different Rust type is an explicit error.
    pub fn get_or_try_init<T: Any + Send + Sync>(
        &self,
        key: &str,
        initialize: impl FnOnce() -> Result<T>,
    ) -> Result<CachedPreparation<T>> {
        self.execution.checkpoint()?;
        let mut entries = self
            .entries
            .lock()
            .map_err(|_| ProcedureError::ResourceStatePoisoned)?;
        if let Some(entry) = entries.get(key) {
            return entry
                .value
                .clone()
                .downcast::<CachedValue<T>>()
                .map(CachedPreparation)
                .map_err(|_| {
                    ProcedureError::OutputContract(
                        "preparation cache key has a different type".into(),
                    )
                });
        }
        let reservation = self
            .execution
            .reserve(key.len().saturating_add(2 * size_of::<(String, Entry)>()))?;
        let value_reservation = self
            .execution
            .reserve(size_of::<CachedValue<T>>().saturating_add(2 * size_of::<usize>()))?;
        let value = Arc::new(CachedValue {
            value: initialize()?,
            _reservation: value_reservation,
        });
        entries.insert(
            key.to_owned(),
            Entry {
                value: value.clone(),
                _reservation: reservation,
            },
        );
        Ok(CachedPreparation(value))
    }

    pub(crate) fn belongs_to(&self, execution: &ExecutionContext) -> bool {
        self.execution.same_query(execution)
    }
}
