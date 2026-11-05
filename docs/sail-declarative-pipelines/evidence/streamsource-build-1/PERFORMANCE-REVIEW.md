# Event-fidelity performance review

## Scope and verdict

The proposed event-fidelity repair has no performance blocker identified by
source inspection. Explicit row counts, preserved schema metadata and exact
placeholder types fit the existing constructors without a new buffering layer,
coordinator, dependency fork or per-row metadata representation. This is a
design and baseline review, not a verdict on an implemented cumulative patch.

The reviewed design is `STREAMSOURCE-EVENT-FIDELITY.md` at documentation commit
`4e2c40e737207745d05cd454df5b39488829cfdc`. Source references below are relative to
`/Users/alexy/src/sail/tmp/streamsource-build-20261105-b52144955`, pinned at
`b52144955b629314a000b1fe49eeea97fa3d0c5c`. The relevant production source was
unchanged when inspected. New regression files were present but uncommitted.
Dependency references use Arrow 59.2.0, matching this checkout's `Cargo.lock`.

## Allocation and validation boundaries

**Zero-column batches need a row-count option, not dummy payload columns.**
The decoder already collects shared array references and slices batches at
`crates/sail-common-datafusion/src/streaming/event/encoding.rs:118-172`.
Keep those operations. Arrow's `RecordBatch::try_new` and
`try_new_with_options` call the same validation implementation at
`arrow-array-59.2.0/src/record_batch.rs:263-266,299-305,326-380`.
The explicit count supplies a scalar the constructor otherwise infers from a
column. It does not require copying data buffers or allocating rows. The rate
generator at `crates/sail-data-source/src/formats/rate/reader.rs:315-339` should
likewise keep its empty action list empty and pass `batch_size` as the count.
This is an allocation-path inference, not a measured latency result.

**Schema metadata belongs in schema construction.**
The encoder and decoder derive their schemas once when created at
`encoding.rs:33-39,109-115`, then share `SchemaRef` values. The conversion helpers
at `crates/sail-common-datafusion/src/streaming/event/schema.rs:36-45,62-74`
currently drop schema-level metadata. Copying its map in those helpers adds
work proportional to metadata size per schema derivation. It should not move
into `encode`, `decode` or a row loop. Existing field definitions must remain
intact; no metadata serialization per data batch is needed for this repair.

**Decimal parameter preservation need not copy the values buffer.**
The baseline decimal branches at
`crates/sail-common-datafusion/src/array/placeholder.rs:338-341` use the generic
zero-value builder at lines 395-401. Arrow's
`PrimitiveArray::with_precision_and_scale` at
`arrow-array-59.2.0/src/array/primitive_array.rs:1637-1648` validates parameters
and changes the type while retaining the array's other members. Use the checked
decimal API without adding a second zero-filled values vector. The event
encoder requests length one at `encoding.rs:63-70`; nested fixed-size children
can still require more physical values. Do not describe all marker allocation
as constant regardless of schema shape.

**Run-end repair must retain physical compression.**
The baseline at `placeholder.rs:356-382` constructs one value and one run end
for any nonempty logical length. Preserve that property, and construct zero
runs for logical length zero. Validate conversion to the signed run-end type
before constructing nested placeholder values. A logical length exceeding the
run-end type's capacity should fail without an allocation proportional to that
length. Preserve field metadata through the exact requested data type after
building valid children.

Arrow's existing `RunArray::try_new` creates default fields, then validates
`ArrayData` at `arrow-array-59.2.0/src/array/run_array.rs:118-143`. A checked
`ArrayData` construction with the requested fields is a narrow alternative;
`arrow-data-59.2.0/src/data.rs:2222-2268` calls the same `validate_data` operation.
Neither requires expanding a repeated value into logical rows. Full recursive
validation belongs in regression checks unless a demonstrated correctness need
requires it in the production constructor. Retain necessary validation rather
than replacing it with unchecked construction for an assumed speed gain.

## Focused checks

The independent tests already cover positive-length zero-column batches,
retractions, mixed-event slices, metadata, decimal parameters, empty run-end
arrays and representability failures. Keep their execution and unmodified-source
controls in the lead engineer's gate.

For the run-end boundary, a structural assertion that nonempty placeholders
have one run end and one physical value would directly protect compression.
Check zero has no runs. The existing positive `i16::MAX` case is useful without
a large allocation; a positive `i32::MAX` case is only appropriate if it inspects
physical structure and never iterates logical rows. These are suggested
nonbenchmark checks, not required throughput tests or evidence of an operating
resource envelope.

Final cumulative review should verify that ordinary data arrays are still
shared, metadata is still derived outside batch loops, decimal changes do not
introduce duplicate payload storage, and run-end construction remains compressed.
No new global memory budget mechanism is justified by this increment. Existing
transport, checkpoint and state-retention resource issues remain outside its
claims.

