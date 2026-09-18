# Lock-free memory accounting — plan

Status: **PLANNED for the release after Tadpole 0.21.0.** Not started. Recorded
2026-09-18. Nothing here is implemented; every number below is an estimate or a
measurement of the code as it stands at `230ae31`.

## Why

`ExecutionContext` already charges work units and observes cancellation without
a lock (`23de753`). Memory is still behind `Shared::state: Mutex<State>`:
`charge_memory`, `check_memory_available`, `usage`, and the `Drop` of
`Reservation` and `MemoryAccount` each take it.

That was the right call when memory charges were "rare" — the comment on
`Shared` says so. It is no longer true for Cypher. The reference executor
charges the logical bytes of every copied value, so a streaming query charges
memory once or more **per element**:

- `bound_value` -> `clone_value` -> `charge_intermediate_copy` ->
  `read_budget::charge_intermediate_bytes` -> `live::charge` ->
  `MemoryAccount::charge` -> `charge_memory` -> lock, check, unlock.

In a profile of `sum(reduce(s = 0, x IN nodeIds | s + toInteger(x)))` over a
4096-node chain (8,390,656 path entries, macOS, release), `pthread_mutex_lock`
plus `pthread_mutex_unlock` were about 330 of about 3,000 active samples, roughly
11%, with `charge_memory` and `MemoryAccount::charge` a further 140. The body
references two variables per element, so it takes the lock twice per element.

**Do not schedule this as the fix for `reduce`.** `reduce` is about four times
the equivalent `UNWIND` aggregate on that query, and this removes only part of
the gap. See "What this will not deliver".

## What the mutex protects today

```rust
struct State {
    live_bytes: usize,                       // accounted memory now
    peak_bytes: usize,                       // high-water mark of live_bytes
    waiters: Vec<Option<std::task::Waker>>,  // cancellation wakers
}
```

Verified in the source, not assumed:

- `waiters` is touched only by `resources/cancellation.rs` (register, replace,
  deregister) and by `cancel()`, which takes them all and wakes them.
- **Nothing waits for memory to be freed.** A release never wakes anyone, so
  the two `Drop` impls need no waker access.
- `live_bytes` and `peak_bytes` are read together only by `usage()`.

So the multi-field atomicity the comment refers to is needed for the waker
list, not for the byte counters.

## Design

Move the two counters out of `State` and into `Shared` as atomics, exactly as
`work_units` already is. Leave `waiters` in the mutex.

```rust
struct Shared {
    limits: ExecutionLimits,
    work_units: AtomicUsize,
    live_bytes: AtomicUsize,     // new
    peak_bytes: AtomicUsize,     // new
    cancelled: AtomicBool,
    charges_since_deadline_read: AtomicUsize,
    state: Mutex<State>,         // waiters only
}
```

- **`charge_memory(bytes, deadline)`**: `check_state(deadline)`, then the same
  compare-exchange loop as `charge_work`: load `live_bytes`, `checked_add`,
  reject above `limits.memory_bytes` with `BudgetExceeded { resource: "memory" }`,
  `compare_exchange_weak`, retry on contention. Admission is recomputed against
  the value actually replaced, so a concurrent charge cannot slip past the
  limit. On success, `peak_bytes.fetch_max(next, Relaxed)`.
- **`check_memory_available(bytes)`**: `check_state(Exact)`, one load, the same
  comparison. It was already advisory: the owner must still reserve.
- **`Drop for Reservation` / `Drop for MemoryAccount`**: `live_bytes.fetch_sub`.
  No lock, so no poison recovery is needed there.
- **`usage()`**: three loads. See the semantic note below.
- **`cancel()` and `Cancellation`**: unchanged.
- Update the comment on `Shared`; it will otherwise describe the old design.

Orderings: follow `charge_work`, which uses `Relaxed` for the counter. The
counters carry no happens-before obligation to another field; `cancelled` keeps
its existing `Release`/`Acquire` pairing.

## Semantics that change, and must be decided rather than discovered

1. **`usage()` is no longer a single snapshot.** `live_bytes` and `peak_bytes`
   are loaded separately, so a reader racing a charge can see a `peak_bytes`
   that is newer than the `live_bytes` beside it. `peak_bytes >= live_bytes`
   can be kept true for any single reader by loading `live_bytes` first and
   `peak_bytes` second, because peak only grows. About 88 call sites read
   `usage()` or `peak_bytes`; the ones inspected read after execution finishes.
   Audit them before merging, especially `grust-procedures/tests/contracts.rs`,
   `grust-datafusion/src/cypher/snapshot_tests.rs` and
   `grust-algorithm-procedures/examples/full_path_receipt.rs`.
