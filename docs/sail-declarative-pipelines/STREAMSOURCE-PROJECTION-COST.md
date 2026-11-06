# Keep synchronous streaming projection inexpensive

Streaming projection must isolate control markers without imposing avoidable work
on ordinary data batches. Preserve output accounting and expression telemetry while
giving synchronous evaluation one active-computation scope. Measure exact
outputs before accepting the change.

A generic asynchronous loop awaits input, scans an event boundary, then projects
its data run. Separate timers measure scanning and synchronous projection;
configuration is cloned even when no asynchronous function exists. These are
suspected costs, not established causes.

A test-profile probe at optimization level 3 divided streaming elapsed time by ordinary
projection time. Median ratios were 1.166 for 128-row batches and 1.043 for
8192-row batches. Both retained standard instrumentation. Mixed-marker fragmentation
is a separate problem; this change cannot settle its batching policy.

Separate awaiting input from extracting its next contiguous event run. Start one
timer after input arrives. Include boundary extraction and synchronous projection
or placeholder construction in that scope. Only asynchronous projections enter
the asynchronous evaluator and clone its configuration. End the boundary timer
before awaiting; continue timing each active helper poll without charging suspension.

Consolidation alone left median data-only ratios near 1.12 in a three-way repeat.
Add a direct synchronous polling path, sharing input acquisition, event extraction,
projection and metrics ownership with asynchronous execution. Release its state on
input completion or error and retain it while input is pending. The asynchronous
path keeps its existing scheduling. Removing observability or batching across markers would change
the contract and cannot supply an equivalent comparison.

Retain exact metrics, completion, error, cancellation and marker-before-error tests.
Compare all no-marker and mixed-marker cells against both ordinary projection and
the preceding instrumented implementation. Keep every sample and host limitation.
If meaningful overhead remains, keep readiness open rather than assuming that
shared-host variability explains it.
