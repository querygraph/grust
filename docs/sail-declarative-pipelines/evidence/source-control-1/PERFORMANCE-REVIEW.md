# Source-control performance and resource review

This is a before-code review of the live source-control increment. The intended
contract supplies ordered marker handoff from an executing source, with bounded
request state and execution-scoped cancellation. It does not supply replay,
durable checkpoint completion or target fencing.

Read the full saved request, `AGENTS.md`, `LAKESAIL.md`, `SHEHAB.md`, `CLARITY.md`,
`WRITING-RULES.md`, source development instructions, `SOURCE-CONTROL.md` and
`SOURCE-CONTROL-LIFECYCLE.md`. Confirmed compliance with those requirements.
The implementation worktree is
`/Users/alexy/src/sail/tmp/source-control-20261106-b6d73d6a`, starting at
`b6d73d6a644dc04b1e6749e171100808c874d788`. The upstream comparison base is
`b52144955b629314a000b1fe49eeea97fa3d0c5c`; separately observed newer main is
not this baseline. Inspected the existing native rate reader, source interface,
local and cluster job runners, logical source occurrence and encoder extraction.
Core control implementation was incomplete at inspection. No builds, executions
or tracked source edits were performed by this reviewer.

## Preserve ordinary execution as an explicit control

The existing local runner executes through DataFusion's `execute_stream` with
the session task context. Rate currently sleeps before each generated batch and
its zero-rate path sleeps without producing data. Rate batch timestamps use
wall time. A live-control branch therefore needs its own wake source, while
timer-dominated rate output is unsuitable for detecting ordinary poll overhead.

The plan's direct forwarding without a control scope is the right cost boundary.
The binding should return the original child stream, preserving its properties,
metrics and schema. It should not install another per-batch scheduler, queue or
control lock for ordinary queries. The ordinary Rate generator should preserve
its existing sleep and allocation path. Context cloning, manifest construction
and control registration belong to controlled startup, not per-row processing.

The encoder extraction caches a complete data schema and flow-event schema.
Its reviewed delta moves the existing encode body into a reusable object and
uses that fixed data schema for marker placeholders. Retain all existing Arrow
encoding and metadata oracles. This initial inspection is not final source
qualification or evidence that later edits preserve those properties.

Use two small, separately interpreted cost comparisons after correctness:

| Comparison | Cells | Required oracle and boundary |
| --- | --- | --- |
| Normal planning before/after this increment | Batch and streaming positive queries, each short and twelve nested projections | Same analyzed input and complete logical/physical output contract; exact rows/schema; preserve pruning and expression-work counts; timing includes only the stated planning stages |
| No-scope physical binding versus its direct child on one candidate binary | Ready deterministic data at 128 and 8192 rows, value-only and empty payload projection | Exact encoded output/order, schema, metric and upstream poll counts; identical batches and consumption; no rate sleeps in the timed path |

For planning, compare pinned starting and final sources with matching optimization,
feature and build settings. For the physical probe, use a finite ready input so
it measures forwarding rather than millisecond timers. Check that the fixture
actually exercises the production binding and absence-of-scope branch. Include
the event encoder's existing ordinary path in the same semantic comparison.
Seven alternating paired samples are sufficient for a first bounded diagnostic;
retain every cell and raw sample. Keep analysis, startup, polling and execution
timings distinct. Shared-host numbers are ratios, with load and unavailable
steal disclosed. Investigate a repeated material slowdown against the baseline;
do not offset it with faster unrelated cells or enlarge the benchmark program
without a concrete unresolved question.

## Make the resource bound cover retained operations

A fixed participant manifest and one operation per participant can bound the
controller's retained state by the admitted participant budget. Validate duplicate
identifiers, partition counts and checked total counts before allocating the
expanded manifest or launching readers. Queue capacity one alone does not prove
the whole bound: a dequeued operation must remain the current operation until
settled, and advancing must retire the previous cached result.

