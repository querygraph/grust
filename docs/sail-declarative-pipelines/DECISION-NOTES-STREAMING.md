# Decisions for streaming tables and change capture

Streaming tables append newly available rows without rebuilding the target.
Change capture applies keyed updates and deletes in sequence order. Sail's
continuous stream of data batches and control markers provides the execution
foundation; recovery must connect those markers to durable table writes.

The choices below concern that connection. Recovery scope comes first because
it determines which writes must finish together. Source and execution choices
can then be evaluated together; state, watermark and target choices matter
only for operations included in the chosen scope. Each note stands alone.
The recommendations are proposals, not settled architecture.

## S6. What must recover together

**Situation.** A flow is one declared computation feeding a target. A checkpoint
names a fixed input boundary and its required output writes. Its recovery
domain is the set of writes tracked together through restart.

Consider append tables that skip a transaction identifier already committed.
Positions name the next unread row. Both tables committed checkpoint 1 at
position 3. Checkpoint 2 records position 6, but only table A commits.
Restarting at 3 and reusing identifier 2 at position 10 makes A skip rows
6 through 9. Using identifier 3 instead repeats rows 3 through 5 in A.
Change capture writes keyed changes and deletion history in separate tables;
its two effects also need recovery, though their write semantics differ.

**Options.**

1. Start with one append flow into one transactional table. Defer change capture.
2. Recover each flow independently, including both change-capture table effects.
3. Coordinate recovery across several independent flows or sinks.

**Recommendation.** Prefer one flow, including change capture if its two-effect
recovery is required. Otherwise start with append. Preserve each prepared
boundary and write outcome until recovery finishes. Output must remain
repeatable, through saved rows or an equivalent replay guarantee. Transaction
tags suppress duplicates; they do not define which rows the tag covers.
This invariant does not require a new coordinator subsystem.

**Check and question.** Interrupt execution between writes, add input, then
restart. Each table must receive exactly its intended effects under the
original tags. Which scope provides the needed user capability, and is atomic
visibility across tables required in addition to eventual recovery?

## S1. Where checkpoint coordination belongs

**Situation.** A checkpoint records an input boundary and progress on its
output writes. Coordination assigns identifiers, requests boundaries and
tracks completion. Its owner must reach every task whose writes recover together.

Sail's local job runner executes in the session process without a driver.
Cluster execution starts a driver and rebuilds source scans on workers.
Reaching a running source therefore requires reaching its task.

**Options.**

1. Let the job runner coordinate directly in local mode and through the driver in cluster mode.
2. Add a local driver and use one placement everywhere.
3. Coordinate beside the session's streaming-query manager, with a separate task-control path.

**Recommendation.** Prefer job-runner ownership when recovery fits one job.
It preserves local execution and leaves query lifecycle with the query manager.
Recovery spanning several jobs could justify broader ownership. First compare
existing lifecycle and durable-progress facilities against the needed guarantees;
placement alone does not justify another service.

**Check and question.** Trace a request to running sources and completion back
to its owner in both local and cluster execution. Interrupt each route and
verify that recovery retains the same boundary. Which existing component can
own the selected scope with the fewest new responsibilities?

## S2. How a source participates

**Situation.** A stream source supplies data continuously. A checkpoint names
a recoverable input boundary. Recovery needs source identity, the position
after that boundary and a guarantee about reading its rows again. A position
alone does not guarantee repeatable results.

**Options.**

1. Add checkpoint operations to every stream source, with defaults for sources that cannot resume.
2. Expose a separate checkpointable-source interface and refuse unsupported sources when recovery requires it.

**Recommendation.** Prefer the separate interface. State position meaning,
source identity, repeatability and failure behavior explicitly. Recovering a
partially written interval needs its exact prepared range and repeatable
transformation, or saved output rows that supply the unfinished writes.

Checkpoint requests must not overwrite an outstanding request. Reaching an
input bound must be distinct from releasing the source's remaining checkpoint
responsibilities. These obligations apply even if the interface is small.

