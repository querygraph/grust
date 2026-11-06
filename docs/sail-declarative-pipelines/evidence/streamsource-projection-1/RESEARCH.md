# Research: marker-isolated streaming projection

Use a Sail streaming projection node that owns event scheduling and reuses
DataFusion's public Projector and AsyncMapper. Evaluate expressions only on each
contiguous data run. Emit preceding markers before evaluating later data. Keep
ordinary batch projection unchanged. This is the smallest coherent architectural
change supported by the inspected APIs; no execution or performance result is
claimed by this report.

## Scope and source pins

Read the complete saved request, its linked predecessor, repository AGENTS.md,
LAKESAIL.md, SHEHAB.md, CLARITY.md, WRITING-RULES.md and Sail's copilot, development
and Rust-review instructions. The seven-role review, design-before-code and codec
requirements apply. This role writes only this report. No builds, tests,
dependency changes, source edits, remote posts or commits were performed.

Source checkout: `/Users/alexy/src/sail/tmp/streamsource-projection-20261105-06dd7e237`.
Starting HEAD: `06dd7e237eb5a343dcc6a6145e775f495e6c30de`. Merge base with upstream:
`b52144955b629314a000b1fe49eeea97fa3d0c5c`. Initial tracked checkout was clean;
`review-logs/` was untracked. The final cumulative implementation requires a new
independent review; this report is architectural research.

Inspected DataFusion 55.2.0 and Arrow 59.2.0 under
`/Users/alexy/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f`.
The extracted package directories lack Cargo VCS/checksum metadata. Independently
compared the five DataFusion source files below with their cached `.crate` archive
members, and verified each archive's SHA-256 against this checkout's Cargo.lock.
They match exactly. Public references below identify the corresponding versioned
primary-source packages, not a claim that latest upstream behaves identically.

| DataFusion 55.2.0 source | SHA-256 |
| --- | --- |
| `datafusion/src/physical_planner.rs` | `9f9c0292abc61ce6fdc43a1d5fd1fe8ef18b5f9765b2417574f01ba3006c010b` |
| `datafusion-physical-expr/src/projection.rs` | `7d0d6b929a4b0f1f04b141845e8c49083b5a4e36c3b9d5572164ccdda352d757` |
| `datafusion-physical-expr/src/async_scalar_function.rs` | `4b152380e544e1cb57d11eeacfa43a08997764aa283647019772aff439d8db6b` |
| `datafusion-physical-plan/src/async_func.rs` | `d9db723989a19c0b25c2e33b77323d15ce005d30468106ac3f6bdb549b5fcf29` |
| `datafusion-expr/src/async_udf.rs` | `fdfeb03e9d0296db53eb5ce36d165d56af6afb7780e16a1284ffd75a93e1d882` |

Canonical local DuckDB and Polars paths under `sail/opt` do not exist. No substitute
checkout or broad optimization research was needed: the decisive interfaces are
already public in Sail's pinned dependencies. No Spark compatibility assertion is
made; the Spark role owns any relevant semantic comparison.

## What existing code does

Sail `sail-plan/src/streaming/rewriter.rs:70–80` prepends marker/retraction
expressions to an ordinary logical Projection. Its physical execution therefore
still evaluates user expressions on marker placeholders. Unlike filtering, this
cannot be repaired by retaining marker rows after evaluation: projection may
throw, invoke native code or initiate asynchronous work before producing a row.

DataFusion's [Projector](https://docs.rs/crate/datafusion-physical-expr/55.2.0/source/src/projection.rs)
precomputes a projection schema and evaluates batches at lines 919–975. It preserves
zero-column row counts explicitly. `make_projector_with_schema_metadata` at
561–599 derives names/types/nullability from physical expressions but copies field
and schema metadata from the supplied projected schema. Use this public component;
no change to its evaluation semantics is required.

