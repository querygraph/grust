# Performance review of the scalar plan and human-review compendium

Reviewed the complete `HUMAN-REVIEW.md` and `COMET-SCALAR-ADAPTER.md` against the
saved request in this directory. Read the repository `AGENTS.md`, `LAKESAIL.md`,
`SHEHAB.md`, `CLARITY.md` and `WRITING-RULES.md`. This is a document review;
no source edits, builds or runtime measurements were performed by this reviewer.

## Verdict

No performance-related design blocker was found for the stated standalone
qualification increment. The documents make no adapter-throughput, package-loading
or production-readiness claim. The negative control is still being compiled by
the implementation owner; neither compilation nor test success is inferred here.

The human-review compendium treats earlier performance branches as hypotheses
to check against current code and resolved dependencies. It requires identical
semantics and inputs, retained slowdowns, exact-output checks and disclosed host
conditions. Its distinction between diagnostic shared-host ratios and production
claims is appropriate. It does not trade away marker ordering, failure propagation
or commit fencing to improve measured results.

Its filter-batching recommendation remains an experiment rather than an assumed
speedup. Copies, retained bytes, latency and cooperative polling are explicit
costs to measure. A preceding marker must reach the consumer before evaluation
of later data that can fail. That preserves the contract established by the
foundation checks.

## Retained code and bounded resources

Process-retained library code is separate from retaining function instances,
session state or host-funded memory. The adapter plan states that the registry
retains neither session state nor kernels. The compendium correctly identifies
separation of the existing full package owner as required porting work, rather
than claiming the existing registry already releases sessions correctly.

The standalone loader deliberately retains each admitted opening. Therefore it
does not establish a bound on the count of retained handles or code mappings.
The plan discloses this and requires package admission limits and content identity
before package integration. Keep that boundary explicit in results: successful
result-lifetime tests would prove callback safety under retained code, not bounded
dynamic package churn. Future integration should prevent repeated unbounded
admissions and measure native-memory settlement independently of code retention.

Preserving actual Arrow argument fields and checking output compatibility are
required correctness work. This review does not infer their runtime cost or
claim that the new C boundary is faster than the existing DataFusion route.
The standalone adapter leaves package/worker execution and durable preparation
as separate increments, so it does not silently reduce the full end-state scope.

## Frozen revised source review

Reviewed all twelve files in the revised staged candidate at
`/Users/alexy/src/sail/tmp/comet-scalar-20261105-2c9fa8499`, including production
adapter code, copied ABI records, fixture, tests, manifests and lock additions.
Independently verified every file hash in `candidate-snapshot-v2.json`, the staged
tree `fd9a3568c6227dea942c54368b3f6282f8bb3370`, the increment diff SHA-256
`7310da99c78170079e056387260c4544bf8776b729d58e3a5afb1b35f4138017` against
`2c9fa84994d317aade0d1c69faa9a378c780127d`, and cumulative diff SHA-256
`292a6b7d08656e2b092148921fe9c5fa65929a65b0601be8493fe5b21dfb860a` against
upstream `b52144955b629314a000b1fe49eeea97fa3d0c5c`.

No must-fix allocation, retention or synchronization finding was identified
within this standalone adapter's declared caller-bounded admission contract.
This is a source-review conclusion, not a throughput, memory-envelope or
completed-gate verdict. The implementation owner's reported fourteen focused
passes and affected Clippy passes are execution by that owner. Final immutable
qualification and reruns of the independent SDK producers remain pending here.

The retention mutex is acquired only during library admission and construction
of imported functions. No global lock is acquired by planning initialization or
per-batch evaluation, and native callbacks do not run while the registry mutex
is held. Factory callbacks may run concurrently under the explicitly unsafe
trusted-producer contract. Each planning/evaluation call creates and releases
its own kernel instance rather than serializing all tasks through shared mutable
instance state. Producer thread safety remains an admission obligation, not a
property established by a numeric version probe.

The registry retains `Arc<Library>` only. It retains no kernel instances,
argument arrays or session owners. Every successful open is retained before
version and discovery callbacks, including refusals, so callbacks on dependent
results remain backed by loaded code. Repeated opens create distinct retained
entries; pointer equality prevents adding the same opening once per kernel but
does not deduplicate paths or content. Registry lookup is linear in prior
admissions and occurs off the data path. The unsafe loader documentation states
that callers must bound admissions. This scope is acceptable for standalone
qualification, but is not a bounded package loader and must not become an
unlimited remotely driven admission path during integration.

Evaluation preserves existing array ownership through shared Arrow buffers and
FFI records; it does not introduce an unconditional deep copy of ordinary input
payloads. Literal scalars expand to row-count arrays as required by the pinned
interface. Per-call allocations include argument/field vectors, encoded field
schemas and pointer lists, plus producer instance creation. Complete field metadata
is cloned and serialized per initialization. Those costs scale with arguments,
schema depth and metadata, not solely row count. A future field-cache optimization
must key the full contract and respect native initialization semantics; this
correctness repair makes no unsupported claim that metadata preservation is free.