2. **`peak_bytes` can lag `live_bytes` for an instant** between the successful
   exchange and the `fetch_max`. It converges, and it never under-reports a
   peak that a completed charge established.
3. **Lock poisoning no longer fails a memory charge.** Today a poisoned mutex
   makes `charge_memory` return `ResourceStatePoisoned`. After this change only
   waker operations can report it. That is a behaviour change to state in the
   changelog, not a regression to hide.

Nothing else should be observable: limits stay exact, cancellation stays
unsampled, `reserve` and `checkpoint` still read the clock, and
`charge_cumulative_memory` and `MemoryAccount::charge` keep the sampled
deadline they gained in Tadpole.

## Milestones

### L0 — Baseline, before touching code

Record, on the same host and build, so the change can be judged:

- the full-path `UNWIND` and `reduce` queries from
  `crates/grust-algorithm-procedures/examples/protocol/mod.rs` at 1024 and 4096
  nodes;
- a bounded and an unbounded 200,000-node scan;
- the algorithms benchmark's direct and Arrow participants, which pass no
  deadline and charge memory rarely. **They are the regression check**: `b5e92bd`
  exists because an atomic read-modify-write on a path that used to be free
  cost the deadline-free kernels 27.8% and 40.6%. Memory charges are far rarer
  in kernels than work charges, so no regression is expected, but it is to be
  measured, not argued.

### L1 — Atomics

The design above, in `crates/grust-procedures/src/resources.rs`. Expected size:
60 to 80 changed lines.

### L2 — Tests

- Exactness under contention: N threads charge fixed sizes against a tight
  `memory_bytes`; the sum admitted never exceeds the limit, and at least one
  charge is rejected.
- Release: dropping reservations and accounts from several threads returns
  `live_bytes` to zero.
- Peak: `peak_bytes` equals the true maximum in a single-threaded sequence, and
  is never below any `live_bytes` a completed charge produced.
- The existing suite stays green unchanged, in particular
  `cancellation_and_budgets_are_never_sampled`,
  `a_deadline_that_expires_mid_run_is_observed_within_the_sampling_interval` and
  `an_explicit_checkpoint_observes_expiry_without_waiting_for_a_sample`.
- If `loom` is acceptable as a dev-dependency, model the charge/release/peak
  interleavings; otherwise say in the PR that it was not model-checked.

### L3 — Measure and report

Rerun L0. Report every cell with its dispersion, including any that get worse.
Hand the build to the algorithms-benchmark agent through `codex-to-codex.md` for
the paired run; that harness, not a single-run probe, decides whether this
ships.

### L4 — Docs

`CHANGELOG.md` entry naming the three semantic changes; the book's execution
accounting section; this file marked complete.

## Testing obligations

Every test in L2. `cargo clippy --workspace --all-features --all-targets -- -D
warnings`, the full workspace test gate, and the package gate from `PUBLISH.md`.

## Sizing

About half a day for L1 and L2. L0 and L3 depend on benchmark host time.

## What this will not deliver

Parity between `reduce` and `UNWIND`. After this change each fold element still
pays, in the streaming path:

- a `Value` clone per variable reference, one of them a `String` allocation
  for the item;
- two thread-local lookups per charge to find the active budget
  (`intermediate_accounting_active` and `live::charge`), which cost more on
  macOS than on Linux;
- general `eval_scoped` dispatch per expression node.

Estimated effect on the measured `reduce` query: from about 4x the `UNWIND`
form to about 3.3x. That estimate comes from sample counts in one profile and
is not a prediction.

The remaining gap needs one of two larger changes, each its own goal:

1. **A compiled fold.** `read/streaming_fusion.rs` already compiles an `UNWIND`
   aggregate's inputs once per upstream row and runs a loop with no AST
   interpretation and no per-scalar clone. The same small IR could cover
   `reduce` bodies of the form `acc <op> f(item)`. It must fall back to the
   general evaluator for anything else and must preserve the seed/body type
   check, integer-overflow errors and three-valued NULL handling exactly. It is
   an optimization layer with a fallback, not a new language shape.
2. **Borrowed evaluation.** Have `eval_scoped` return `Cow<'_, Value>` so a
   variable reference does not clone. This touches every expression arm and is
   the more general fix.

Neither is part of this plan.
