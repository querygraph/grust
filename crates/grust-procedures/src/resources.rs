//! Shared cooperative limits with reservations retained by buffer owners.

use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Instant;

use crate::{ProcedureError, Result};

mod cancellation;
pub use cancellation::Cancellation;

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
    live_bytes: usize,
    peak_bytes: usize,
    waiters: Vec<Option<std::task::Waker>>,
}

/// Charges sample the deadline instead of reading the clock for every unit.
/// Kernels charge once per visited entry, so a per-unit read costs more than the
/// work it guards wherever the clocksource is paravirtualised rather than a
/// register read. Cancellation is never sampled, and `checkpoint` always reads
/// the clock, so a caller that needs an exact poll has one.
const DEADLINE_SAMPLE_UNITS: usize = 1024;

/// Work and cancellation are lock-free because kernels charge per unit of work,
/// once per visited entry or reconstructed path step. Memory reservations and
/// wakers stay behind the mutex: they are rare and need multi-field atomicity.
#[derive(Debug)]
struct Shared {
    limits: ExecutionLimits,
    concurrency: Option<usize>,
    work_units: AtomicUsize,
    cancelled: AtomicBool,
    charges_since_deadline_read: AtomicUsize,
    state: Mutex<State>,
}

/// Units a [`WorkMeter`] admits in one shared-counter operation while the budget
/// has room for a whole block. Kernels charge once per visited entry, so at N
/// workers the shared counter would otherwise be a contended cache line rather
/// than an occasional one. Near the limit the meter drops to exact admission,
/// so a budget still fails at exactly the unit that exceeds it.
pub const WORK_BLOCK_UNITS: usize = 1024;

