# ORC writer ownership and resource protocol proposal

This is the W2 design checkpoint announced after the option/default work. The
[source packet](evidence/orc-writer-ownership/README.md) pins the actual local and
distributed execution paths, DataFusion55.2.0 and object_store0.13.2. It extends
the [writer plan](ORC-WRITER-DESIGN.md). This is a proposed protocol and build
handoff; production cleanup, allocator instrumentation and distributed retry
behavior still require implementation and executed fault tests.

## Findings that constrain the implementation

`TaskMonitor::run` selects between execution and cancellation. Selecting cancel
drops the execution future and sends Canceled; it does not await an upload abort.
`TaskRunnerActor::handle_run_task_batch` currently shares an Arc<TaskContext>
between attempts. A session/batch-wide cancellation extension would therefore
have the wrong ownership boundary. TaskRunnerActor::stop presently drains only
Celeborn service state before its actor context is dropped.

The local path is different: LocalJobRunner calls execute_stream directly, and
stop sets an atomic flag. It has no TaskMonitor. A monitor-only cleanup change
would miss local writes. ActorRunner calls actor.stop before dropping its task
JoinSet, providing an existing graceful-stop hook, but ActorSystem drop can
abort actors. Graceful drainage cannot imply cleanup after process death.

ObjectWriterBuilder discards AbortableWrite. BufWriter::abort returns early for
Buffer/Prepare, panics after shutdown, and is not an idempotent general cleanup
operation. WriteMultipart::finish consumes the handle and can replace a complete
error with an abort error through `?`. The new supervisor should own the direct
MultipartUpload handle and keep primary operation errors separately from cleanup
errors. These are source observations, not new observed production failures.

## Ownership boundary and minimal shared interface

Introduce a task/job resource scope below sail-execution, accessible through
TaskContext configuration extensions. Keep ORC-specific encoding and upload state
in sail-data-source. The scope needs no Iggy, catalog or graph-service dependency.

The proposed scope interface has three operations:

- Register a resource before starting any side effect, returning its cancellation
  token and a completion/report channel. Registration fails after admission seals.
- Seal admission and request cooperative cancellation on failure/cancel. The
  registry, not the dropped stream, owns the supervisors until their reports arrive.
- Drain registered resources and return a structured cleanup report. A clean
  report requires confirmed completion/abort and release of owned reservations.
  Timeout alone never creates that report.

Install a fresh scope for each distributed TaskKey before TaskPreparation begins.
Preserve the existing registry admission/tombstones and task identity. Reconstruct
TaskContext using its public constructor/getters, copying all four UDF maps,
session configuration, runtime and IDs, then replace only the scope extension.
TaskContext is not Clone: a helper that rebuilds only its configuration would
silently lose functions or runtime identity. Test this context derivation directly.

LocalJobRunner owns a per-job scope registry, registering each job before calling
execute_stream. Returned stream drop signals cancellation; the job runner retains
the scope and supervisor ownership. Local stop seals admission, cancels live jobs
and awaits their reports. The registry must reject a late registration racing
with stop, even if execute previously read the stopped flag as false.

TaskMonitor should await scope closure before sending a cleanup-qualified terminal
report. CloseJob cancels and drains that job's scopes; graceful actor stop drains
all remaining scopes before ActorContext drops its tasks. A separate execution
unit must define how driver cleanup acknowledgments are retained: sending StopTask
or CloseJob is not itself a resource-cleanup acknowledgment. The current driver
schedules those sends asynchronously. Do not claim driver/session shutdown is
fully drained merely because a worker monitor has the new scope.

## Per-file supervisor and worked cancellation trace

A supervisor is registered before awaiting multipart creation. It owns the create
future, upload handle when available, all in-flight part futures, the blocking
encoder join handle, and the report sender. Consumer futures await a shared result;
they do not own the sole JoinHandle. Dropping a consumer requests cancellation.

Success follows this order: validate schema/options, acquire a writer slot and
reservations, register, create upload, encode all assigned batches, close the one
native footer, finish all parts, complete upload, release resources, report file
success, and finally return the sink's row count after all files succeed.

For cancellation while the encoder is blocked on a full byte queue:

1. The task/job owner seals scope admission and signals cancellation.
2. The uploader closes its chunk receiver, waking the blocking producer. The
   synchronous Write bridge returns an I/O error; it cannot remain stuck waiting
   for a receiver that has exited.
3. The supervisor joins the encoder and cancels/joins part futures. Reservations
   stay attached to their actual owners until those owners release buffers.
4. It aborts the still-owned upload and records the result. An abort error becomes
   secondary cleanup context; it must not overwrite the original typed cause.
5. Only confirmed cleanup permits a clean drained report and terminal status.

