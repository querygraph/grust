//! Shared cooperative limits with reservations retained by buffer owners.

use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex, RwLock, Weak};
use std::time::Instant;

use crate::{ProcedureError, Result};

mod accounting;
mod cancellation;
mod child;
pub use accounting::{Accounting, Interruption, WorkAccounting, WorkCount};
pub use cancellation::Cancellation;
pub use child::ChildLimits;

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
    /// Cumulative admitted work, or [`WorkCount::NotCounted`] when the execution
    /// disabled work accounting. Never a zero standing in for "not counted".
    pub work_units: WorkCount,
    /// The accounting mode the execution ran with, so a report can name it.
    pub accounting: Accounting,
}

impl ResourceUsage {
    /// Counted work, or `None` when the execution did not count work.
    pub fn counted_work(&self) -> Option<usize> {
        self.work_units.counted()
    }
}

#[derive(Debug, Default)]
struct State {
    waiters: Vec<Option<std::task::Waker>>,
    /// Child executions that cancelling this one must reach. Registered and
    /// collected under this lock, as waiters are, so a child created while
    /// this execution is being cancelled is either collected or sees the flag.
    children: Vec<Weak<Shared>>,
}

/// Charges sample the deadline instead of reading the clock for every unit.
/// Kernels charge once per visited entry, so a per-unit read costs more than the
/// work it guards wherever the clocksource is paravirtualised rather than a
/// register read. Cancellation is never sampled, and `checkpoint` always reads
/// the clock, so a caller that needs an exact poll has one.
const DEADLINE_SAMPLE_UNITS: usize = 1024;

/// Work, memory and cancellation are lock-free: kernels charge work once per
/// visited entry, and the reference Cypher executor charges memory once per
/// copied value. Only the cancellation wakers and children stay behind the
/// mutex; they are rare, and they are the one place that needs several fields
/// to move together. A child with a memory sub-limit of its own also takes its
/// own `admitting` lock, shared, per charge; a root never does.
#[derive(Debug)]
struct Shared {
    limits: ExecutionLimits,
    /// Fixed at construction and never written again, so a charge reads it as
    /// a plain field and a loop that charges can branch on it without an atomic.
    accounting: Accounting,
    concurrency: Option<usize>,
    work_units: AtomicUsize,
    cancelled: AtomicBool,
    charges_since_deadline_read: AtomicUsize,
    /// Unspent balances of the live work meters, so a meter that runs out can
    /// take back what idle ones hold. Never touched on a charge. A meter
    /// admitting a block holds it shared; creating, dropping and refusing hold
    /// it exclusively. See [`WorkMeter`]'s admission for why.
    grants: RwLock<Vec<Arc<AtomicUsize>>>,
    /// Accounted memory now, and its high-water mark. Atomics, like
    /// `work_units`: the reference Cypher executor charges the logical bytes of
    /// every copied value, so a streaming query charges memory per element and
    /// a lock here was a tenth of its profile. Nothing waits for memory to be
    /// freed, so a release needs no waker and no lock either.
    live_bytes: AtomicUsize,
    peak_bytes: AtomicUsize,
    /// Cancellation wakers and the children cancellation must reach.
    state: Mutex<State>,
    /// The execution this one draws memory from; `None` for a root. See
    /// [`ExecutionContext::child`].
    parent: Option<ExecutionContext>,
    /// Whether `limits.memory_bytes` is enforced at this level. Always for a
    /// root. A child enforces it only when it set a sub-limit of its own;
    /// otherwise its figures are accounting only, and its ancestors' admission
    /// is the check.
    own_memory_limit: bool,
    /// A limited child's claim on its own sub-limit: `live_bytes` plus bytes
    /// claimed here whose admission by an ancestor has not yet been decided.
    /// Admission compares against this; usage reports `live_bytes`, which only
    /// ever holds decided bytes, so a peak never counts a refused charge.
    claimed_bytes: AtomicUsize,
    /// Held shared by a limited child across the moment its claim is
    /// undecided, and exclusively by a charge about to be refused here. See
    /// [`ExecutionContext::admit_memory`] for why.
    admitting: RwLock<()>,
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
    /// Work is counted and cancellation observed: this is
    /// [`Self::with_accounting`] with [`Accounting::COUNTED`].
    ///
    /// # Errors
    /// Rejects zero batch size.
    pub fn new(limits: ExecutionLimits) -> Result<Self> {
        Self::with_accounting(limits, Accounting::COUNTED)
    }

