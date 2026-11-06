# Decisions for recoverable streaming pipelines on Sail

Sail Declarative Pipelines should keep tables current from declared computations and
resume safely after failures. The proposed design uses Sail's continuous execution
model, adds deterministic updates and deletions, and preserves separately packaged
native Extensions. The first milestone should prove one replayable source feeding
one append-only destination through a process restart.

This memo asks for three architectural decisions. The components built so far provide
reference implementations and tests; they do not yet form a recoverable pipeline.
The decisions determine which components to integrate and what the first delivery promises.

## Use Sail's existing execution ownership

Sail already carries data and ordered control messages through streaming plans. A
`StreamSource` describes a reader; the executing task owns the actual running reader.
Local execution uses the job runner. Distributed execution uses driver and task actors.

Checkpoint requests must reach those live readers, including readers waiting for input.
A checkpoint is a saved recovery point matching input positions, computation state and
intended output. A message passing through the plan identifies its boundary but does
not itself make that state durable. Responses from a replaced task must not advance
the new task's progress.

**Recommend coordinating through the existing job runner and distributed actors.** A
separate coordinator could span independent jobs, but introduces another lifecycle and
ownership boundary. Use it only if coordination across jobs belongs in the first delivery.
Local control tests support the proposed route; real worker replacement and cancellation
still need testing.

There is a related operator choice. User expressions must evaluate data, not internal
control placeholders: a cast on a placeholder can fail a valid query. Dedicated streaming
filter and projection nodes work locally, but alternating data and control messages
produce expensive small batches. Adapting existing operators is another reasonable
mechanism. **Choose which operator boundary Sail should maintain.** Both options must
preserve message order and pass performance checks; the current reference code does
not settle that choice.

## Choose where a destination accepts a write

Delta stores table data in files and records table changes in a transaction log.
It is a practical first source and destination because Sail already reads and writes
it. Use separate source and target tables, initially with the local job runner.
The source requires retained immutable files and a stable storage location. Its
saved description and replay repairs are built; the complete saved file list and
continuous recovery reader remain to be built and integrated.

Recovery has two distinct problems. A write may succeed but lose its reply, so restart
must look up that same write instead of issuing a new one. Also, a paused worker may
resume after a replacement has taken over. Reading the newest table version does not
restore its permission to write. The destination must check current ownership together
with acceptance of each write. This rejection of obsolete writers is called fencing.

**Support one Delta append target first, and select its commit mechanism before code.**
The alternatives are:

| Mechanism | Why consider it | What must be established |
| --- | --- | --- |
| Extend an existing catalog's commit operation | Reuses the catalog's control over table changes | It can atomically check ownership and recognize the exact repeated write; version ordering alone is insufficient |
| Record ownership and append decisions in the same Delta log | Orders takeover and writes together without another commit history | A required writer protocol and enforcement or refusal on every permitted write path, including other engines |
| Use a separate durable commit service | Can provide one acceptance interface for several table formats | Protection against direct writes, recovery of accepted but unpublished output, and safe service restart and restore |

Prefer an existing catalog if it can enforce the contract. For a filesystem-managed
Delta target, compare the same-log and protected-service designs explicitly; neither
is selected by this memo. A property that only cooperating Sail writers honor cannot
control other permitted clients. Creation, maintenance and retries need the same
protection as ordinary appends.

The first failure model also needs a choice. Surviving a process crash while the OS
and filesystem remain running is narrower than surviving power loss or machine loss.
Existing create-only file publication does not establish power-loss durability.
**Recommend the narrower process-crash milestone with that limit stated explicitly,**
or include the broader storage work in the first delivery. Managed Delta and Iceberg
remain required subsequent adapters, each with demonstrated ownership enforcement.

## Keep existing native packages and select the Comet interface explicitly

Existing Extensions use DataFusion's foreign-function interface, which connects compiled
libraries through DataFusion types. Apache DataFusion Comet, a native accelerator for
Spark, offers an Arrow-only C interface for scalar
functions. It reduces coupling to those Rust types, but its binary contract must still
be pinned and checked against the producer.

Replacing the existing interface would force package migration alongside streaming work.
Supporting both adds loader and compatibility responsibilities. **Recommend preserving
the existing route and letting each exported function select the additional C interface.**
Decide whether that extra boundary belongs in Sail's host.

Standalone adapter and producer probes support feasibility. Package and worker integration
must still verify matching code, memory ownership, cancellation and returned-array lifetime.
Native code remains trusted code; a version check is not a sandbox. A C interface for
relations is a separate decision because scalar calls do not define source execution.

## What Flink contributes to these decisions

Flink's Materialized Tables pair declarations with continuously running jobs. Its runtime
coordinates source and operator snapshots, while connectors determine when output becomes
visible. Iceberg's Flink connector can complete a checkpoint before a table commit succeeds.
This supports keeping saved recovery progress separate from publication status. Flink's
internal ownership checks also do not prove that an arbitrary table rejects an old writer.
The [Flink comparison](FLINK-COMPARISON.md) supplies versioned sources and explains the
implications; it does not substitute for testing Sail's chosen target.

## The requested outcome

Select the execution and operator boundaries, first target's commit mechanism and failure
model, and native package boundary. Append recovery comes before keyed change capture
because the latter adds durable record versions to that same recovery path. Configuration
validation and native interface work can proceed independently once their own boundaries
are agreed. Strict configuration validation, optional authoring with the typed configuration
language Dhall, and deterministic change ordering remain requirements. Spark compatibility
cannot justify weaker behavior.

For fuller context, read [the overview](HUMAN-REVIEW.md),
[streaming](STREAMING-ON-STREAMSOURCE.md), [change capture](CHANGE-CAPTURE-ON-STREAMSOURCE.md),
then [Extensions](EXTENSIONS-STREAMSOURCE-INTEGRATION.md). The
[delivery plan](REDESIGN-PLAN.md) and detailed evidence are optional references.
