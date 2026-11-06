# Source-control test-oracle review

This is a pre-implementation test proposal, not an execution verdict. The contract
is testable through the real local runner and native rate reader. A mailbox-only
test would not establish the planned source binding, encoding or output handoff.
No builds, tests or source edits were performed for this review.

Source inspected at `b6d73d6a644dc04b1e6749e171100808c874d788` in
`/Users/alexy/src/sail/tmp/source-control-20261106-b6d73d6a`. The cumulative
upstream base remains `b52144955b629314a000b1fe49eeea97fa3d0c5c`.
Newly observed upstream main is a separate comparison, not the implementation base.
The saved request, AGENTS, LAKESAIL, SHEHAB, CLARITY, WRITING-RULES and source
Copilot/development/Rust/Python review instructions were reread.

## Actual seams

`LocalJobRunner::execute` currently traces the plan and calls `execute_stream`
with `ctx.task_ctx()`. `StreamSourceWrapperNode` planning calls the provider's scan
and optionally renames its output. `RateSourceExec::execute` creates a fresh
partition-local generator; zero-rate execution waits without producing data.
`EncodedFlowEventStream::encode` owns the existing marker construction. The codec
already serializes rate options, original schema and projection. These are the
production paths the new tests must connect.

The session participation tests already compile through Sail's analyzer, mandatory
streaming preparation and physical planner. Their `encoded` helper asserts a
`StreamCollectorExec` and extracts its encoded child for marker inspection. Reuse
that approach for a planned local-control test; separately execute the complete
collector for the user-data result. Do not substitute a hand-built rate plan for
all planning coverage.

DataFusion 55.2 `TaskContext::new` accepts scalar, higher-order, aggregate and window
registries, runtime, session/task identifiers and SessionConfig. Both opaque typed
SessionConfig extensions and ConfigOptions extensions must survive reconstruction.
The worker currently obtains a base context once; `TaskPreparation` decodes a plan
and executes its partition. A local test does not qualify future task-attempt
routing through those worker paths.

## Minimal discriminating cases

| Case | Setup and independent oracle |
| --- | --- |
| Native idle handoff | Compile a one-partition zero-rate source, retain the planned binding, and use actual `LocalJobRunner` controlled execution. Poll output to establish registration and a stored waker. Request checkpoint 10. Receipt remains pending while output is not polled. The request wakes the source, one output poll produces an encoded checkpoint 10, and the receipt identifies that binding, partition, scope/token and exclusive ordinal 0. A duplicate emits no second marker. |
| Native cut among data | With paused Tokio time, rate 2000 and one partition produces two rows per millisecond. Assert first data values `[0,1]`, checkpoint 10 with ordinal 2, next data `[2,3]`, checkpoint 11 with ordinal 4. Decode exact marker bytes and retraction flags. Do not assert wall-clock timestamp values or describe the ordinal as replay state. |
| Projection and filter independence | Repeat with empty payload projection and with a filter retaining only value 1 from the first pair. Empty payload still has two data rows; filtered output has one. Both receipts report source ordinal 2. This rejects deriving positions from downstream output. Preserve field/schema metadata, duplicate projections and timezone types. |
| Bounded request state | Before registration, expected participant returns NotReady. After registration, request 10 twice and observe one operation; a different request while 10 is pending is Busy. Drop a waiter, retry 10 and still receive the original outcome. After completion, a greater ID advances once and an older ID is Stale according to the final precedence contract. Cover ID 0 and `u64::MAX` without arithmetic wrap. |
| Manifest and missing execution | Two occurrences of one provider produce different binding IDs; cloning, child replacement and codec preserve each ID. Two executions of the same compiled plan retain binding IDs but get distinct scopes and registration tokens. A source under LIMIT 0 stays in the manifest, never executes or polls, and returns NotReady. Unknown IDs and out-of-range partitions receive named refusals and never enlarge the manifest. |
| Independent participants | Use two source occurrences and two partitions with independent requests. Holding one participant pending must not block another. Receipts cannot be exchanged between occurrences, partitions or jobs. An empty live registry cannot turn the nonempty expected manifest into successful checkpoint completion. |
| Token and terminal lifecycle | Reject duplicate active registration. Retire a registration, install its replacement, then deliver old cleanup and old acknowledgement: neither may remove or complete the replacement. Scope revocation rejects late registration and settles pending receipts. Exercise stream EOF, stream error, output drop, explicit runner stop and drop after accepting a command. Preserve the original output error and emit no synthetic EndOfData or successful boundary. |
| Encoding before acknowledgement | Use the actual extracted encoder with a valid Arrow schema whose marker placeholder construction returns a checked error, such as a nonnullable fixed-size list of Int16 run-end values exceeding that run length. The source reports the encoding error and the pending receipt cannot succeed. This is a controlled-source fixture, not a claim that native rate's two primitive fields ordinarily fail encoding. |
| Context fidelity | Put a named function and alias in each of all four registries, a sentinel typed extension, a ConfigOptions extension, nondefault batch size and identifiers, and an identifiable runtime/memory pool in the original context. A real executed child looks each up in its received context and asserts the original Arc identities and configuration values. New job scopes differ and the original session context remains unchanged. |
| Codec and binding properties | Roundtrip a planned bound rate source, then execute that reconstructed plan through the local runner and obtain a real barrier. Assert binding ID, capability, partition count, exact schema, original projection, boundedness and emission/ordering properties; test child replacement too. Ordinary codec reconstruction without a scope must still execute. Serialization alone is insufficient. |
| Unsupported paths | Socket and the current bounded adapter do not advertise live-barrier/replay support. A controlled cluster call returns the explicit unsupported-routing error before dispatching execution. Ordinary cluster calls retain their previous route. Use actual runner entry points, not a dummy trait implementation alone. |
| Due-data fairness | Establish a pending rate timer, advance paused time to its deadline, and keep requesting increasing barriers as output is polled. Assert that already-due data progresses within the implementation's documented finite arbitration bound. Repeated commands cannot perpetually reset the deadline or win every selection. Keep a data-only control and a zero-rate command control. |