    /// Establish an execution that performs only the cooperative checks named
    /// by `accounting`. Memory admission is always performed.
    ///
    /// A limit that the chosen mode could not enforce is refused here rather
    /// than accepted and silently ignored: disabling work accounting requires
    /// `work_units == usize::MAX`, and disabling interruption requires no
    /// deadline. A caller therefore cannot hold a context whose limits look
    /// enforced and are not.
    ///
    /// # Errors
    /// Rejects zero batch size, a work budget with uncounted work, and a
    /// deadline with interruption disabled.
    pub fn with_accounting(limits: ExecutionLimits, accounting: Accounting) -> Result<Self> {
        validate(&limits, accounting)?;
        Ok(Self(Arc::new(Shared::new(limits, accounting, None, None))))
    }
}

/// The checks [`ExecutionContext::with_accounting`] makes, shared with
/// [`ExecutionContext::child`] so a child cannot hold limits a root would refuse.
fn validate(limits: &ExecutionLimits, accounting: Accounting) -> Result<()> {
    if limits.batch_rows == 0 {
        return Err(ProcedureError::InvalidArguments(
            "batch_rows must be positive".into(),
        ));
    }
    if !accounting.counts_work() && limits.work_units != usize::MAX {
        return Err(ProcedureError::InvalidArguments(format!(
            "work accounting is disabled but a work budget of {} was set; an uncounted \
             execution cannot enforce one, so work_units must be usize::MAX",
            limits.work_units
        )));
    }
    if !accounting.observes_interruption() && limits.deadline.is_some() {
        return Err(ProcedureError::InvalidArguments(
            "interruption is disabled but a deadline was set; an execution that never \
             reads the clock cannot enforce one"
                .into(),
        ));
    }
    Ok(())
}

impl Shared {
    /// A fresh execution's state. `parent` and `own_memory_limit` are only
    /// set for a child; a root always enforces its own memory limit.
    fn new(
        limits: ExecutionLimits,
        accounting: Accounting,
        concurrency: Option<usize>,
        parent: Option<(ExecutionContext, bool)>,
    ) -> Self {
        let (parent, own_memory_limit) = match parent {
            Some((parent, own)) => (Some(parent), own),
            None => (None, true),
        };
        Self {
            limits,
            accounting,
            concurrency,
            work_units: AtomicUsize::new(0),
            cancelled: AtomicBool::new(false),
            charges_since_deadline_read: AtomicUsize::new(0),
            grants: RwLock::new(Vec::new()),
            live_bytes: AtomicUsize::new(0),
            peak_bytes: AtomicUsize::new(0),
            state: Mutex::new(State::default()),
            parent,
            own_memory_limit,
            claimed_bytes: AtomicUsize::new(0),
            admitting: RwLock::new(()),
        }
    }
}

