# LanceDB cancellation handoff candidate

Status: implemented, not yet qualified or integrated. Based on `0176718`.
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
and ten thousand cancelled waiters. These tests await execution; no passing
result, memory improvement or release readiness is claimed yet.

Required before integration: qualify the deterministic component tests and the
full live adapter suite, run warnings-denied Rust checks, inspect the branch
against current main, and retain the original failure and corrected receipts.
The existing cache/index/compaction changes still need their own disclosed
benchmark evidence. Ostracod's running release source remains separate.
