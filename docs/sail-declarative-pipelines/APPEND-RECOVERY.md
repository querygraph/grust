# Recover a complete Delta append pipeline after a process crash

A pipeline must resume correctly when a write succeeds but its reply is lost. Build
one usable path that reads a Delta table continuously, applies a declared computation,
and appends to another Delta table. After restarting, it must finish the original saved
work before reading beyond it. A replaced process must be unable to commit new writes.

This is the first local implementation of the shared streaming design. It covers process
crashes while the operating system and local filesystem survive. Power loss, storage
rollback, concurrent replacement of table directories, distributed execution and transactions
across tables remain outside this milestone. Its limits must be explicit in the public API.

## Reuse Sail and make one implementation choice

Use `StreamSource`, Sail's streaming planner and data-only expression operators, and
`LocalJobRunner`. One long-lived reader consumes files and later commits; checkpoints
do not launch a sequence of bounded queries. Reuse Arrow batches, Parquet reading,
Delta metadata and the existing memory pool. Attach an append consumer to the prepared
logical stream before physical planning; the ordinary collector drops control markers
and rejects continuous input. The initial query supports one source with
row filtering and projection. Reject stateful operators, additional inputs and unsupported
expressions before starting effects.

Choose the Delta transaction log itself as the first target's ownership and recovery
record. A commit service would require another durable history and a protected deployment.
An existing catalog is preferable where it can enforce the same checks, but no such
adapter is qualified here. The same-log choice gives one table a single ordering point:
creating its exact next log version only if that version does not already exist.

Add a required writer feature identifying the recovery protocol. Generic Sail writers
must not advertise support for it. Protocol-compliant other writers must refuse the table;
the dedicated pipeline writer alone implements its ownership checks. Ordinary reads keep
their table interface. This protects against obsolete cooperating processes, not arbitrary
raw modification by a principal with filesystem access. Creation, maintenance and every
exposed mutation route must enforce the protocol or refuse before modifying reachable data.

## Public entry and fixed computation

Provide a local `sail pipeline run --config <file>` entry backed by a typed runtime
API. The ordinary Spark `writeStream` lifecycle does not save the source positions and
prepared writes required by this command. Its declaration
names one pipeline, one local Delta source, one target and a SQL query over `input`.
A bounded mode captures the current input end and finishes its final write; continuous
mode waits for later commits. This first entry does not replace the existing bounded SDP API.

A `run_id` names the requested run separately from the fixed pipeline computation. A
retry with that identifier resumes its saved end or returns its recorded completion,
even when new source data has arrived. A different identifier can capture a new end
only after the preceding run completes. Save that end before processing any output.
Reusing an older identifier must never start fresh work; refuse it with its recorded
status if returning its old result is unavailable. Keep completed identifiers in the
retained log, including runs that produced no rows. Operational budgets and batch size
may change on restart without changing the computation.

Parse configuration into a strict versioned type. Reject duplicate or unknown keys,
wrong types, conflicting paths and unsupported choices. Start with JSON, which is also
a concrete rendered artifact for future YAML and optional Dhall frontends. Keep those
frontends and the wider SDP declaration API as required subsequent integration work.

Before target creation, save an immutable definition containing normalized configuration,
the resolved source descriptor, output schema, runtime interpretation version and target
identity. Restart reads that original definition rather than resolving a fresh start.
Changing the source, query or interpretation requires an explicit new generation; silently
reusing the old checkpoint is refused. Bind actual runtime build identity where needed
for deterministic recomputation, and reject unknown interpretation versions.

## Read reproducible input

The first source uses a stable local table location and retained immutable data files.
Its descriptor fixes table identity, schema and interpretation. This first adapter
requires canonical table-relative data paths; external and absolute data paths are refused. Detect observed recreation,
missing files, incompatible schema/protocol changes and data-changing tail removals.
An empty range still checks identity.

Save exact file metadata and ordering in bounded immutable pages before a recovery point
can refer to them. Reuse the complete Add decoder and sorted replay where their contracts
apply; validate raw log input before parsing can discard duplicate fields or other evidence.
The first JSON-history path requires complete contiguous JSON history to construct an
initial snapshot. Refuse missing history explicitly; checkpoint-only snapshot reconstruction
requires a later qualified decoder rather than a permissive fallback.

A source position names its descriptor, saved segment and the next physical row in a file,
or an explicit position after a commit version. Count before filtering or projection so
changed batch sizes do not change progress. File scans preserve the fixed schema, partition
values and supported column mapping. Unsupported source features receive explicit errors.
No missing input may advance progress.