impl ExecutionContext {
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
        if self.0.parent.is_some() {
            // A child is registered with its parent from birth, so it is not
            // reliably unshared; its concurrency is one of its `ChildLimits`.
            return Err(ProcedureError::InvalidArguments(
                "a child's concurrency is set by ChildLimits::concurrency when it is created"
                    .into(),
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

    /// The cooperative checks this execution performs, fixed at construction.
    pub fn accounting(&self) -> Accounting {
        self.0.accounting
    }

    /// Signal cancellation to all owners. Cancellation never resets.
    ///
    /// Cancelling an execution cancels every child created from it, and theirs
    /// in turn, as a process shutting down stops everything it started; a
    /// child created after this call starts cancelled. Cancelling a child
    /// reaches neither its parent nor its siblings.
    ///
    /// # Errors
    /// Refuses an execution constructed with [`Interruption::Disabled`]: nothing
    /// in it would observe the signal, and accepting it would let the caller
    /// believe the execution was stopping.
    pub fn cancel(&self) -> Result<()> {
        if !self.0.accounting.observes_interruption() {
            return Err(ProcedureError::Unsupported(
                "cancelling an execution constructed with interruption disabled".into(),
            ));
        }
        self.signal_cancelled()
    }

    /// Cancel this execution and its descendants. Every descendant of an
    /// execution that observes interruption observes it too, which
    /// [`Self::child`] enforces, so none of them refuses the signal.
    fn signal_cancelled(&self) -> Result<()> {
        // Publish cancellation before collecting wakers and children, so a
        // registration that races this call either observes the flag or is
        // collected by it.
        self.0.cancelled.store(true, Ordering::Release);
        let mut state = self
            .0
            .state
            .lock()
            .map_err(|_| ProcedureError::ResourceStatePoisoned)?;
        let waiters = std::mem::take(&mut state.waiters);
        let children: Vec<ExecutionContext> = state
            .children
            .iter()
            .filter_map(Weak::upgrade)
            .map(ExecutionContext)
            .collect();
        // Release the lock before waking or cancelling anything, and before
        // the upgraded children can drop: a child's drop takes this lock.
        drop(state);
        for waker in waiters.into_iter().flatten() {
            waker.wake();
        }
        let mut outcome = Ok(());
        for child in children {
            // Every child is reached even if one's state is poisoned.
            if let Err(error) = child.signal_cancelled() {
                outcome = Err(error);
            }
        }
        outcome
    }

    /// Poll cancellation and deadline without charging work. Unlike a charge,
    /// this always reads the clock, so an explicit poll is exact. With
    /// interruption disabled it checks nothing.
    #[inline]
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
    ///
    /// With work accounting disabled the meter is never registered and never
    /// holds a balance, so creating and dropping one takes no lock, and a charge
    /// touches no shared state beyond the cancellation flag, if that is observed.
    pub fn work_meter(&self) -> WorkMeter {
        let accounting = self.0.accounting;
        let balance = Arc::new(AtomicUsize::new(0));
        if accounting.counts_work() {
            // Registration is per meter, not per charge: a kernel creates one
            // per chunk of work, so this lock is taken a handful of times per
            // region.
            self.0
                .grants
                .write()
                .unwrap_or_else(|poison| poison.into_inner())
                .push(Arc::clone(&balance));
        }
        WorkMeter {
            counts_work: accounting.counts_work(),
            observes_interruption: accounting.observes_interruption(),
            uncounted_since_sample: 0,
            context: self.clone(),
            balance,
        }
    }

    fn release_meter(&self, own: &Arc<AtomicUsize>) {
        // Take the registry first. Emptying the balance and refunding it are
        // two steps, and between them the units are in no balance and still in
        // the counter. A refusal is decided under this same lock, so holding it
        // across both steps means a refusing meter never looks during them. It
        // once did: the hand-back ran before the lock, and a slow CI runner
        // refused work that fitted once in two hundred rounds.
        let mut grants = self
            .0
            .grants
            .write()
            .unwrap_or_else(|poison| poison.into_inner());
        self.refund_work(own.swap(0, Ordering::Relaxed));
        grants.retain(|balance| !Arc::ptr_eq(balance, own));
    }

    /// Charge work before performing it. Counter overflow is a budget failure.
    ///
    /// With work accounting disabled this admits and counts nothing; with
    /// interruption disabled it reads neither the cancellation flag nor the
    /// clock. With both disabled it is an inlined test of a field that never
    /// changes, and does nothing else.
    #[inline]
    pub fn charge_work(&self, units: usize) -> Result<()> {
        self.check_state(DeadlineCheck::Sampled)?;
        if !self.0.accounting.counts_work() {
            return Ok(());
        }
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

    #[inline]
    fn check_state(&self, deadline: DeadlineCheck) -> Result<()> {
        if !self.0.accounting.observes_interruption() {
            return Ok(());
        }
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
            bytes: AtomicUsize::new(bytes),
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
    ///
    /// On a child this checks its own sub-limit, if it has one, and every
    /// ancestor's budget.
    pub fn check_memory_available(&self, bytes: usize) -> Result<()> {
        self.check_state(DeadlineCheck::Exact)?;
        self.memory_fits(bytes)
    }

    fn memory_fits(&self, bytes: usize) -> Result<()> {
        if self.0.own_memory_limit {
            let held = if self.0.parent.is_some() {
                &self.0.claimed_bytes
            } else {
                &self.0.live_bytes
            };
            held.load(Ordering::Relaxed)
                .checked_add(bytes)
                .filter(|next| *next <= self.0.limits.memory_bytes)
                .ok_or_else(|| self.memory_exceeded())?;
        }
        match &self.0.parent {
            Some(parent) => parent.memory_fits(bytes),
            None => Ok(()),
        }
    }

    fn memory_exceeded(&self) -> ProcedureError {
        ProcedureError::BudgetExceeded {
            resource: "memory",
            limit: self.0.limits.memory_bytes,
        }
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
        self.check_state(deadline)?;
        self.admit_memory(bytes)
    }

    /// Admit `bytes` at this level and every level above it, or at none.
    ///
    /// A root admits with one compare-exchange, exactly as before children
    /// existed. A child without a sub-limit asks its parent, and counts the
    /// bytes for its own usage only once the parent has admitted them, so its
    /// figures never hold an undecided byte.
    ///
    /// **A child with a sub-limit** must pass both its own limit and every
    /// ancestor's, and no single-word exchange covers two counters. So it
    /// *claims* the bytes against its own limit first, then asks its parent,
    /// and withdraws the claim if the parent refuses. Neither level can be
    /// overrun: each admits by its own exchange, against the value it
    /// replaces, and a byte is counted at a level only by that level's own
    /// admission. The parent is always asked last, so a root never holds an
    /// undecided byte, and siblings never see one another's claims. Checking
    /// both levels first and adding afterwards, as two separate steps, is what
    /// this replaces: that lets concurrent children jointly overrun the parent,
    /// which `concurrent_children_never_jointly_overrun_their_parent` catches.
    ///
    /// **Why a refusal at the sub-limit is exact, not merely unlikely.** For an
    /// instant, a claim the parent will refuse sits in `claimed_bytes`, and a
    /// charge on the same child that fits could be refused because of it,
    /// although in either order the two charges could have run it is admitted.
    /// This is the failure the work meter's idle blocks once caused, and it is
    /// avoided the same way: a claim is made and decided under the child's
    /// `admitting` lock held *shared*, and a charge that finds no room takes
    /// the lock *exclusively* and asks once more. Under the exclusive hold no
    /// claim is undecided, `claimed_bytes` is exactly what has been admitted,
    /// and the answer is the one a single thread would get. Shared holders
    /// never wait for each other, so while the child has room this costs one
    /// uncontended acquisition per charge. Locks are only ever taken child
    /// before parent, so the exclusive paths of different levels cannot
    /// deadlock.
    fn admit_memory(&self, bytes: usize) -> Result<()> {
        let Some(parent) = &self.0.parent else {
            // Admit exactly, as `admit_work` does: the exchange recomputes
            // admission against the value it actually replaces, so concurrent
            // charges cannot slip past the limit between them.
            let next = claim(&self.0.live_bytes, bytes, self.0.limits.memory_bytes)
                .ok_or_else(|| self.memory_exceeded())?;
            // The peak can trail `live_bytes` for the instant between these
            // two lines; it never misses a completed charge.
            self.0.peak_bytes.fetch_max(next, Ordering::Relaxed);
            return Ok(());
        };
        if !self.0.own_memory_limit {
            parent.admit_memory(bytes)?;
            self.count_admitted(bytes);
            return Ok(());
        }
        {
            let _deciding = self
                .0
                .admitting
                .read()
                .unwrap_or_else(|poison| poison.into_inner());
            if claim(&self.0.claimed_bytes, bytes, self.0.limits.memory_bytes).is_some() {
                return self.decide_claim(parent, bytes);
            }
        }
        let _exclusive = self
            .0
            .admitting
            .write()
            .unwrap_or_else(|poison| poison.into_inner());
        claim(&self.0.claimed_bytes, bytes, self.0.limits.memory_bytes)
            .ok_or_else(|| self.memory_exceeded())?;
        self.decide_claim(parent, bytes)
    }

    /// Ask the parent for bytes this child has claimed, and count them here if
    /// it admits them or withdraw the claim if it refuses. The caller holds
    /// `admitting`, shared or exclusive, across this call.
    fn decide_claim(&self, parent: &ExecutionContext, bytes: usize) -> Result<()> {
        match parent.admit_memory(bytes) {
            Ok(()) => {
                self.count_admitted(bytes);
                Ok(())
            }
            Err(refused) => {
                self.0.claimed_bytes.fetch_sub(bytes, Ordering::Relaxed);
                Err(refused)
            }
        }
    }

    /// Count bytes every level above has admitted. A child's live figure never
    /// exceeds its parent's, which bounds it, so the addition cannot overflow.
    fn count_admitted(&self, bytes: usize) {
        let next = self.0.live_bytes.fetch_add(bytes, Ordering::Relaxed) + bytes;
        self.0.peak_bytes.fetch_max(next, Ordering::Relaxed);
    }

    /// Release bytes a reservation or account admitted. Only their `Drop`
    /// calls this, with what they hold, so the counter cannot underflow.
    ///
    /// A child releases its own figures before its parent's, so a child's
    /// live figure never exceeds its parent's, and every level returns what it
    /// admitted.
    fn release_memory(&self, bytes: usize) {
        if bytes == 0 {
            return;
        }
        self.0.live_bytes.fetch_sub(bytes, Ordering::Relaxed);
        if let Some(parent) = &self.0.parent {
            if self.0.own_memory_limit {
                self.0.claimed_bytes.fetch_sub(bytes, Ordering::Relaxed);
            }
            parent.release_memory(bytes);
        }
    }

    /// Current accounted usage, including batches retained by a consumer.
    ///
    /// The three figures are read one after another, not as one snapshot: a
    /// reader racing a charge can see a peak newer than the live figure beside
    /// it. Live is read first and the peak only grows, so `peak_bytes >=
    /// live_bytes` holds for every reader. Read after execution for exact
    /// totals.
    pub fn usage(&self) -> Result<ResourceUsage> {
        let live_bytes = self.0.live_bytes.load(Ordering::Relaxed);
        let peak_bytes = self.0.peak_bytes.load(Ordering::Relaxed).max(live_bytes);
        let work_units = if self.0.accounting.counts_work() {
            WorkCount::Counted(self.0.work_units.load(Ordering::Relaxed))
        } else {
            WorkCount::NotCounted
        };
        Ok(ResourceUsage {
            live_bytes,
            peak_bytes,
            work_units,
            accounting: self.0.accounting,
        })
    }
}

/// Add `bytes` to `counter` if the sum stays within `limit`, and return the
/// sum; `None`, changing nothing, if it would not, including on overflow.
fn claim(counter: &AtomicUsize, bytes: usize, limit: usize) -> Option<usize> {
    let mut current = counter.load(Ordering::Relaxed);
    loop {
        let next = current.checked_add(bytes).filter(|next| *next <= limit)?;
        match counter.compare_exchange_weak(current, next, Ordering::Relaxed, Ordering::Relaxed) {
            Ok(_) => return Some(next),
            Err(observed) => current = observed,
        }
    }
}

/// One worker's share of the work budget, admitted in blocks.
///
/// Created by [`ExecutionContext::work_meter`], used by one thread, and dropped
/// at the end of that thread's chunk. Charge before performing the work, as with
/// [`ExecutionContext::charge_work`].
pub struct WorkMeter {
    /// Copies of the execution's fixed accounting mode, held by value so that a
    /// kernel loop charging through `&mut WorkMeter` tests its own fields, which
    /// nothing else can write, and the optimiser can hoist the test out.
    counts_work: bool,
    observes_interruption: bool,
    /// Units charged since the deadline was last sampled, used only when work
    /// is uncounted and interruption observed. Local, so never contended.
    uncounted_since_sample: usize,
    context: ExecutionContext,
    /// Admitted but unspent units. Shared, not local, because a meter that runs
    /// out must be able to take back what idle meters are sitting on.
    balance: Arc<AtomicUsize>,
}

impl WorkMeter {
    /// Charge work this worker is about to perform.
    ///
    /// # Errors
    /// Reports cancellation, an expired deadline, and a work budget that the
    /// charge would exceed.
    #[inline]
    pub fn charge(&mut self, units: usize) -> Result<()> {
        if self.observes_interruption {
            self.context.check_cancelled()?;
        }
        if !self.counts_work {
            // A counted meter samples the deadline in `admit`, once per block.
            // An uncounted one never admits, so without this it would never
            // read the deadline at all. Count locally and sample at the same
            // cadence; nothing shared is touched between samples.
            if self.observes_interruption {
                self.uncounted_since_sample = self.uncounted_since_sample.saturating_add(units);
                if self.uncounted_since_sample >= WORK_BLOCK_UNITS {
                    self.uncounted_since_sample = 0;
                    self.context.check_state(DeadlineCheck::Sampled)?;
                }
            }
            return Ok(());
        }
        // The balance can be taken by another meter between the load and the
        // exchange, so this retries rather than subtracting blindly.
        let mut held = self.balance.load(Ordering::Relaxed);
        while held >= units {
            match self.balance.compare_exchange_weak(
                held,
                held - units,
                Ordering::Relaxed,
                Ordering::Relaxed,
            ) {
                Ok(_) => return Ok(()),
                Err(observed) => held = observed,
            }
        }
        self.admit(units)
    }

    /// Admit a block; failing that, exactly what was asked for; failing that,
    /// take back every idle grant and ask once more.
    ///
    /// The last step is what keeps admission independent of the number of
    /// meters. Without it, a block granted to a meter that has stopped charging
    /// counts against the budget until that meter drops, so work that fits
    /// could be refused because of who else exists — the failure the contract
    /// test `an_idle_meters_unspent_block_does_not_refuse_work_that_fits`
    /// reproduces.
    ///
    /// **Why a refusal here is exact, not merely unlikely.** A refusal is
    /// right only if every admitted, unspent unit has been found and handed
    /// back first. Units are invisible for one moment: after a meter's block
    /// has been added to the shared counter and before it appears in that
    /// meter's balance. So a meter admitting a block holds the registry
    /// *shared* across exactly that moment, and a meter about to be refused
    /// holds it *exclusively*. Under the exclusive hold no block is in
    /// transit, every unspent unit sits in some balance, reclaiming empties
    /// them all, and the counter then holds only work performed. The refusal
    /// that follows is the one a single thread would have met at the same unit.
    ///
    /// An earlier version retried three times with no exclusion and refused
    /// work that fitted in most runs of
    /// `many_meters_racing_for_the_last_of_a_budget_that_exactly_fits` on a
    /// ten-core host: meters that ran out together each emptied their own
    /// balance onto their stack, found the others' empty, and gave up.
    ///
    /// Shared holders never wait for each other, so while the budget has room
    /// this costs one uncontended acquisition per [`WORK_BLOCK_UNITS`] per
    /// worker. Exclusive holds happen only when a block no longer fits, which
    /// is the end of the budget, and when a meter is created or dropped.
    /// Dropping must be among them: a dropping meter hands its block back in two
    /// steps, and between them the units are in no balance.
    #[cold]
    fn admit(&mut self, units: usize) -> Result<()> {
        self.context.check_state(DeadlineCheck::Sampled)?;
        // A block on top of the need, while the budget has room for one. What
        // this meter already holds stays in its balance, where it can be seen.
        // The only failure `admit_work` reports is an exceeded budget, which
        // the exclusive path handles, so it is discarded here.
        let block = units.saturating_add(WORK_BLOCK_UNITS);
        if block > units {
            let shared = self
                .context
                .0
                .grants
                .read()
                .unwrap_or_else(|poison| poison.into_inner());
            if self.context.admit_work(block).is_ok() {
                self.balance.fetch_add(block - units, Ordering::Relaxed);
                return Ok(());
            }
            drop(shared);
        }
        let grants = self
            .context
            .0
            .grants
            .write()
            .unwrap_or_else(|poison| poison.into_inner());
        // Hand back what this meter holds and ask for exactly the charge, so
        // the budget fails at the unit that exceeds it rather than a block early.
        self.context
            .refund_work(self.balance.swap(0, Ordering::Relaxed));
        if self.context.admit_work(units).is_ok() {
            return Ok(());
        }
        // Take back what idle meters hold. A meter charging from its balance at
        // this moment loses the exchange, finds too little, and waits its turn.
        let mut reclaimed = 0usize;
        for balance in grants.iter() {
            reclaimed = reclaimed.saturating_add(balance.swap(0, Ordering::Relaxed));
        }
        self.context.refund_work(reclaimed);
        self.context.admit_work(units)
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
        // An uncounted meter was never registered and never held a balance.
        if self.counts_work {
            self.context.release_meter(&self.balance);
        }
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
        self.context.release_memory(self.bytes);
    }
}

#[derive(Debug)]
struct Reservation {
    context: ExecutionContext,
    /// Atomic only so that [`MemoryReservation::shrink`] can lower it through
    /// a shared token; it never grows.
    bytes: AtomicUsize,
}

impl Drop for Reservation {
    fn drop(&mut self) {
        self.context.release_memory(*self.bytes.get_mut());
    }
}

/// Shared memory admission token. Leaking it conservatively retains the charge.
#[derive(Clone, Debug)]
pub struct MemoryReservation(Arc<Reservation>);

impl MemoryReservation {
    /// Number of accounted bytes retained by this token.
    pub fn bytes(&self) -> usize {
        self.0.bytes.load(Ordering::Relaxed)
    }

    /// Lower the charge to `bytes`, returning the rest to the execution now.
    ///
    /// For a caller that reserved an upper bound before allocating and knows
    /// the real size afterwards. The excess is released at once, through every
    /// level of a child execution, as a drop would release it; the peak keeps
    /// the bound, which was admitted. Clones share one charge, so shrinking
    /// through any clone shrinks it for all of them. A reservation never grows:
    /// more memory is admitted by reserving again.
    ///
    /// # Errors
    /// Refuses a size larger than the reservation holds, changing nothing.
    pub fn shrink(&self, bytes: usize) -> Result<()> {
        let mut held = self.0.bytes.load(Ordering::Relaxed);
        loop {
            if bytes > held {
                return Err(ProcedureError::InvalidArguments(format!(
                    "cannot shrink a {held}-byte reservation to {bytes} bytes; a reservation \
                     grows only by reserving again"
                )));
            }
            match self.0.bytes.compare_exchange_weak(
                held,
                bytes,
                Ordering::Relaxed,
                Ordering::Relaxed,
            ) {
                Ok(_) => {
                    // Only the exchange that lowered it releases the difference,
                    // so racing shrinks through clones release each byte once.
                    self.0.context.release_memory(held - bytes);
                    return Ok(());
                }
                Err(observed) => held = observed,
            }
        }
    }

    pub(crate) fn belongs_to(&self, context: &ExecutionContext) -> bool {
        Arc::ptr_eq(&self.0.context.0, &context.0)
    }
}