Do not abort the supervisor as the cancellation mechanism. Native encode calls
may reach a cooperative check only between bounded slices or Write calls; this
protocol does not establish a hard cancellation latency. Bound slice/value sizes
and test queued, executing and blocked producers separately.

If cancellation arrives during upload creation, keep ownership of the creation
future until its outcome resolves. A returned handle can then be aborted. A
remote creation that succeeds but loses its response may leave no usable upload
identifier: report unresolved cleanup instead of pretending no upload existed.
Similarly, a lost complete response can leave a published object. Do not delete
or replay that object based solely on an absent response or an expired timeout.
Completed files from a partially failed listing write follow Sail's publication
contract; cleanup alone does not provide table atomicity or exactly-once retries.

A cleanup deadline may expose an incomplete report to the caller, with attempt,
path and pending operation context. It must retain supervisor ownership while the
worker service remains alive. Define unresolved-outcome transport and driver
handling before implementation; neither ordinary Canceled nor a dropped handle
proves that the upload was aborted. Process/worker loss needs provider lifecycle
cleanup/reconciliation and cannot be solved by an async Rust destructor.

## Account actual owned capacity

Use DataFusion MemoryReservation for Sail-owned resources and a small native
writer budget/accountant trait with a compatibility no-op default for direct
native users. Sail's writer must supply the accounting implementation. Native
budget callbacks must precede allocation/capacity growth; sampling memory after
encoding is insufficient. Keep native ORC independent of DataFusion types.

Charge retained input buffers conservatively, native column/presence/length
capacities, compression output and scratch/context bounds, queued owned chunks,
part payloads and stripe/footer directory capacity. Attribute every reservation
to the object that retains the bytes. Releasing a queue slot does not release
bytes still retained by a part future. Reserve additional copy capacity before
copying the synchronous encoder's borrowed buffer into an owned upload chunk.
Release only the departing resource's credit, preserving siblings' reservations.

Input admission checks must handle one oversized variable-width value before
encoding copies it. Checked arithmetic is required for size sums and encoder
bounds. Account the simultaneous peak during stripe flush and footer compression,
not just steady-state buffers. A single complete file's stripe directory can grow
without bound: reserve its capacity and fail explicitly if admission cannot grow.
Any file rollover policy must respect single-file output mode and shared naming.
Do not silently discard rows or weaken file-output semantics to meet a budget.

The byte queue and writer fan-out must both be bounded. Acquire a file-writer slot
before starting an encoder or upload; the demuxer producing many paths is not a
license to create unlimited supervisors. A memory-pool denial becomes a typed
resource error and enters the same cleanup protocol rather than waiting in a
self-deadlock while the encoder holds the rest of its stripe budget.

Exact capacity-growth and codec-context upper bounds still need a native source
inventory and allocation-failure tests. ZSTD is required by the Spark default;
its context/scratch costs cannot be excluded from a claimed writer budget.
A logical reservation model does not prove a whole-process heap bound: allocator
bookkeeping, shared upstream allocations and third-party internals must be stated
explicitly. Do not label the production writer bounded until the stated controlled
allocation scope is implemented and its transient peaks are tested.

## Reviewable build sequence and acceptance

| Unit | Required behavior and evidence |
| --- | --- |
| W2a | Pure scope admission/seal/drain protocol; registration-vs-close race, idempotent closure, sibling isolation and per-resource release tests |
| W2b | Fresh TaskContext scope derivation preserving all UDF maps/runtime/IDs; distributed monitor success/error/cancel reports after drain |
| W2c | Local runner drop/stop ownership; graceful task-runner shutdown, job-close and driver acknowledgment/timeout behavior |
| W2d | Native budget callbacks and complete capacity inventory, including compression contexts, stripe directory and flush peaks |
| W4a | Owned direct upload and bounded Write bridge; failures at creation, each part, footer, completion and abort; preserve primary errors |
| W4b | Memory, fan-out and cancellation fault tests using real encoders and controlled object-store futures; no leaked reservations or unowned tasks |
| W5 | Decoded worker sink execution and retry/publication audit; cancellation/takeover cannot silently duplicate a completed file |

The [finite model](evidence/orc-writer-ownership/model.json) explores two lifetime
resources with four abstract byte units. It checks seal-before-terminal,
per-resource credit release, separate attempt scopes and unresolved outcomes.
Its source-supported old-path counterexample reports Canceled while an upload
is still pending. This is protocol evidence only; the model does not execute
Sail, allocate native buffers, inject network faults or prove distributed safety.
An earlier aggregate-credit draft is retained as superseded because it did not
attribute releases to individual owners.

These units refine W2; they do not mark it implemented or qualify public ORC
writing. Keep the original writer-to-CTAS-to-MV and later streaming assertions in
the full Spark acceptance inventory. Existing source, options and native admission
commits remain useful prerequisites.
