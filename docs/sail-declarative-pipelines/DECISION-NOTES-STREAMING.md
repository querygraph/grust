# Decision notes: streaming tables and change capture

Draft discussion posts. Every recommendation is proposed; no maintainer answer
has been recorded. Identifiers remain stable. Begin with the first user
scenario and S6. Bring S8 and S11 into that discussion where needed, then resolve the dependencies
explained in REDESIGN-REVIEW-PACKET.md. These notes are not a serial approval
queue; resolve the notes relevant to a path before implementing that path.
Each section below is a separate outward post.

## S6. What must recover together

**Situation.** A checkpoint names a fixed input boundary and the output writes
that must survive a restart. Its recovery domain is the set of writes that
must complete together. Recording positions before writing is necessary, but
does not settle recovery after only some writes commit.

Suppose both tables committed checkpoint 1 at input position 3. Checkpoint 2
records position 6, but only table A commits. Restarting at 3 and reusing
identifier 2 at position 10 makes A skip rows 6 through 9. Using identifier 3
instead repeats rows 3 through 5 in A. Change capture applies keyed updates
and deletes to a target. Keeping deletion history in a separate table gives
one such flow this same problem.

**Options.**

1. Start with append-only flows into one transactional table. Defer change
   capture and shared recovery across tables.
2. Recover each flow independently, including its target and deletion-history
   table. Preserve the prepared boundary, output rows frozen for retries,
   and a receipt recording each completed write until recovery finishes.
3. Extend that recovery domain across several flows or sinks, with their
   boundaries, state and write receipts coordinated together.

**Recommendation.** Decide the domain before coordinator placement. Prefer
one flow, deferring independent multi-sink queries. Include change capture only
if its two-effect recovery is accepted; otherwise start with one append
transaction. Preserve the original prepared boundary and each write outcome.
Table transaction tags prevent duplicate writes; they do not identify the
rows an identifier was meant to cover.

**Evidence and question.** A transition model demonstrates the counterexample;
the complete recovery protocol has not been executed. Which domain should the
first design support, and what crash evidence would settle that choice?

## S1. Where the checkpoint coordinator lives

**Situation.** A checkpoint coordinator assigns checkpoint identifiers,
requests source positions and tracks completion. Its ownership depends on
which writes must recover together.

Sail's local job runner executes in the session process without a driver.
Cluster execution starts a driver and rebuilds source scans on workers.
Reaching a running source therefore requires reaching its task.

**Options.**

1. Let the job runner own coordination, directly in local mode and through
   the driver in cluster mode.
2. Add a driver to local mode and use one placement everywhere.
3. Put coordination beside the session's streaming-query manager, with a
   separate path to running tasks.

**Recommendation.** Prefer job-runner ownership if the chosen recovery domain
fits one job. It preserves local execution and lets the streaming-query
manager retain query lifecycle responsibilities. A domain spanning jobs may
require different ownership; that is an architectural decision, not a detail
to conceal behind the interface.

**Evidence and question.** An in-process prototype requests markers from two
rate sources. It establishes neither durable coordination nor driver-to-task
control. Which placement fits the recovery scope you want?

## S2. How a source participates

**Situation.** A stream source supplies data continuously. Recovery also needs
the position after a checkpoint's rows and a guarantee about reading those
rows again. A position alone does not guarantee repeatable results.

**Options.**

1. Add checkpoint operations to every stream source, with defaults for sources
   that cannot resume.
2. Expose a separate checkpointable-source interface and refuse unsupported
   sources when the selected recovery guarantee requires it.

**Recommendation.** Prefer the separate interface. It should state source
identity, position meaning, repeatability and failure behavior explicitly.
For partial-commit recovery, either it can reproduce the exact prepared range
or an archive of frozen rows must supply the already prepared output.

Checkpoint requests must not overwrite an outstanding request. Source
completion must also distinguish reaching the input bound from releasing the
source's checkpoint responsibilities.

**Evidence and question.** Prototype rate and broker sources report positions.
Inspection found that overlapping requests can be lost in a latest-value
channel. That concurrency case has not been executed. Which source contract
fits the chosen recovery domain, and should the first version permit only one
outstanding checkpoint?

## S4. How inputs align a checkpoint

**Situation.** Inputs reach a checkpoint marker at different times. An
operator's snapshot must include every input before its marker and exclude
every input after it.

**Options.**

1. Stop reading each input when its marker arrives. Once all participating
   inputs reach that marker, snapshot state and forward one marker.
2. Continue reading and record the intervening rows as part of recovery.

**Recommendation.** Prefer the first option, called barrier alignment, for
the initial scope. It avoids an additional record of rows still in transit.
The tradeoff is waiting for slower inputs; workload evidence must determine
whether that cost is acceptable.

The participant set must be explicit. An input that emits end of data and
then closes is one completed input, not two. Reaching end of data must not
silently remove an input that still owes a checkpoint acknowledgement.

