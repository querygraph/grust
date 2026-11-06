# Streaming projection: correctness and remaining cost

Streaming projection now evaluates expressions on data runs and forwards ordered
markers without invoking those expressions. It uses Sail's streaming rewriter,
extension planner and worker codec, preserving the ordinary batch path. Local
correctness qualification passed; performance gaps and source detection still prevent
a general pipeline-readiness claim.

## What the implementation preserves

A flow-event batch carries data and control rows together. Its leading columns
identify markers and per-row retraction flags. A retracted data row cancels an
earlier data row. Marker payloads are placeholders, so a strict integer cast must
never evaluate their empty-string values. The new projection forwards a preceding marker before evaluating later
data that may fail. Adjacent markers may share an output batch.

The logical node retains qualified names and complete projected Arrow fields.
The physical node uses DataFusion's public projector and supported asynchronous
helper, preserving aliases, metadata, repeated columns and zero-payload row counts.
Worker serialization reconstructs the same node and expression mapping. A repair
to the bounded-source adapter retains table qualifiers when it adds control fields.

Synchronous evaluation uses direct polling. Asynchronous evaluation completes each
data run before its following marker, preserving existing nested-call refusals.
Tested asynchronous paths return arrays; scalar results remain unqualified. Empty
input invokes no expression; zero ideal batch size is refused before execution.
Dropping a local future does not establish cancellation of remote side effects. Volatile retractions and reproducible replay remain separate
semantic decisions.

Marker construction supports nullable encodings rather than forcing representative
non-null values. A narrowly owned Arrow 59.2 null constructor returns errors for
unrepresentable run ends and size overflows. It preserves null dictionaries
with empty value children, nested fields and metadata. Pinned attribution and the
comparison against Arrow are retained. This is neither recoverable allocation
failure nor a task memory budget.

Each partition retains one baseline-metrics owner. Output counts include encoded
markers; reported output bytes can count shared buffers repeatedly. Active-compute
timers exclude input waiting and asynchronous suspension. Sail's existing projection
exporter includes expression metrics for the new physical node.

## Evidence and its boundary

The local source branch `work/streamsource-projection-20261105` is the subject of
these results. Commit `327572240365e2507f348ee92bc009cbfc67abe9` has tree
`bb8699fdfbc4ca88fa6c0e816e189af80e560efd` and parent
`06dd7e237eb5a343dcc6a6145e775f495e6c30de`. All seven specialist reviews cover
its cumulative patch against upstream `b52144955`.

The immutable verification passed formatting, strict Rust documentation,
workspace Clippy across all targets and features, and 2,074 Rust tests. One
pre-existing test remains skipped. The increment adds 40 Rust tests and four
public projection tests. A fresh CLI passed 14 live-server tests and nine mocked
client fixtures with verified server version 4.2.1. Python formatting and lint
checks passed. A separate production-path probe reproduced source erasure;
it is evidence of an open limitation, not an additional product-regression pass.
The retained evidence includes controls that fail when markers reach the ordinary
projector, when empty inputs invoke expressions, and when telemetry dispatch is
removed. Arrow capacity controls reproduce actual constructor panics. A nullable
dictionary counterexample rejects replacing every null placeholder with a value.
Intermediate fixture failures remain distinct from source defects.

Internal tests cover all marker kinds, retractions, strict casts, real data errors,
marker-before-error order, sliced and empty batches, metadata, nested Arrow types,
controlled asynchronous suspension and drop, optimizer properties, child replacement
and worker reconstruction. Public tests exercise a real bounded branch's end marker
alongside a rate source and ordinary batch behavior. They use a freshly built
server and an existing native import fixture, with PySpark 4.2.1 retained; they do
not qualify a new wheel or cluster deployment. Spark 4.2.1 source inspection
supports the intended data semantics; a JVM differential run is not claimed.

## Performance remains part of the decision

Equivalent-output arithmetic probes compare ordinary projection, the preceding
instrumented streaming implementation and the repaired node. They use two input
batch sizes and four marker layouts, retaining every sample. Marker payloads are
chosen so ordinary projection is equivalent for this fixture; ordinary projection
remains unsafe for arbitrary marker-sensitive expressions.

The shared macOS host does not provide isolated CPU or steal measurements. Results
are diagnostic ratios, not production throughput. The probe uses synchronous
nonnullable primitives and does not establish nullable-constructor, native-function
or asynchronous resource costs. Every cell below passed exact ordered-output checks.
Ratios divide repaired-node time by the indicated comparison. Tail places one
marker last; middle pair places two adjacent markers centrally; alternating places
a marker after every data row.

| Input rows per batch | Markers | Median vs ordinary | Sample range | Median vs preceding streaming | Output batches ordinary/streaming |
| ---: | --- | ---: | ---: | ---: | ---: |
| 128 | none | 1.030 | 0.792–1.090 | 0.908 | 512/512 |
| 128 | tail | 2.263 | 2.097–2.492 | 0.855 | 512/1024 |
| 128 | middle pair | 3.159 | 2.997–3.172 | 0.881 | 512/1536 |
| 128 | alternating | 109.739 | 102.882–116.562 | 0.893 | 512/65536 |
| 8192 | none | 0.958 | 0.534–1.046 | 0.958 | 8/8 |
| 8192 | tail | 2.712 | 2.547–3.005 | 0.652 | 8/16 |
| 8192 | middle pair | 2.761 | 2.734–2.794 | 0.653 | 8/24 |
| 8192 | alternating | 1072.750 | 894.303–1292.256 | 0.899 | 8/65536 |

Each cell processes 65,536 encoded rows with seven measured rotations after two
warmups. The ten-logical-CPU host load rose from 9.26 to 11.48 across this run.
Data-only medians are near ordinary projection after the synchronous-path repair.
Mixed-marker costs remain material, especially when alternating rows produce
65,536 output batches. These measurements do not qualify production performance.

## What must happen before integrated recovery

Logical optimization can remove a streaming scan under a constant-false predicate
before Sail detects streaming. An executed production-path probe retains that
counterexample separately from product regressions. Projection cannot preserve
markers from a source that never reaches it. Streaming graph identity must survive
optimization, or planning must reject transformations that erase required source
participation, before expression isolation can become a global guarantee.

Mixed-marker fragmentation needs a bounded batching policy that preserves marker
delivery before later evaluation errors. Resource admission must account for shared
buffers, asynchronous chunk accumulation and retained input. The public explain
analyzer path also does not establish streaming physical planning.

Checkpoint controls, transport alignment, durable preparation, enforced target
fencing, change-capture merges, typed configuration and native package/worker
integration remain independent implementation obligations. Component correctness
and codec reconstruction do not prove distributed execution or process-restart
recovery.

The [projection plan](STREAMSOURCE-PROJECTION.md),
[placeholder decision](STREAMSOURCE-MARKER-PLACEHOLDERS.md),
[metrics decision](STREAMSOURCE-PROJECTION-METRICS.md) and
[cost decision](STREAMSOURCE-PROJECTION-COST.md) explain the selected boundaries.
The [evidence directory](evidence/streamsource-projection-1/) retains source
identities, specialist reviews, controls and measurement receipts.