The [default physical planner](https://docs.rs/crate/datafusion/55.2.0/source/src/physical_planner.rs)
at 2989–3077 builds physical expressions, maps async calls, inserts AsyncFuncExec,
then creates the final ProjectionExec with logical output metadata. Its column
alias handling uses physical input field names for logical column references,
avoiding qualified derived-expression names. A replacement planner branch must
preserve that distinction rather than derive every alias from display text.

[AsyncFuncExec](https://docs.rs/crate/datafusion-physical-plan/55.2.0/source/src/async_func.rs)
at 211–271 coalesces input batches before invoking async expressions sequentially.
That operator cannot remain immediately below an isolated synchronous projection:
it would evaluate async calls on marker rows first. Its output uses `Schema::new`,
which drops schema-level metadata; the streaming implementation should preserve
metadata explicitly when constructing its temporary augmented batch.

## Supported async behavior and limits

Public AsyncMapper at `async_func.rs:424–511` collects async scalar expressions,
assigns appended result columns, and rewrites references. Keep the original physical
expressions for codec reconstruction; rebuild this derived mapping at construction
and worker decode. Append async outputs in the mapper's recorded order, then run
Projector on the augmented data batch. Each async expression evaluates against the
original data batch, matching the existing operator.

AsyncMapper is not a dependency scheduler for nested async calls. It records
original subtrees; AsyncFuncExpr evaluates its arguments synchronously. Sail already
rejects async-within-async at `sail-plan/src/function/mod.rs:88–112`, and calls that
preparation in `sail-session/src/planner.rs:114`. Preserve this named refusal,
including expressions exposed by the new logical node. Do not add nested async
execution under the guise of marker isolation.

Only Jev implements AsyncScalarUDFImpl in the inspected Sail tree. It inherits
`ideal_batch_size=None`, honors `number_rows`, handles empty input and returns
arrays at `sail-function/src/scalar/jev/mod.rs:194–200,308`. Its codec preserves
the async wrapper at `sail-execution/src/proto/codec.rs:3546–3548,4043–4045`.
That is a concrete supported path for a worker reconstruction test.

The pinned [AsyncFuncExpr invocation](https://docs.rs/crate/datafusion-physical-expr/55.2.0/source/src/async_scalar_function.rs)
at 108–208 has three source-derived limits:

- `ideal_batch_size=Some(0)` never advances a nonempty remainder. Refuse this
  invalid configuration before execution rather than allow an unending loop.
- Empty input with a positive ideal size collects no arrays and passes an empty
  collection to concat. The existing AsyncFuncExec coalescer skips empty batches,
  confirmed in Arrow `coalesce.rs:446–451`, so this direct-helper case is not an
  established successful batch-plan behavior.
- Scalar callback results expand to one row at line 192, regardless of the chunk
  length. They do not establish general scalar broadcasting for multirow input.

These are source observations, not executed reproductions. They must not be
represented as successful capabilities that this increment is required to mimic.
Positive-size chunking of correctly sized array results is part of the existing
helper path. AsyncMapper also records repeated occurrences without deduplicating
its invocation list; changing volatile-call counts is a separate semantic decision.

## Smallest implementation and ownership choice

Introduce a logical StreamProjection node following the existing StreamFilter
seam in `sail-session/src/planner.rs:471–484`. It exposes the original expressions
so async preparation and expression visitors continue to see them. The physical
node retains expressions, aliases and explicit projected metadata. Keep the two
transport columns at their original input indices while slicing rows, so existing
physical column references and argument fields remain correct.

For data-only batches, invoke Projector directly for synchronous projections.
For mixed batches, keep a lazy cursor over contiguous data/marker runs. Marker
output uses its existing marker bytes and retraction column plus correctly typed
output placeholders; it must not invoke the expression tree. Async evaluation
holds one data-run future at a time and yields it before advancing. It must neither
pre-evaluate a later run nor coalesce across a marker. Release exhausted batches
and completed futures before yielding output where ownership permits.

This explicit event scheduler is preferable to copying all ProjectionExec or
AsyncFuncExec. Those plans contain optimizer/properties/metrics/protobuf machinery
whose execution is designed for ordinary batches. Projector and AsyncMapper already
expose the required unchanged functionality. There is no need for a fake child
plan, recursively executing a replacement physical plan per run, or a blocking
async bridge inside PhysicalExpr::evaluate.

For the selected working async surface, public AsyncFuncExpr can be reused with a
zero-ideal refusal and no async invocation for empty data. If the implementation
instead promises corrected generic scalar and empty/chunk behavior, take ownership
of its approximately hundred-line invocation routine with pinned attribution and
an exact comparison, making only those explicit fixes. Its public `func` allows
access to ScalarFunctionExpr, arguments, async UDF and the original return field.
Do not copy the full async planner merely because one helper has edge defects,
and do not layer several result-shape repairs around the faulty routine.

Marker isolation necessarily changes async batch formation: markers terminate a
run. Compare data-only and mixed-marker cases before claiming comparable cost.
Preserving correct row results does not establish a remote-call throughput budget
or replay safety for side effects.

## Codec and discriminating checks

Add the physical node to Sail's protobuf and extension codec. Encode original
physical expressions and aliases plus the projected schema metadata, not temporary
AsyncMapper indices. Decode against the input schema, then reconstruct derived
mapping/projector state. Existing physical-projection helpers at
`codec.rs:5673–5724` treat an empty vector as absent; preserve a meaningful empty
payload projection rather than accidentally replacing it with identity. If stored
expressions always include the two transport columns, state that invariant.

Projection properties must project equivalences and partitioning through aliases,
as DataFusion does at `physical-plan/projection.rs:224–243`; do not clone input
partition expressions when their referenced columns have disappeared. Preserve
pipeline boundedness and ordering without inventing a repartition.

Required cases include a throwing/counted expression on marker-only input; data,
marker, failing-data ordering; retraction alignment; zero payload columns; exact
field/schema metadata; all Arrow placeholder families; multiple independent async
calls and async inside a synchronous expression; pending/cancelled async work;
the existing nested-call refusal; codec round trips for sync and Jev async plans;
and unchanged ordinary batch planning. Marker-only input must produce zero user
calls. A later error must not hide an earlier marker. An async mock should record
actual rows/argument fields, not merely whether a future returned successfully.

Recorded: 2026-11-06T02:06:44.692260+00:00


## Implementation review before freeze

Research verdict: no must-fix source defect found within the declared projection
increment. This is a source-review result, not a test or readiness verdict.
Reread the saved request, AGENTS.md, LAKESAIL.md, SHEHAB.md, CLARITY.md,
WRITING-RULES.md, Sail's applicable instructions and the complete
STREAMSOURCE-PROJECTION.md after compaction.

Reviewed the new logical and physical nodes, original-expression traversal,
rewriter, extension-planner branch, protobuf/codec, and the five new Rust test
files. Compared the tracked increment with starting HEAD `06dd7e237eb5a343dcc6a6145e775f495e6c30de`
and inspected the cumulative change inventory against upstream
`b52144955b629314a000b1fe49eeea97fa3d0c5c`. Existing foundation and scalar-adapter
source is unchanged by this increment; its Research coverage remains the earlier
pinned reviews in `streamsource-build-1/ARROW-TYPE-RESEARCH.md` and
`comet-scalar-1/RESEARCH.md`. New untracked projection files were read explicitly;
they are not represented by the current tracked-only git diff.

The coordinator announced a temporary negative-control mutation during review.
The reviewed operator is preserved at
`review-logs/controls/projection-original.rs`, SHA-256
`cbab2dbd17beb5a52437c07a60c4d288bd4a3be15b470824bc143f972085f9f2`.
No verdict applies to the deliberately mutated operator. Supporting file hashes:

| File | SHA-256 |
| --- | --- |
| `sail-logical-plan/src/streaming/projection.rs` | `f43576eb9124d213790ab099803eedc38f0a662da9381f821e53299b3aeec9db` |
| `sail-session/src/planner.rs` | `2fc2747015fabb5b733e7ef80771ee3c0949be5a85ddafba91cf8e22a5b54bad` |
| `sail-plan/src/streaming/rewriter.rs` | `106f188c2abc8715351ed0c895f234dcee3e6a9372b1b15670647f1286f9bbfe` |
| `sail-execution/src/proto/codec.rs` | `40c10d9a3f5b42168c999e7b588edeeec90415913886e8944e80df69a8960cda` |

The implementation agrees with the pinned public APIs:

- `DataProjector` records original physical expressions and uses AsyncMapper to
  derive temporary result columns. Async calls receive the original data run,
  with unchanged argument-field metadata. Their results are appended in mapper
  order. The augmented schema preserves input metadata, and Projector receives
  the intended output field/schema metadata. Physical names, types and
  nullability remain expression-derived, as DataFusion's API specifies.
- The run cursor advances lazily. Marker output copies the two control arrays
  and constructs typed payload placeholders without expression evaluation.
  Earlier output is returned before later data evaluation. The try-unfold future
  owns pending state, so dropping the stream drops local pending evaluation;
  this does not establish cancellation of remote side effects.
- Empty async input bypasses invocation; zero ideal size is refused at planning.
  Positive ideal sizes delegate chunking to the pinned helper. No implementation
  claim repairs generic scalar-result broadcasting or nested async execution.
  The logical node exposes expressions to Sail's existing nested-call refusal.
- The codec stores original expressions, aliases and output schema, then calls
  the same constructor on decode. Two mandatory control expressions avoid the
  generic helper's empty-vector ambiguity for zero-payload projection. Reexporting
  the existing rewrite entry points adds no alternative rewrite implementation.

Correction to the earlier properties recommendation: projecting ordinary
DataFusion equivalences is insufficient for encoded markers. A data expression
that is always 17 can have a marker placeholder of 0. The implementation correctly
uses conservative equivalences and unknown partitioning with the existing
partition count, boundedness and partition-local order. It should not promise
computed-constant or hash-partition guarantees for marker payloads. The added
physical-optimizer counterexample specifically exercises this distinction.

The small Sail-owned scheduler plus unchanged public evaluators is an appropriate
ownership boundary for the supported surface. Copying the full projection or async
operator would carry coalescing and property behavior that this stream cannot use.
The two explicitly bounded helper cases do not yet justify taking ownership of a
larger evaluator. If generic scalar callbacks become an admitted requirement,
revisit the earlier narrow-helper ownership option with a failing control.

Two verification suggestions were sent to the coordinator: exercise multiple
independent async calls in one projection, and exercise the existing nested-call
refusal through the new logical Extension. These are coverage gaps in the files
read, not identified source failures. Existing tests inspect ordered errors,
controlled-future drop, metadata, exact Arrow types, optimizer integration and
codec reconstruction. Their presence alone is not an executed result. The Jev
codec check uses marker-only input and therefore does not establish successful
remote-service invocation after transport.

Frozen cumulative patch review, public-query execution, unchanged-source controls,
performance measurements and immutable qualification remain pending. This role
ran no build, test or source mutation.

Recorded: 2026-11-06T02:22:08.978992+00:00


## Final frozen cumulative Research verdict

No unresolved Research finding blocks this candidate's source review. This verdict
covers the frozen index tree below, including the cumulative changes against
upstream. It does not certify pending runtime gates, benchmark results, distributed
recovery or native-package integration.

| Identity | Verified value |
| --- | --- |
| Starting HEAD | `06dd7e237eb5a343dcc6a6145e775f495e6c30de` |
| Upstream base | `b52144955b629314a000b1fe49eeea97fa3d0c5c` |
| Frozen index tree | `52cbe5f4281bf74b9d54615504ce7eb9e062f80d` |
| Increment SHA-256 | `5fa79cdd5f911e5449ffb64b0991ef7a21d3d3101e2311576cddb0f143022ecc` |
| Cumulative SHA-256 | `70390f447d0b7425a49cc8cbec2649ec1a3a11a5f2cb5d5ea7a372c11dfc6b20` |

Independently verified all 52 cumulative file hashes in
`review-logs/candidate-snapshot-final.json` against both working-tree bytes and
staged Git blobs. All match. Independently regenerated both binary Git diffs and
matched their hashes to the manifest and retained `increment-v1.patch` and
`cumulative-v1.patch`. There is no unstaged tracked diff. The staged index contains
19 increment paths; remaining cumulative files retain their previously reviewed
foundation and scalar-adapter content. Reviewed the cumulative production changes
within the Research specialty, their interaction with projection, the final
increment and new test cases. Earlier primary-source comparisons remain applicable
because the dependency versions and those source bodies are unchanged.

The final operator differs from the retained pre-control operator only by placing
the zero-row return before both synchronous and asynchronous evaluation. Its
SHA-256 is `a94b5dae694a667fa850a3a65746fdc17cc972c8d4705ecc7f99e171b2513800`.
The new counting-expression test asserts zero calls on an empty input, the planned
column count and zero output rows. Inspected `empty-sync-control.log`: it records
one call where zero was expected before this repair. This is retained coordinator
execution evidence, not a test run by this reviewer. Returning an empty batch
under the precomputed output schema implements the declared stream contract
without altering ordinary batch projection.

The bounded-source adapter now prepends unqualified control fields while retaining
the input's qualified logical fields and metadata. This agrees with DataFusion
55.2.0 `datafusion-common/src/dfschema.rs:154–171`: qualifiers are stored separately
from the underlying Arrow schema. Reconstructing only from Arrow discarded them.
The focused source-adapter test checks qualifiers, field metadata and nullability
through field equality, schema metadata and child replacement. The public bounded/rate
union test exercises the downstream strict-cast trigger. This is a targeted
resolution repair, not a new name-resolution policy.

Both earlier coverage suggestions are closed in source:
`streaming_projection_plans_multiple_independent_async_results` uses distinct
argument expressions and verifies both mapped result columns;
`streaming_projection_preserves_named_nested_async_refusal` checks the existing
named refusal after streaming rewrite. Planner fixtures now install Sail's
analyzer, logical-optimizer and physical-optimizer rule lists. This reflects the
server's rule-selection seam, while it does not reproduce every session or runtime
configuration. The final tests and public Python cases were inspected, not run here.

The final design accurately limits public-helper reuse: it preserves existing
call-site behavior, admits that chunk results and concatenation can retain more
memory than one run implies, and leaves resource budgeting, scalar-result helper
correction and external-effect cancellation unproven. The selected public
Projector/AsyncMapper integration still needs no copied dependency implementation.
The source-rewrite entry-point exports reuse existing logic. Codec reconstruction,
control-column checks and conservative stream properties remain unchanged from the
preceding source review.

Confirmed compliance with the saved full request and governing instructions read
for this review; reread the request and final design before closing. No builds,
tests, dependency changes, source edits or remote actions were performed by this
role. Source-review findings are closed; immutable runtime qualification and final
performance assessment remain separate pending evidence.

Recorded: 2026-11-06T02:40:05.358705+00:00


## Superseding marker-capacity finding and dependency ownership

The tree `52cbe5f4281bf74b9d54615504ce7eb9e062f80d` is superseded. Subsequent
review identified a valid nullable run-end type for which Arrow's null constructor
panics at a representational boundary. The earlier no-blocker source verdict did
not catch this case and is not a readiness verdict for that tree. The coordinator
reports executed direct/nested failing controls; this follow-up independently
verified the source mechanism, without executing it.

Owning Arrow's null constructor is feasible and preferable to either blanket
non-null placeholders or a second recursive preflight layered around it. Copy the
exact Arrow 59.2.0 `ArrayData::new_null` implementation, retain its encoding choices,
and make only the fallibility, checked sizing and public-import changes required.
The method is `arrow-data/src/data.rs:672–832`, 161 lines including signature/braces.
Its dependencies are public: DataType::primitive_width, Buffer, MutableBuffer,
NullBuffer, bit_util, ArrowNativeType and ArrayDataBuilder. No private Arrow helper
or field is needed. Replace Self recursion with the owned Result-returning helper;
replace both unchecked builders with public `build()?`; construct an ArrayRef with
`make_array` only after successful construction.

Primary source:
[Arrow 59.2.0 ArrayData](https://docs.rs/crate/arrow-data/59.2.0/source/src/data.rs).
Verified the extracted registry source byte-for-byte against its cached package:

| Artifact | SHA-256 |
| --- | --- |
| `arrow-data-59.2.0.crate`, also Cargo.lock checksum | `723fe4aeed7604e00b9883a465af4ff0a0e6c44c03e41a68c3d1cbc403e0e44d` |
| Complete `src/data.rs` | `456e411ac7f3610fdf50ac1b1173f960fe62ac1338d18a81cba561d622b1024b` |
| Exact lines 672–832, preserving indentation/newlines | `8eb6f6c718362b05fa0b763939b09cfb6ccc61dc0abd452dcf239ab0bffff1c2` |

The package declares Apache-2.0; the source carries the ASF license header and the
package NOTICE identifies Apache Arrow and its contributors. Preserve the source
header and a version-pinned CREDIT, and retain the exact extraction and comparison
diff showing every Sail change. This is source-provenance reporting, not a legal
opinion about distribution. The coordinator owns those artifacts and implementation.

### Preserve each nullable representation

The chosen encoding determines child lengths. Nullable dictionaries have zero
values and null keys. Null List, LargeList, ListView and Map arrays have empty
children. Struct and sparse Union children have the parent length. FixedSizeList
children have checked `size * len` length. Dense Union chooses the first child at
length `len`, with other children empty. Nonempty RunEndEncoded has one checked
run endpoint and one nullable value; empty run arrays have two empty children.

Consequently, nullable
`Dictionary<Int8, FixedSizeList<nullable RunEndEncoded<Int16>, 32768>>` at length
one can retain an empty dictionary values array, including an empty run-end child.
The non-null dictionary placeholder's single value forces an unrepresentable
32768-element run-end child. Do not replace the former encoding with the latter,
and do not reject a type merely because an inactive or empty child would overflow
at the parent's length. Existing non-null placeholder branches that previously
used Arrow null construction for nullable children should call the fallible null
helper at those same positions.

Required checks follow the implementation's actual allocations and offsets:

- Check `len + 1`, byte-width products and fixed-size child multiplication before
  allocation or recursion. Reject negative fixed sizes before casting to usize.
- Check the selected Int16/Int32/Int64 run endpoint before building child arrays.
  Return an error for a requested single-array extent that cannot be represented;
  do not label the data type itself unsupported.
- Check dense Union's current i32 endpoint and buffer capacities before allocating
  the IDs. Retain its existing first-child selection and offset construction.
- Check each allocation layout, including packed null bits. Public
  `arrow::alloc::ALIGNMENT` and `std::alloc::Layout::from_size_align` cover the
  layout precondition of MutableBuffer::from_len_zeroed. A global `len <= isize`
  restriction would be unnecessary for types such as Null with no value buffer.
- Replace dictionary-key unwraps, missing union-child unwraps and invalid run-type
  unreachable branches with named errors. Checked builders do not themselves
  validate every malformed datatype that `make_array` cannot dispatch, such as
  invalid Time32/Time64 units; preserve an explicit valid-type contract or refuse
  those malformed forms before conversion.

These checks prevent known arithmetic/layout panics, not allocator exhaustion or
arbitrarily deep schema recursion. Buffer allocation still follows Arrow/Rust
allocation behavior. ArrayDataBuilder::build performs content validation and can
add work relative to Arrow's unchecked construction; do not claim this cost is
negligible without the applicable marker-heavy measurements.

Relevant secondary source seams are `arrow-buffer/src/buffer/mutable.rs:128–168`,
`arrow-buffer/src/util/bit_util.rs:24–26,95–96`,
`arrow-data/src/data.rs:1158–1290,1358–1460,2222–2266`, and
`arrow-array/src/array/mod.rs:890–986,1020–1022`. All are pinned 59.2.0 sources.
The last function confirms that new_null_array directly calls ArrayData::new_null.

A recursive preflight followed by the unchanged constructor would have to mirror
these same layout decisions while leaving panic sites in another implementation.
Catching panics is not a fallible construction contract. Splitting oversized marker
runs can be a later scheduling choice but does not resolve fixed-size nested
children that exceed capacity even for one parent row. The narrow owned constructor
addresses the current failure while preserving successful encodings.

The future candidate needs fresh exact-type and validate_full checks across all
Arrow families, direct/nested run overflow errors, and the valid empty-dictionary
counterexample. Neither the ownership recommendation nor source inspection proves
those cases pass. No builds, tests, source changes or remote actions were performed
by this Research role; a new frozen candidate review remains required.

Recorded: 2026-11-06T03:04:08.742480+00:00


## Revised frozen Research verdict after nullable-construction repair

No unresolved Research source finding blocks the revised candidate. The previously
identified run-end panic and nullable-dictionary restriction are closed by the
inspected implementation and discriminating regression fixtures. This supersedes
the source verdict on tree `52cbe5f4`; runtime qualification remains separate.

| Identity | Independently verified value |
| --- | --- |
| Starting HEAD | `06dd7e237eb5a343dcc6a6145e775f495e6c30de` |
| Upstream base | `b52144955b629314a000b1fe49eeea97fa3d0c5c` |
| Frozen index tree | `0fd5f5e69cf79ce8afed06474219ef81730a84de` |
| Increment SHA-256 | `97566bc3fcdb028e8fa524c5ade7b0e765bee5c323acfba35e2eac889a1c29b3` |
| Cumulative SHA-256 | `b888f019db493c1865e9fcbe43a061b85df9cc7d7db0af264039bc5634d38fb6` |

Verified all 54 cumulative manifest file hashes against both working-tree files
and staged Git blobs. Reconstructed both binary Git diffs and matched their hashes.
The index tree matches; there is no unstaged tracked diff. Reviewed all 26 increment
paths in the cumulative context, with earlier unchanged foundation and Comet code
retaining its prior source-review coverage. The coordinator's temporary untracked
performance probe is explicitly outside this candidate and this source verdict.

Read the final projection plan and the new self-contained marker-placeholder plan.
The owned constructor implements their chosen boundary: valid Arrow datatypes,
fallible representational sizing, preserved nullable encodings, and no promise of
recoverable allocator exhaustion. It retains Arrow's layouts and exact datatype,
including nested field metadata. Recursive calls use the materialized child
lengths, and every constructed ArrayData uses the checked builder. Fixed-size
products, offsets, byte widths, dense-union limits and run-end conversions are
checked at their relevant construction sites. No duplicate preflight traversal or
private Arrow dependency was introduced.

Independently reproduced the ownership receipt in
`review-logs/null-ownership/comparison-v1.json`. The upstream extract equals cached
Arrow 59.2.0 lines 672–832, and the retained initial copy contains those bytes
verbatim. The final method matches `sail-new-null-method-v1.rs`, including its final
newline. Recreated the unified comparison and matched `comparison-v1.patch`
exactly. Its changes are the Result boundary, recursive error propagation,
capacity/conversion checks and checked builders, plus necessary formatting.
The final source retains the ASF header and pinned CREDIT. Verified that the
[credited Arrow 59.2.0 source URL](https://github.com/apache/arrow-rs/blob/59.2.0/arrow-data/src/data.rs#L672)
resolves to the official versioned source.

| Ownership artifact | Verified SHA-256 |
| --- | --- |
| Final `array/null.rs` | `d64dca64da53d5a3d79b5dc7dc1fc4758ce424d9b65b97a2938e68ab778cac65` |
| Final extracted Sail method | `2117ad4597e9f2e228f3e5a05bef40791f4747fb406aa265edcef5fbb7d2e5d6` |
| Exact upstream comparison | `806c40919188abb6ce157601049835c5eec1d496969c832ad7f53eecf39171f6` |

Nullable children in the existing non-null placeholder constructor again follow
their original null-producing branches, now through the fallible helper. Empty
non-null dictionaries no longer construct an unused representative value.
Projection uses the same nullable/nonnullable choice for both markers and empty
results. Event encoding uses it for generic payloads; the established fixed Binary
control array on the ordinary data path remains unchanged. This last choice avoids
extending generic checked construction to the source data path unnecessarily.

Inspected fixtures cover exact types and full Arrow validation, physical run ends
at all integer limits, nested Struct/Union/FixedSizeList limits, checked size
arithmetic, and empty dictionary values with otherwise unrepresentable nested
run-end values. The projection boundary fixture first verifies that its source
delivers the full 32768-row marker batch, so batching cannot hide the failure.
Its expression call count remains zero. The event-encoding dictionary case tests
the valid one-row encoding and marker round trip. These are source-inspected tests;
this reviewer did not execute them or independently certify the reported affected
suite pass.

The earlier async, metadata, qualifier, codec and conservative-property assessments
remain applicable. Public tests now omit diagnostic output and compare exact data
multisets where SQL supplies no ordering guarantee. No new distributed ordering,
checkpoint recovery, external-service cancellation or native-package claim follows.
The valid-type precondition is material: this helper is not a validator for every
malformed DataType value, and checked Arrow construction is not an out-of-memory
recovery protocol. General non-null allocation hardening outside the changed paths
is not established by this review.

Confirmed compliance with the saved full request and previously reread governing
instructions, with the current request and final plans reread before this verdict.
No builds, tests, source edits, commits or remote mutations were performed by this
role. The new immutable runtime gate and final optimized performance assessment
remain pending and must name this candidate or its byte-identical committed tree.

Recorded: 2026-11-06T03:19:12.956639+00:00


## Final pin confirmation after Python lint repair

Verified the advanced frozen index tree
`b67d1a9416d22241ab0359e2ef96dcdf3c678757`, retaining starting HEAD
`06dd7e237eb5a343dcc6a6145e775f495e6c30de` and upstream base
`b52144955b629314a000b1fe49eeea97fa3d0c5c`. All 54 cumulative file hashes match
both working-tree bytes and staged blobs; the 26 increment paths remain the same.
No unstaged tracked changes were present. Independently regenerated the patches:

- Increment SHA-256: `0a556ee174bbd47da7148e8ae8f999707482b8078b6fcabed553882fa015bea3`.
- Cumulative SHA-256: `c34dcc56ba6d8f7260e7d6eb0997a7dd016fd07de6e79d5a2424da574d6cf1bf`.

The actual Git tree comparison with reviewed tree `0fd5f5e6` changes only three
lines in `test_projection.py`: SQL strings selecting the rate column with limits
become `table(...).select("value").limit(...)`. Assertions, fixtures, strict casts
and invalid-data checks are unchanged. All runtime code, including the owned null
constructor, is byte-identical. This independently agrees with
`review-logs/performance/source-equivalence-v3.json`; the ownership assessment and
source verdict therefore carry to the new pin. Runtime equivalence of the two
Python planning routes is for the pending public gate to execute, not established
by this diff alone.

No new Research finding. No builds, tests or source edits were performed by this
role. The reported optimized probe is separate coordinator evidence; this note
certifies source identity and the reviewed test-only delta, not performance or
whole-workspace gate success. Saved-request and governance compliance remains
confirmed for this continuing review.

Recorded: 2026-11-06T03:22:33.624510+00:00


## Telemetry integration research before revised implementation

The `b67d1a94` candidate is superseded by a concrete integration gap: its new
physical projection exposes raw Projector metrics, but Sail's telemetry dispatcher
recognizes only DataFusion ProjectionExec. It also lacks the baseline output and
compute metrics supplied by that ordinary operator. This section recommends the
minimal repair; it is not a source verdict on the coordinator's ongoing edits.

Use a typed `StreamProjectionExec` case in the existing projection-emitter branch,
with an explicit `sail-telemetry` dependency on `sail-physical-plan`. The dispatcher
at `sail-telemetry/src/execution/metrics/mod.rs:77–117` already selects emitters by
operator type. ProjectionMetricEmitter recognizes `expr_N_eval_time`, maps its
`expr` label and partition to the registered expression metric, then chains to the
default emitter. DefaultMetricEmitter otherwise treats this named Time as unknown.
Generic name-based dispatch would avoid the new crate edge but expand the global
meaning of those names to arbitrary operators. The typed addition retains Sail's
existing ownership of metric interpretation and needs no new emitter or registry.

Ran only the read-only command
`cargo metadata --no-deps --locked --offline --format-version 1`, parsed its full
output in memory, and checked workspace reachability across every listed dependency
kind, including optional dependencies. Its output SHA-256 before the proposed edge
was `d3e2453c096f2826dffcb2d87cdf1d21d4dfd8d289d4ae9e16ce7997d4e6680f`.
There are 41 workspace packages. Physical-plan depends directly on cache, catalog,
common-datafusion and logical-plan; no transitive workspace path reaches telemetry.
The proposed telemetry-to-physical-plan edge is therefore acyclic in this metadata.
It adds nine reachable workspace packages to standalone telemetry: physical-plan,
cache, catalog, function, logical-plan, object-store, sql-analyzer, sql-macro and
sql-parser. This is a real build-dependency cost, not a runtime cycle or a new
external version requirement. Existing application crates already use both seams.

### Baseline metrics and async timing

Reuse DataFusion 55.2's public BaselineMetrics. Its implementation creates start/end,
elapsed-compute, output-row, output-byte and output-batch metrics. `record_poll`
records each successful batch through RecordOutput and marks EOF/errors complete.
RecordOutput counts encoded rows, including control rows. Output bytes can count
shared slice buffers repeatedly; they are not peak retained memory.

Keep exactly one owning BaselineMetrics instance for the executing stream. Every
clone's Drop calls try_done, so a temporary per-run clone can publish an end
timestamp while the stream still has work. For the existing try_unfold design,
keep the instance in stream state and record each successful output once; consuming
that state on EOF, error or cancellation drops it and records completion. An outer
record_poll wrapper is also sound, but must not additionally count those same
outputs. Borrow the baseline or clone only its Time handle for helper timing.

ScopedTimerGuard records all elapsed wall time from construction until stop/drop.
Never keep it across input.next().await or async invocation await. The smallest
scope measures synchronous marker construction, result assembly and Projector
calls in lexical blocks that contain no await. If helper work is included, time
each poll of that helper future and end the guard before returning Pending. This
records active polling time without counting suspended waits or downstream pauses.
Do not time the whole outer stream poll, which can include child execution.

The upstream AsyncFuncExec explicitly leaves elapsed_compute as a TODO at
`async_func.rs:228–230`; it is not a reference for complete async compute accounting.
Projector's existing per-expression timers cover the final mapped synchronous
expressions, not remote-service latency or the full async helper. Preserve those
semantics rather than relabel their values as async call duration.

Primary source is
[DataFusion 55.2 metrics](https://docs.rs/crate/datafusion-physical-expr-common/55.2.0/source/src/metrics/baseline.rs).
Independently matched `baseline.rs` and `value.rs` against the cached package:

| Artifact | SHA-256 |
| --- | --- |
| Package archive and Cargo.lock checksum | `f8c5c67aa252886f4d6b331c8114797f5b140464e774c4da36889269a1bf1bd8` |
| `metrics/baseline.rs` | `784eb8e45c1833cb0b69578b4fdf442412529bc703ac6867f36c51481c36c009` |
| `metrics/value.rs` | `9afd86d188b4349bcf0d56e5e8400f929f83736ec9618da00e02cd0f40a1b6b6` |

Relevant locations are baseline.rs:53–104,190–249,316–348;
value.rs:317–363; physical-plan/projection.rs:670–705; and the already pinned
physical-expr/projection.rs:928–967. No dependency code needs to be copied.

Use the existing MetricEmitterTester with a real StreamProjectionExec and an
in-memory exporter to cover typed dispatch, baseline names and expression names.
Check exact output counters for data/markers/empty output and ensure end_time is
unset after a yielded run with later work pending, then set at EOF/error/drop.
That lifecycle test discriminates premature clone destruction without relying on
timing thresholds. Verify timer scope through source and controlled-future behavior;
do not add a brittle real-time assertion as a substitute for separating poll time
from await time. New measurements and immutable qualification must include the
telemetry repair, since instrumentation can change cost.

Saved-request and governance compliance remain confirmed. No builds, tests, source
edits, dependency additions or remote mutations were performed by this Research
role. Workspace metadata execution is the only additional command beyond source
and evidence inspection. A new frozen source review remains required.

Recorded: 2026-11-06T03:37:02.588729+00:00


## Frozen cumulative verdict with projection telemetry

No unresolved Research source finding blocks the revised candidate. The missing
baseline and typed expression telemetry findings are closed by the inspected
implementation. This verdict applies to the following exact staged source;
whole-workspace runtime qualification and the updated cost comparison remain
separate evidence.

| Identity | Independently verified value |
| --- | --- |
| Starting HEAD | `06dd7e237eb5a343dcc6a6145e775f495e6c30de` |
| Upstream base | `b52144955b629314a000b1fe49eeea97fa3d0c5c` |
| Frozen index tree | `5a8f4f67535644e0cb8e4eb52389cfb4395bc3d9` |
| Increment SHA-256 | `e0ed57aa267daafbc6c4517a2712c4b1e9cbc050bf544bc62e4f7a1e9e4200f5` |
| Cumulative SHA-256 | `450642c939973266f80b2e7bcb52fe60dad7bc0f69fac5d733b9e18f34c77023` |

Verified all 58 cumulative file hashes against both working-tree bytes and staged
Git blobs, all 31 increment paths, the index tree, and independently regenerated
binary patches against both bases. No unstaged tracked change was present. The
comparison with previously reviewed tree `b67d1a94` contains only the seven expected
telemetry, dependency, test and Rustdoc files. Earlier cumulative runtime source
and the owned-null comparison are unchanged. Rechecked the final null source and
comparison hashes against their retained ownership receipt.

Read `STREAMSOURCE-PROJECTION-METRICS.md` and its before-code archive. The archive's
SHA-256 independently matches its receipt:
`a2b984babdf208e9880fa91b91646c08e44c9db303e78fc23711b8dacbd7b2a2`.
The final note correctly describes encoded-row counts and repeated counting of
shared buffers, distinguishes active polling from suspension, and explains typed
telemetry dispatch and its build-dependency tradeoff.

The implementation has one BaselineMetrics in the try-unfold stream state, with
no baseline clones. Every successful output invokes RecordOutput exactly once.
State ownership survives yielded runs and is consumed on EOF, error or cancellation,
so the baseline's Drop records completion at the stream lifecycle boundary.
The new lifecycle fixture explicitly checks that completion is unset before
polling and after an initial output, then set at EOF, error or destruction.
Its assertions use state transitions rather than duration thresholds.

Timer placement agrees with the pinned DataFusion API semantics:

- Boundary-scan timing starts only after input polling returns a batch.
- Marker/empty placeholder construction and synchronous Projector calls are timed
  in scopes that contain no suspension.
- Each async helper future poll has its own local timer guard. Returning Pending
  drops that guard before suspension; subsequent polls get new guards.
- Array conversion, augmented-batch construction and the final projection have
  separate synchronous scopes. The per-iteration conversion guard ends before
  the next async invocation. No compute timer survives an await suspension.

This measures elapsed time while actively evaluating or polling, not operating
system CPU accounting or remote-service latency. Projector's per-expression metrics
retain their existing mapped-expression meaning. The output-count tests match on
built-in MetricValue variants rather than sum_by_name, and retain exact expected
rows, batches and bytes. The positive-data exporter fixture executes a real
StreamProjectionExec and expects both baseline and expression metrics.

Typed dispatch now recognizes StreamProjectionExec alongside ProjectionExec and
uses the existing projection/default emitter chain. The only lockfile addition is
the existing workspace dependency. Re-ran read-only Cargo metadata with the same
locked/offline/no-deps command. Output SHA-256 is
`e176490697ad30bb0f33c01736409aaf5a5b8859a177a05f810b1f1464043c6f`.
The new edge is present, and physical-plan still has no transitive workspace path
back to telemetry. The earlier acyclicity analysis is therefore confirmed on the
actual revised dependency graph, not merely on a hypothetical edge.

Inspected the retained controls: disabling typed dispatch reports only the missing
expression-evaluation export; the earlier baseline control reports missing
baseline exports and no output-row counter. These are coordinator-run logs, not
executions performed by this reviewer. The reviewed fixture correction changes
how built-in metrics are read, without relaxing the exact expected counts. The two
schema Rustdoc changes qualify existing RecordBatch links and change no behavior.

Confirmed continued compliance with the saved request and governing instructions.
No builds, tests, source edits, commits or remote mutations were performed by this
role; only read-only metadata and source/evidence inspection were used. All Research
findings are closed for this source pin. Successful final runtime gates or acceptable
performance must be reported from their own pinned receipts, not inferred here.

Recorded: 2026-11-06T03:53:00.567066+00:00


## Frozen cost-repair source verdict

No new Research source finding. Verified the revised tree
`8b03aee0e5a6909b8b3f7aef085a525de1914b14`, all 58 cumulative file hashes against
both working files and staged blobs, the same 31 increment paths, and no unstaged
tracked diff. Starting HEAD remains `06dd7e237eb5a343dcc6a6145e775f495e6c30de`;
upstream base remains `b52144955b629314a000b1fe49eeea97fa3d0c5c`.
Independently regenerated both binary diffs:

- Increment SHA-256: `5fd32ec3258c10719cd2e1951846365d69a85199cfb19d8ef1cdfdba0f7f8d08`.
- Cumulative SHA-256: `4dd11e5232f1f1a326cf362c225854b0117f1154330260f323986203b778945d`.

The actual tree comparison with reviewed tree `5a8f4f67` changes only
`sail-physical-plan/src/streaming/projection.rs`. Reviewed that full delta and its
surrounding operator/lifecycle context. All other cumulative source and tests are
byte-identical, retaining the preceding Research coverage. The nullable constructor
and exact upstream-comparison hashes still match the ownership receipt.

Read the first-principles cost note and its before-code archive. The archive matches
SHA-256 `9b3943a961537c7a04832270e2fa27b8f9b36bf73b718a126a1c357e9ce64b3e`.
It correctly labels configuration cloning and separate timers as suspected costs,
without presenting them as proven causes or claiming this repair settles mixed-marker
batching. This review does not independently certify the note's performance ratios.

The refactoring preserves the timer and state contracts. `next_input` retrieves
pending input or awaits a new child batch before a timer exists; offset reset
occurs only for new input. The synchronous `next_run` retains the original cursor
and slicing logic. One timer now covers scanning plus synchronous projection or
placeholder creation. The async branch explicitly drops it before awaiting the
helper. Empty and marker-only runs stay outside user invocation. Configuration is
cloned for asynchronous data evaluation only. Existing per-helper-poll timers and
post-await synchronous timer scopes remain unchanged.

There is still one stream-owned baseline and one RecordOutput call per successful
output. Errors leave through the same consumed-state path; completion and cancellation
ownership are unchanged. Boundary scanning does not advance into later data before
returning an earlier marker. Typed telemetry dispatch, codec reconstruction,
metadata preservation, dependency acyclicity and nullable representation choices
remain as reviewed. No dependency ownership change is introduced by consolidating
these local timer scopes.

Confirmed continued saved-request/governance compliance. No builds, tests, source
edits or remote mutations were performed by this Research role. All Research source
findings are closed for this exact pin. Runtime gates and the repeated optimized
comparison must establish their own results; fewer timers alone is not a performance
verdict.

Recorded: 2026-11-06T04:02:53.756321+00:00


## Frozen direct-poll source verdict

No new Research source finding for frozen v7. This verdict supersedes the preceding
source pin; it does not establish runtime qualification or acceptable performance.

| Identity | Independently verified value |
| --- | --- |
| Starting HEAD | `06dd7e237eb5a343dcc6a6145e775f495e6c30de` |
| Upstream base | `b52144955b629314a000b1fe49eeea97fa3d0c5c` |
| Frozen index tree | `bb8699fdfbc4ca88fa6c0e816e189af80e560efd` |
| Increment SHA-256 | `9414d2b00491eedfd76e52e212459f92735963e46a6eb0d3c9f79b444e4693a2` |
| Cumulative SHA-256 | `7f2cf1d64419f8968e311f04b4b132bed8ee05e5e94be995dcf083b10dd9f8aa` |

Verified all 58 cumulative file hashes against both working bytes and staged Git
blobs, all 31 increment paths and the actual index tree. Independently regenerated
both binary patches; the retained cumulative-final-v7 patch has the same hash.
There was no unstaged tracked diff. Compared the cumulative candidate with reviewed
tree `5a8f4f67`: only `projection.rs` and `projection_metrics_tests.rs` differ.
Read their complete delta and final operator context. All other cumulative code,
tests, dependency wiring and ownership adaptations retain the earlier source review
coverage because their bytes are unchanged, including the foundation and standalone
Comet changes reviewed in the linked preceding evidence.

Read the current projection, marker-construction, metrics and cost plans. The
before-code direct-poll plan matches its recorded SHA-256
`ab5cddb8bcb35d9258495c456c45ed7a22dfbe2f6bacf05f464e8f32123efea4`.
It preserves instrumentation and explicitly leaves mixed-marker batching and measured
performance open. This role did not independently measure its reported ratios.

The synchronous stream now uses a public futures poll wrapper with an optional
owned ProjectionStream. At `projection.rs:168–194`, Pending leaves that state
intact. `poll_input` at lines 348–354 passes the caller's Context directly to the
child and consumes a retained batch before polling another input. Thus the child
registers the actual consumer waker; no additional wake service is introduced.
A successful run records output once. Projection errors, child errors and EOF take
and drop the state before returning. Subsequent polls return EOF, and dropping an
unfinished wrapper also drops its owned state. This releases the child, pending
batch and single BaselineMetrics without requiring the consumer to destroy an
already terminated stream. Output slices may still retain their own Arrow buffers,
as the plan explicitly allows.

The shared `next_run` retains the previous cursor and marker-boundary behavior.
Synchronous execution and async execution use the same extraction and evaluator
helpers. A marker is returned before later data is evaluated. Empty batches and
marker runs use fallible placeholders without invoking expressions. The sync timer
at lines 358–361 starts after child polling and covers scanning plus projection.
It cannot survive Pending because that path has no timer. The async branch drops
its scanning timer before awaiting evaluation, and each helper poll still owns a
separate local timer at lines 307–314. No BaselineMetrics clone or duplicate output
accounting was introduced. The existing typed telemetry export and dependency graph
are unchanged.

The new channel fixture independently exercises initial Pending, producer wake,
correct data after wake, an upstream error followed by buffered unread input, input
release while the outer stream still exists, completion accounting and repeated
EOF. Its weak-reference and closed-channel assertions check release directly; its
wake assertion uses a synchronous channel event rather than a duration threshold.
The pre-existing EOF, expression-error and cancellation checks remain intact.
This paragraph describes inspected assertions, not tests executed by this reviewer.

Rechecked the exact pinned helper semantics in the locally cached futures-util
0.3.34 primary source. Its `src/stream/poll_fn.rs:48–56` calls the supplied closure
on each poll and supplies no implicit terminal state; Sail's explicit Option is
therefore necessary. `src/stream/try_stream/try_unfold.rs:97–126` retains the future
on Pending, clears it on readiness, restores state only for a successful yielded
item, and remains terminated after EOF or error. This supports the preserved async
lifecycle and the equivalent explicit synchronous terminal behavior. Both inspected
files match the cached crate archive, whose SHA-256 matches Cargo.lock:
`0d50a92467f8ba5dd6e3ee5d4bd04d73ab2e4e1c44474a0674821dfce14b79bc`.
The file hashes are respectively
`35952ea514b8aade14a3934d7777006475f50bbf0c5b50141710e31637f980be` and
`aaf0f4857a4ec8233ac842ae509f29e5a210827a0bb40cfc0dc3e858f153d2b4`.
Re-read pinned DataFusion 55.2 BaselineMetrics Drop and RecordOutput contracts;
the single-owner lifecycle continues to satisfy them.

Public Projector, AsyncMapper and AsyncFuncExpr reuse remains appropriate within
the documented supported async scope. This direct polling change needs no modified
dependency implementation. The independently reviewed owned Arrow null constructor
and comparison still match their retained hashes, including nullable dictionaries
with empty values and checked nested capacity failures. No new ownership exception
or stronger type, recovery, cancellation or async-result guarantee is asserted.

Reread the saved full request and AGENTS.md, LAKESAIL.md, SHEHAB.md, CLARITY.md,
WRITING-RULES.md and applicable source instructions after compaction; confirmed
compliance. No builds, tests, source edits, commits or remote mutations were performed.
All Research source findings are closed for this exact frozen pin. Final gate and
performance evidence must supply their own receipts, including any unresolved
mixed-marker cost; this review does not infer their outcomes.

Recorded: 2026-11-06T04:12:05.785033+00:00
