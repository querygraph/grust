# Regression review of the human-review compendium

**Verdict: no introduced requirement regression or unsupported implementation
qualification found in the reviewed compendium.**

Reviewed the full `HUMAN-REVIEW.md`, SHA-256
`eed251526e19a5380b73d1d704430f28a61447ed935170cb6551d7d41719e3fe`, against the
current pipeline plan, extension integration decisions, standalone scalar plan,
foundation results and filter-batching note. This verdict covers the compendium,
not the work-in-progress scalar adapter or its still-unqualified test controls.

## Requirements and evidence retained

The document preserves the full end state: declarative table maintenance, ordered
change capture, crash recovery, existing native extension behavior, the added Comet
scalar route and measured performance improvement within Sail's execution model.
The smaller first delivery explicitly defers capabilities without replacing the
overall objective.

Prepared original effects, fixed input/computation identity, saved output or proven
identical replay, uncertain-outcome reconciliation and commit-time fencing remain
requirements. The document distinguishes cancellation, stream closure and durable
completion. Change capture retains complete ordering, symmetric upsert/delete
comparison, deletion versions, validation before reduction and the stated scope
of historical conflict checking. Ordinary table behavior remains protected; a
sidecar does not acquire an unsupported cross-table atomicity claim.

The extension summary preserves existing version guards, including mixed packages,
worker identity, explicit boundary selection, memory funding and lifetime
obligations. Process-retained code does not justify retaining session resources.
It correctly treats Comet purity and pointer validity as producer obligations
that a numeric probe cannot prove. It does not claim that scalar layout provides
a relation protocol, recovery or package integration.

The status table places metadata/lifetime qualification in progress and package,
worker and durable integration in future work. It explicitly distinguishes
inspection, fixture success, compilation and qualified interface behavior. The
new adapter's negative controls were compiling at the time of the review request;
the compendium reports no result for them.

The performance discussion retains the mixed-marker regression and requirements
for exact outputs, retained bytes, latency and cooperative polling. Inspected the
existing optimized sparse/grouped summary and receipt under
`evidence/streamsource-build-2/optimized-layouts/`: they report overhead on both
layouts and unchanged source at foundation commit
`2c9fa84994d317aade0d1c69faa9a378c780127d`. They support the compendium's limited
overhead statement, not a production throughput claim. A batching prototype is
proposed and conditional on preserving marker-before-later-error order.

## Review scope and compliance

The document reinforces self-contained plans before dependent code, focused
changes, negative controls and cumulative immutable qualification. It keeps local
implementation progress separate from upstream readiness. Detailed plan contracts
remain in force; the compendium does not state that its summary supersedes them.

Read the exact saved request and latest steering. The full AGENTS.md, LAKESAIL.md,
SHEHAB.md, WRITING-RULES.md and CLARITY.md were read earlier in the continuing
review; verified they are unchanged from baseline `ea0874db`. No context compaction
occurred since that reading. No source edits, builds, tests or benchmarks were
performed. Only this assigned evidence file was written.

## Frozen standalone adapter source review, candidate v2

**Verdict: one return-nullability gap requires resolution before this candidate
receives an unqualified source verdict. No other concrete introduced regression
was found in the reviewed increment.**

Reviewed all 12 changed files in
`/Users/alexy/src/sail/tmp/comet-scalar-20261105-2c9fa8499`, including the ABI,
loader, adapter, handwritten producer, tests and lockfile. Independently recomputed
increment SHA-256
`7310da99c78170079e056387260c4544bf8776b729d58e3a5afb1b35f4138017`
against foundation `2c9fa84994d317aade0d1c69faa9a378c780127d`, and cumulative
SHA-256 `292a6b7d08656e2b092148921fe9c5fa65929a65b0601be8493fe5b21dfb860a`
against `b52144955b629314a000b1fe49eeea97fa3d0c5c`. Both match
`review-logs/candidate-snapshot-v2.json`, whose tree is
`fd9a3568c6227dea942c54368b3f6282f8bb3370`.

### Required correction: logical nulls in nonnullable results

At `crates/sail-c-udf/src/udf.rs:237`, the adapter checks `array.null_count()`
before accepting a nonnullable planned result. Arrow 59.2.0 defines this as the
physical null count. Its `Array` documentation at `arrow-array/src/array/mod.rs`
lines 210–243 and 290–325 distinguishes logical nulls in dictionary, run-end,
union and null arrays. For example, dictionary keys `[0]` with values `[null]`
have no physical key null but contain a logical null. Such output bypasses this
guard even though the diagnostic promises to reject nulls for a nonnullable field.

This is a source-derived counterexample, not an executed result. Resolve the
guard using logical null semantics and add nonempty encoded-null controls, with
positive nullable/non-null cases. The existing all-family test constructs only
empty arrays and cannot detect this gap. A trusted producer is still responsible
for valid pointers and ABI behavior; that safety contract does not make the
new output-nullability check complete.

### Preserved behavior and remaining qualification

The increment changes no foundation operator or existing extension host. The
lockfile adds the two new workspace packages without updating existing resolved
dependencies. Existing DataFusion-FFI registration and worker behavior therefore
remain untouched rather than being implicitly requalified by this increment.

Library code is retained before calling version/discovery functions; kernel and
session state are not retained in the code registry. Unsupported declared
volatility is rejected before opening a library. Admission remains explicitly
unsafe and process-retained openings must be bounded by later integration.
The lifetime test observes retention after dropping function/library owners and
then uses and releases a sliced result. Its negative control avoids executing a
callback into unloaded code during assertion unwinding.

