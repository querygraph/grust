# StreamSource resource and performance audit

## Scope and verdict

Build on Sail's flow events, job/task ownership, memory pools, temporary-file
manager and object-store interfaces. These are useful integration points,
not proof of bounded memory or durable stream recovery. The current transport,
prototypes and bounded change-capture implementation contain allocations that
are not governed by the configured memory pool in the inspected paths.

Correctness comes first. Preserve marker ordering, validated immutable retry
input, commit-time fencing and recovery references while replacing unbounded
materialization. Neither Spark compatibility nor an assumed performance benefit
justifies dropping those guarantees. No benchmark establishes a throughput,
latency or memory envelope for the proposed integrated runtime.

This is read-only source inspection and complexity analysis. No Rust, Spark,
broker, benchmark or runtime test was executed. Proposed tests below are not
results. The saved request and AGENTS.md, LAKESAIL.md, SHEHAB.md,
WRITING-RULES.md and CLARITY.md were read. The engineering-over-conformance
directive governs the recommendations.

References use these roots:

| Prefix | Checkout and inspected revision |
| --- | --- |
| U | `/Users/alexy/src/sail/tmp/streamsource-review-20261105-85c6cca01`, `85c6cca01cd521dd778bc200c987a34edf141de1` |
| P4 | `/Users/alexy/src/sail-proto-p4`, `4fad33ca531ec44170d0e8d11c794df14835ff37` |
| P3 | `/Users/alexy/src/sail-proto-p3`, `ef5f848a758ed48067a751165d8bf9a756f2c482` |
| R | `/Users/alexy/src/sail-pipelines-proposal`, `99dc47788941daf28eec847527949a4cadafdbd2` |

All source paths below begin with `crates/`. `performance-source-manifest.json`
records file hashes and inspected sections. Foundation and fencing findings
were read in STREAMSOURCE-FOUNDATION.md and FENCING-AUDIT.md. Their broader
correctness reviews are not independently repeated here.

## Material findings

### 1. Transport channel capacity does not bound retained memory

U `sail-execution/src/stream/local/memory.rs:35–42,62–139` creates bounded
channels but uses an unbounded `VecDeque` for each slow replica. Writes use
`try_send`, append overflow and report active without waiting for that replica.
Finalization drains overflow at `:142–157`; a long-running stream cannot rely
on finalization to constrain its backlog. Arrow clones share payload buffers,
so replica count is not an automatic multiplier of all payload bytes. A slow
replica nevertheless retains those buffers after faster consumers release them,
and each replica adds queue metadata.

This is not fixed by replacing the deque with a blocking send. The comment at
`:64–68` identifies deadlocks with bounded buffers; channel writes and
finalization deliberately run concurrently in `stream/writer.rs:50–79`.
Preserve that progress property. Design byte credits, spill or explicit
unsupported-topology admission with the actual producer/consumer graph.
Test a slow or unread replica, dependent consumers, cancellation and final
checkpoint delivery. Control progress must remain possible under resource
pressure without allowing markers to overtake preceding data.

### 2. Reuse existing resource managers, but account for custom allocations

U `sail-session/src/runtime.rs:63–97` already installs Greedy/Fair or unbounded
DataFusion memory pools and a temporary-file manager with a size setting.
The custom deques, append buffers and snapshot maps inspected here do not
reserve their allocations through those interfaces. Merely selecting a bounded
pool therefore does not account for them.

Use the existing runtime resource interfaces where their ownership fits.
Charge retained Arrow buffers, encoded key/order data, queue metadata,
serialization buffers and state separately, with a documented policy for
shared buffers. Budget aggregate usage across active partitions and tasks;
many individually bounded queues can still exceed a process limit. Temporary
spill is not durable recovery storage and must not own accepted artifacts.

### 3. Existing shuffle storage is a reuse seam, not a ready stream spill log

U `sail-execution/src/stream/storage/core.rs:23–25,137–144` describes blocking,
attempt-scoped shuffle storage. Its writer serializes into `Vec<u8>` at
`:215,228–230`, then checks the rotation size only after writing a complete
batch at `:278–290`. One large batch can exceed that threshold. Fetch lists
all objects, sorts their paths and loads each object's bytes at `:84–127`.
Its configured file size is not a hard memory bound.

