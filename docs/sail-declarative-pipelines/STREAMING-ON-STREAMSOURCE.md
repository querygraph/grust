# Recoverable streaming tables on Sail

A streaming table continuously appends new rows from a declared computation. If its
process fails, restarting should neither duplicate rows already written nor skip rows
still waiting to be written. Build that guarantee on Sail's continuous execution model,
starting with one computation feeding one destination table.

The first delivery handles append output. Keyed replacements and deletions add the
rules in the change-capture proposal. General stateful queries and transactions across
independent pipelines require further contracts.

The pipeline keeps its identity across task and process retries. A rebuild gets a new
computation generation so its writes cannot be confused with the previous computation.

## Extend Sail's existing execution model

Sail's `StreamSource` describes a scan. Its streaming planner produces a continuous
sequence of flow events: data rows and control messages. Data carries retraction flags
that cancel earlier rows. Control messages indicate timing, progress, checkpoints and
end of input. A checkpoint marks a point from which execution intends to recover;
the message alone does not save anything durably.

| Existing component | Proposed responsibility |
| --- | --- |
| Streaming planner and operators | Preserve data and control order; evaluate user expressions only on data |
| Sources and worker plan reconstruction | Read reproducible input and let controls reach the running reader |
| Merge, shuffle and replica paths | Coordinate matching recovery points across their inputs |
| Local job runner, driver and task actors | Save progress for the job and reject responses from replaced task attempts |
| Table writers and catalogs | Commit the intended output, recognize retries and reject obsolete writers |
| Memory pools and temporary storage | Bound queued data, saved output and operator state |

User expressions must never evaluate internal control placeholders. A cast can fail on
such a placeholder even when every user row is valid. Dedicated streaming filter and
projection operators solve this locally, but alternating data and control messages
currently produce costly small batches. Changing existing operators is another option.
Choose the boundary with measured batching costs while preserving event order, including
control messages that precede a later expression error.

## Read the same input after restart

A saved position is useful only if the source can reproduce the input it identifies.
Record which source is being read, how positions are interpreted, and how long the
underlying input remains available. Recreating a table or broker partition must create
a different source identity, even if its name is unchanged.

Delta stores table data in files and records changes in a transaction log. For a Delta
source, the recovery record needs the table identity, schema, log versions
and exact files to read. A saved file list does not preserve the files themselves.
The initial design requires retained, immutable data files and a stable storage location;
concurrent replacement of that location is unsupported. Missing history or changed
identity must stop recovery rather than silently omit data.

A run that stops after existing input captures an ending position and reads exactly
that range. It must check identity even when the range is empty. Reading continuously
uses the same protocol without a fixed end. Several sources captured separately do
not form a simultaneous snapshot merely because their positions were saved together.

Checkpoint and cancellation requests must reach the reader owned by the executing task,
including while it waits for input. Route them through the local job runner or existing
distributed actors. A plan object cannot control a separate reader reconstructed on a
worker. Identify each running partition and task attempt so late replies from an old
attempt cannot advance progress. Define how newly discovered partitions join the job.

Sail's rate and socket sources do not currently provide reproducible input. Producing
a checkpoint message is useful for testing controls, but does not make a source recoverable.

## Save matching progress across the computation

At a checkpoint, input positions, operator state and intended output must describe the
same work. Initially allow one checkpoint at a time. When one input reaches its marker,
hold it there until the other participating inputs reach that checkpoint. This is
checkpoint alignment. It avoids saving data still moving between operators, but waits
for the slowest input.

Alignment must cover the real transport graph, including shuffle, replicas and sources
whose rows an optimizer removes. Testing a local merge does not prove that coverage.
Saving in-flight data instead can reduce waits, but adds recovery state and complexity;
introduce that option only when measurements justify it.

An input ending is different from a transport closing, a cancellation or a failure.
Keep a bounded source available until its final checkpoint is resolved. Report a bounded
run as successful only after its final required writes finish.

## Save intended output before writing it

Suppose rows through source position 6 reach the destination, but the commit reply is
lost. Restarting with a new write identifier can append them twice. Reusing the original
identifier for rows through position 10 can instead skip the extra rows when the target
recognizes a repeated write.

