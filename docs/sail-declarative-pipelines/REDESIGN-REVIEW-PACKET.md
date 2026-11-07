# Decisions for recoverable streaming pipelines on Sail

Declarative pipelines let a user describe the tables they want instead of the jobs that
produce them. Each table or view is declared as a query over sources or other tables,
in SQL or Python. The engine reads the declarations, works out the dependency graph,
creates the tables, and keeps them up to date in the right order. Users write no
orchestration code, no scheduling, and no bookkeeping of what has already been processed.
Spark 4.2 ships this as Spark Declarative Pipelines, with an unchanged client that talks
to the server over Spark Connect; we have implemented its batch part on Sail.

The same declarations cover streaming and change data capture. A **streaming table**
processes only data that arrived since the last run, or continuously as it arrives,
instead of recomputing everything. A **change-capture flow** reads a stream of inserts,
updates and deletes from a source database or log, keyed by a primary key and ordered
by a version, and keeps a table holding the current state of each record, even when
changes arrive late or out of order. Both are what users otherwise hand-build with
streaming jobs, merge statements and checkpoint directories.

This memo proposes how Sail should run those two incremental kinds. Build them on
Sail's existing continuous `StreamSource` execution rather than on repeated batch jobs,
make the result of a change-capture flow depend only on the data, not on how it was
split into batches, and keep separately packaged native Extensions working inside
pipelines. Because these pipelines run unattended and write tables, the part that most
needs agreement is what happens when they stop partway: a restart must neither lose
rows nor write them twice. The decisions below are mostly about that.

The memo asks for four architectural decisions. To test the design, a local
implementation reads one Delta table continuously and appends to another, and resumes
correctly after the process is killed at any point before or after a write, including
when the write succeeded but its reply was lost. It is local only: one source partition,
the local job runner, process crashes but not power loss. It is offered as reference
material for these decisions, in a few large pull requests that each explain one
boundary, not as something to merge as is. The proposed first milestone is that same
shape, one replayable source feeding one append-only table through a restart.

## Use Sail's existing execution ownership

Sail already carries data and ordered control messages through streaming plans. A
`StreamSource` describes a reader; the executing task owns the actual running reader.
Local execution uses the job runner. Distributed execution uses driver and task actors.

Checkpoint requests must reach those live readers, including readers waiting for input.
A checkpoint is a saved recovery point matching input positions, computation state and
intended output. A message passing through the plan identifies its boundary but does
not itself make that state durable. Responses from a replaced task must not advance
the new task's progress.

**Decision 1: recommend coordinating through the existing job runner and distributed
actors.** A separate coordinator could span independent jobs, but introduces another
lifecycle and ownership boundary. Use it only if coordination across jobs belongs in the
first delivery. Local control and process-replacement tests support the proposed route.
Distributed task replacement and cancellation still need testing.

**Decision 2: where user expressions are kept away from control messages.** A control
message travels as a row whose data columns hold placeholders, so a strict cast on a
placeholder can fail a valid query. The reference code adds dedicated streaming filter and
projection nodes that evaluate only data rows and pass control rows through in order. On
data-only input they cost about the same as the ordinary operators. When control messages
alternate with data row by row, each run becomes its own output batch, and the measured
slowdown is roughly a hundred to a thousand times; with one control message per batch it
is two to three times. The alternative is to change Sail's existing filter and projection
to skip control rows. **Choose which operator boundary Sail should maintain**, and whether
batching adjacent outputs under a byte limit is an acceptable way to remove that cost.

## Choose where a destination accepts a write

Delta stores table data in files and records table changes in a transaction log.
It is a practical first source and destination because Sail already reads and writes
it. Use separate source and target tables, initially with the local job runner.
The source requires retained immutable files and a stable storage location. Its
reader saves exact file lists and physical-row positions for restart. Initial snapshot
capture requires contiguous JSON history; source data files must remain available.

Recovery has two distinct problems. A write may succeed but lose its reply, so restart
must look up that same write instead of issuing a new one. Also, a paused worker may
resume after a replacement has taken over. Reading the newest table version does not
restore its permission to write. The destination must check current ownership together
with acceptance of each write. This rejection of obsolete writers is called fencing.

**Decision 3: support one Delta append target first, and choose its commit mechanism
explicitly.** The local implementation records ownership and publication in the same Delta
log. To stop other writers from bypassing that check, it marks each pipeline target table
with a Sail-specific required writer feature: Delta writers that do not implement the
feature must refuse the table, and ordinary Sail writes refuse it too. Reads are unchanged.
That is a visible change to what these tables are, and it needs your agreement.
The alternatives are:

| Mechanism | Why consider it | What must be established |
| --- | --- | --- |
| Extend an existing catalog's commit operation | Reuses the catalog's control over table changes | It can atomically check ownership and recognize the exact repeated write; version ordering alone is insufficient |
| Record ownership and append decisions in the same Delta log | Orders takeover and writes together without another commit history | A required writer protocol and enforcement or refusal on every permitted write path, including other engines |
| Use a separate durable commit service | Can provide one acceptance interface for several table formats | Protection against direct writes, recovery of accepted but unpublished output, and safe service restart and restore |

Prefer an existing catalog if it can enforce the contract. The local filesystem target
uses the same-log design to avoid a second durable authority. Decide whether that cost
and storage contract fit Sail, or whether a catalog or protected service is preferable. A property
that only cooperating Sail writers honor cannot control other permitted clients. Creation, maintenance and retries need the same
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
Supporting both adds loader and compatibility responsibilities. **Decision 4: recommend preserving
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
A separate comparison with Flink supplies versioned sources and explains the
implications; it does not substitute for testing Sail's chosen target.

## The requested outcome

Select the execution and operator boundaries, first target's commit mechanism and failure
model, and native package boundary. The reference implementation is started by a separate
local command, `sail pipeline run --config <file>`, rather than through the Spark pipelines
API; say whether a separate entry point is acceptable or whether recovery must arrive
through the existing API first.

Separately, testing found defects in the current streaming code on `main` that do not
depend on these decisions: marker encoding drops decimal precision and schema metadata
and decodes payload-free batches with zero rows, the streaming filter evaluates casts on
marker placeholders, and a failed streaming query can be reported as successful. Each fix
has a test that fails on `main`, and they can be reviewed as one small pull request now.

Append recovery comes before keyed change capture because the latter adds durable record
versions to that same recovery path. Configuration validation and native interface work
can proceed independently once their own boundaries are agreed. Strict configuration validation, optional authoring with the typed configuration
language Dhall, and deterministic change ordering remain requirements. Spark compatibility
cannot justify weaker behavior.

Optional detail, not needed to answer the questions: the streaming, change-capture and
Extensions proposals, a comparison with Flink's design, and the test evidence for the
reference implementation.