## Evidence and compliance

Read the full saved build request, the prior engineering directive, `AGENTS.md`,
`LAKESAIL.md`, `SHEHAB.md`, `WRITING-RULES.md` and `CLARITY.md`; reread them after
context compaction. Read the complete event-fidelity design and the source
sections cited above. No source files were edited, no build or test was run,
and no benchmark was performed by this reviewer. This report establishes no
throughput, latency, memory ceiling, distributed recovery or durable-sink claim.

## Implementation review addendum

Reviewed the three production fidelity diffs against `b52144955`, with combined
diff SHA-256 `8afc60612934b3b135d0b2a6896c32cf230bdfdfe6dc21f76e82e02423350a3c`.
No performance blocker was found in those edits. The decoder still shares payload
arrays; row-count options add no dummy column. Schema metadata is copied only in
the existing conversion helpers. The decimal builder keeps one values buffer;
Arrow 59.2.0's builder parameter setter changes its type without another buffer
allocation at `arrow-array/src/builder/primitive_builder.rs:382-392`.

Run-end compactness follows directly from the new
`placeholder.rs:364-401`: `run_count` is zero or one, both child lengths use that
count, and signed capacity is checked before child values are created. The
logical length only sets the one run end and parent length. One short-lived
`Arc` now wraps the primitive run-end child for conversion to `ArrayData`.
Returning `ArrayData` directly from that match could avoid it, but this small
allocation does not justify blocking the correctness repair or a larger refactor.
The rate-source constructor was not yet changed in this reviewed diff.

Also read the complete `STREAMSOURCE-DATA-ONLY-EXPRESSIONS.md` design and the
filter patch at
`/Users/alexy/src/sail/tmp/streamsource-filter-20261105-b52144955/filter-review/filter-increment.patch`,
SHA-256 `756c669c7b57e09a593c3449955d4514cc4af0a67fe6a2966bda496853e00052`.
That patch has one introduced lifetime concern requiring resolution or explicit
assessment before the final performance verdict:

- `FilteredFlowEventBatch` retains its input batch and marker buffers after the
  terminal data-only `batch_filter` call returns an output. They are released only
  when a later downstream poll drops the exhausted iterator. The baseline's
  `map` closure drops its consumed input before yielding. A selective or false
  predicate can therefore leave a full input batch retained while the consumer
  stalls on a small or empty output. This is at most one extra current batch per
  operator partition, not an unbounded queue. Clear the owned pending batch and
  marker state on terminal paths while retaining unfinished mixed-batch input.
  A deterministic test can retain only a weak reference to an ordinary payload
  array, poll a false-filter result once, and assert the consumed array is released
  without another poll. Use a consuming stream or test the iterator directly;
  the existing in-memory test source itself retains input batches.

The no-marker branch at `filter.rs:192-197` retains one filter-kernel invocation
and does no row scan or payload slice. It adds reference clones and iterator
dispatch; the patch does not materialize a collection of output batches. The
mixed path at lines 203-219 scans marker validity and creates one shared-buffer
slice per contiguous run. `RecordBatch::slice` creates column wrappers and a
column vector at `arrow-array/src/record_batch.rs:681-694`; shared buffers do not
mean allocation-free slicing. Alternating data and markers increase kernel and
output-batch counts. No comparison has measured that overhead here.

The iterator emits a preceding marker before evaluating the next data run, so a
later expression error does not erase that earlier marker. Adjacent markers are
forwarded as one contiguous slice without invoking the predicate. Pending mixed
input remains bounded to the current batch, although a slice can keep the whole
underlying Arrow buffer alive. Existing counting tests structurally check one
predicate invocation per data run and the unchanged data-only call count.

The expression design asks for a performance comparison. A focused follow-up
can compare identical safe predicates and inputs on baseline and candidate with
128- and 8192-row batches, no markers versus alternating markers, and zero,
half and full data selectivity. Keep a legacy marker-preserving predicate where
needed to compare equivalent results. Record payload width, batch count, input
hash, optimized plan and source pins. Interleave runs and report shared-host
ratios with uncertainty rather than publish absolute timings. This comparison
has not been run and is not needed to establish the lifetime finding.

No source edits, tests, builds or benchmarks were performed in this addendum.
The lead's reported pass/fail counts were not independently executed by this
reviewer. The final immutable cumulative review remains pending.

## Filter lifetime correction reviewed

