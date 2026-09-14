# Shared query lifetime control qualification

Final source under test: `3139917`. Status: broader consumer tests and Clippy
are running on Capitola with four nice Cargo jobs. This is unreleased work,
not a completed release gate or a performance measurement.

The preliminary `91e6da7` run passed 41 DataFusion and 22 procedure tests,
with zero failures/ignored, plus warnings-denied focused Clippy. The subsequent
`a690dad` stream-lifetime tests passed; Clippy rejected two collapsible `if`
checks. Both successes and that failure are retained in `preliminary-logs.tar.gz`.
The final source fixes those checks and includes the reentrant-waker regression.

Coverage includes multiple cancellation waiters, waiter replacement/removal,
callbacks outside resource locks, pending future/stream cleanup, absolute
deadlines without provider wakeups, terminal errors, unchanged Arrow buffer
identity, sibling execution independence, and SQL cancellation through the
blocking Arrow reader used for ADBC. This does not claim live-driver conformance,
preemption of synchronous work, full read-policy accounting or automatic routing.
