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