Reviewed the retention delta SHA-256
`464cf28659447b0f2890f8199ac77a66fad4f8bd9295a3f47ed0d38c90fc4975` and verified
the updated full filter patch SHA-256
`085a4512cd4130f4db4d7d537a086074e748662c989083c00c770c694b1d6847`.
The source correction resolves the identified input-retention regression:
`next` takes ownership of the optional pending batch and marker together and
restores them only after successful processing when rows remain. Terminal,
data-only and error paths release that owned state before yielding. Output
slices can still share the original buffers, as required by existing Arrow
slice behavior; the fix removes the iterator's unnecessary retained owner.

Two added tests check release after a false data-only result and retention only
while mixed input still has unprocessed rows. They use weak payload references
and do not depend on timing. They were inspected but not executed by this reviewer.
No performance blocker remains in the reviewed fidelity and updated filter
source patches. Runtime comparison and immutable cumulative qualification remain
pending; this source verdict does not replace either.

## Executed cost probe and data-only correction

The lead executed the prepared probe successfully in the implementation worktree.
Reviewed its full table and receipt under
`review-logs/filter-cost/runs/20261105T195319.063799Z/`. The run used compiler
1.98.1 and the unoptimized test profile on a shared ARM64 host. It checked all
12 input cells before timing, then recorded seven paired samples per cell with
alternating execution order. The receipt pins the measured filter source as
`3801504f5407a51bc1790c5e0c20e40867cd72daa155a252a7c63767fcb8196e` and confirms
the tracked candidate stayed unchanged. The baseline filter source came exactly
from `b52144955`; both operators used the same resolved dependencies and safe
numeric predicate with marker preservation.

For data-only batches, median candidate/baseline time ratios were 1.038 to 1.107
at 128 rows and 1.000 to 1.013 at 8192 rows. All paired ratios in the smaller-batch
cells exceeded one. These observations warrant reducing avoidable work rather
than dismissing it as noise. They do not establish optimized production overhead.

At the lead's request, changed only `filter.rs` in the separate filter worktree.
The new polling closure processes data-only input directly, without creating a
per-batch inner stream or cloning its predicate and marker buffers. It still
validates the marker column and invokes the same batch-filter kernel once.
Marker-containing batches retain the existing lazy iterator, preserving the
marker-before-later-error behavior and release of exhausted input before yielding.
The helper and regression tests were left unchanged.

The source correction has SHA-256
`cb8b337f46395c0e76573eeca068586871e7ca7e84ee800756558fe0af3026dd`.
Its delta from the measured source is
`filter-review/filter-data-only-delta.patch`, SHA-256
`6e8a9a4dcc95d3e3db8ad0b4e343ad46074b8626de417a25d45c8ce326d05b4a`.
The complete filter diff against the upstream baseline is
`filter-review/filter-data-only-full.patch`, SHA-256
`5ff6e91f9181b52ee075d804315a10f9b8908043f937c5a47bd5d01d616c358e`.
Rust formatting and the scoped whitespace check passed. No build or test was
run by this reviewer; integration, correctness rerun and repeated comparison
are still required. Reduced source work is not yet a measured speed improvement.

Alternating markers produced median ratios from 18.29 to 143.71 in the initial
unoptimized run, with 65,536 output batches from 512 or eight input batches.
The comparison exposes severe fragmentation cost for this adverse fixture.
Preserving per-run evaluation boundaries explains additional calls but does not
prove every allocation or output fragment is necessary. Any further change must
retain marker order and emit preceding markers before later expression failure;
gathering data across markers would invalidate the comparison's contract.
Optimized measurements remain necessary before judging the remaining cost, and
the result must not be presented as a qualified production performance envelope.

## Final cumulative source review and second probe

Reviewed the complete 19-file cumulative change against `b52144955`, preserved as
`review-logs/cumulative-four-design-notes.patch`, SHA-256
`6782613a31c5278296421622c5a5fcea918603506a70de62c0f77671fa0f3376`.
The review includes the final test additions, rate-source constructor, console
failure propagation, query-state changes and Spark Connect exception serialization.
Also read the complete failure-propagation and error-protocol design notes.

Reviewed the subsequent three-file correction against local commit
`d57946ee24199b3287386aebd64c87cf9ee68211`, preserved as
`review-logs/failure-reporting-cost-fix.patch`, SHA-256
`73baa58870461a4b5143a97d24145a5dc86d896e51338a5e42da7075499587f1`.
It closes both resource regressions identified in the cumulative review:

- The first console implementation acquired the global stdout lock before
  building and rendering its pretty table. The correction completes both
  `pretty_format_batches` and `to_string` before locking, restoring the baseline
  critical section while retaining fallible header/body writes. The live sink
  path still propagates formatting failures before writing.
- The first active-query listing constructed names and error-message strings
  for stopped queries before discarding them. The correction checks the stopped
  state before allocation, then materializes active status using the same watch
  borrow. It preserves atomic observation of terminal state and cause.

