# Prepared-stream ownership and registered cleanup

Recorded 2026-10-30T05:08:27.857230+00:00. Sail `f3d32b89597edba155805a2ce5922f83b8821d7a` is a separate
human-reviewable commit based on `5fc71b379244591c45979ece706e082ec7e56f3f`.

ManagedRecordBatchStream and its control handle retain a prepared upstream stream
independently of whether its consumer polls. A PollLease performs upstream polling
outside the mutex on the consumer's thread; successful batches retain array identity
and there is no background polling or batch queue. Cancellation disposes a retained
unpolled stream or waits for an outstanding synchronous poll to return its lease.

EOF seals resource admission without canceling successful supervisors. Stream
disposal precedes resource drainage; late cancellation still reaches a pending
drain. Completion waiters share an immutable report and do not own cleanup. A guard
constructed before spawning reports interrupted cleanup if the runtime drops the
task before its first poll or during drainage. `cancel()` initiates cancellation;
`completion().await` provides the terminal report. Its `result()` combines primary
and cleanup failures, while `cleanup_result()` reports cleanup-only failures,
retaining structured and unknown-commit causes through source
wrappers and DataFusion Shared/Collection errors. Supplied schema construction
avoids invoking an upstream schema method.

Twelve new tests cover the ordinary data path, abandoned next() wakeups, retained
unpolled cancellation, a held synchronous poll, consumer Drop, abandoned/shared
completion waiters, successful EOF with pending resources and late cancellation,
resource failure after EOF, poll and Drop panics, Drop panic without a prior query
error, old-waker destruction during handoff, and both runtime-shutdown phases.
Read-only review found three ownership windows before recovery guards existed;
they were corrected before candidate capture. The final candidate's first Rust
gate passed. An earlier working-copy formatter attempt failed because the new test
module had not yet been created; preparation-note.md records that distinction.

No runner uses this component yet. It owns an already-prepared stream and registered
supervisors, not preparation admission or unregistered spawned-task joins. Local
runner job retirement, fallible stop, truthful session deletion, checkpoint effects
and cluster shutdown remain separate required integration work. No generic cleanup
failure is relabelled as a proven mutation, and its report does not itself add a
new scheduler retry policy.

All 99 sail-common-datafusion library tests, formatting and strict
all-target/all-feature Clippy pass at this exact detached candidate. All 12
selected lifecycle tests also pass in an optimized release binary while one owned
busy process runs per logical CPU (10 on this host). The
receipt records compiler/profile overrides, exact binary hash, filter and worker
PIDs/exit codes. This is a stress check, not a performance measurement or an
exhaustive concurrency proof. Test ordering uses explicit ownership/latches rather
than elapsed-time windows. The owned load processes were terminated and joined.

The [selected design](../../LOCAL-STREAM-OWNERSHIP-DESIGN.md) and its caller audit
state the remaining boundaries. No dependency or Cargo.lock change is included.
No new public CLI, original Scala-suite, ORC writer, Iggy or CDC execution verdict
follows from this library component. Full Spark4.2.1 SDP acceptance remains open.
