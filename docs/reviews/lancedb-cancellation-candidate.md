# LanceDB cancellation handoff candidate

Status: component and branch adapter tests passed; current-main integration
awaits qualification. Original branch base: `0176718`.
This branch does not alter any running benchmark source pin.

The leading caller owns an explicit token backed by the queue's shared state.
The token travels in the oneshot handoff message, so dropping the receiver before
its next poll releases or transfers leadership. Sending and dropping channel
values happens outside the queue mutex. Failed sends disarm their returned
tokens and continue iteratively, avoiding recursive cleanup of long cancelled
queues. FIFO pending storage uses `VecDeque` instead of front-removing a vector.

Existing batch completion and uncertain-durability outcomes remain explicit.
Single-row submissions now validate their key rather than bypassing the key
callback. Tests live in separate source files. Deterministic manual-poll tests
cover cancellation before the handoff receiver polls, an already-waiting
successor, in-flight batch abandonment, apply failure, invalid single-row keys,
and ten thousand cancelled waiters. All six component tests passed at `870cf42`. The full branch adapter suite
passed 32 tests, with one ignored; warnings-denied Clippy is still running.
No general memory improvement or release readiness is claimed.

Required before integration: qualify the deterministic component tests and the
full live adapter suite, run warnings-denied Rust checks, inspect the branch
against current main, and retain the original failure and corrected receipts.
The existing cache/index/compaction changes still need their own disclosed
benchmark evidence. Ostracod is delivered and remains unchanged. The integration retains current
0.18 dependencies and moves maintenance helpers into a focused module. Its
commit counter wraps explicitly; no benchmark threshold is inferred.