Reuse object-store access and encoding where appropriate, while defining
chunk publication, bounded reads, resumable manifests and recovery-aware
retention. Do not attach durable checkpoints to job-attempt cleanup.
U `stream/accessor.rs:285–340` and `stream/merge.rs:21–35` merge channels with
`select_all`; `stream/celeborn/core.rs:141–167` does likewise. Neither supplies
checkpoint alignment. Correct exchange marker routing is required before
comparing aligned and unaligned checkpoint costs.

### 4. The append prototype buffers an entire interval; cadence is not a limit

P4 `sail-physical-plan/src/streaming/append_sink.rs:170–203` retains every data
batch until a checkpoint and stops polling input while awaiting the gate and
commit. With a final-only checkpoint, the interval can be the entire backlog.
Intermediate checkpoints can shorten intervals, but large batches, delayed
markers or slow commits still require explicit resource policy. The sink
requires one input partition at `:221–223`; this is evidence for a narrow
mechanism, not scalable parallel commit performance.

Separate checkpoint triggers from hard limits. Choose triggers from recovery
distance, output visibility and admitted workload costs; combine elapsed time
or bytes with a mandatory final boundary where appropriate. No particular
period is justified by the evidence. Limit pending checkpoints and prepared
bytes, stop admission or spill before exhaustion, and fail explicitly if the
guarantee cannot be maintained. A checkpoint request must not queue indefinitely
behind already exhausted memory. Stage output incrementally under an immutable
identity instead of requiring a whole-interval `Vec<RecordBatch>`.

P4 `streaming/merge.rs:213–239` has a bounded event-count queue and pauses each
input at its marker. It waits for slower participants and bounds neither event
bytes nor upstream transport buffers. Measure alignment delay and retained
bytes together. Saving in-flight rows is an alternative with additional state,
I/O and recovery complexity, not an assumed improvement.

### 5. Full snapshots amplify state size, allocation and checkpoint work

P4 `streaming/window.rs:178–190,218–250` stores every open window/key pair.
`:254–274,302–310` materializes the entire map into Arrow arrays at each
checkpoint while the map remains live. `streaming/state_store.rs:76–105`
synchronously writes the full file and manifest; restore collects snapshot
batches at `:111–129` before rebuilding the map at `window.rs:194–213`.
Window closure can also materialize all newly closed rows at `:277–299`.
These synchronous calls execute from the async event path. Their scheduling
impact is inferred from the call graph, not measured.

State can grow with key cardinality or stalled watermarks; a finite window
duration alone does not bound it. More frequent full snapshots increase
materialization and writes even when little state changed. Choose full
snapshots only for a declared practical envelope. Beyond it, evaluate
partitioned/incremental snapshots or a spillable indexed store, preserving
deletions, schema/configuration identity and exact restore boundaries. Use
bounded snapshot concurrency and a suitable I/O execution path. Never reclaim
state needed by incomplete effects simply to stay under quota. Backpressure,
explicit exhaustion and operator admission are safer than silent eviction.

### 6. Sealing is reusable; whole-memory archives are not a requirement

R `sail-spark-connect/src/pipelines/autocdc/write.rs:477–495` collects all
selected rows, then exposes their batches through a MemTable. `durable.rs:127–146`
serializes an additional complete archive into a byte vector, writes it and
hashes its contents. Restore at `:157–170` reads the full archive and collects
decoded batches. The actual peak depends on Arrow ownership and allocation;
no fixed memory multiplier is claimed.

Preserve the immutable artifact, validation identity and per-effect receipts.
Implement bounded artifact chunks, incremental hashing, atomic manifest
publication and streaming reads instead of requiring whole-memory archives.
Account for simultaneous live state, staged rows and serialization. The
existing source validation executes an aggregate over a logical input at
`microbatch.rs:55–83`, followed by reconciliation execution in
`write.rs:420–450,477–482`. Do not carry repeated evaluation forward solely to
match Spark's error counts. Normalize and validate the same rows once, while
staging privately; publish no effects until the required validity evidence is
complete. This preserves validation and avoids relying on a separately rerun
computation. It is a proposed implementation, not an established speedup.

