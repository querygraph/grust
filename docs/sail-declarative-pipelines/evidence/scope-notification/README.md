# Resource-scope sealing and cancellation notification

Recorded 2026-10-30T05:08:27.823650+00:00. Sail `5fc71b379244591c45979ece706e082ec7e56f3f` is a separate
human-reviewable commit based on `71f24a87a2f2b5b38bd012388e3ce6589c7c6d46`.

TaskResourceScope now exposes a synchronous noncanceling seal. Cancellation
constructs/retains the shared drain under the mutex, releases it, then notifies
watch listeners. Reentrant listeners see sealed admission without running under
the resource-scope lock. Already-Closing scopes still receive cancellation.

Two new tests verify pending admitted work is not canceled by sealing, and a
custom synchronous watcher reenters public spawn on both Open and Closing paths.
A try_lock guard makes the old deadlock fail an assertion instead of hanging the
test process. The exact new regression was executed against unchanged production
source: one test failed at the held-lock assertion. That control and its raw log
are preserved in baseline-control. The fix does not activate a runner or sink.

All 87 sail-common-datafusion library tests, formatting and strict
all-target/all-feature Clippy pass at this exact detached candidate. All 9
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