Route controls to the executing reader. When a checkpoint reaches the output, its source
position describes exactly the data before that marker. Hold later input while output is
saved and committed. Use one partition and one checkpoint at a time initially; no claim
of distributed alignment follows from that restriction.

## Put ownership, saved work and completion in one history

Store a versioned application record in each relevant target log commit. It contains the
immutable definition identity, current owner number, committed source position, last write
receipt and at most one pending prepared-write reference. A receipt records which exact
output was published. The log is the only advancing checkpoint history; there is no second
mutable latest-checkpoint file.

| Operation | Durable change |
| --- | --- |
| Create | Version zero installs table metadata, required protocol and initial ownership together |
| Take over | The next log version changes ownership and preserves all pending work and completion evidence |
| Prepare | After immutable output and its metadata exist, record their exact reference and input boundary |
| Publish | One log version adds the output files, records its receipt and advances the source position together |

Creation has a stable request identifier. A retry observes the same table or refuses a
conflicting definition; it cannot enroll an unrelated existing table. Taking over is a
separate explicit operation with the expected owner, inspected log version and request
identifier. Check both committed and pending run identities before acquiring ownership.
A different run cannot interrupt a prepared starting boundary. If the inspected state
changes before acquisition, refuse without replacing its owner; the caller can inspect
again in a new attempt. Repeating a superseded acquisition must fail rather than take
ownership again. Retrying an append
never acquires ownership.

If A checks ownership at version N and B takes over at N+1, A cannot create N+1. Its
retry must reload and reject A's original owner number. If A publishes first, B must
observe that publication before taking over. Apply this check on every retry, including
after metadata refresh. Ownership becomes effective only when its log entry is published.

A successor first completes any prepared write using its saved output and original
identity. The append receipt and new source position become visible atomically. A lost
reply is resolved by looking up that same receipt. Publication requests name the exact
prepared-write digest rather than publishing whatever work is currently pending.
Reusing a write identifier for different
content is an error. Writes have increasing sequence numbers; preparing the next write
acknowledges the previous receipt. Takeover must preserve that receipt until it is no
longer needed to resolve uncertainty.

## Bound preparation and preserve uncertain work

Stream output into uniquely named immutable Parquet chunks. Check memory and disk limits
before growth, bound file-list pages and log records, and fail explicitly when a record or
checkpoint exceeds its configured limits. Do not collect an entire table or checkpoint
in memory. Saved metadata includes content digests; verify it before publication or restart.
Committed input files are immutable by contract rather than rehashed on every read.

The first implementation performs no automatic deletion of recovery artifacts. Count
retained preparation against an explicit budget and stop safely when it is exhausted.
A later cleanup policy must prove that no pending write or supported restart needs each
artifact. Process cancellation or loss of ownership does not make uncertain files disposable.
The initial directory budget conservatively counts published output too. Increasing it
allows recovery without changing the computation. These checks bound one active writer's
preparation; a hard quota shared by overlapping processes requires a filesystem quota.
Published output also has the table's ordinary retention responsibilities.

## Build and verify in reviewable pieces

Implement target conditional publication and creation, saved source segments and continuous
reading, then typed configuration and coordination. Their module interfaces must keep
format-specific operations in the Delta crate and job lifecycle in the existing execution
and session layers. A CLI wrapper is not a second execution engine. Add worker codecs or
explicitly refuse unsupported distributed reconstruction for every new physical node.

Use real subprocess failures with deterministic stopping points. Kill the pipeline before
and after preparation, and after append publication before its reply. Add more input while
it is down, restart with the same definition, then restart again without new input. Read
the target through Sail's ordinary Delta reader and compare the full row multiset, including
legitimate identical rows. This detects both duplicate writes and accidentally skipped rows.
Deterministic stopping points use a no-op observer in production and a default-off test
feature in the CLI. Test controls are not part of pipeline configuration.

Pause A immediately before conditional publication, let B take over, then resume A
before B publishes and require rejection. Also resume A after B publishes: it may
recognize the same receipt, but must never create a second append. Test concurrent creation, changed content under one write
identifier, missing input and prepared files, empty input, changed batch sizes and bounded
completion. Ordinary reads must succeed; ordinary writes to a protected target must fail
without changing its log or rows. Test resource failures without advancing progress.

A task panic or a closed status channel must report failure rather than successful
termination. Verify those cases with focused regression tests and a failing control. Keep all failures, source pins and performance costs
in the evidence. Passing these local tests establishes this path only; migration of SDP,
keyed change capture, managed targets, Extensions, broader failure models and distributed
recovery remain part of the full redesign.
