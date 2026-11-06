# Research: standalone Comet scalar adapter

The narrow admission API should explicitly require a trusted immutable kernel
library. Preserve full argument fields, retain library code before invoking foreign
callbacks, and distinguish output schema compatibility from field naming. These
are recommendations for the increment under construction, not a final code verdict.

## Sources and scope

Confirmed the complete saved request, previous build-2 request and governing
AGENTS.md, LAKESAIL.md, SHEHAB.md, CLARITY.md and WRITING-RULES.md. Reviewed the
copied prototype and pinned dependency sources. No builds, fixture execution,
source edits, environment changes or remote posts were performed.

- Implementation checkout: `/Users/alexy/src/sail/tmp/comet-scalar-20261105-2c9fa8499`.
- Starting foundation: `2c9fa84994d317aade0d1c69faa9a378c780127d`.
- Copied prototype: `ef7286ca28222d9f25b719aacda6baea2876a0de`.
- Retained initial comparison: `review-logs/prototype-port.patch`, SHA-256
  `bde908972c8dc51ab7a6c2cc9981706cafbe4d997d0ac627a81fa74d09dc84ae`.
- Comet reference: `0f7f8e45399847715093b3d3affdfa97614b39dc`.
- Local dependencies inspected: DataFusion 55.2.0, Arrow 59.2.0, libloading 0.8.9
  under `/Users/alexy/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f`.

The prior source inventory and 17 file hashes remain in
`../streamsource-build-2/EXTENSIONS-RESEARCH.md`. The initial prototype comparison
is not a final cumulative patch and does not compare the resulting adapter with
Comet. Retain a separate pinned upstream comparison when the implementation is
settled, including any metadata or admission changes beyond Comet's importer.

## Minimal admission API

Prefer an explicitly unsafe low-level function such as
`unsafe load_trusted_immutable(path)`, or an equivalent unforgeable admission
object whose unsafe constructor documents the same obligations. Avoid treating a
boolean declaration as verification. The library supplies executable code and
raw pointer layouts; a numeric version cannot validate them.

The caller must establish that initialization and callbacks are safe to invoke,
the symbols and structs obey the pinned contract, pointers and ownership transfers
are valid, callbacks do not unwind across C, factory callbacks permit concurrency,
and each function is pure and deterministic for its arguments. Returned allocations
must remain valid after the per-call instance is destroyed and be independently
releasable. The loader still rejects missing/wrong probes and malformed supported
records it can diagnose. This is trusted native code, not isolation from a
misbehaving plugin.

The public adapter constructor must not bypass admission. Make it crate-private,
or expose it only with the same explicit unsafe obligations and code-retention
invariant. Comet's constant-binding parameter remains null for ABI v1; this is
part of the supported interface, not a feature to fill from DataFusion literals.
A function needing literal values during type inference belongs to another
interface or a named refusal. Immutable admission is mandatory because DataFusion
may fold or reuse calls; it is not evidence of replay safety for external effects.