/// Whether a state check must read the clock or may rely on the sampled read.
#[derive(Clone, Copy)]
enum DeadlineCheck {
    Exact,
    Sampled,
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
            concurrency: None,
            work_units: AtomicUsize::new(0),
            cancelled: AtomicBool::new(false),
            charges_since_deadline_read: AtomicUsize::new(0),
            state: Mutex::new(State::default()),
        })))
    }

    /// Permit kernels to use up to `workers` threads for this execution, and
    /// with it the parallel implementation of each kernel, even at one worker.
    ///
    /// Concurrency is a property of one execution, not of the process: an
    /// embedder that runs kernels inside a server with its own runtime and
    /// thread pool decides here how many threads a query may add, and the
    /// default of one keeps existing callers single-threaded. Set it before
    /// the context is shared, so no worker can observe it changing.
    ///
    /// # Errors
    /// Rejects zero workers, and a context that is already shared.
    pub fn with_concurrency(mut self, workers: usize) -> Result<Self> {
        if workers == 0 {
            return Err(ProcedureError::InvalidArguments(
                "concurrency must be at least one".into(),
            ));
        }
        let shared = Arc::get_mut(&mut self.0).ok_or_else(|| {
            ProcedureError::InvalidArguments(
                "concurrency must be set before the context is shared".into(),
            )
        })?;
        shared.concurrency = Some(workers);
        Ok(self)
    }

    /// Threads kernels may use for this execution; one unless set.
    pub fn concurrency(&self) -> usize {
        self.0.concurrency.unwrap_or(1)
    }

    /// The concurrency the caller asked for, or `None` when it never asked.
    ///
    /// Kernels distinguish the two: an execution that says nothing about
    /// threads runs exactly the code it ran before parallel paths existed,
    /// while an execution that explicitly asks for one worker runs the parallel
    /// implementation on one thread. Keeping those apart is what lets a
    /// benchmark separate the cost of threading from the change of algorithm.
    pub fn concurrency_requested(&self) -> Option<usize> {
        self.0.concurrency
    }

    /// Read immutable limits.
    pub fn limits(&self) -> ExecutionLimits {
        self.0.limits
    }

    /// Signal cancellation to all owners. Cancellation never resets.
    pub fn cancel(&self) -> Result<()> {
        // Publish cancellation before collecting wakers, so a registration that
        // races this call either observes the flag or is woken by it.
        self.0.cancelled.store(true, Ordering::Release);
        let mut state = self
            .0
            .state
            .lock()
            .map_err(|_| ProcedureError::ResourceStatePoisoned)?;
        let waiters = std::mem::take(&mut state.waiters);
        drop(state);
        for waker in waiters.into_iter().flatten() {
            waker.wake();
        }
        Ok(())
    }

    /// Poll cancellation and deadline without charging work. Unlike a charge,
    /// this always reads the clock, so an explicit poll is exact.
    pub fn checkpoint(&self) -> Result<()> {
        self.check_state(DeadlineCheck::Exact)
    }

    /// A batched work meter for one worker inside a parallel region.
    ///
    /// The meter admits [`WORK_BLOCK_UNITS`] at a time from the shared counter
    /// and spends them locally, so N workers do not contend on one cache line
    /// per visited entry. Admission stays exact: when a block does not fit, the
    /// meter admits precisely the units asked for, so the budget fails at the
    /// same unit it would fail at single-threaded. Unspent units are returned
    /// when the meter drops, so final usage counts work actually performed;
    /// [`Self::usage`] read while meters are live can exceed it by less than
    /// one block per worker.
    ///
    /// Cancellation is still observed per charge. The deadline is sampled per
    /// block, which is the same cadence per worker as a single-threaded charge.
    pub fn work_meter(&self) -> WorkMeter {
        WorkMeter {
            context: self.clone(),
            granted: 0,
        }
    }

    /// Charge work before performing it. Counter overflow is a budget failure.
    pub fn charge_work(&self, units: usize) -> Result<()> {
        self.check_state(DeadlineCheck::Sampled)?;
        self.admit_work(units)
    }

    fn admit_work(&self, units: usize) -> Result<()> {
        // Admit exactly, never overshooting the budget: the compare-exchange
        // recomputes admission against the value it actually replaces, so a
        // concurrent charge cannot slip past the limit between load and store.
        let mut current = self.0.work_units.load(Ordering::Relaxed);
        loop {
            let next = current
                .checked_add(units)
                .filter(|next| *next <= self.0.limits.work_units)
                .ok_or(ProcedureError::BudgetExceeded {
                    resource: "work",
                    limit: self.0.limits.work_units,
                })?;
            match self.0.work_units.compare_exchange_weak(
                current,
                next,
                Ordering::Relaxed,
                Ordering::Relaxed,
            ) {
                Ok(_) => return Ok(()),
                Err(observed) => current = observed,
            }
        }
    }

    /// Return admitted units that were never spent. Only a meter calls this,
    /// and only with units it admitted, so the counter cannot underflow.
    fn refund_work(&self, units: usize) {
        if units != 0 {
            self.0.work_units.fetch_sub(units, Ordering::Relaxed);
        }
    }

    fn check_cancelled(&self) -> Result<()> {
        if self.0.cancelled.load(Ordering::Acquire) {
            return Err(ProcedureError::Cancelled);
        }
        Ok(())
    }

    fn check_state(&self, deadline: DeadlineCheck) -> Result<()> {
        if self.0.cancelled.load(Ordering::Acquire) {
            return Err(ProcedureError::Cancelled);
        }
        // An execution without a deadline pays nothing here: no clock, and no
        // sampling counter either. Ticking one unconditionally cost the
        // deadline-free kernels more than the check it was meant to amortise.
        let Some(limit) = self.0.limits.deadline else {
            return Ok(());
        };
        if matches!(deadline, DeadlineCheck::Sampled)
            && !self
                .0
                .charges_since_deadline_read
                .fetch_add(1, Ordering::Relaxed)
                .is_multiple_of(DEADLINE_SAMPLE_UNITS)
        {
            return Ok(());
        }
        if Instant::now() >= limit {
            return Err(ProcedureError::DeadlineExceeded);
        }
        Ok(())
    }

    /// Reserve bytes before allocating. Retain the token beside the allocation.
    ///
    /// Cloning a token shares its charge. Only dropping its last owner releases
    /// memory admission; dropping the context/cursor alone does not.
    pub fn reserve(&self, bytes: usize) -> Result<MemoryReservation> {
        self.charge_memory(bytes, DeadlineCheck::Exact)?;
        Ok(MemoryReservation(Arc::new(Reservation {
            context: self.clone(),
            bytes,
        })))
    }

    /// Reserve one worker's scratch times the number of workers, before the
    /// parallel region starts.
    ///
    /// Memory admission takes a lock, which single-threaded is a constant
    /// overhead and under threads would be a serialization point. Kernels that
    /// need per-worker scratch admit all of it here, once, so admission is
    /// exact and does not depend on how work happens to be scheduled.
    ///
    /// # Errors
    /// Reports a memory budget the total would exceed, including on overflow.
    pub fn reserve_for_workers(
        &self,
        workers: usize,
        bytes_each: usize,
    ) -> Result<MemoryReservation> {
        let bytes = workers
            .checked_mul(bytes_each)
            .ok_or(ProcedureError::BudgetExceeded {
                resource: "memory",
                limit: self.0.limits.memory_bytes,
            })?;
        self.reserve(bytes)
    }

    /// Check admission without reserving or changing measured peak usage.
    /// The actual owner must still reserve before allocating.
    pub fn check_memory_available(&self, bytes: usize) -> Result<()> {
        let state = self
            .0
            .state
            .lock()
            .map_err(|_| ProcedureError::ResourceStatePoisoned)?;
        self.check_state(DeadlineCheck::Exact)?;
        state
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
    ///
    /// A materializing consumer charges once per copied row, so this samples the
    /// deadline as [`Self::charge_work`] does. The byte limit and cancellation
    /// are exact; [`Self::reserve`] and [`Self::checkpoint`] read the clock.
    pub fn charge_cumulative_memory(&self, bytes: usize) -> Result<()> {
        self.charge_memory(bytes, DeadlineCheck::Sampled)
    }

    fn charge_memory(&self, bytes: usize, deadline: DeadlineCheck) -> Result<()> {
        let mut state = self
            .0
            .state
            .lock()
            .map_err(|_| ProcedureError::ResourceStatePoisoned)?;
        self.check_state(deadline)?;
        let next = state
            .live_bytes
            .checked_add(bytes)
            .filter(|next| *next <= self.0.limits.memory_bytes)
            .ok_or(ProcedureError::BudgetExceeded {
                resource: "memory",
                limit: self.0.limits.memory_bytes,
            })?;
        state.live_bytes = next;
        state.peak_bytes = state.peak_bytes.max(next);
        Ok(())
    }

    /// Current accounted usage, including batches retained by a consumer.
    pub fn usage(&self) -> Result<ResourceUsage> {
        let state = self
            .0
            .state
            .lock()
            .map_err(|_| ProcedureError::ResourceStatePoisoned)?;
        Ok(ResourceUsage {
            live_bytes: state.live_bytes,
            peak_bytes: state.peak_bytes,
            work_units: self.0.work_units.load(Ordering::Relaxed),
        })
    }
}

