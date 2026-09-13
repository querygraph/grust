//! Shared cooperative limits with reservations retained by buffer owners.

use std::sync::{Arc, Mutex};
use std::time::Instant;

use crate::{ProcedureError, Result};

/// Limits shared by projection preparation, kernels and consumers.
#[derive(Clone, Copy, Debug)]
pub struct ExecutionLimits {
    /// Maximum concurrently retained accounted memory, in bytes.
    pub memory_bytes: usize,
    /// Maximum cumulative work units.
    pub work_units: usize,
    /// Maximum rows returned in one provider batch; must be positive.
    pub batch_rows: usize,
    /// Optional caller-owned deadline, shared across all execution phases.
    pub deadline: Option<Instant>,
}

/// Accounted live/peak bytes and cumulative work, not allocator/RSS measurements.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct ResourceUsage {
    /// Bytes retained by live reservations.
    pub live_bytes: usize,
    /// Largest live reservation total so far.
    pub peak_bytes: usize,
    /// Cumulative admitted work.
    pub work_units: usize,
}

#[derive(Debug, Default)]
struct State {
    usage: ResourceUsage,
    cancelled: bool,
}

#[derive(Debug)]
struct Shared {
    limits: ExecutionLimits,
    state: Mutex<State>,
}

/// Cloneable handle to one query's resource state; no global state or worker pool.
#[derive(Clone, Debug)]
pub struct ExecutionContext(Arc<Shared>);

impl ExecutionContext {
    pub(crate) fn same_query(&self, other: &Self) -> bool {
        Arc::ptr_eq(&self.0, &other.0)
    }
    /// Establish a bounded execution. Zero memory/work limits admit no such work.
    ///
    /// # Errors
    /// Rejects zero batch size.
    pub fn new(limits: ExecutionLimits) -> Result<Self> {
        if limits.batch_rows == 0 {
            return Err(ProcedureError::InvalidArguments(
                "batch_rows must be positive".into(),
            ));
        }
        Ok(Self(Arc::new(Shared {
            limits,
            state: Mutex::new(State::default()),
        })))
    }

    /// Read immutable limits.
    pub fn limits(&self) -> ExecutionLimits {
        self.0.limits
    }

    /// Signal cancellation to all owners. Cancellation never resets.
    pub fn cancel(&self) -> Result<()> {
        self.0
            .state
            .lock()
            .map_err(|_| ProcedureError::ResourceStatePoisoned)?
            .cancelled = true;
        Ok(())
    }

    /// Poll cancellation and deadline without charging work.
    pub fn checkpoint(&self) -> Result<()> {
        self.charge_work(0)
    }

    /// Charge work before performing it. Counter overflow is a budget failure.
    pub fn charge_work(&self, units: usize) -> Result<()> {
        let mut state = self
            .0
            .state
            .lock()
            .map_err(|_| ProcedureError::ResourceStatePoisoned)?;
        self.check_state(&state)?;
        state.usage.work_units = state
            .usage
            .work_units
            .checked_add(units)
            .filter(|next| *next <= self.0.limits.work_units)
            .ok_or(ProcedureError::BudgetExceeded {
                resource: "work",
                limit: self.0.limits.work_units,
            })?;
        Ok(())
    }

    fn check_state(&self, state: &State) -> Result<()> {
        if state.cancelled {
            return Err(ProcedureError::Cancelled);
        }
        if self
            .0
            .limits
            .deadline
            .is_some_and(|deadline| Instant::now() >= deadline)
        {
            return Err(ProcedureError::DeadlineExceeded);
        }
        Ok(())
    }

    /// Reserve bytes before allocating. Retain the token beside the allocation.
    ///
    /// Cloning a token shares its charge. Only dropping its last owner releases
    /// memory admission; dropping the context/cursor alone does not.
    pub fn reserve(&self, bytes: usize) -> Result<MemoryReservation> {
        self.charge_memory(bytes)?;
        Ok(MemoryReservation(Arc::new(Reservation {
            context: self.clone(),
            bytes,
        })))
    }

