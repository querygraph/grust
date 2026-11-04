# Streaming tables on Sail's flow event model

Streaming tables let a pipeline append newly available rows without rebuilding
the target from its entire source history. The intended guarantee is that a
successful recovery neither loses nor duplicates those rows. This proposal
uses Sail's existing streaming plans to provide that behavior.

It does not propose a second streaming engine or full Structured Streaming
operator coverage. Recovery scope and changes to existing marker contracts
need agreement before production implementation.

## Fit with Sail

Sail's `StreamSource` provides a streaming scan. Its output is a sequence of
flow events: data batches or control markers carried in order with the data.
A retraction flag identifies rows that cancel earlier rows. The existing
markers describe latency, watermarks, checkpoints and end of data.

The streaming rewriter already handles sources and several stateless
operations. At the inspected upstream revision it refuses windows,
aggregates, joins and repartitions. The proposed additions are checkpoint
coordination, source participation, table sinks and selected stateful
operators. The existing encoding remains the starting point, with any
contract changes discussed explicitly. The
[marker definitions](https://github.com/lakehq/sail/blob/62251e0a27bbab0a15547562e829cad2a418f353/crates/sail-common-datafusion/src/streaming/event/marker.rs)
already describe waiting for a checkpoint after end of data.

## Decide the recovery scope first

A checkpoint identifies a cut through the source positions and operator
state. A sink makes the corresponding output visible through a table commit.
Recording positions before a commit is necessary, but does not alone make
recovery safe when effects complete separately.

Suppose two sinks have completed a checkpoint at source position 3. The next
checkpoint records position 6, but only one sink commits. A restart at 3
must not reuse that identifier for rows through position 10: the completed
sink would skip rows 6 through 9. A new identifier would instead repeat rows
3 through 5 in that sink.

There are three useful initial scopes:

- One append sink whose output fits one table transaction.
- One flow that may have several effects, including change capture's two
  table merges, with recovery tracking each effect.
- Several independent sinks coordinated as one recoverable query.

We recommend starting with one flow and deferring independent multi-sink
queries. If change capture is included, its two effects still require a
recovery protocol. Any prepared checkpoint must keep its boundary and
required state while an effect can still depend on them. An identifier must
not silently acquire different rows. Atomic visibility across tables is a
separate guarantee and is not claimed here.

Would you include two-effect change capture initially, or start with one
append transaction? The answer determines what the recovery experiment must
prove before a sink can be offered for merge.

## Coordination and bounded completion

We propose that the job runner own checkpoint coordination. Local execution
has no driver; distributed execution would delegate coordination to the
driver and reach sources through their running tasks. A separate optional
source capability would request markers, report positions and establish a
bounded end. The exact interfaces depend on the recovery decision.

Operators with several inputs would align markers by holding each input at
its barrier until the other inputs reach the same checkpoint. Requests must
be serialized or queued so no input misses an identifier. Source end,
physical stream closure and completed sink effects need distinct accounting.
The run finishes only after the globally final checkpoint completes.

Spark 4.2.1 pipelines use available-now execution: each source captures a
target offset and may process it over several batches. It does not imply one
checkpoint or a single simultaneous snapshot across all sources. We propose
allowing intermediate checkpoints plus a mandatory final checkpoint for
bounded runs. A continuous run would have no bounded end and would extend
Spark's pipeline execution modes. The
[available-now source contract](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/catalyst/src/main/java/org/apache/spark/sql/connector/read/streaming/SupportsTriggerAvailableNow.java)
states the offset and multiple-batch behavior.

## Sinks, sources and state

For Delta, the proposed commit tag uses its application identifier and
transaction version. The application identity must survive restarts and
separate full refresh generations. The checkpoint identifier names one
prepared boundary. Other formats need their own verified commit and retry
contract; attaching metadata alone is not an implementation of idempotency.
An append sink rejects retractions.

Apache Iggy is a message broker that stores data in partitions. Its source
would record each partition's next offset and incarnation,
the identity that distinguishes a recreated partition. Reads and bound
capture must reject retention gaps and incarnation changes before advancing
progress. The client belongs in an optional crate. Upstream dependency
compatibility is a separate admission decision.

The initial state store candidate uses Arrow segments and manifests naming
complete snapshots. Recovery must pair source positions with the correct
operator state and configuration. State remains while any incomplete effect
or recovery point requires it. Merely recording a newer position does not
permit deleting older state. Publication durability, ownership and cleanup
need a defined protocol before the local file experiment becomes production
storage.

Checkpoint frequency trades replay size against commit and snapshot work.
Periodic checkpoints alone do not bound memory. The prototype buffers append
rows and rewrites complete window state; byte limits, backpressure or spill
need an explicit resource decision. No performance envelope is established.

## Watermarks and differences from Spark

An event-time watermark lets an operator decide which old state it can
discard. Spark derives progress from observed event times and a configured
delay, and its late-row decisions depend on batch boundaries.

Sail's current marker instead promises that older timestamped data will not
follow. Placing an event-time operator after a projection and permitting late
rows needs an agreed interpretation or amendment of that contract. We should
settle it before adding window and deduplication operators. Immediate marker
advancement could change which rows Spark accepts within one batch; that is
an open behavior choice, not an established compatibility claim.

Stream joins and broader stateful coverage remain outside the initial scope.

## Evidence and the next decision

Local experiments exercise marker transport, controlled alignment, one file
sink's restart, separate Delta write options, broker range checks and window
restoration from recorded events. Those historical runs do not establish a
complete recovery protocol. Source review identified untested completion,
concurrent-request and bound-capture cases, plus a possible concurrent Delta
creation issue.

Spark 4.2.1 source and the pinned Sail revision were inspected for this
proposal. No Spark, broker or Rust suites were rerun during its revision.
Distributed coordination, durable recovery and planner integration remain
unbuilt.

Please decide the initial recovery scope first. We would then use one small
local experiment to distinguish the selected protocol's failure cases, and
bring its evidence back before preparing an implementation for merge.