**Evidence and question.** A prototype aligns markers from two rate sources.
Inspection found incorrect completion counting and a request-overlap risk;
those traces remain to be reproduced. Is aligned checkpointing the desired
starting point, with controlled tests for staggered completion and overlap?

## S9. How a bounded run finishes

**Situation.** A bounded run must consume its captured input and complete its
required writes before reporting success. Sail's end-of-data marker leaves
the stream open until the following checkpoint.

**Options.**

1. Fix each source's end position, emit end of data upon reaching it, and
   finish after the globally final checkpoint completes.
2. Stop sources at a chosen time, accepting a different input boundary.

**Recommendation.** Prefer fixed source positions. Capture each bound in
coordination with its reader so the reader cannot pass that bound before it
is installed. Verify source identity when capturing and using the bound.
This does not promise an atomic snapshot across independent sources.

An ended source must remain available for the checkpoint obligations the
protocol assigns it. Global completion requires every participating source
and every required write, not merely a closed result stream.

**Evidence and question.** Prototypes exercise bounded completion. Inspection
found that a partition recreated between scan and bounding can evade the
identity check, and that completion accounting can count one input twice.
Those cases need controlled reproduction. Does this completion contract fit
the existing marker, and which component should own the final completion
acknowledgement?

## S3. When checkpoints start

**Situation.** A bounded run fixes an input end position and eventually
finishes. An unbounded run continues reading. Both may hold more uncommitted
data than memory can accommodate if checkpoints are too far apart.

**Options.**

1. Use periodic checkpoints for either run kind, plus a final checkpoint for
   a bounded run.
2. Trigger on accumulated volume, plus the final checkpoint.
3. Use only the final checkpoint for bounded runs, with an explicit buffering
   limit or a spill policy.

**Recommendation.** Prefer periodic checkpoints plus a final checkpoint if
the first source protocol supports their overlap safely. Cadence alone is not
a memory bound: slow writes and large state also require resource limits,
backpressure or spilling. More frequent snapshots also cost more writes.

The scheduling rule must preserve each request. A final checkpoint cannot
overwrite an ordinary checkpoint still awaiting acknowledgements. Finishing
the earlier checkpoint before requesting the final one is the simplest
candidate, subject to the completion protocol.

**Evidence and question.** The prototype append sink buffers rows in memory
until a marker arrives. No large-backlog or overlapping-request result has
been established. Which trigger and resource policy should the initial scope
support?

## S5. How operator state is stored

**Situation.** Window aggregation and duplicate removal retain state between
checkpoints. Recovery must pair that state with the exact input boundary it
describes. A manifest names the files for one snapshot.

**Options.**

1. Write immutable Arrow files with a manifest for each checkpoint.
2. Use an embedded key-value store with snapshots.

**Recommendation.** Prefer files for the initial evidence if expected state
size makes full snapshots practical. Recover the manifest named by the
recovery record, never simply the newest file. Preserve snapshots required by
incomplete writes and the oldest valid restart point. Recording newer input
positions alone does not make older state disposable.

Prepared snapshots must not be overwritten while an outstanding write still
refers to them. Shrinking state needs a snapshot that represents removal,
not merely appended records. Recovery must verify the schema and operator
contract that gave the snapshot meaning.

**Evidence and question.** A prototype writes compacted snapshots and restores
recorded state. It does not establish safe reclamation, power-loss durability,
distributed storage behavior or performance as state grows. Which storage
scope and durability contract should be demonstrated before choosing the store?

## S7. What a watermark promises

**Situation.** Sail's watermark marker promises that its source will emit no
later row with an older timestamp. A threshold derived from observed event
times does not by itself provide that guarantee: late rows can still arrive.
A window uses a watermark to decide when its result is final.

**Options.**

1. Preserve the existing guarantee. Reject or otherwise handle late rows
   before they enter the downstream stream, including rows arriving after
   the watermark was emitted.
2. Explicitly revise the marker contract to carry an event-time threshold,
   with downstream operators deciding which late rows remain admissible.

**Recommendation.** Settle this contract before implementing the watermark
operator. Place event-time measurement where it is declared, so preceding
filters and renames have their intended effect. Combining inputs also needs
rules for streams without watermarks and streams that have ended.

The proposed window rule closes a window when its end is at or before the
threshold. A row can update an open window despite having an earlier event
time. That behavior must be reconciled with the chosen marker guarantee,
not described as an unchanged contract.

**Evidence and question.** Recorded-event tests exercise closure and snapshot
restoration. They do not establish repeatable watermark interleaving when
independent sources are rescheduled. Which contract should Sail expose, and
what progress must recovery preserve to keep accepted results stable?

## S8. Which operators belong in the first scope

**Situation.** Window aggregation and duplicate removal keep state between
checkpoints. A streaming join keeps state from multiple inputs. Change capture
can instead reduce each interval and retain ordering in its target tables.

**Options.**

1. Start with append-only flows and stateless transformations.
2. Add windows and duplicate removal once their state recovery is established.
3. Include streaming joins in the first implementation as well.

