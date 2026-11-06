# Live source control: Spark semantics and correctness review

## Scope and evidence

Read the saved full request and governing AGENTS, LAKESAIL, SHEHAB, CLARITY,
WRITING-RULES and source instructions. Inspected starting Sail commit
`b6d73d6a644dc04b1e6749e171100808c874d788` in the assigned detached worktree.
The cumulative upstream base remains `b52144955b629314a000b1fe49eeea97fa3d0c5c`;
newly observed upstream work is a separate reference, not silently part of this pin.

The canonical `/Users/alexy/src/sail/opt/spark` path is absent. Verified Spark
4.2.1 at `617618396087429b5627a86ce933bb0f5d6645cb` in the sparse checkout
`/Users/alexy/src/spark-sdp-4.2.1` and read its Git source objects. No JVM comparison,
Sail build, runtime experiment or test was performed by this reviewer. These are
observed source facts and proposed requirements before implementation.

## Actual Sail source behavior

StreamSource is a planning interface. Its scan method returns a physical execution
plan, with optional projection, predicates and row limit. It has no live checkpoint,
seek, captured-end or commit callback. RateSourceExec and SocketSourceExec are
serialized by the physical codec and reconstructed on execution workers.

RateSourceExec ignores TaskContext and creates a fresh generator during every
execute call. The generator starts offset zero independently per partition and
uses Utc::now for every generated timestamp batch. Projection and zero-column
cardinality are supported, but the current position alone cannot replay identical
wall-clock timestamps. The source emits only data. Zero rows-per-second sleeps
indefinitely; controls cannot depend on waiting for a data batch to arrive.

SocketSourceExec also ignores TaskContext. It connects once, batches lines and
emits data or errors. It explicitly performs no reconnect or retry. EOF produces
stream closure without EndOfData or a checkpoint. The socket is a testing source,
not evidence of replayable source capability. Adding a registry does not supply
missing retained bytes, stable positions or reincarnation detection.

StreamSourceAdapterExec wraps finite batch input and chains EndOfData after it,
then closes. It does not remain alive for a subsequent final checkpoint. Generic
stream chaining can also reach that marker if a caller continues polling after
an input error. The query runner currently stops at the first error, drops input
and atomically publishes its terminal cause. Signal cancellation publishes stopped
without a cause. Neither terminal path is a durable completion receipt.

The distributed TaskPreparation path owns a TaskKey containing job, stage,
partition and attempt, decodes the worker plan and then calls execute. That is a
real execution ownership seam. Source registration belongs at execution, not in
the reusable planning descriptor. Local execution needs a corresponding live attempt
context through its existing runner, without introducing a local driver.

## Contracts worth retaining from Spark

SparkDataStream.initialOffset is only an initial starting point: its documentation
explicitly says recovery uses a checkpointed position instead. deserializeOffset
must reject an invalid encoding for that reader. commit(end) confirms the engine
has completed processing the preceding range and will not request it again; stop
releases resources. These are distinct operations. A source acknowledging a live
barrier is not permission to discard its replay history.

ContinuousPartitionReader exposes the current per-partition record position, and
ContinuousStream merges partition positions and can request reconfiguration.
The useful property is explicit partition/source interpretation and reader lifecycle,
not a requirement to copy Spark’s epoch scheduler. MicroBatchExecution retains
source identities independently of optimized data plans, writes commit metadata and
invokes source commits through explicit engine-controlled paths. Source offsets,
sink effects and engine completion are different facts.

SupportsTriggerAvailableNow captures a target frontier and forbids future latest
offsets above it, including careful treatment of an uncommitted range at restart.
Sail should retain the fixed-boundary idea within its continuous protocol rather
than implement repeated bounded batch execution. Recomputing a later end during
retry would change the work under its original identity.

Spark’s rate source persists creation origin and versions its source metadata.
Its continuous rate source records partition values and runtime interpretation.
This illustrates information needed for replay beyond a numeric position; it is
not proof that arbitrary regrouping of Sail’s wall-clock records is deterministic.
Spark Offset compares serialized JSON strings. Sail should instead define explicit
versioned typed position semantics rather than inherit lexical equality or an
imagined total order over unrelated partitions.

## Required Sail control invariants

Name a source’s capabilities truthfully. Separate live barrier/control support,
replay support, captured-end support and durable-progress acknowledgment. A source
may support one without the others. Socket must not be admitted for durable recovery
merely because it can receive a command; rate needs stable generation identity and
timestamp interpretation or saved prepared output before replay claims.

Identify endpoints by the executing task attempt and source/partition occurrence.
Registration replacement, commands, acknowledgments and deregistration must check
the same incarnation/token. An obsolete task must not answer for its successor,
and dropping its registration must not remove the newer endpoint. In-process tokens
are not restart-stable durable identities. Cluster routing must carry the required
identity through existing actors and reconstructed task context.

Process controls at an explicit ordered source boundary. The acknowledged position
must describe exactly the records before its marker and use a documented inclusive
or exclusive convention. Exclusive next-position semantics are reasonable for Sail,
provided every adapter agrees. Do not derive acknowledgment from generator state
advanced before a batch error or from unconsumed output. Requests must wake an idle
or zero-rate source independently of data readiness.

Serialize checkpoint requests initially. Retries of an already accepted request
need the original cut or a named conflict; they must not silently capture a different
position under the same checkpoint identity. Cancellation, errors and task replacement
must settle queued replies explicitly rather than leave waiters hanging. An unknown
response is not a newly authorized request. These live guarantees still do not
establish persisted preparation, target acceptance or integrated recovery.

Sail’s watermark promises that future data will not have strictly older timestamps.
Wall-clock time alone does not prove this, especially when time can move backward
or replay may emit older records. Do not fabricate watermarks from control receipt
time. Unsupported watermark requests need a named refusal or an explicit stronger
source contract.

EndOfData forbids later data events while retaining availability for the next
checkpoint. The marker documentation says sinks wait for all inputs and the final
checkpoint before completion. Transport closure is different. An unexpected EOF
on an admitted recoverable continuous source should fail that contract; best-effort
socket termination can retain an explicitly limited ephemeral behavior. A finite
consumer’s cancellation, including LIMIT 0, must not masquerade as EndOfData or
successful durable completion.

## Discriminating qualification

Use held data and deterministic channel control to test idle source wakeup, exact
positions on both sides of a marker, retry/conflicting requests, end capture, stale
attempt commands and stale registration drop. Test errors and cancellation while
requests are queued, including replacement before late replies. Verify that source
failure cannot turn into a successful final marker or checkpoint acknowledgment.

Rate tests need identical records for the same admitted generation/position if
replay is claimed, including timestamps and partition interpretation. Separate
source-marker receipt from persisted checkpoint and target effect completion.
Exercise local execution and decoded worker plans; a registry utility test alone
does not prove routing to the running scan. Source-control capability tests do not
qualify shuffle alignment, final durable sinks, fencing or complete recovery.

Findings were sent to the integration owner before dependent implementation. No
source edits, builds, tests, cleanup or remote actions were performed. Saved prompt
and governance compliance are confirmed; final cumulative source review remains
pending.