    /// Check admission without reserving or changing measured peak usage.
    /// The actual owner must still reserve before allocating.
    pub fn check_memory_available(&self, bytes: usize) -> Result<()> {
        let state = self
            .0
            .state
            .lock()
            .map_err(|_| ProcedureError::ResourceStatePoisoned)?;
        self.check_state(&state)?;
        state
            .usage
            .live_bytes
            .checked_add(bytes)
            .filter(|next| *next <= self.0.limits.memory_bytes)
            .ok_or(ProcedureError::BudgetExceeded {
                resource: "memory",
                limit: self.0.limits.memory_bytes,
            })?;
        Ok(())
    }

    /// Account temporary allocations with one lexical owner. Individual charges
    /// are admitted before allocation and all release when the owner drops.
    /// Values backed by this account must not escape its lifetime.
    pub fn memory_account(&self) -> MemoryAccount {
        MemoryAccount {
            context: self.clone(),
            bytes: 0,
        }
    }

    /// Charge bytes copied by a legacy materializing consumer for the remainder
    /// of this query. Unlike a live reservation, this cumulative charge is never
    /// refunded. Both forms consume the same memory envelope, so alternating
    /// provider allocations and downstream copies cannot acquire two allowances.
    pub fn charge_cumulative_memory(&self, bytes: usize) -> Result<()> {
        self.charge_memory(bytes)
    }

    fn charge_memory(&self, bytes: usize) -> Result<()> {
        let mut state = self
            .0
            .state
            .lock()
            .map_err(|_| ProcedureError::ResourceStatePoisoned)?;
        self.check_state(&state)?;
        let next = state
            .usage
            .live_bytes
            .checked_add(bytes)
            .filter(|next| *next <= self.0.limits.memory_bytes)
            .ok_or(ProcedureError::BudgetExceeded {
                resource: "memory",
                limit: self.0.limits.memory_bytes,
            })?;
        state.usage.live_bytes = next;
        state.usage.peak_bytes = state.usage.peak_bytes.max(next);
        Ok(())
    }

    /// Current accounted usage, including batches retained by a consumer.
    pub fn usage(&self) -> Result<ResourceUsage> {
        Ok(self
            .0
            .state
            .lock()
            .map_err(|_| ProcedureError::ResourceStatePoisoned)?
            .usage)
    }
}

/// An exclusive owner of temporary allocation admission. Unlike a reservation,
/// it can grow without allocating a token per scalar or intermediate row.
pub struct MemoryAccount {
    context: ExecutionContext,
    bytes: usize,
}

impl MemoryAccount {
    /// Shared execution state for this account.
    pub fn execution(&self) -> &ExecutionContext {
        &self.context
    }
    /// Admit another temporary allocation before constructing it.
    pub fn charge(&mut self, bytes: usize) -> Result<()> {
        self.context.charge_memory(bytes)?;
        // Shared admission already checked the sum of all live accounts.
        self.bytes += bytes;
        Ok(())
    }
    /// Bytes admitted for the owner's lifetime.
    pub fn bytes(&self) -> usize {
        self.bytes
    }
}

impl Drop for MemoryAccount {
    fn drop(&mut self) {
        let mut state = self
            .context
            .0
            .state
            .lock()
            .unwrap_or_else(|poison| poison.into_inner());
        state.usage.live_bytes -= self.bytes;
    }
}

#[derive(Debug)]
struct Reservation {
    context: ExecutionContext,
    bytes: usize,
}

impl Drop for Reservation {
    fn drop(&mut self) {
        // Recover only for cleanup; operational calls still report poisoning.
        let mut state = self
            .context
            .0
            .state
            .lock()
            .unwrap_or_else(|poison| poison.into_inner());
        state.usage.live_bytes -= self.bytes;
    }
}

/// Shared memory admission token. Leaking it conservatively retains the charge.
#[derive(Clone, Debug)]
pub struct MemoryReservation(Arc<Reservation>);

impl MemoryReservation {
    /// Number of accounted bytes retained by this token.
    pub fn bytes(&self) -> usize {
        self.0.bytes
    }

    pub(crate) fn belongs_to(&self, context: &ExecutionContext) -> bool {
        Arc::ptr_eq(&self.0.context.0, &context.0)
    }
}