**Check and question.** Overlap two requests and end one source while the other
is still reading. A latest-value channel can lose a request; a queue or one
outstanding request avoids that ambiguity. Which source guarantees are required,
and can the first design serialize checkpoint requests?

## S4. How inputs align a checkpoint

**Situation.** A checkpoint marker is an ordered control message naming an
input boundary for recovery. Inputs reach that marker at different times.
An operator snapshot must include each input before its marker and exclude
rows after it.

**Options.**

1. Stop reading an input at its marker. After every participant reaches that checkpoint, snapshot state and forward one marker.
2. Continue reading and record intervening rows as part of recovery.

**Recommendation.** Prefer the first option, called barrier alignment. It
avoids a separate record of rows still in transit. Its cost is waiting for
slower inputs; workload measurements must establish whether that is acceptable.

Define the participant set explicitly. An input that emits end of data and
then closes counts once. End of data must not silently remove an input that
still owes a checkpoint acknowledgement. Concurrent requests must retain
their identifiers throughout alignment.

**Check and question.** Hold one input back, end another and overlap checkpoint
requests. Verify exact state boundaries and eventual completion without
counting any input twice. Is waiting for the slowest participating input an
acceptable initial tradeoff, or does the workload require recording in-flight rows?

## S9. How a bounded run finishes

**Situation.** A bounded run captures an end position for each source and
processes those ranges. It must complete required table writes before reporting
success. Sail's end-of-data marker leaves the stream open until the following
checkpoint, the boundary at which recovery progress is recorded.

**Options.**

1. Fix source end positions, emit end of data upon reaching them and finish after the final checkpoint completes.
2. Stop sources at a chosen time, accepting a different input boundary.

**Recommendation.** Prefer fixed positions. Coordinate capture with each reader
so consumption cannot pass its bound before installation. Check source identity
during capture and reads. A partition incarnation distinguishes a recreated
partition whose offsets may have restarted. Independent source bounds do not
promise an atomic snapshot across all sources.

An ended source remains responsible for acknowledgements assigned by the
checkpoint protocol. Completion requires every participating source and every
required write, not merely a closed result stream.

**Check and question.** Recreate a partition during bound capture and let another
reader continue concurrently. Then stagger end-of-data and closure events.
Verify the selected ranges and count each input once. Does this contract fit
the intended bounded-run semantics, and which execution component should
confirm final completion?

## S3. When checkpoints start

**Situation.** A checkpoint records an input interval and the completion of
its output writes. A bounded run fixes an end position; an unbounded run
continues reading. Either can accumulate more uncommitted data than fits in
memory when checkpoints are too far apart.

**Options.**

1. Checkpoint periodically, with a final checkpoint for bounded runs.
2. Trigger on accumulated volume, plus the final checkpoint.
3. Use only the final checkpoint for bounded runs, with an explicit memory limit or disk spill policy.

**Recommendation.** Prefer periodic checkpoints plus a final checkpoint.
Serialize requests initially unless concurrent checkpoints are needed. A final
request must not overwrite an ordinary request awaiting acknowledgements.

Cadence alone does not bound memory. Slow writes and large state require limits,
backpressure that slows upstream producers, or disk spill. Frequent snapshots
reduce replay distance but increase snapshot and commit work. The trigger and
resource policy must be designed together.

**Check and question.** Run a large backlog with a slow target, then request
bounded completion while a checkpoint is pending. Verify bounded resource use
under the declared policy and preservation of both requests. Which trigger and
resource limits fit the first supported workload?

## S5. How operator state is stored

**Situation.** Window aggregation and duplicate removal retain state between
input batches. A checkpoint pairs a snapshot of that state with an exact input
boundary for restart. A manifest names the files forming one snapshot.

**Options.**

1. Write immutable Arrow files with a manifest for each checkpoint.
2. Use an embedded key-value store with snapshots.