Use explicit polls, channels and counting wakers as the primary synchronization.
Tokio `test-util` is already enabled in the workspace. A watchdog may stop a hung
test, but elapsed wall time is not the correctness oracle. Do not await a receipt
while the same task is responsible for polling its source output. Single-partition
idle tests avoid mistaking eager coalescing/background polling for source handoff.

## Decisions needed for exact assertions

The plan should fix precedence for retrying completed ID 10 while ID 11 is pending,
retrying an old completed ID after revocation, and requesting an older ID while a
different one is pending. It should name the rejection for an unknown binding or
invalid partition. Tests must assert the chosen outcomes, not accept several enum
variants. “Fair progress” also needs a deterministic arbitration rule or finite
bound before the fairness assertion is frozen. These questions do not require a
new durable protocol.

## Controls and qualification limits

Retain existing encoder tests for all applicable Arrow families, zero-column row
counts, exact nested types and metadata when extracting the reusable encoder. Add
standalone-encoder equivalence to those existing oracles rather than inventing a
second type generator. Keep public Python rate, projection, participation and
composition cases as ordinary-execution controls. Their API cannot yet issue a
source-control command; Rust utility and real-runner tests are required for that
new internal contract. No Spark equivalence claim is proposed for this Sail control
API and no JVM run was performed here.

The preceding implementation lacks this API, so a compilation failure is not an
executed behavioral counterexample. Once the API exists, retain minimal controls
that disable binding propagation, move acknowledgement before encoding, suppress
revocation/token checking, or re-enqueue a duplicate ID. Each selected control must
fail its intended assertion and pass after restoration. Record execution errors,
fixture failures and unsupported cases separately. Keep the request table bounded
under many sequential IDs; dropping caller-owned receipt handles must not retain
an unbounded internal history.

Run lifecycle concurrency stress with explicit synchronization in an optimized
build under load. Report the schedules and limits; a single green stress run does
not prove race freedom. Normal execution and controlled polling costs are separate
performance measurements, with no timestamp/replay determinism inferred from rate.
Codec support establishes reconstruction only. Distributed attempt routing,
transport alignment, recovery, target fencing and durable completion remain
unqualified until their own integrated tests exist.

Plan SHA256 at review: `d849346dc7a7130ff670330bf7cfe7770dbdb4d31cfcaae0017bfde0daf5268c`.
Recorded at 2026-11-06T10:30:03.672130+00:00.