/// One worker's share of the work budget, admitted in blocks.
///
/// Created by [`ExecutionContext::work_meter`], used by one thread, and dropped
/// at the end of that thread's chunk. Charge before performing the work, as with
/// [`ExecutionContext::charge_work`].
pub struct WorkMeter {
    context: ExecutionContext,
    granted: usize,
}

impl WorkMeter {
    /// Charge work this worker is about to perform.
    ///
    /// # Errors
    /// Reports cancellation, an expired deadline, and a work budget that the
    /// charge would exceed.
    pub fn charge(&mut self, units: usize) -> Result<()> {
        self.context.check_cancelled()?;
        if let Some(left) = self.granted.checked_sub(units) {
            self.granted = left;
            return Ok(());
        }
        self.admit(units)
    }

    /// Admit a block, or exactly what was asked for when a block does not fit.
    #[cold]
    fn admit(&mut self, units: usize) -> Result<()> {
        self.context.check_state(DeadlineCheck::Sampled)?;
        let wanted = units.saturating_add(WORK_BLOCK_UNITS);
        if wanted > units && self.context.admit_work(wanted - self.granted).is_ok() {
            self.granted = wanted - units;
            return Ok(());
        }
        // Near the limit, spend the remaining budget one charge at a time so
        // that the failure happens at the same unit as it would at one thread.
        self.context.admit_work(units - self.granted)?;
        self.granted = 0;
        Ok(())
    }

    /// Shared execution state, for an exact poll or a nested reservation.
    pub fn execution(&self) -> &ExecutionContext {
        &self.context
    }

    /// Poll cancellation and the deadline exactly, as [`ExecutionContext::checkpoint`].
    ///
    /// # Errors
    /// Reports cancellation and an expired deadline.
    pub fn checkpoint(&self) -> Result<()> {
        self.context.checkpoint()
    }

    /// Return unspent units now rather than at drop.
    pub fn finish(self) {
        drop(self);
    }
}

impl Drop for WorkMeter {
    fn drop(&mut self) {
        self.context.refund_work(self.granted);
        self.granted = 0;
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
        self.context.charge_memory(bytes, DeadlineCheck::Sampled)?;
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
        state.live_bytes -= self.bytes;
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
        state.live_bytes -= self.bytes;
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