No further must-fix allocation or retention regression was identified in this
reviewed union. This is a source-review conclusion with the known dense-marker
performance limitation below, not an upstream readiness verdict. The immutable
candidate pin and final gates must include the correction; earlier gate results
alone do not qualify it.

The event-fidelity paths retain shared payload buffers, zero-column row counts
and once-per-schema metadata copies. Run-end tests now assert zero or one
physical run and value as well as exact types, including the boundary-length
case. The failure runner retains one first cause and drops input before publishing
terminal state. It replaces two watch channels with one and introduces no
per-row notification or error-history buffer. Manager waits add a vector of
watch receivers and two scans proportional to the existing query-handle set;
they retain the existing one-waiter-task-per-handle design. Exception serialization
adds a class prefix when explicitly requested by a client. Its string work is
proportional to the cause size and is outside data evaluation.

The lead's second successful probe is preserved under
`review-logs/filter-cost/runs/20261105T200822.823114Z/`. Its receipt identifies
the exact cumulative patch above and direct-poll filter SHA-256
`cb8b337f46395c0e76573eeca068586871e7ca7e84ee800756558fe0af3026dd`.
Both probes used the unoptimized test profile and the same probe sources. The
second probe's median candidate/baseline ratios were:

| Batch rows | No-marker selectivity 0% | 50% | 100% |
| ---: | ---: | ---: | ---: |
| 128 | 0.9915 | 0.9931 | 1.0036 |
| 8192 | 1.0037 | 1.0052 | 1.0008 |

These observations support retaining the simpler direct path. They do not prove
optimized performance neutrality. Shared-host load differed between runs, and
individual paired samples vary. The full tables preserve every cell rather than
reporting only improvements.

Dense alternating markers still produced median ratios from 17.89 to 141.10,
with 65,536 output batches from 512 or eight inputs. The source correction can
serve as a correctness reference, subject to correctness review and final gates.
It has not qualified dense-marker throughput or general upstream performance
readiness. No release-profile measurement or production resource envelope is
claimed, and no absolute shared-host timing is published here.

### Next bounded experiment and decision

First run the unchanged 12-cell probe on the immutable corrected candidate with
a genuinely optimized profile. Preserve exact-output checks, paired execution
orders and all results. If fragmentation remains dominant, use a small additional
8192-row layout sweep: a marker at the batch boundary, sparse interior markers,
adjacent marker groups and the existing alternating arrangement. Record output
batch and predicate-invocation counts separately from timing. This distinguishes
marker handling from the cost of splitting a batch into many data runs.

Before adding output coalescing, agree on a bounded byte/row policy and its
latency consequence. Only consider assembling already evaluated data with its
immediately following marker. A marker must be emitted before evaluating later
data that can fail. Never gather data from both sides of that boundary merely
to restore baseline batching. Extra copying may cost more than the saved output
fragments, so an assembly policy requires its own measured comparison and the
existing ordering, failure and lifetime checks.

This final pass performed no source edits, builds, tests or new timing runs.
It inspected retained execution evidence from the lead. The saved request and
governing files were read as recorded above, and the full build request was
refreshed for this pass. No context compaction occurred after those reads.

## Immutable source pin confirmation

Confirmed commit `2c9fa84994d317aade0d1c69faa9a378c780127d`, tree
`5d67cdc81cdd9ba7eb18a74eda17d84b9e5d30c7`. Its complete binary-capable Git diff
against `b52144955b629314a000b1fe49eeea97fa3d0c5c` has SHA-256
`bda65fdba075378f3088a2b00681fdf63f57b9d9a66722ec78c8e1f688220163` and touches
the same 19 reviewed files. Independently recomputed the diff from the baseline
to `d57946ee24199b3287386aebd64c87cf9ee68211`, obtaining the reviewed
`6782613a...` hash, and the diff from that commit to the final pin, obtaining
the reviewed `73baa588...` correction hash. The immutable source is therefore
exactly the reviewed cumulative patch plus the reviewed cost correction.

Read the complete `STREAMSOURCE-FILTER-BATCHING.md` decision note, SHA-256
`a637afe558a9be57409f350f0f338bacbc08cecd70b2d089a9dcb8980e633bbc` at review.
Its rounded diagnostic ratios agree with the retained second probe. The
one-output-batch-per-input-row description matches that alternating fixture,
including empty filtered outputs. Its distinction between a correctness
reference and unqualified production throughput is appropriate. Its proposed
comparison preserves marker forwarding before later evaluation and treats
buffering, copying and latency as tradeoffs rather than measured improvements.
Suggested defining the ratio direction explicitly and replacing “after
optimization” with “after the direct-path change” to avoid confusion with build
optimization. No substantive performance claim in the note requires correction.

This confirmation used read-only Git and document inspection. It makes no
format, Clippy, test, benchmark or completed-gate claim for the immutable pin.