Instances and temporary schemas/arrays are RAII-owned. Failure strings are copied
before the instance can release them. Result arrays are imported and checked before
return; their buffers and release callbacks can outlive the function because code
is separately retained. The producer contract requires independently releasable
outputs. Tests exercise retained output and slices after dropping library/function
owners; they do not qualify arbitrary native producers or session quota settlement.

Return-field compatibility checks precede execution and preserve exact nested
types and metadata while allowing DataFusion's documented outer-field treatment.
Nullary planning is admitted without forcing an unnecessary argument, and kernels
still decide their own arity. Neither change adds per-row synchronization or an
additional execution pass over ordinary input payloads. Output nullability and
row-count checks remain necessary contract checks.

The latest saved request and the complete updated human-review compendium were
reread. Governing-file compliance remains confirmed. No source edits, builds,
tests, cleanups or timing experiments were performed by this reviewer.

## Frozen v4 logical-null and resource review

The revised candidate supersedes v2's output nullability check. Independently
verified all fifteen file hashes in `candidate-snapshot-v4.json`, staged tree
`637c9cc4c8f12591a0ef89c2765869c83771ec5f`, increment diff SHA-256
`d87f310f63f8515a04aff5c9bfba6acc84ae1473fe636e524cb935240f9ae879`, and cumulative
diff SHA-256 `1f42e598ff9297d1b37eace3c5edf5307a0ef2c3b97db8d62b975d425ce4c4d7`.
Reviewed the complete new `nulls.rs`, updated invocation path and nonempty encoded
array tests, including nested encodings and the million-row compressed-run case.
Read the standalone nullability decision note preceding this change.

No must-fix correctness or resource finding was identified in this delta. The
direct existence predicate fits the stronger declared scalar guarantee better
than expanding an entire logical-null bitmap. Nonnullable results must contain
no null scalar values even where their physical top-level validity bitmap is
absent. Nullable outputs retain their prior path. Row-count refusal now precedes
the predicate, preventing unnecessary traversal of an already invalid result.

Ordinary arrays use their physical null count. Null arrays are nonnull only when
empty. Dictionaries inspect selected keys when their values may contain logical
nulls; ordinary physically nonnull values bypass key traversal. Unions follow the
actual type ID and value offset for each selected row, avoiding assumptions about
contiguous or zero-based IDs. Dictionary and union recursion follows one selected
value rather than examining unused children. List and struct child nulls do not
incorrectly make an otherwise present parent null.

Run-end arrays restrict inspection to physical values for runs intersecting the
logical slice. Confirmed these accessor semantics against Arrow 59.2.0's
`RunArray` implementation: `values()` is unsliced, while start/end physical indices
and per-element physical lookup account for the logical offset. This supports
the code's explicit physical-value slice and selected-index recursion. An empty
array returns before calculating inclusive run bounds.

For ordinary primitive arrays the additional check is constant work. Unions may
scan the output rows. Dictionaries with potentially nullable/encoded values may
scan keys and revisit repeated values. Recursive dictionary/union selections do
work proportional to their selected path depth; selected run-end values can add
physical-index lookup cost. Run-end traversal is proportional to active physical
values and nested work, rather than expanding every logical run row. It may create
small slice wrappers, but creates no logical-row-sized null bitmap or result copy.
The million-row test protects compressed structure with only two physical runs
and values; it is structural evidence, not a measured peak-memory envelope.

These traversal costs are necessary to enforce the chosen nonnullable contract.
They need batch-size, nesting-depth and native-producer resource bounds when the
adapter becomes an externally admitted package path. The present trusted,
caller-bounded standalone scope does not need another caching framework or
dependency fork before a local reference commit. It must not claim constant-time
validation for all Arrow encodings. There is still no new per-row lock or global
data-path synchronization.

The implementation owner reports seventeen focused tests, affected strict Clippy
and two independently built SDK-producer probes passed on this candidate. Those
are reported execution results, not tests run by this reviewer. The final broader
immutable gate remains pending, and this review supplies no throughput or full
package/worker readiness verdict. No source edits or builds were performed.

## Final candidate pin confirmation

Independently verified every file hash in `candidate-snapshot-final.json`, staged
tree `455101575ecbfbec6f843464ce178e0d09046f51`, increment SHA-256
`7477e67e9b6262e5aec067714c586ef7ac49790e8e6ac7d14116829213bdf325`, and cumulative
SHA-256 `743a1346feb7ae62a4cded0224b007312b471b09d80d149b2b0bdf5c25c25b30`.
Compared the final tree directly with the reviewed v4 tree. Only Rustdoc credit
and hyperlink formatting changed in `abi.rs` and `lib.rs`; runtime code is
unchanged. The v4 correctness, work-complexity and resource verdict therefore
applies to this final candidate. No builds or tests were run for this confirmation.
Precommit and final immutable qualification remain the implementation owner's
pending gates; this pin confirmation does not imply they have passed.