**Recommendation.** Prefer files if expected state size makes full snapshots
practical. Recover the manifest named by the recovery record, never simply
the newest file. Retain snapshots required by unfinished writes and the oldest
valid restart point. Recording newer source positions does not make older
state disposable.

A snapshot must remain immutable while any pending write refers to it.
Shrinking state needs a snapshot representing removals. Restore must check
schema and operator configuration, such as window size and key expressions;
identical types do not guarantee identical meaning. Atomic rename alone does
not establish power-loss durability.

**Check and question.** Interrupt snapshot publication and output commits,
then restart with both unchanged and changed operator configuration. Measure
snapshot cost as state grows and progress stalls. What storage durability,
state size and snapshot cost must the first implementation support?

## S7. What a watermark promises

**Situation.** Event time is a row's timestamp. A window groups rows into a
time interval. Sail's [watermark marker](https://github.com/lakehq/sail/blob/62251e0a27bbab0a15547562e829cad2a418f353/crates/sail-common-datafusion/src/streaming/event/marker.rs)
promises that its source will emit no later row with an older timestamp.
A threshold derived from observed event times alone cannot provide that
guarantee, because late rows can still arrive.

**Options.**

1. Preserve the guarantee. Reject or otherwise handle late rows before they enter the downstream stream, including arrivals after the marker.
2. Revise the marker to carry an event-time threshold, with downstream operators deciding which late rows remain admissible.

**Recommendation.** Resolve the contract before adding a watermark operator.
Measure event time where declared so preceding filters and renames have their
intended effect. Combining inputs needs rules for sources without watermarks
and sources that have ended.

The proposed window rule closes a window when its end is at or before the
threshold. A row can still update an open window despite having an earlier
timestamp. This rule must be reconciled with the chosen marker guarantee.
It cannot be presented as preserving the existing contract automatically.

**Check and question.** Replay the same rows with different source interleavings
and restart points. A test restoring one recorded event order does not
establish equivalent accepted rows under another. Which contract should Sail
expose, and what input progress must recovery preserve?

## S8. Which operators belong in the first scope

**Situation.** A stateful operator retains information between input batches.
Window aggregation groups rows by time interval; duplicate removal remembers
keys; a streaming join retains rows from several inputs. Each adds state that
must match the recovered input boundary.

Change capture applies keyed updates and deletes. A checkpoint marker names
an input boundary for restart. Reduction can choose one change per key between
markers and preserve ordering across intervals in its
target and deletion-history tables, rather than retaining every target key
inside an operator forever.

**Options.**

1. Start with append flows and stateless transformations.
2. Add windows and duplicate removal with their state recovery.
3. Include streaming joins as well.

**Recommendation.** Choose the smallest operator set needed by the first user
scenario, together with its recovery scope. Evaluate change capture separately:
its bounded interval reduction and two table writes have different recovery
costs from a persistent streaming join. Unsupported shapes should fail during
planning with the operation named.

**Check and question.** For each included stateful operator, restore exact state
at a checkpoint and exercise growing cardinality or delayed input. Preserving
the event format alone does not establish operator support. Which operations
are necessary for a useful first capability, and which can remain unsupported?

## S10. Apache Iggy as a source

**Situation.** Apache Iggy is a message broker with partitioned streams.
Messages have offsets within a partition. A checkpoint position for restart
must also identify the partition's incarnation, because recreation can restart
offsets. Adding the client also adds dependencies to Sail's build.

**Options.**

1. Put the broker client in an optional crate, disabled in default builds.
2. Include the client in the default build.

**Recommendation.** Prefer the optional crate. Refuse missing retained data or
a changed incarnation instead of silently advancing. Check each poll and the
identity observed while capturing a bounded run's end position. Coordinate
that capture with the reader so consumption cannot pass the chosen bound.

Keep broker acknowledgements separate from pipeline progress; this source
proposal does not acknowledge reads at the broker. Client dependency changes
must be assessed separately from source semantics. An optional feature does
not by itself resolve incompatible dependency versions.