Two-table effects currently execute sequentially at `durable.rs:737–767`.
Fenced Delta acceptance additionally reads and hashes the staged log entry,
ratifies it and publishes it at `sail-delta-lake/src/physical_plan/commit_exec.rs:1043–1077`.
Those are real I/O/control steps whose costs must be measured with the selected
target. Do not remove acceptance or content binding to reduce calls. Prefer
target-native atomic ownership checks or the existing authority seam; a new
service needs correctness and deployment justification, not an unsupported
latency claim. The existing Turso authority explicitly qualifies one process
at `sail-sdp-control/src/turso_store.rs:1–5`.

### 7. Long-lived metadata and event history also need retention contracts

P4 `sail-common-datafusion/src/streaming/checkpoint.rs:47–50,74–77,98–103`
retains every recorded position and can clone the whole map. Rate control
retains per-checkpoint partition positions at
`sail-data-source/src/formats/rate/checkpoint.rs:14–24,73–81`. P3
`sail-iggy-bounded/src/stream.rs:101–111,437–445` does the same. Their metadata
grows with checkpoint count and participating partitions. P4 file-sink
`last_committed` scans all checkpoint directories at `append_sink.rs:64–81`
and is called each checkpoint. With accumulating directories, each lookup
grows with history; a constant-cost latest-head lookup is not demonstrated.

Retain pending records and valid restart points, then compact completed
metadata under an explicit recovery policy. Admission must limit outstanding
work and retained artifact bytes; storage pressure cannot authorize deletion
of accepted-but-unpublished effects. Source bounds are positions, not byte
limits. P3 polls pages by message count at `stream.rs:496–511`, so page count
alone is not a byte envelope for variable-size payloads.

The revised SEMANTICS-AUDIT.md correctly avoids a mandatory all-history
conflict ledger. A latest-version register needs retained state per live or
deleted key; exhaustive conflict detection needs additional state for retained
key/version or event identities, including superseded events. Offer the latter
only with a declared horizon, state budget and behavior for older arrivals.
A verified source/order frontier may permit retirement; arbitrary wall-clock
expiry does not prove it safe. Version/tombstone state likewise cannot be
discarded just because its target row was deleted. This is a semantic storage
cost, not evidence against deterministic change processing.

## Required envelope and decisive validation

Specify limits for batch bytes, active partitions, retained transport bytes,
operator state, pending prepared bytes, snapshot workspace/concurrency,
temporary disk and durable recovery artifacts. Specify what happens at each
limit: backpressure, bounded spill, admission refusal or explicit failure.
Include control progress, cancellation and accepted-effect recovery in those
rules. Expose measured high-water usage, spill bytes, alignment/commit delay,
snapshot bytes and retained metadata. Select values from representative
workloads and deployment budgets; this review invents no defaults.

First establish correctness under slow consumers, slow/failed targets, large
individual batches, growing keys, stalled watermarks, disk exhaustion and
interrupted publication. Verify final progress and exact recovery with limits
enabled. Only then compare candidate snapshot/transport designs under the same
source rows, topology, host and resource budgets, retaining failures as well
as timings. Correctness defects cannot be dismissed as performance tradeoffs.

Typed pipeline configuration should express durations and byte quantities
explicitly and reject impossible combinations before execution, as proposed
in TYPED-PIPELINE-CONFIG.md. Dhall belongs in optional authoring, not the stream
data path. Compiler time/memory/output/import limits remain separate from
runtime memory and recovery guarantees. No Dhall performance measurement or
integration result is asserted here.

Stateless append does not need a window state store. Deterministic interval
reduction does not need an all-target in-memory map, although its interval can
still exceed memory: P4 `streaming/changes.rs:33–57` encodes key and sequence
columns for the whole supplied batch before selecting winners. Reuse existing
execution ownership, resource managers and persistence contracts, then add only
the missing guarantees. A second general coordinator or an unconditional
history database is not established as necessary by these findings.
