# What Sail should learn from Flink

Sail should maintain declared tables continuously and recover without losing or
duplicating committed changes. Flink provides useful precedents for coordinating
that work and exposing its lifecycle. The recommendation is to adopt those
separations within Sail’s existing execution model, while proving each table
writer’s recovery behavior independently.

This comparison uses Flink 2.2 documentation, identifying itself as 2.2.1, and
release-2.2.1 source. Flink CDC 3.5 and Iceberg 1.10.0 are separate component
references, not a tested deployment combination. This is documentation and source
inspection, with no Flink execution or comparative performance measurements.

## Compare the right layers

Flink has three relevant layers. **Materialized Tables** let users declare a query
and desired freshness, then manage its refresh job. **The Flink runtime** executes
continuous operators and saves coordinated recovery points. **Flink CDC**, a
separately released integration framework, turns YAML pipeline declarations into
Flink jobs, including database capture, routing and schema evolution.
[Materialized Tables](https://nightlies.apache.org/flink/flink-docs-release-2.2/docs/dev/table/materialized-table/overview/),
[Flink CDC introduction](https://nightlies.apache.org/flink/flink-cdc-docs-release-3.5/docs/get-started/introduction/).

| User need | Flink approach | Implication for Sail |
| --- | --- | --- |
| Keep a declared query result current | Materialized Tables use a continuous job or scheduled full refresh | Keep the declaration separate from execution and publication policy |
| Resume after a failure | Coordinated source and operator snapshots, called checkpoints | Extend Sail’s ordered checkpoint markers into recoverable state |
| Publish without duplicate effects | Connector-specific transactions or repeat-safe writes | A source position alone cannot establish table recovery |
| Capture database changes | Flink CDC combines source-specific snapshot and log reading | Require an explicit transition from initial contents to subsequent changes |

Materialized Tables’ continuous mode resembles the proposed Sail direction. Its
full-refresh mode instead schedules batch overwrites. Flink treats freshness as a
target, and table visibility depends on the connector. In continuous mode,
freshness controls checkpoint frequency. For Sail, report observed publication
lag separately from configured checkpoint frequency; avoid implying that either
is a latency guarantee. Suspend and resume are also useful product precedents:
Flink’s continuous suspension normally saves a durable recovery snapshot before
stopping. [Refresh behavior](https://nightlies.apache.org/flink/flink-docs-release-2.2/docs/dev/table/materialized-table/overview/),
[lifecycle statements](https://nightlies.apache.org/flink/flink-docs-release-2.2/docs/dev/table/materialized-table/statements/).

## Save a consistent point in continuous execution

Suppose two input partitions feed one computation. Saving the first partition’s
new position with the second partition’s old state can skip or repeat work.
Flink sends checkpoint barriers through the dataflow. A barrier marks which
records belong before a recovery point. With aligned checkpoints, an operator
waits for that barrier on all participating inputs before proceeding beyond it.
Recovery restores the corresponding operator state and source positions.
[Flink checkpoint model](https://nightlies.apache.org/flink/flink-docs-release-2.2/docs/concepts/stateful-stream-processing/).

This supports Sail’s continuous flow-event model and initial choice of one aligned
checkpoint at a time. Alignment must cover actual shuffle and fan-in connections,
not just a local merge operator. It does not require converting the stream into
repeated bounded queries.

Flink separates the source definition, a coordinator that assigns files or log
partitions, and readers running in tasks. Reader progress is captured in
reassignable work units called splits. The coordinator also retains its assignment
state. This is a useful model for Sail’s distinction between a `StreamSource`
description and controls reaching the actual running source. Use Sail’s existing
job runner and task actors; copying Flink’s process layout is unnecessary.
[Source API](https://nightlies.apache.org/flink/flink-docs-release-2.2/docs/dev/datastream/sources/).

Flink’s MySQL source illustrates why source recovery needs connector-specific work.
It combines parallel snapshot chunks with database-log positions, checkpoints
completed chunks, then transitions to log reading. Its documentation also warns
that expired log history can prevent restart. Sail’s proposed Delta source needs
its own proof for snapshot identity, retained files and continuation positions.
Passing an offset through the API is insufficient.
[MySQL capture](https://nightlies.apache.org/flink/flink-cdc-docs-release-3.5/docs/connectors/flink-sources/mysql-cdc/).

## Separate a recoverable checkpoint from published output

A table write may succeed while its response is lost. Recovery must recognize the
same write and finish it without inserting the rows again. Flink’s sink API
separates writers that prepare output from committers that publish it. Prepared
commit descriptions can survive recovery. Its delivery guarantees explicitly
depend on the source and sink connectors.
[Sink API](https://nightlies.apache.org/flink/flink-docs-release-2.2/docs/dev/datastream/sinks/),
[connector guarantees](https://nightlies.apache.org/flink/flink-docs-release-2.2/docs/connectors/datastream/guarantees/).

The distinction matters operationally. In Flink 2.2.1, `CommitterOperator` commits
pending output when notified that a checkpoint completed. On restoration, it
also attempts recovered commits. Therefore, checkpoint completion can precede
external publication. Iceberg’s connector documentation explicitly warns that
checkpoints can succeed while table commits fail, and recommends monitoring time
since the last successful table commit.
[Committer implementation](https://github.com/apache/flink/blob/release-2.2.1/flink-runtime/src/main/java/org/apache/flink/streaming/runtime/operators/sink/CommitterOperator.java),
[Iceberg commit monitoring](https://iceberg.apache.org/docs/1.10.0/flink-writes/#metrics).

Sail should expose these states distinctly: recoverable work saved, table write
accepted, and publication completed. Keep the original output identity and
content until uncertain writes are resolved. A bounded pipeline should report
success only after its required table effects finish. This is a recommendation
for Sail’s lifecycle, not a claim that Flink makes all sinks visible atomically.

The Kafka connector shows why “exactly once” needs qualifications. Its transaction
mode requires checkpointing, consumers reading committed transactions, distinct
transaction prefixes between applications, and transaction lifetimes sufficient
for checkpoint and restart delays. These are properties of that connector and
Kafka, not an automatic guarantee for Delta or Iceberg.
[Kafka guarantees](https://nightlies.apache.org/flink/flink-docs-release-2.2/docs/connectors/datastream/kafka/#fault-tolerance).

## Reject an old writer where it can still cause damage

Suppose worker A pauses, worker B replaces it, and A later resumes. Choosing B as
leader does not by itself stop A from writing directly to storage. **Fencing** is
the check that rejects A’s obsolete authority when it attempts that write.

Flink’s internal remote calls carry ownership tokens. Its `FencedRpcEndpoint`
accepts a call only when the token matches the endpoint’s current token. That
protects the covered calls. It does not establish that an arbitrary external
table rejects an old writer using separate storage credentials.
[Flink ownership checks](https://github.com/apache/flink/blob/release-2.2.1/flink-rpc/flink-rpc-core/src/main/java/org/apache/flink/runtime/rpc/FencedRpcEndpoint.java).

The implication for Sail is two separate requirements: reject obsolete task
commands, and enforce current write ownership at the target. Prefer an existing
catalog that can perform the latter check. A protected commit service or a
mandatory table protocol may provide alternatives. Flink’s runtime design does
not choose between them or prove their enforcement. Table creation, maintenance
and other permitted writers must obey the same chosen mechanism. This requirement
is broader than demonstrating that one job recovers through one connector.

## Keep change meaning separate from delivery guarantees

Flink SQL represents changing tables through append, retract or keyed upsert
streams. Retractions remove previous rows; upserts insert or replace by a unique
key. This fits Sail’s existing retraction flags, but encoding a deletion does not
define how to compare late versions of the same business record.
[Dynamic tables](https://nightlies.apache.org/flink/flink-docs-release-2.2/docs/dev/table/concepts/dynamic_tables/).

Flink’s documented SQL deduplication keeps the first or last row ordered by a time
attribute. That operation does not establish Sail’s proposed contract for
contradictory events, stable per-key versions or retained deletion versions.
Those rules remain necessary when inputs can arrive out of business order.
Likewise, Iceberg upsert support requires suitable keys and table features; it
does not by itself supply that version comparison.
[Deduplication](https://nightlies.apache.org/flink/flink-docs-release-2.2/docs/dev/table/sql/queries/deduplication/),
[Iceberg upserts](https://iceberg.apache.org/docs/1.10.0/flink-writes/#upsert).

Flink explicitly documents nondeterminism from changed replay input, processing
time and automatic expiry of state. This supports Sail’s requirement to define
retention from the recovery and ordering contract. Deleting a remembered deletion
after an arbitrary timeout can let an older row reappear. Sail additionally
requires checking original events before discarding losing versions. Repeat-safe
delivery does not validate business meaning.
[Determinism](https://nightlies.apache.org/flink/flink-docs-release-2.2/docs/dev/table/concepts/determinism/).

Flink keeps per-key state in a configured backend, such as heap memory or embedded RocksDB.
Checkpoint storage is configured separately for recovery snapshots.
Sail instead proposes keeping authoritative change versions
with the target, including versions of deleted rows. That moves lookup, indexing and
consistency work into the table adapter. Compare recovery time, lookup cost and retained
bytes before choosing the layout; neither approach is inherently faster.
[State backends](https://nightlies.apache.org/flink/flink-docs-release-2.2/docs/ops/state/state_backends/).

A watermark describes progress in event timestamps. Flink permits older records to arrive
after it; window operators can drop them, allow additional lateness or send them to a
separate output. Sail's existing contract instead promises that older timestamped data
will not follow. Enforce that promise or explicitly revise it before borrowing Flink's
late-data policies. A watermark cannot silently justify forgetting required deletion history.
[Late elements](https://nightlies.apache.org/flink/flink-docs-release-2.2/docs/concepts/time/#late-elements),
[window handling](https://nightlies.apache.org/flink/flink-docs-release-2.2/docs/dev/datastream/operators/windows/#allowed-lateness).

## Borrow bounded mechanisms, not unsupported promises

Flink can avoid waiting for aligned inputs by also saving records still in
transit. These unaligned checkpoints trade waiting time for additional storage
traffic. Sail should first measure alignment delays and retained bytes, then
consider that complexity if needed. Neither mechanism establishes a performance
advantage without comparable workloads and failure tests.
[Checkpoint tradeoffs](https://nightlies.apache.org/flink/flink-docs-release-2.2/docs/concepts/stateful-stream-processing/#unaligned-checkpointing).

Flink’s runtime YAML configuration rejects duplicate keys and uses declared option
types. Flink CDC’s pipeline YAML is a separate interface. For Sail, retain one
strict typed configuration model with optional authoring in Dhall, a typed configuration language. Type checking must
cover connector options and invalid combinations; choosing YAML alone settles
none of those rules.
[Flink configuration](https://nightlies.apache.org/flink/flink-docs-release-2.2/docs/deployment/config/#flink-configuration-file).

Flink’s user functions have explicit evaluation, setup, cleanup and determinism
contracts. These are useful review questions for Sail Extensions. They do not
settle the native Comet interface’s binary compatibility, memory ownership or
worker loading. Those need separate package-level tests.
[Function lifecycle](https://nightlies.apache.org/flink/flink-docs-release-2.2/docs/dev/table/functions/udfs/#runtime-integration).

The remaining human decisions are concrete. Which existing Sail component owns
checkpoint coordination? Which target mechanism actually rejects obsolete writers,
under which storage failures? Before keyed capture, can versions share the target transaction?
Flink supplies strong precedents for these boundaries; Sail must demonstrate the
chosen source-to-table path before replacing its existing runtime.