Before writing, persist a prepared checkpoint: the input range, computation and
configuration, required state, intended output and stable identifiers for each write.
Save immutable output chunks unless retained input and deterministic computation prove
that the exact output can be reproduced. After a lost reply, look up whether the original
write was accepted and finish it; never reuse its identifier for different content.

Distinguish a recoverable checkpoint from output visible in the table. A target may
accept responsibility for a write before making it visible. Save that acceptance and
finish publication after restart. The target must distinguish accepted, rejected and
unknown outcomes. For several writes, record completion separately; this does not
promise atomic visibility across tables.

Delta application transaction tags can help recognize repeated appends. They do not
prove that input is reproducible or that a writer still owns the pipeline. Retain
prepared output and state while pending writes or supported restart points need them.
Missing or corrupt recovery files are errors. Restoring always uses the state named
by the chosen recovery point.

Before activating a rebuilt generation, resolve pending writes under their original
rules. Already accepted writes must finish; work known not to have been accepted may
be explicitly superseded. A successor can take ownership to complete that recovery.

## Stop replaced workers from committing new work

Consider worker A pausing long enough for worker B to take over. A later resumes and
reads the newest table version. An ordinary version-conflict check can now accept A's
write, although A no longer owns the computation. A timeout or lease permits takeover;
it does not by itself prevent that write.

The destination must reject replaced owners at the point it accepts a write. This
protection is called fencing. Check ownership and the write together as one atomic
decision. Ownership needs a number that changes on takeover, and the request must also
identify the table, the computation generation and the exact write content.

A successor may finish publishing an already accepted write with its original content.
The old worker cannot authorize new work. Creation, schema changes, refresh and
maintenance need the same protection, or an explicit refusal. Failure of the authority
that accepts writes must not enable an unchecked alternative route.

Prefer an existing catalog when it can enforce this contract. Other choices are checks
in the table's own commit protocol or a protected commit service. Every permitted writer
must enforce the rule or be unable to write; a custom property that another engine
ignores is insufficient. The first delivery can support one such target. Managed Delta
and Iceberg need their own enforcement before joining the supported durable paths.

## Bound resources and make configuration precise

Measure queued data, prepared output and state in bytes. Use Sail's memory pools and
temporary files with explicit disk and retention limits. Periodic checkpoints do not
bound memory. Adding blocking queues can also deadlock a producer feeding several
consumers; test progress and total resource use under slow readers together.

Validate YAML, JSON and API input through one strict, versioned type before planning.
Reject unknown or duplicate keys, incorrect scalar types and conflicting options,
including connector options. Dhall, a typed configuration language, can optionally produce
the same validated input. Server validation remains authoritative. Pin its compiler and bound its
imports and resource use, or accept only rendered configuration in deployments.
Save the effective configuration with the checkpoint so restart cannot change the work.

Refuse unsupported output modes and retractions explicitly. A watermark states progress
in event timestamps. Sail's contract promises that older timestamped data will not follow;
future event-time operators must honor that promise or propose a changed contract first.
Late-data handling is separate from checkpoint frequency.

## What would establish this design

The local Delta append implementation connects these boundaries through a single reader
and protected target. Its [qualification summary](HUMAN-REVIEW.md) distinguishes tested
behavior from remaining work. Acceptance requires process and task failures around saving
work and publishing output, including lost replies, replaced workers, missing input,
source replacement, final completion and resource exhaustion. Distributed execution and
other target adapters need the same evidence for their own contracts.

Flink offers a useful comparison: it coordinates source and operator state through
checkpoints, while external publication depends on the sink connector. Its internal
leader checks cannot substitute for destination enforcement. The
[Flink comparison](FLINK-COMPARISON.md) supplies sources and connector examples.

Confirm or adjust the source-control route, expression-operator boundary and first
destination's commit mechanism before adopting them as supported interfaces. The [decision memo](REDESIGN-REVIEW-PACKET.md)
contains the alternatives; [architecture](STREAMING-ARCHITECTURE.md) and
[commit ownership](FENCED-TABLE-COMMITS.md) are optional technical references.