Sources: libloading `src/safe.rs:27–39,84`; Comet
[SDK contract](https://github.com/apache/datafusion-comet/blob/0f7f8e45399847715093b3d3affdfa97614b39dc/native/comet-udf-sdk/src/c_abi.rs#L136),
including instance ownership at lines 215–275, reserved constants at 230–236 and
immutable-only admission at 350–363. Comet's SDK remains experimental and
release-specific, despite using Arrow's stable C data layout.

## Ownership and retention

After `Library::new` succeeds, retain a process-owned Arc before calling the
version probe or discovery. Library initialization necessarily precedes this
point and is already part of unsafe admission. Retention before subsequent
callbacks covers failure paths as well as successful imports. Store code ownership,
not per-session state or quota reservations; keeping code loaded must not prevent
kernel/list/instance release.

The prototype's function-held Arc alone is insufficient: output Arrow arrays may
outlive the function, query and session and still call the producer's release
function. Comet explicitly relies on its process cache for this case. A result-owner
wrapper could permit unloading, but it would need to cover every allocation and
callback; it is broader than the chosen increment.

Keep the callback records' exact release/move discipline: moved list entries get
empty placeholders, each owned record releases once, and partial/error paths release
remaining objects while code is resident. Copy the last-error string before another
callback or instance destruction invalidates it. Concurrent factory calls create
separate per-call instances; no shared mutable instance or whole-kernel mutex is
required by this contract.

Sources: Comet
[importer lifetime](https://github.com/apache/datafusion-comet/blob/0f7f8e45399847715093b3d3affdfa97614b39dc/native/core/src/execution/c_udf/imported_c.rs#L85),
[cache](https://github.com/apache/datafusion-comet/blob/0f7f8e45399847715093b3d3affdfa97614b39dc/native/core/src/execution/c_udf/cache.rs#L18),
and [loader move/release](https://github.com/apache/datafusion-comet/blob/0f7f8e45399847715093b3d3affdfa97614b39dc/native/core/src/execution/c_udf/loader.rs#L199).
This review infers the prototype gap from ownership structure; it does not claim
an executed unload crash.

## Argument and return-field semantics

DataFusion `datafusion-expr/src/udf.rs:426–447` carries actual argument fields and
the planned return field into execution. Its physical expression obtains child
fields from the input schema and passes them through at
`datafusion-physical-expr/src/scalar_function.rs:243–260`. Use those fields rather
than rebuilding them from arrays: rebuilding loses metadata, names and nullability.
Check argument-field cardinality and matching data types before exporting buffers.
Reject inconsistent input instead of silently substituting fabricated fields.

Use a fresh kernel instance for each inference/evaluation. Compare its initialized
return schema with the planned output before decoding its buffers under a type.
DataFusion explicitly ignores the top-level return-field name at
`udf.rs:656–657`; do not reject an otherwise compatible output merely because that
name differs. Nested field names, data types and metadata retain semantic meaning.
Arrow extension types live in metadata. Preserve those, and reject changed type
or metadata rather than silently reinterpret the result.

Nullability requires a stated policy. `ScalarFunctionExpr::with_nullable` can
replace the planned nullable flag. A kernel declaring non-null output is compatible
with a nullable planned field; the reverse promises more than the kernel declares.
Requiring exact nullability is a narrower admission policy, not an Arrow memory
safety requirement. Do not use physical `null_count` alone to claim logical-null
validation for dictionary, union or run-end arrays. Avoid adding an unrelated
full-row validation pass under the guise of metadata preservation.

Comet permits input arrays of length one or `n_rows`; P5 expands scalar values to
`n_rows`. If adding length checks, preserve that documented broadcast allowance
unless a narrower public contract is intentional. Output row count must satisfy
the host invocation contract. DataFusion's physical expression also checks it at
`scalar_function.rs:263–280`. These checks do not establish correctness of arbitrary
foreign buffers; valid layouts remain an unsafe admission obligation.

The currently copied P5 adapter loses execution argument fields and has no explicit
process retention. Root is repairing those paths. Test these findings with a
metadata-sensitive kernel, contradictory return schemas, zero rows, sliced/nested
arrays, retained outputs after owners drop, and release/error paths. Arithmetic
success alone does not exercise them.

## Independent producer for the integration owner

No cached Comet SDK/test producer source was found in the inspected Sail/tmp,
Sail, pipeline, P5, grust-sdp or user-cache paths. Previous research read official
pinned sources directly. The independent producer is small and does not require
building Comet's engine. At the pinned commit, use these unchanged source files:

- `native/comet-udf-sdk/Cargo.toml`, `src/lib.rs`, `src/c_abi.rs`.
- `native/comet-test-udfs/Cargo.toml`, `src/lib.rs`.
- The parent `native/Cargo.toml` provides inherited package/dependency declarations.

The [test producer](https://github.com/apache/datafusion-comet/blob/0f7f8e45399847715093b3d3affdfa97614b39dc/native/comet-test-udfs/src/lib.rs)
exports arithmetic, identity, formatting, timestamp, map, struct and panic fixtures.
It depends only on Arrow and the sibling SDK; the SDK depends only on Arrow.
The parent declares Arrow 59.2.0 with `prettyprint`, `ffi` and `chrono-tz`, edition
2021, Rust floor 1.95.0 and package version 1.3.0. That matches the adapter's Arrow
line without making DataFusion part of the producer.

The owner can fetch the pinned source into an isolated retained fixture directory
and build with its own target directory. Preserve the license/notice, original
manifests, hashes, resolved lockfile and commands. If using a minimal workspace
manifest to avoid resolving unrelated Comet members, retain its exact difference
and call this unchanged producer/SDK source under an adapted build manifest, not
an unchanged full-workspace build. Do not edit producer kernels to accommodate
host failures. SDK panic fixtures test exporter containment; host catch_unwind
cannot repair a foreign callback violating its C ABI.

This increment still supplies no package discovery, worker loading, relation
boundary, marker isolation or durable recovery. A later cumulative review and
immutable gates must name the exact resulting source; this advisory is not a
pass verdict on those future changes.

Recorded: 2026-11-05T23:29:38.886573+00:00

## Primary producer file hashes

| Pinned Comet path | SHA-256 |
| --- | --- |
| `native/Cargo.toml` | `42e0b6232b0ef0e8fcafa51ec7823f4c5614b32f283c6b3f8119e12462c3e2b0` |
| `native/comet-udf-sdk/Cargo.toml` | `19366302979f496ddd60d54204e6c087f479c2e8163e826c9097b660313d18d6` |
| `native/comet-udf-sdk/src/lib.rs` | `c0e71c4d559e7a4b14ebdb9a0571a55f790adefb4da21b4397c159d41a06a1a8` |
| `native/comet-udf-sdk/src/c_abi.rs` | `5998bdb824db455b8d778cd879b82a0d65d2650530e73302e8b9e7b852f1869c` |
| `native/comet-test-udfs/Cargo.toml` | `bbe2fef13f9cabdc9d32527d222add5a6e7abe03800432d9ad7da0497b73c447` |
| `native/comet-test-udfs/src/lib.rs` | `ea476f617a4e3ea5b46c35995f17fa94e79485e774f5fdc8318dcb72217dea91` |


## Human-review compendium check

Read the updated saved request and HUMAN-REVIEW.md end to end. The compendium
states the full pipeline/Extensions/performance objective and distinguishes
foundation checks, standalone fixtures and unbuilt integrated recovery. Its Comet
constraints agree with the pinned source: dependency decoupling is not general ABI
stability, trusted immutable admission remains necessary, and scalar calls do not
define a relation protocol. No new executed compatibility claim is introduced.

Two precision improvements should be incorporated before treating it as the
complete source-grounded summary:

1. The “Existing Sail component” table includes extension discovery/registration
   and worker loading without saying that this host exists on the older pipeline
   integration branch and is absent from the upstream-based foundation. State
   that location inline so readers do not infer these are already mainline seams.
2. Code/session-memory separation is a required new integration property, not
   established by the old scalar registry. At host pin
   `99dc47788941daf28eec847527949a4cadafdbd2`, registration at
   `crates/sail-session/src/extensions/mod.rs:278–302` puts both the bound session
   and exporting object in the OwnedScalar owner. The process-wide registry at
   `crates/sail-common-datafusion/src/native_scalar.rs:70–89` retains that scalar;
   `extensions/python_owner.rs:20–25` releases only when its last owner drops.
   Explicitly identify that retained-state ownership as integration work before
   promising independently releasable session resources. No runtime leak or
   measured resource effect was executed or inferred from this source observation.

The recommended process-retained Library-only adapter is narrower and fits the
new separation requirement. Preserve existing functional behavior as a control,
while deliberately correcting ownership rather than copying the old registry's
state retention blindly. Performance measurements were not independently audited
by this Research check. No source edits, builds or tests were performed.

Reviewed HUMAN-REVIEW.md SHA-256: `f1b9e7836840e3c6c72191f502e8ecbbd196f0542973352ef2ba2939f864f23b`.
Recorded: 2026-11-06T00:22:47.155217+00:00


## Frozen staged candidate: final Research source review

No new ownership or field-metadata correctness blocker was found within the
explicitly trusted immutable scalar scope. This is a source-review verdict on
the frozen index, not an immutable build gate or a general Comet compatibility
certification. The attribution/comparison requirement below remains open.

Reviewed index tree `d8e9633355f2bac78ab9470e49aceda1992d2388` from foundation
`2c9fa84994d317aade0d1c69faa9a378c780127d`. Independently recomputed both staged
patches and verified the retained files match:

- Increment SHA-256: `0561254aaed99782dd50a4901f4c28162f799748cfcdac7dd6f5f6ea08676d64`.
- Cumulative SHA-256 against upstream `b52144955b629314a000b1fe49eeea97fa3d0c5c`:
  `59706bb772a2ef606b2bab5657fbe2fe8f18507661110eb0baf53dac50caa376`.
- All twelve staged file hashes match `review-logs/candidate-snapshot.json`.
  During review, the working metadata test acquired an unstaged stronger diagnostic
  assertion. This verdict uses its frozen staged version. Any subsequent source
  change needs its own reviewed pin.

Re-read the complete saved current and previous request, AGENTS.md, LAKESAIL.md,
SHEHAB.md, CLARITY.md and WRITING-RULES.md after compaction. No source edits,
builds or tests were performed by this reviewer. The existing foundation portion
of the cumulative patch relies on the prior source review of foundation `2c9fa8499`.

### Source findings

The loader rejects nonimmutable declarations before opening a library, exposes
unsafe admission explicitly, and makes the adapter constructor crate-private.
`loader.rs:119,183` retains the Library Arc before probe, discovery and kernel
callbacks. The process registry holds library ownership alone; list, kernel and
per-call instance releases remain independently owned. No registry mutex spans
foreign execution. Moved discovery entries are replaced before list release,
including partial-import errors. Error text is copied before instance release.
These mechanisms address the reviewed lifetime gap under the stated trusted
producer obligations. Repeated openings remain retained and require bounded
admission at later package integration.

The C records, callback signatures, integer widths and release discipline match
the pinned SDK records. Comet's [importer lifetime rationale](https://github.com/apache/datafusion-comet/blob/0f7f8e45399847715093b3d3affdfa97614b39dc/native/core/src/execution/c_udf/imported_c.rs#L81)
and [process cache](https://github.com/apache/datafusion-comet/blob/0f7f8e45399847715093b3d3affdfa97614b39dc/native/core/src/execution/c_udf/cache.rs#L18)
confirm why function ownership alone does not cover returned array callbacks.
The candidate retains code earlier than Comet's successful-load cache, including
refused openings. It does not copy Comet's package/path cache or retain session
objects.

`udf.rs:154,174–197` passes actual argument fields at planning and evaluation,
checks cardinality/type/length, compares the initialized return type and metadata,
and admits safe nullability widening while ignoring the top-level return name.
DataFusion 55.2.0 `udf.rs:426–447,656–657` and
`scalar_function.rs:143–150,243–280` support those API assumptions. Nested fields
participate in Arrow DataType equality. Arrow Field equality deliberately omits
IPC dictionary identifiers and ordering flags; this is schema equality, not
byte-for-byte preservation of every IPC attribute. Reserved scalar initialization
remains null, consistent with the pinned SDK.

Correction to the earlier dependency inventory: this candidate resolves
**libloading 0.9.0**, not 0.8.9. Inspected its `src/safe.rs:24–38,84` directly;
loading and possible termination routines remain caller safety obligations.
No dependency-version behavior change was inferred solely from the version.

### Required attribution and bounded claims

Before offering the adapter upstream, add the pinned public source URL to its
`[CREDIT]` attribution and retain an explicit comparison against the cited Comet
SDK/importer/loader. The current `lib.rs` names repository, paths and commit but
has no URL. `prototype-port.patch` compares with the earlier local prototype,
not Comet. The pinned SDK source copy and producer hashes do not replace the
Dependency Ownership requirement to expose and explain adapter differences.

Keep these limits visible in results and later integration decisions:

- `Signature::variadic_any` at `udf.rs:77` excludes zero-argument functions in
  DataFusion 55.2.0 `type_coercion/functions.rs:116–130`. Comet's importer uses
  UserDefined. Current probes exercise nonempty argument lists, and Comet's
  bundled `sum_c` itself requires at least one argument. Nullary kernel support
  is neither established nor silently implied by this adapter's compatibility
  claim.
- The output `null_count` check at `udf.rs:233` concerns physical validity bits.
  Arrow distinguishes that from logical nulls for dictionary, union, run-end and
  null arrays at `arrow-array/src/array/mod.rs:285–326`. This is a diagnostic for
  some producer violations, not general validation of arbitrary returned data.
  Producer schema/ownership correctness remains an unsafe admission obligation.
- Every Arrow family is represented by empty-array tests; populated/sliced
  coverage uses selected integer, string, decimal, struct and list cases. Do not
  describe this as exhaustive populated-type qualification.
- Immutable declaration is an operator obligation, not measured purity, replay
  safety or isolation. No package discovery, worker distribution, relation ABI,
  marker isolation, session-resource reclamation or durable recovery is proved.

### Retained experiment evidence inspected

Verified all six pinned Comet file hashes against this report's earlier inventory.
The five SDK/test member source and manifest files are byte-identical between
`review-logs/comet-producer/upstream/native` and `isolated`. Only the isolated
workspace manifest adapts the build. The build receipt and interop log report
successful producer compilation and two probe tests. Reading their assertions
supports arithmetic/null/order/retained-result checks and SDK containment of
initialization/execution panics, not interoperability of every exported kernel
or every external producer. The numeric ABI probe remains release-specific.

The retained candidate log reports thirteen focused tests passing. Control logs
and receipts distinguish the original-P5 metadata control from the modified
loader lifetime control. These are reported owner executions inspected here,
not independent Research executions. Focused Clippy and these logs do not replace
the future immutable workspace qualification.

Recorded: 2026-11-06T00:35:26.600582+00:00


## Revised frozen candidate v3: Research re-review

**Verdict: the new all-type logical-null guarantee has an unresolved dependency
counterexample.** Ownership, field metadata, nullary admission and copied ABI
records have no additional source-review defect identified. The logical-null
finding below prevents treating this exact revision as fully qualified under its
newly stated guarantee. It was derived from pinned source; this reviewer has not
executed the reproduction.

Verified all fourteen staged and working file hashes, the index tree
`ad453e21427f3f702a342a033dc6c488ab9a7195`, and both retained/current staged patches:

- Increment SHA-256 `a4a1634ae6c0d087f5735cb911da43be19529fec10145ff4333c947562214224`.
- Cumulative SHA-256 against upstream `b52144955b629314a000b1fe49eeea97fa3d0c5c`:
  `094bbb2510294c4e705cb0bd1dce41366b6bcb74d12bc25ba372af09d67406a3`.

Read the latest saved request, HUMAN-REVIEW.md and
COMET-SCALAR-NULLABILITY.md with the previously re-read governing instructions.
The new note explicitly chooses evaluated-value nullability rather than Arrow
RecordBatch's weaker physical-null check, and discloses key scans and potentially
large logical-row bitmaps. That is a coherent contract; the selected dependency
method does not implement it correctly for every admitted shape.

### Single-child dense unions with a nonzero type ID

Pinned Arrow 59.2.0 `arrow-array/src/array/union_array.rs:794–812` handles unions
with at most one child by passing `(0, logical_nulls)` into `gather_nulls`, even
when the sole actual field ID is nonzero. `gather_nulls` at lines 608–648 indexes
by each row's actual type ID and defaults entries without a supplied null buffer
to valid. Therefore the following valid array's selected null is hidden by
`logical_null_count()`:

- One nullable Int64 field with union type ID 3.
- Dense row type IDs `[3]`, offsets `[0]`.
- The only child contains `[None]`.

The expected scalar value is null, but the dependency inserts its validity under
ID 0 and reads the default valid entry under ID 3. The candidate's nonnullable
output guard consequently admits it. The populated union tests use two fields
with IDs 3 and 7 and do not enter the defective branch. Empty single-child
coverage cannot distinguish the behavior. Root and Test Case Generation received
the exact reproduction and source references for execution.

This also affects encoded containers whose selected values are such unions:
DictionaryArray and RunArray derive their logical nulls recursively. A fix limited
to the top-level union shape would need an explicit restriction or further handling
for those compositions. Use selected child validity as an independent test oracle,
not the same dependency method being checked. This finding concerns valid Arrow
layouts, not untrusted pointers or deliberately malformed input.

Check output row count before logical-null inspection as well. The current order
can allocate a large run-end validity bitmap before rejecting an incorrect output
length. This is a source-derived cost observation, not a measured slowdown.

### Earlier findings addressed and remaining provenance boundary

`OneOf(Nullary, VariadicAny)` permits empty arguments without coercing nonempty
arguments. DataFusion 55.2.0 `signature.rs:863–871` and
`type_coercion/functions.rs:992–1000,1029–1057` support this behavior. The new
DataFusion planning test and the original-signature-only control discriminate it.
The return-field test now demands the intended diagnostic, and its guard-only
control reports unexpected acceptance. The missing-probe test now loads a real,
controlled library rather than relying on executable loading behavior.

Independently confirmed that the 7,930-byte retained Comet record extract is an
exact substring of both pinned SDK source and candidate `abi.rs`. Its SHA-256 is
`65d19203743e72f6db37f8e6f525605ba3020984e8c3915629539a2c621a762b`.
The retained comparison is correctly empty. The copied records retain the ASF
license, pinned source URL, original Comet names, defaults and release functions;
Sail aliases do not change their layouts. This closes the ABI-record attribution
and copy-comparison finding. The host loader/importer remain stated adaptations;
the retained comparison does not cover them. Preserve their comparisons against
the credited pinned Comet host files before an upstream offer.

The inspected owner logs report fifteen focused tests and affected strict Clippy
passing. The physical-null control fails on its first dictionary case; it does not
execute every later encoded case after that failure. The logical-null test's passing
case checks selected-null and unused-null behavior for its existing fixtures,
not the missing single-child union counterexample. The independent producer rerun
was pending when this review began; no new result is claimed here. No builds,
execution, source edits or remote actions were performed by Research.

Recorded: 2026-11-06T00:51:00.403968+00:00


## Frozen candidate v4: logical-null finding closed

**Source verdict: no unresolved Research correctness blocker found in v4.**
The v3 single-child union finding and the row-check ordering finding are closed.
The new predicate follows selected values recursively rather than calling the
faulty Arrow logical-null method. Final immutable qualification remains outside
this review; the host-comparison receipt refresh noted below remains necessary.

Independently verified all fifteen staged and working file hashes and the index
tree `637c9cc4c8f12591a0ef89c2765869c83771ec5f`. Both retained patches exactly
match the staged diffs:

- Increment SHA-256 `d87f310f63f8515a04aff5c9bfba6acc84ae1473fe636e524cb935240f9ae879`.
- Cumulative SHA-256 against `b52144955b629314a000b1fe49eeea97fa3d0c5c`:
  `1f42e598ff9297d1b37eace3c5edf5307a0ef2c3b97db8d62b975d425ce4c4d7`.

Read the current saved request and revised COMET-SCALAR-NULLABILITY.md. The prior
AGENTS/LAKESAIL/SHEHAB/CLARITY/WRITING-RULES reread remains applicable; there has
been no intervening compaction. Reviewed the full new `nulls.rs`, invocation
ordering, populated fixtures, retained failure log and updated producer receipts.
No builds, tests, source edits or remote actions were performed by this reviewer.

### Why the recursive predicate satisfies the selected contract

Dictionary keys and single-key access respect sliced key buffers, as implemented
in Arrow 59.2.0 `dictionary_array.rs:399–415`. A physical null key is null;
otherwise recursion follows only its selected dictionary value. The fast path for
ordinary nonnullable values is sound because a valid list or struct remains
present even when one of its children is null.

Unions use the actual row type ID and value offset. `union_array.rs:250–285`
returns the selected child/offset, and its slicing implementation at 331–350
slices dense offsets or sparse children correctly. This removes the hardcoded-ID
fault and handles nested union/dictionary/run-end combinations. It neither scans
unused union children nor treats their nulls as selected results.

Run-end arrays inspect the inclusive physical-run interval intersecting their
logical slice. The new range is the same operation as Arrow's public
`RunArray::values_slice` at `run_array.rs:268–279`. Single-slot recursion uses
`get_physical_index`, which includes the logical offset in
`arrow-buffer/src/buffer/run.rs:232–268`. The early empty-array return protects
the empty range. Nonempty Null arrays are always null. The dispatch macros cover
all supported integer dictionary keys and Int16/Int32/Int64 run-end types.

The UDF now rejects incorrect row counts before null inspection, and nullable
planned results bypass the predicate. The algorithm constructs no logical-row
validity bitmap; its remaining work follows selected keys, union rows and active
physical runs, with recursion for encoded values. This is a source property,
not a benchmark or proof of bounded runtime for arbitrarily deep schemas.
Caller resource limits and trusted foreign-buffer validity remain required.

The retained `arrow-union-control.log` records the precise earlier failure:
the old helper returned an accepted dense union whose selected child was null.
The new tests use known selected child values rather than that faulty helper as
the oracle. Their nested dictionary/run-end cases, nonzero-ID slices and million-row
compressed run distinguish the repair and avoid claiming exhaustive populated
Arrow-type qualification. The owner logs report seventeen focused tests, strict
affected Clippy and two independent SDK producer probes passing. Those executions
were inspected, not performed by Research.

### Host comparison provenance

The previously missing loader/importer comparisons now exist, with pinned URLs,
source hashes and an explicit statement that they are adaptations rather than
verbatim host adoption. Independently verified both source hashes and reconstructed
the comparison targets in memory. The loader comparison exactly reproduces current
`loader.rs` SHA-256 `2eb758ba2463077ecae3600aac77661d62e3f5ac655b58f33eab0f3a6900e990`.
The importer comparison and receipt still reproduce the earlier `udf.rs` SHA-256
`9edb35ebe3566b5581bb4f335a7a5be169d14e01ac418a5450d75c8e3c6bf3ac`, while v4 is
`5022f1f3fa806a5055e81fabca81aa8c6aef63e6554a15bc88584c2010e5bf98`.
Root has been asked to refresh this evidence against v4. This is a provenance
receipt correction, not a requested source change or a new ownership defect.

Recorded: 2026-11-06T01:02:33.889152+00:00


## Final frozen pin: all Research findings closed

Verified final index tree `455101575ecbfbec6f843464ce178e0d09046f51`, all fifteen
staged/working file hashes, increment SHA-256
`7477e67e9b6262e5aec067714c586ef7ac49790e8e6ac7d14116829213bdf325`, and cumulative
SHA-256 against `b52144955b629314a000b1fe49eeea97fa3d0c5c`
`743a1346feb7ae62a4cded0224b007312b471b09d80d149b2b0bdf5c25c25b30`.
The entire v4-to-final delta changes only Rustdoc credit/link formatting in
`abi.rs` and `lib.rs`; the reviewed UDF and recursive null predicate are unchanged.

The refreshed `host-comparisons-v4.json` and both `*.comparison-final.diff` files
close the remaining provenance finding. Independently reconstructed their targets
in memory from the hash-verified pinned Comet sources. They reproduce the final
loader and UDF bytes exactly, including UDF SHA-256
`5022f1f3fa806a5055e81fabca81aa8c6aef63e6554a15bc88584c2010e5bf98`.
The copied ABI extract remains byte-identical to the pinned SDK. The final Rustdoc
log reports successful documentation generation; Research did not run that check.

All Research findings for this frozen standalone adapter candidate are now closed.
The source verdict remains limited to the reviewed trusted immutable scalar
contract, with the evidence and integration limits already stated above. It is
not a broad-gate pass, package/worker integration verdict or general guarantee for
arbitrary native code. The broad immutable gate remains pending. Confirmed the
saved request and governing-instruction compliance established in this review;
no intervening compaction occurred. No builds, tests or source edits were performed.

Recorded: 2026-11-06T01:10:08.774641+00:00
