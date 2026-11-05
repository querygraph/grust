# Streaming tables and change capture: architecture

Streaming tables append newly available rows to a target without rebuilding
its full history. Change capture applies keyed updates and deletes while
preserving their sequence order. Both need recovery that completes interrupted
work without losing or repeating its effects.

This design uses Sail's streaming execution model. It does not require atomic
visibility across independent tables or a general transaction coordinator.
The recovery scope, component ownership and watermark contract remain choices.

## Execution model and recovery scope

Sail's `StreamSource` supplies a streaming scan. Its flow events carry data
batches and ordered control markers. A checkpoint marker names an input
boundary at which positions and operator state can be recorded for restart.
A sink writes the resulting rows to a target. A flow is one declared
computation feeding a target.

The recovery domain is the set of output effects whose completion is tracked
together. Its size determines which failures must be coordinated:

| Candidate scope | Required recovery work | Cost or limitation |
| --- | --- | --- |
| One append flow into one transactional table | Pair source positions and any operator state with the table commit | Smallest scope; does not support change capture |
| One flow, including change capture | Also retain repeatable input and separate completion records for its two table effects | Supports keyed changes; must recover a crash between the effects |
| Several flows or sinks together | Coordinate participating sources, state and effects across outputs | Wider scope and shared failure handling across otherwise independent flows |

Change capture writes both its target and an auxiliary table. The auxiliary
table stores deletion sequences so an older update cannot resurrect a deleted
key. One logical flow therefore does not always mean one table transaction.

The recommended starting point is one flow, including change capture if its
two-effect recovery is required. Independent multi-sink recovery can wait.
An append-only first step is simpler but leaves keyed updates and deletes
outside that path.

## The partial-commit problem

Consider append sinks that skip a transaction identifier already committed.
Positions below name the next unread input row. Both tables have committed
checkpoint 1 at position 3. Checkpoint 2 records position 6, but only table A
commits it before a crash.

Restarting at position 3 and reusing identifier 2 at position 10 loses rows
6 through 9 from A: its existing tag suppresses the entire retry. Assigning
identifier 3 to that replay instead duplicates rows 3 through 5 in A.

Recording positions before commits is necessary, but recovery must also
preserve what each committed tag means. This example rules out two retry
policies. It does not select a storage system or prove that every effect must
share a new coordinator. Change-capture merges have different semantics, but
their separate commits likewise need an explicit recovery protocol.

## Component responsibilities

Sail already supplies streaming scans, flow events, the streaming rewriter and
local and cluster job execution. Recoverable table writes require additions:
source checkpoint participation, durable progress, state snapshots and sink
completion tracking. The table assigns those responsibilities without assuming
that each needs a new component.

| Component | Responsibility and ownership choice |
| --- | --- |
| Pipeline planner | Bind source reads and target writes; refuse unsupported query shapes |
| Streaming rewriter | Build flow-event operators for the selected query shapes |
| Job runner and driver | Candidate owners of checkpoint requests and completion; local execution has no driver, while cluster scans run on workers |
| Source checkpoint capability | Report source identity, exact positions, bounded ends and replay guarantees |
| Stateful operator | Snapshot the state associated with its aligned input boundary |
| State store | Publish snapshots and retain every snapshot still required for recovery |
| Table sink | Perform a recoverable write and expose evidence of its completion |

Coordinator placement follows the domain. One job may fit its existing job
runner; several jobs may need broader ownership. Source participation and
completion contracts constrain that choice. Existing lifecycle and durable
progress facilities should be reused where their guarantees fit.

## Candidate recovery protocol

A prepared checkpoint is a durable description of work that may have started
writing but is not yet complete. One candidate records this description before
the first output effect. It binds:

- A stable flow identity and a generation distinguishing each full rebuild of its target.
- Source identities and exact input boundaries, including partition incarnations that distinguish recreated sources.
- Operator snapshots, their schemas and the plan configuration that gives the state meaning.
- Repeatable output, either saved rows or a proved equivalent replay mechanism.
- Evidence that all original change rows passed the required validation.
- Required table effects and a completion receipt identifying each successful write.

Sealing means persisting selected rows unchanged for retries. It avoids
re-evaluating nondeterministic expressions or choosing a different winner
among tied changes. Replay without sealing is an alternative only if both
the source range and transformed results remain reproducible and available.
Source positions alone establish neither property.

A candidate execution order is input alignment, state and row preparation,
durable publication of the prepared checkpoint, then individually tagged
effects. Recovery completes the original effects with their original meaning.
It must not attach newly evaluated rows to a tag a table already holds.

A checkpoint completes only when every required effect is confirmed. A closed
result stream does not prove that. Readers may see partial table effects
before completion; cross-table atomic visibility is a separate guarantee.

Storage placement and durability remain open. Atomic file rename does not
alone establish survival after power loss. Format-specific transaction checks
must also remain valid when concurrent writers refresh a table snapshot.

## State and source lifecycle