Duplicate requests should share one operation and result state. Do not accumulate
a controller-owned vector of waiter senders or historical receipts. Callers may
retain arbitrary receipt clones, whose memory and wakeups remain proportional
to those callers. State that distinction explicitly. The service cannot promise
constant total memory independently of caller-held handles. Dropping a waiting
future must remove its waiter without cancelling the current operation.

Reject Busy, Stale, Unsupported and invalid targets before enqueueing or creating
another operation. Repeated rejected requests should not grow registry or command
state. Registration generations must use checked monotonic progression and never
wrap into a live older identity. A receipt should retain its immutable result
and identity, not accidentally retain the output stream or an execution-owner
cycle. Historical success remains a historical fact after revocation; it must
not keep the execution alive or authorize a replacement.

Control locks may protect admission and atomic acknowledgement/revocation.
Never hold them across source polling, encoding, an await or an actor turn that
waits for data. Complete notifications after releasing locks where possible,
so waking a receiver cannot reenter locked control state. Scope revocation
should visit only the fixed manifest and current operations. Its cost is
proportional to admitted participants and live waiters, not prior request history.

## Test scheduling and lifetime with explicit progress oracles

The controlled rate loop must preserve its pending data deadline across commands.
Recreating sleep after every command can postpone data indefinitely. Random
selection between ready branches provides probabilistic fairness, not a bounded
progress argument. Prefer a documented deterministic progress rule, then test
that rule by keeping a data deadline ready while repeatedly completing barriers.
Do not infer fairness from one timing run.

The following tests should precede cost measurements:

| Case | Observable requirement |
| --- | --- |
| Zero-rate reader pending on output | Sending one command wakes the registered output waker; explicit polling produces exactly one matching encoded marker without advancing data time |
| Backpressured output | Enqueueing and waiting alone do not acknowledge handoff; acknowledgement occurs only after a poll encodes the marker; no subsequent data overtakes it |
| Data deadline remains ready during repeated barriers | Exact data values make progress under the chosen deterministic scheduling bound, without skipped ordinals or duplicate markers |
| Duplicate pending and completed identifier | One marker and one shared outcome; independently dropped waits do not create another command or cancel the current one |
| Greater request while queued or dequeued | Busy until the existing operation settles; pending state cannot disappear merely because the queue became empty |
| Completion, error, scope cancellation and output drop | All pending receipts settle, including dequeued commands; no fabricated success or EndOfData; later requests return the specified refusal |
| Replacement registration | Old handle, late acknowledgement and old cleanup cannot affect the new registration; two executions of one compiled plan remain independent |
| Fixed resource budget | Registry/current-operation/queue counts remain bounded through many completed, duplicate, stale and rejected requests; dropping waiters and completed scopes releases retained allocations |

Use paused time, explicit polls, waker counters, exact marker/data decoding and
drop counters as primary oracles. A timeout is a watchdog, not proof of ordering
or a throughput result. Include zero-column payloads because their row counts
still advance the source's exclusive live ordinal. Verify ordinal overflow is
checked rather than silently wrapping.

Run lifecycle races in an optimized build with coordinated starts, both on an
otherwise available host and under owner-managed CPU load. Race cancellation
against encoding/acknowledgement and against output drop, and race old cleanup
against replacement. Require each outcome to match the atomic state transition;
do not require one side to win. Repeat enough to exercise contention, retaining
the repetition count, source pin, host, commands and every failure. Use bounded
CPU-load duration and retain all artifacts. A passing finite corpus supports
these transitions, not an unrestricted concurrency or resource envelope.

## Initial disposition

The planned ownership seam, direct ordinary path and fixed-manifest/current-operation
model are appropriate for this increment. Implementation should make fairness,
dequeued-operation settlement and caller-owned waiter costs explicit before
qualification. No measured performance result or final source verdict exists yet.
Controlled cluster execution must remain a named refusal until attempt routing
is implemented. Prior mixed-marker fragmentation and short-stream planning costs
remain open; live source control does not repair or waive them. Final cumulative
source review, resource checks, bounded comparisons and immutable qualification
remain required before this unit receives a readiness verdict.