**Recommendation.** Select operators after selecting the recovery domain.
Prefer the smallest set needed for the first accepted use case. Treat change
capture separately: its interval reduction is not an operator that remembers
every key forever, and its target writes still need recovery.

Unsupported shapes should fail during planning with the operation named.
Do not imply that preserving the event format establishes support for every
stateful operator.

**Evidence and question.** A tumbling-window prototype and an interval reducer
exercise distinct mechanisms. Neither supplies the planner or complete
change-capture write path. Which operator set should determine the next
decision-resolving experiment?

## S10. Apache Iggy as a source

**Situation.** Apache Iggy is a message broker with partitioned streams.
Messages have offsets within each partition. A checkpoint position must also
identify the partition's incarnation, because recreation can restart offsets.

**Options.**

1. Put the broker client in an optional crate, disabled in default builds.
2. Include the client in the default build.

**Recommendation.** Prefer the optional crate. Reject missing retained data
or a changed incarnation instead of silently advancing. Check every poll,
and also validate identity when fixing a bounded run's end position. Keep
broker acknowledgements separate from pipeline progress; the proposed source
does not acknowledge reads at the broker.

The client's dependency requirements must fit the accepted Sail dependency
set. Moving unrelated dependencies is a separate design decision.

**Evidence and question.** Broker tests cover normal resume, a retention gap
and recreation before scan. Recreation during bounding and concurrent
consumption while bounds are captured remain untested. Should this optional
source be part of the first scope, and what dependency change would be
acceptable?

## S11. How change rows are validated and reduced

**Situation.** A change row identifies a key, an ordering value and an insertion,
update or delete. Reducing an interval chooses a winner for each key.
An invalid losing row disappears if validation sees only the winners.
Sealing saves the winners so every retry reads the same rows.

**Options.**

1. Validate every original row, seal the chosen winners once, and promise
   stable winners when retrying that sealed interval.
2. Also define a total order over source identity, partition and position,
   so equal ordering values choose the same winner across input schedules.

**Recommendation.** Preserve original-row validation and sealed winners in
either option. Keep deletes with their ordering values; withdrawing an old
result does not express a durable deletion at a particular sequence.

Prefer the narrower tie guarantee unless a stable cross-partition order is
required. A receipt proving validation must identify the interval and schema
it validated. Validation of reduced rows is not equivalent evidence.

**Evidence and question.** Spark 4.2.1 [validates original rows before reduction](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/autocdc/Scd1ForeachBatchHandler.scala#L39)
and [leaves equal-sequence selection undefined](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/autocdc/Scd1BatchProcessor.scala#L80).
The reducer prototype chooses the later row in
one supplied batch. It carries no cross-partition provenance, so it does not
establish the stronger guarantee. Which tie behavior should be promised, and
how should validation evidence be bound to the archived interval?

## S12. How keys and full refresh affect recovery

**Situation.** Changing a change-capture key changes which rows identify the
same entity. A full refresh rebuilds a target from source history. Neither
operation can safely reuse unrelated progress or validation evidence.

**Options.**

1. Refuse key changes during incremental execution and require a full refresh.
2. Support a separately specified migration of keys and existing state.

**Recommendation.** Prefer refusal and explicit refresh for the first scope.
Check retained source history before destructive reset. A source missing its
origin cannot support the proposed complete rebuild. This retained-origin
requirement is a proposed Sail policy, not a claim about every Spark connector.

The refresh contract must define a new identity for progress, archives and
write tags, while retaining evidence needed to finish or reject interrupted
effects. It must also define when new schema and key definitions become
authoritative. Clearing positions alone is not a complete reset protocol.

**Evidence and question.** Spark 4.2.1 [compares key names and types under its
name resolver](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/graph/FlowExecution.scala#L514);
changing declaration order alone is accepted. Streaming reset recovery remains
unimplemented in the prototypes.
Should retained-origin capability belong on the source interface, and what
interrupted-refresh behavior should the first scope guarantee?

## S13. Which targets need a writer fence

**Situation.** A lease gives one writer temporary ownership. Each new owner
gets a greater epoch, an ownership number. A fence is the target's rejection
of writes carrying an older epoch. A lease alone
cannot stop a paused writer from resuming after a successor takes over.

**Options.**

1. Require a target-enforced fence for every target admitted to durable
   change capture.
2. Fence supported targets and explicitly require one externally managed
   writer for the others.

**Recommendation.** Preserve existing fencing where available and state its
scope precisely. Catalog ordering alone must not be presented as proof that
a stale owner cannot write. A successor must resolve earlier prepared effects
under the recovery contract rather than discard them merely because ownership
changed.

The same ownership checks must cover target recreation and full refresh.

**Evidence and question.** A bounded reference implementation fences unmanaged
Delta targets; equivalent coverage has not been established for every catalog and
format. Which target set and external ownership assumptions are acceptable
for the first design?