A manifest names the files forming one operator snapshot. Recovery loads the
manifest associated with its input boundary, never simply the newest file.
A snapshot referenced by outstanding effects stays immutable. Cleanup retains
all state required by incomplete effects and the oldest valid restart point.
Recording a newer source position does not itself permit deleting older state.

Schema equality alone cannot establish snapshot compatibility. Window sizes,
key expressions and other operator configuration can change the meaning of
identically typed state. Recovery must check that contract too.

A bounded run captures an end position for each source and finishes after
processing those ranges. Each source must coordinate bound capture with its
reader so consumption cannot pass the bound before it is installed. A broker
partition's incarnation must be checked during capture as well as during
reads. Independent source bounds do not imply an atomic pipeline-wide snapshot.

End of data means no further rows; it does not release every checkpoint
obligation. An input that ends and later closes counts once. Ordinary and final
checkpoint requests must be serialized or queued so no identifier disappears.
Final completion waits for the participating sources and required table effects.

## Watermarks and resource limits

An event-time window groups rows into a timestamp interval. A watermark tells
operators when older data can no longer change a result. Sail's existing
[marker contract](https://github.com/lakehq/sail/blob/62251e0a27bbab0a15547562e829cad2a418f353/crates/sail-common-datafusion/src/streaming/event/marker.rs)
promises that a source will emit no later row with an older timestamp.
A threshold derived from observed event times does not itself establish that
promise, because late rows can still arrive.

There are two choices: enforce the existing guarantee before rows enter the
downstream stream, or amend the marker to carry a threshold with explicit
late-row rules. The proposed window rule accepts a row while at least one
window it belongs to remains open, even if its timestamp precedes the
threshold. That rule must be reconciled with the marker contract.

Combining input watermarks, handling ended inputs and restoring progress are
related decisions. Replaying identical rows under a different input schedule
can change which rows reach an operator before its watermark advances.
A snapshot test over one recorded event order does not establish equivalent
results under another order.

Checkpoint frequency trades buffered output and replay distance against commit
and snapshot work. An append sink that buffers until the next marker needs a
size limit, backpressure or spill policy. Periodic checkpoints alone do not
bound memory. Open-window cardinality and stalled watermarks can also grow
state, while frequent full snapshots increase materialization and write cost.
No throughput or memory envelope follows from the event model alone.

## Change-capture validation, ties and ownership

A change row carries a key, an ordering value and an insertion, update or
delete. Validate every original row before reduction or either table effect.
A losing row with an invalid sequence must still fail the interval. Spark
4.2.1 [validates before reducing and then performs the two merges](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/autocdc/Scd1ForeachBatchHandler.scala#L39).
The proposed reducer chooses one winner per key between checkpoint markers.
Ordering across intervals belongs in the target and auxiliary tables, avoiding
an unbounded duplicate of every target key in operator state.

Spark [leaves equal-key, equal-sequence selection undefined](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/autocdc/Scd1BatchProcessor.scala#L80).
Sealing preserves a chosen winner during retry. A stronger guarantee across
independently scheduled inputs also needs a total order over source identity,
partition and position. Selecting the later row of one batch does not define
that order. Prefer stable sealed winners unless the stronger contract is needed.

Keep both table outcomes and validation evidence until pending effects finish.
An archive of sealed rows can complete a prepared effect despite lost source data;
it cannot supply unread future input. Full refresh rebuilds the target and
needs a distinct recovery identity. A requirement to rebuild from the absolute
source origin also needs a retained-history check before destructive reset.
That is a source-admission policy, not an automatic property of table reset.

A lease grants temporary writer ownership. A fence rejects writes carrying an
older ownership number after a successor takes over. Catalog commit ordering
alone does not provide this guarantee. The design must either require target
fencing or state which targets depend on externally enforced single-writer
ownership. Target recreation and interrupted refresh need the same protection.

## Tests that distinguish the choices

The decisive recovery test interrupts execution between required table effects,
then resumes after new input has arrived. Every completed tag must retain its
original meaning, and required state must remain available. Repeat it with
source data removed after sealing to distinguish archive recovery from replay.

Source tests must overlap checkpoint requests, stagger end-of-data and closure,
and recreate a partition during bound capture. Stateful tests must change input
interleaving and operator configuration during restart. Writer tests must pause
an owner past lease expiry and resume it after takeover. Resource tests must
exercise a large backlog, stalled watermarks and slow commits.

Existing mechanism tests cover controlled marker alignment, one file sink's
simulated restart, broker resume checks and recorded-window restoration.
They do not establish the combined protocol, distributed coordination or a
resource envelope. [Prototype results](PROTOTYPE-RESULTS-STREAMING.md) provide
optional detail; the architecture's recovery obligations do not depend on
those experiments having passed.

The consequential choices are the initial flow and operator scope, whether
existing job ownership can coordinate its recovery, and the watermark promise
for any included windows. The recommended first capability is one independently
recoverable flow, including change capture only with both table effects covered.
Does that scope meet the intended use case, and which supported targets and
resource limits should constrain its implementation?