**Check and question.** Exercise normal resume, retention loss and recreation
both before scan and during bound capture. Run the reader concurrently with
capture. Is a broker source needed in the first capability, and which dependency
changes are acceptable for that support?

## S11. How change rows are validated and reduced

**Situation.** A change row carries a key, an ordering value and an insertion,
update or delete. A checkpoint marker names an input boundary for restart.
Reduction chooses one winner per key between markers. An invalid losing row disappears if validation sees only
winners. Sealing saves selected rows unchanged for retries.

Spark 4.2.1 [validates original rows before reduction](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/autocdc/Scd1ForeachBatchHandler.scala#L39)
and [leaves equal-key, equal-sequence selection undefined](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/autocdc/Scd1BatchProcessor.scala#L80).

**Options.**

1. Validate original rows, seal winners once and promise stable winners when retrying that sealed interval.
2. Also define an order over source identity, partition and position so ties choose the same winner across input schedules.

**Recommendation.** Preserve original-row validation in either option. Prefer
stable sealed winners unless ordering across input schedules is required.
Selecting the later row in a supplied batch does not establish that stronger
guarantee. Keep deletes with their ordering values; withdrawing a previous
result does not express a durable deletion at a particular sequence.

Validation evidence must identify the original interval and schema it checked.
Keep that evidence and saved rows until both target and deletion-history writes
finish. Validating reduced rows is not equivalent evidence.

**Check and question.** Place an invalid row behind a valid winner, then reverse
tied rows across input schedules and retries. Which tie guarantee is needed,
and how should validation evidence bind to the saved interval?

## S12. How keys and full refresh affect recovery

**Situation.** Change capture applies keyed updates and deletes. Its key defines
which rows identify the same entity. A full refresh rebuilds a target from
source history. Changing keys or rebuilding must not reuse unrelated progress
or evidence that older rows passed validation.

**Options.**

1. Refuse key changes during incremental execution and require full refresh.
2. Specify a migration of keys and existing state.

**Recommendation.** Prefer refusal and explicit refresh initially. If complete
rebuild means reading from the source origin, check retained history before
destructive reset. A missing origin makes that rebuild impossible. This is a
proposed source-admission policy, not a universal Spark connector guarantee.

Refresh needs a distinct identity for progress, saved rows and write tags.
It must retain evidence needed to finish or reject interrupted effects and
define when new schemas and keys become authoritative. Clearing positions
alone does not provide a reset protocol.

Spark 4.2.1 [compares key names and types under its name resolver](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/graph/FlowExecution.scala#L514).
Changing declaration order alone is accepted; a key-change rule should not
reject that as an entity-identity change.

**Check and question.** Interrupt refresh before and after each destructive or
writing step, including when old source data is unavailable. Should retained
origin be a required source capability, and what recovery outcome must an
interrupted refresh guarantee?

## S13. Which targets need a writer fence

**Situation.** A lease grants temporary writer ownership. Each new owner gets
a greater ownership number, or epoch. A fence is the target's rejection of
writes carrying an older epoch. A lease alone cannot stop a paused writer
from resuming after its successor takes over.

Change capture writes keyed changes to a target and deletion sequences to an
auxiliary table. Recovery must protect both effects from stale writers.

**Options.**

1. Require target-enforced fences for every admitted change-capture target.
2. Fence supported targets and require an externally enforced single writer for the others.

**Recommendation.** Reuse fencing where available and state target coverage
precisely. Catalog commit ordering alone does not prove that a stale owner
cannot write. A successor must resolve previously prepared effects under the
recovery contract rather than discard them because ownership changed.
Target recreation and full refresh, which rebuilds a target, need the same
ownership protection.

**Check and question.** Pause an owner past lease expiry, let its successor
write, then resume the old owner. Repeat across each supported target and
reset operation. Which targets can enforce stale-writer rejection, and where
is external single-writer ownership an acceptable restriction?
