# Streaming foundation repairs and remaining decisions

Streaming queries must preserve their data and report execution failures accurately.
The implementation on local branch `work/streamsource-foundation-20261105` repairs
event encoding, filter evaluation and failure reporting within Sail’s existing
continuous execution model. These repairs support later recoverable pipelines;
they do not implement durable checkpoints or change capture.

## What the implementation changes

A flow event contains data, per-row retraction flags that cancel earlier rows,
or a control marker. Sail’s markers describe latency, watermarks, checkpoints
and end of data. Sail encodes these events in Arrow batches, adding control
columns and placeholder values where a marker has no user data.

| Existing component | Implemented change | Why it matters |
| --- | --- | --- |
| Flow-event encoder and decoder | Preserve schema metadata, decimal parameters, run-end field definitions and positive row counts without payload columns | Adding a marker must not change the data’s type or cardinality |
| Rate source | Preserve row count when projection selects no source columns | Literal-only and empty projections still represent the requested rows |
| Streaming filter | Evaluate predicates on contiguous data runs and forward marker runs without evaluation | A strict cast must not fail on a synthetic marker placeholder |
| Console sink and streaming-query manager | Propagate failures, retain the first cause and publish stopped state with that cause atomically | A failed query must not appear to have completed successfully |
| Spark Connect exception response | Serialize the retained cause in the form the client expects | Error retrieval must return the original failure rather than fail while parsing it |

No new coordinator or execution subsystem is introduced. The filter remains
Sail’s `StreamFilterExec`, retaining its planner and serialization interfaces.
The query manager uses one watched terminal state. The console sink renders
output before acquiring its existing output lock and propagates write errors.

## Why these boundaries were chosen

Marker placeholders are an encoding detail, not rows on which user expressions
may run. Adding a marker-preserving Boolean term to a predicate is insufficient:
another expression can still evaluate the placeholder and fail. The filter now
separates contiguous marker and data runs while preserving their order. A marker
preceding bad data reaches the consumer before that data’s error.

Ordinary batches without markers retain one direct filter call. The filter drops
its own reference to a consumed input batch before yielding output. Returned
arrays may still share its buffers.
Projection and asynchronous expression evaluation still need their own isolation
changes; this filter repair does not qualify every streaming expression.

Failure and terminal state must be observed together. Separate notifications can
wake a waiter before stopped state becomes visible. The implemented state transition
retains the first cause, releases input and then publishes termination atomically.
Manager reset does not erase an individual query’s failure. This preserves existing
stop behavior; cancellation classification, panic supervision and durable completion
remain separate work.

## What was verified

The implementation is based on Sail `b52144955b` and ends at `2c9fa8499`.
The final checks used that immutable detached commit and an independent build
directory. The checked source stayed unchanged throughout.

| Check | Result and boundary |
| --- | --- |
| Workspace Rust tests | 2,017 passed; one pre-existing ignored type-coercion test remained skipped |
| Workspace lint and formatting | Strict Clippy across all targets and features, Rust formatting and changed Python formatting passed |
| Public Python checks | Ten live tests against the fresh server and nine PySpark client fixtures with mocked transport passed |
| Unmodified-source controls | New tests reproduced encoding, filter, console and query-failure defects before their repairs |
| Atomic termination and wire-format controls | Deterministic interleaving tests rejected split terminal publication; the client reproduced failure to parse an unprefixed exception |

The Arrow checks cover applicable type families, nested decimals, empty and
nonempty run-end arrays, metadata, all marker kinds, retractions and sliced
batches. Filter checks cover strict casts, scalar predicates, ordered errors and
input lifetime. Public checks include a failing console query and its individual
and manager waiters.

Spark 4.2.1 source was inspected for the retained client and query semantics.
The live tests used the actual PySpark 4.2.1 client against Sail; client-only
fixtures exercised exception decoding. Neither is a Spark-engine differential run.
Workspace tests and selected public tests do
not qualify the replacement pipeline runtime, distributed recovery or table
commit protocols.

## Performance limits the next step

Splitting mixed batches preserves semantics but can create many tiny outputs.
A shared-host diagnostic compared identical safe predicates and verified exact
ordered outputs before timing. The build was unoptimized, so these ratios identify
costs rather than establish production throughput.

| Input pattern | Median elapsed-time ratio, new filter divided by previous filter |
| --- | ---: |
| Data only, across tested sizes and selectivities | 0.99–1.01 |
| Alternating data and markers | 17.9–141.1 |

The alternating fixture produced one output batch per input row. This is a
material unresolved performance limitation. Keep the implementation as a
correctness reference while repeating the comparison in an optimized build and
varying marker frequency and placement.

Combining evaluated data with its following marker may reduce dispatch costs,
but adds buffering, copies and latency. A proposed combiner must bound retained
bytes and emit the marker before evaluating subsequent data. Gathering data across
markers would weaken the established error-order contract.

## Decisions before the dependent code

Should filtering combine adjacent outputs under a byte limit? Optimized measurements
and exact ordering, lifetime and latency checks should settle that choice.

Which target can enforce ownership at commit acceptance while preserving ordinary
table access? A lease alone cannot reject a stale writer. Durable append needs
that enforced fence, a replayable source, aligned checkpoint markers and a persisted
prepared record identifying the original effects before output commits. These
parts remain unbuilt and must be qualified together before change capture uses them.

Which typed configuration model should planning consume? Strict YAML, JSON and
API inputs should normalize into one versioned model. Dhall, a typed configuration
language, should optionally compile to the same validated representation. That independent work can proceed before
durable integration, which needs stable normalized configuration identity.

The accompanying branch design notes explain
[event fidelity](STREAMSOURCE-EVENT-FIDELITY.md),
[expression isolation](STREAMSOURCE-DATA-ONLY-EXPRESSIONS.md),
[failure publication](STREAMING-FAILURE-PROPAGATION.md),
[exception serialization](STREAMING-ERROR-PROTOCOL.md) and
[the batching decision](STREAMSOURCE-FILTER-BATCHING.md).
The [evidence record](evidence/streamsource-build-1/README.md) contains exact pins,
commands, review findings, retained failures and qualification limits.