Planning and execution use the actual argument fields. Return checks preserve
exact type and metadata while allowing the documented top-level alias and safe
nullability widening. Tests now separately reject altered return type, metadata
and unsafe narrowing. Nullary and variadic signatures delegate actual arity to
the kernel; the new nullary DataFusion test reaches planning and execution.
The ABI comparison artifact is empty, consistent with the pinned record copy
and local import/alias adaptations described in the source. The factory/instance
thread-safety and ownership obligations remain explicit.

The lead reports 14 focused passing tests and strict affected-crate Clippy, with
separate failing controls for metadata, lifetime, return-field guards and nullary
planning. These are reported results, not executions by this reviewer. They do
not resolve the encoded-null finding above or establish all nonempty Arrow-type
behavior. Broader immutable verification is pending. Package loading, worker
identity integration, bounded admissions, streaming expression isolation and
durable recovery remain outside this standalone source verdict.

Reread the latest saved request, current human-review compendium and adapter plan.
The governing files previously read remain unchanged except CLARITY.md, which
was reread in full with its new compendium requirement. No compaction occurred
since the full governing-file reading. No source edits, builds or tests were
performed; only this evidence file was updated.

## Frozen candidate v4: nullability finding resolved

**Verdict: the original return-nullability finding is resolved under the explicit
logical-nonnull scalar-result contract. No new concrete introduced regression
found in the reviewed final source. Broader immutable verification remains
pending.** The v2 finding and its evidence above are retained.

Read `COMET-SCALAR-NULLABILITY.md`, written before the revised guard. It deliberately
requires that a planned nonnullable native result contain no logical null value.
This is stronger than Arrow RecordBatch's physical-validity check. It preserves
the separate unsafe admission obligations for foreign buffers and callbacks;
the new predicate is not an arbitrary-producer safety validator.

Independently recomputed increment SHA-256
`d87f310f63f8515a04aff5c9bfba6acc84ae1473fe636e524cb935240f9ae879`
against `2c9fa84994d317aade0d1c69faa9a378c780127d`, and cumulative SHA-256
`1f42e598ff9297d1b37eace3c5edf5307a0ef2c3b97db8d62b975d425ce4c4d7`
against `b52144955b629314a000b1fe49eeea97fa3d0c5c`. Both match frozen
`review-logs/candidate-snapshot-v4.json`, tree
`637c9cc4c8f12591a0ef89c2765869c83771ec5f`. Reviewed all seven files changed
since the v2 tree in the context of the earlier full source review. No foundation
operator or existing dependency version changed in that delta.

`src/udf.rs` now checks result length before null traversal and calls the new
predicate only for planned nonnullable outputs. `src/nulls.rs` checks selected
dictionary keys, actual union type IDs and offsets, and physical run values
intersecting the current run-end slice. It recurses through encoded values rather
than invoking the problematic union logical-null bitmap helper. An empty result
is accepted before indexing runs; a nonempty Null array is rejected. Ordinary
present list or struct parents are not incorrectly rejected merely because a
child is null.

Inspected Arrow 59.2.0's public run-array/run-buffer and union-array accessors to
confirm their slice-aware indices and offsets. The code does not inspect unused
dictionary values or unused union children as though they were selected rows.
Run-end traversal slices the physical value array and does not expand it into a
bitmap proportional to logical row count. Nullable output retains the previous
pass-through path.

The new tests exercise nullable preservation and nonnullable refusal for populated
dictionary, run-end, dense-union, sparse-union and Null arrays. They include actual
nonzero union IDs, dictionary/run-end nesting around a single-child union, valid
offset slices retaining unused null storage, and a million-row result represented
by two physical runs. The single-child union tests use explicitly known values
rather than the faulty Arrow helper as their oracle. The million-row check asserts
physical compression; source inspection, rather than that assertion alone,
establishes that the predicate traverses physical runs.

The missing-version-probe control now loads a deliberately probe-free test library
instead of relying on whether the platform permits opening a test executable.
The asserted named refusal remains unchanged.

The lead reports the physical-only control and Arrow-helper control failing,
followed by 17 focused passes, strict affected-crate lint and two independent SDK
probes passing. These remain reported executions, not runs by this reviewer. The
predicate can traverse selected dictionary keys and union rows and recurse through
encoding depth; this is not a constant-time performance claim. No package,
worker-runtime, complete Arrow-value coverage or durable recovery qualification
is inferred. The final cumulative gate remains necessary.

The latest request, compendium and full governing-file readings recorded above
remain current; no compaction occurred. No source edits, builds or tests were
performed in this follow-up. Only this assigned evidence report was appended.

## Final frozen pin and explicit finding closure

Verified `review-logs/candidate-snapshot-final.json`, tree
`455101575ecbfbec6f843464ce178e0d09046f51`. Independently recomputed its increment
SHA-256 `7477e67e9b6262e5aec067714c586ef7ac49790e8e6ac7d14116829213bdf325`
against foundation `2c9fa84994d317aade0d1c69faa9a378c780127d`, and cumulative
SHA-256 `743a1346feb7ae62a4cded0224b007312b471b09d80d149b2b0bdf5c25c25b30`
against `b52144955b629314a000b1fe49eeea97fa3d0c5c`. Both match the snapshot.

The complete tree-to-tree delta from v4 changes only Rustdoc credit and URL
rendering in `src/abi.rs` and `src/lib.rs`. Runtime code, the recursive null
predicate and all tests are unchanged. The v4 source verdict applies to this
final frozen tree.

The earlier physical-versus-logical null finding is **closed under the explicit
logical-nonnull scalar-result contract**. The selected-value predicate resolves
both the original physical-count gap and the single-child union-ID issue in
Arrow's logical helper. Original observations and negative-control qualifications
remain recorded above. Reported focused tests and SDK probes do not substitute
for the pending final cumulative gate or establish package/runtime readiness.
No builds, tests or source edits were performed for this confirmation.
