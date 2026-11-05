# Exact Arrow types in streaming placeholders

Recommendation: retain Sail's type-specific constructors, fix decimals with
Arrow's fallible precision/scale builder, and construct run-end arrays from
validated `ArrayData` carrying the requested fields. Do not replace all
placeholder construction with a generic buffer algorithm. The defects have
different causes and need small, separately explainable repairs.

This is source inspection, not execution. No source edits, builds or tests
were performed by this Research task. The exact request and governing files
were read. The source checkout was clean when inspected at
`b52144955b629314a000b1fe49eeea97fa3d0c5c`, in
`/Users/alexy/src/sail/tmp/streamsource-build-20261105-b52144955`.

## Pinned dependency and source

The source checkout's `Cargo.lock` resolves `arrow-array`, `arrow-data` and
`arrow-schema` to 59.2.0. Inspected dependency files are under
`/Users/alexy/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f`.
The release has no `.cargo_vcs_info.json` in these local package directories;
the package versions, lockfile archive checksums and inspected file hashes
identify this review instead of an invented Arrow Git commit.

| Package | Lockfile archive checksum |
| --- | --- |
| arrow-array 59.2.0 | `bc9a4a4b2b5ecd0e04df03471661cb61f28bed3c7fd50994715129b01b2edb97` |
| arrow-data 59.2.0 | `723fe4aeed7604e00b9883a465af4ff0a0e6c44c03e41a68c3d1cbc403e0e44d` |
| arrow-schema 59.2.0 | `e6fed2ca0d1eade57e811cbe73b98ad50cc08a1183e13b2d2aa43a7df593f40e` |

Sail references below are to
`crates/sail-common-datafusion/src/array/placeholder.rs` at that commit.
Dependency references are relative to the registry root and include their
package version. The public [Arrow 59.2.0 source](https://docs.rs/crate/arrow-array/59.2.0/source/src/array/primitive_array.rs)
provides an optional release-pinned reference; local source was the principal
evidence.

## Decimal fidelity and the smallest repair

Sail lines 338–341 dispatch all four decimal widths to a generic primitive
builder. Lines 395–400 fill zero values but never apply the requested decimal
precision and scale. Arrow's builder therefore retains its type defaults.
This also affects nonnullable decimal children reached recursively.

There are three plausible repairs:

| Mechanism | What the pinned implementation does | Assessment |
| --- | --- | --- |
| `PrimitiveArray::with_data_type` or builder equivalent | Retains data and checks the primitive type family; decimal compatibility ignores precision and scale | Sufficient for exact valid metadata, but permits invalid decimal parameters and can panic for a wrong type family |
| `with_precision_and_scale` on a decimal builder or array | Preserves values while validating decimal parameters and setting the exact decimal type | Preferred narrow fallible repair |
| Generic `ArrayData::builder` with requested type and zero buffer | Preserves the declared type; ordinary data validation checks buffer layout, not decimal precision/scale validity | Adds lower-level responsibility without solving parameter validation automatically |

Arrow references: `arrow-array-59.2.0/src/array/primitive_array.rs:707–769,1637–1648`;
`src/builder/primitive_builder.rs:177–195,383–391`;
`src/types.rs:1405–1443`; and
`arrow-data-59.2.0/src/data.rs:977–1013,1486–1545,2222–2267`.

The fallible decimal helper can retain the existing zero-fill behavior and
builder allocation. It does not need to change the public generic primitive
helper or timestamp helper. Zero is representable at every valid decimal
precision, so changing metadata does not require rescaling nonzero values.
This reasoning concerns placeholders only, not a general decimal cast.

The validator rejects zero precision, precision beyond the width's maximum,
scale above the width's maximum, and positive scale above precision. Negative
scale is supported; it must not be rejected as malformed. Width maxima are
9, 18, 38 and 76 digits for Decimal32, Decimal64, Decimal128 and Decimal256.
See `arrow-schema-59.2.0/src/datatype.rs:357–404,869–899`.

## Run-end fields and empty arrays are a separate defect

Sail lines 356–379 call `RunArray::try_new`. Arrow's implementation at
`arrow-array-59.2.0/src/array/run_array.rs:118–143` creates new `run_ends`
and `values` fields, forces the latter nullable, and does not copy their
metadata. The type is therefore changed even when the value array is correct.
Sail also constructs a single run end equal to the requested length. At zero
length that is a run end of zero, which Arrow rejects.

Build the run-end child and value child, then use an `ArrayData` builder with
the original `DataType::RunEndEncoded` and explicit logical length. Its checked
`build()` validates the run structure before `RunArray<R>::from` or `make_array`.
The conversion preserves the supplied type at `run_array.rs:356–397`.
For length zero use two empty children, as Arrow's own null-array construction
does at `arrow-data-59.2.0/src/data.rs:757–763`. For a positive length use one
run and one value. Use checked conversion to the selected signed run-end width;
`length as i16` can wrap and silently change meaning.

Arrow requires a nonnullable run-end field of Int16, Int32 or Int64, equal
physical child lengths, and positive strictly increasing run ends. Sources:
`arrow-data-59.2.0/src/data.rs:993–1005,1246–1262,1684–1721`.
The [Arrow format](https://arrow.apache.org/docs/format/Columnar.html#run-end-encoded-layout)
also prescribes the names `run_ends` and `values`. Use those canonical names
with metadata and both value-nullability choices in standards-valid regression
cases. Arbitrary names accepted by an in-memory constructor are an optional
preservation check, not evidence of format compliance. The parent has no
validity bitmap; null runs are represented in its values child.

## Nested arrays and nullability

| Existing path | Source-derived fidelity consequence | Focused coverage |
| --- | --- | --- |
| List, list view, fixed-size list and large variants | Build with the requested parent type; nonnullable children recurse while nullable children use Arrow null arrays | Exact child type and metadata, nullable/nonnullable decimals, zero-length and positive-length parents |
| Struct | Keeps requested fields and creates one child per field | Field names, metadata, nullability and nested decimal/run-end children; zero-field struct length |
| Dictionary | `DictionaryArray::try_new` derives its type from actual keys and values | All signed/unsigned integer key widths and a nondefault decimal value type; fixing the value must fix the dictionary type |
| Sparse/dense union | Keeps supplied union fields, mode and IDs, but chooses its first field's placeholder | Nonzero/gapped IDs, both modes, nullable first child and nested decimals |
| Map | Builds with the supplied entry field and sortedness flag | Preserve those properties and decimal entry children; use valid nonnullable map entries |
| Timestamp and other primitives | Timestamp helper explicitly restores timezone; ordinary primitives have no decimal-style parameters | Preserve existing units/timezones and representative ordinary values without broad refactoring |

Sail references: lines 42–99,161–355,403–411.
Arrow dictionary construction: `arrow-array-59.2.0/src/array/dictionary_array.rs:288–319`.
Union validation: `src/array/union_array.rs:174–241`.

The helper's existing tests assert physical `null_count() == 0`, not that
every logical value is non-null. `NullArray` has zero physical null count and
all logical values null; a union or run-end array can select a nullable child.
Nullable nested fields may also legitimately hold nulls. Preserve that behavior
while fixing exact type identity. Do not strengthen the assertion to universal
logical non-nullness or replace existing nullable children with fabricated
non-null values. See `arrow-array-59.2.0/src/array/null_array.rs:26–43,117–127`.

## Valid-input boundary and tests needed now

For each existing supported type family, assert exact `array.data_type()`
equality, requested length and `array.to_data().validate_full()`, rather than
only physical validity. Arrow's `ArrayDataBuilder::build` calls nonrecursive
`validate_data`; full validation recursively checks children. It still does
not replace every type-specific validator. Definitions are at
`arrow-data-59.2.0/src/data.rs:1360–1392,2222–2267`.

The immediate discriminating cases are all four decimal widths with nondefault
precision/scale and negative scales; nested decimals; run-end metadata and value
nullability; empty run-end arrays; and Int16 run ends at 32767 versus 32768
and 65537. The last case is the stronger negative control: the old cast wraps
to positive one, whereas 32768 already wraps negative and is rejected by Arrow.
Exercise lengths zero, one and several rows, and the four marker kinds through
the encoding caller. Invalid decimal parameters must yield a useful error in
the changed decimal path. Invalid run-end types or nullable run-end fields
must not be silently converted to another valid type.

Do not confuse invalid types with absent coverage. Time32 only permits seconds
or milliseconds, Time64 only microseconds or nanoseconds; dictionary keys must
be integer; fixed-size widths cannot be negative. An empty union can represent
zero rows through Arrow's checked union constructor but cannot supply a value
for a positive-length marker. Sail currently refuses an empty union in all
cases. That pre-existing representability limit is not a reason to invent a
type or silently coerce one. Negative fixed-size allocation and general hostile
schema hardening are separate existing concerns unless the patch touches those
paths. No exhaustive arbitrary-schema safety claim follows from this unit.

## Upstream conventions

Read `.github/copilot-instructions.md`, `.github/instructions/dev.instructions.md`
and `.github/instructions/rust-review.instructions.md` in the pinned checkout.
Development guidance names nightly formatting, strict all-target/all-feature
Clippy, nextest and relevant pytest. It prefers BDD/Python for query and Arrow
behavior; Rust tests are reserved for internal utilities with straightforward
inputs and outputs. Constructor-level fidelity is that narrow utility case,
not a substitute for later real streaming-query coverage. Preserve existing
gold-file generation practices. New expression or plan nodes require cluster
codec support; this constructor repair does not require a new node.

The Test Case specialist received the focused cases and the distinction between
physical and logical nulls. The lead retains source ownership and decides the
increment's final scope. This report offers source-grounded implementation
choices; the cumulative patch and executed controls still require review.

## Inspected file hashes

Recorded: 2026-11-05T19:20:40.831334+00:00

Sail HEAD: `b52144955b629314a000b1fe49eeea97fa3d0c5c`.

| File | SHA-256 |
| --- | --- |
| `Cargo.lock` | `d0780bd83e5f9ebc5919982fee85c28a412aa644ab64a1153fe88210c1d7b5c6` |
| `crates/sail-common-datafusion/src/array/placeholder.rs` | `e7d1dfc125c0422d33577ae4d1bdbc605d94fa63c30f44d13bca4d32f4574d8e` |
| `.github/instructions/dev.instructions.md` | `461c4adbc50eb5fb8a66e52a484f69bc136bdc42d4d32838d6a35d6e07db152d` |
| `.github/instructions/rust-review.instructions.md` | `750d5bfe8b47f8a158401ca80a45d619d2be9b32321a2a9f30edef03cd21aba5` |
| `arrow-array-59.2.0/src/array/primitive_array.rs` | `36c0d618f16ea9bef08027ddc9261c611e007589c175ebc02a2e1f228ffb3ea3` |
| `arrow-array-59.2.0/src/builder/primitive_builder.rs` | `8732bf77608277b16e475e024889e14ec53dd0247b5f0aa556492dad23995a84` |
| `arrow-array-59.2.0/src/types.rs` | `0410e95297da4d0b02be3eb63499c851d5057e593b50c48af67f5f396b86155d` |
| `arrow-array-59.2.0/src/array/run_array.rs` | `b0624a3937b706b52238c4621c84769bf5bb30ad046f3255e2f97dc924ba8737` |
| `arrow-array-59.2.0/src/array/dictionary_array.rs` | `27bc3a27f3fe2819c4d81d390557f48d4fcfb1ee879c5b8aa4d58cd4de85e950` |
| `arrow-array-59.2.0/src/array/union_array.rs` | `8aebb3984b8c66cbebc282e8de2d20e36e39fc3d54f70a7caed5d34fd231f3c9` |
| `arrow-array-59.2.0/src/array/null_array.rs` | `43765935e2b5ef4239aae75f99386f7728eec8b3ea8d6d67848ad0c76cf1e3cf` |
| `arrow-data-59.2.0/src/data.rs` | `456e411ac7f3610fdf50ac1b1173f960fe62ac1338d18a81cba561d622b1024b` |
| `arrow-schema-59.2.0/src/datatype.rs` | `641a04897876b1d2be8f574b4ca245ca4fc62a4ff710e7f224630e5229c3dfb0` |

## Cumulative code review: fidelity and filter isolation

Research verdict: no must-fix finding in this inspected code scope. This is a
source review of the current worktree, not the later immutable acceptance
candidate or a test-run verdict. No builds or tests were executed by this
reviewer. The prompt and applicable governance remain confirmed.

Recorded: 2026-11-05T19:41:31.893534+00:00

Baseline: `b52144955b629314a000b1fe49eeea97fa3d0c5c`. The path-scoped cumulative diff covering the eleven files below has SHA-256 `1f9e9719eaaf597bc5072f21181977c554fe2866e7ba86d73c5970ef2aadcef7`, computed from `git diff --no-ext-diff <baseline> -- <listed paths>`.

The decimal change uses the checked Arrow precision/scale builder and leaves
ordinary primitive and timestamp construction intact. It preserves zero values
and rejects malformed parameters in the changed decimal path. Run-end arrays
now use the original fields, checked length conversion, empty children for empty
arrays, and validated ArrayData before make_array. These choices agree with the
pinned constructor contracts above and do not rely on unchecked reinterpretation.

Explicit RecordBatch row counts preserve zero-column decoder and rate-source
rows. Arrow 59.2.0 `arrow-array/src/record_batch.rs:324–365` uses the supplied
count and still checks every nonempty column against it. Its slice at
`:681–696` carries the slice length even without columns. Schema conversions
retain schema metadata while preserving existing fields. The rate regression
uses actual SQL constant projection and an empty DataFrame projection.

The filter classifies rows using the encoded marker column's validity, evaluates
only contiguous data spans, and forwards marker spans unchanged. The lazy
iterator exposes an earlier marker before evaluating later data that may fail.
A failing data span drops remaining spans from that input batch. All-data and
empty-data batches retain one kernel call. This changes mixed-batch grouping at
control boundaries deliberately; it does not claim to preserve batch-sensitive
user-function behavior across arbitrary transport regrouping.

Pinned DataFusion 55.2.0 `datafusion-physical-plan/src/filter.rs:1229–1261`
evaluates the predicate once, expands scalar results to the input row count,
and calls Arrow's record-batch filter. Arrow 59.2.0
`arrow-select/src/filter.rs:225–245,257–272,445–464` applies one selection to all
columns, treats null predicates as unselected and preserves schema and selected
row count. Thus payload and retraction columns stay aligned without reevaluating
the predicate. Existing encoded-schema column indices remain valid on slices.
The existing StreamFilter codec path remains applicable because no new plan
node or serializable field was added.

Fixture inspection found valid sparse/dense union IDs 3 and 7, canonical map
entry fields, and canonical run-end fields with metadata and both value-nullability
choices. Huge run-end logical lengths exercise O(1) run storage and reject
conversion before allocating child values. The 65537 case distinguishes the
old positive Int16 wrap. Assertions correctly use physical null counts and exact
types. The matrix covers every type family, not every parameterization or every
malformed recursively constructed schema.

The ownership tests observe original ArrayRef wrapper release and absence of
pending input. They do not measure all backing buffers: downstream slices can
legitimately retain shared storage. Source inspection confirms the iterator
releases its extra parent reference once consumed or failed. No memory envelope
or throughput claim follows from those tests.

Remaining limits: this unit does not repair arbitrary projections, qualify
optimizer changes or distributed marker alignment, or establish durable success
and error propagation for the whole pipeline. Follow-up failure-propagation
changes were still being developed and are excluded from this review. Reported
pass counts and controls must be tied to their owner's execution receipts;
this review does not promote those reports into a fresh execution.

| Reviewed file | SHA-256 |
| --- | --- |
| `crates/sail-common-datafusion/src/array/mod.rs` | `bce6749f4895179583287010b3fba73301f886c1b7baa39bbb65415464224049` |
| `crates/sail-common-datafusion/src/array/placeholder.rs` | `2ed82d062db98e872a8afeba0e2c808f149948c2a0706bfad8c8afabd599e697` |
| `crates/sail-common-datafusion/src/array/placeholder_tests.rs` | `76f54e7df915d13c1b664e3b80065bf5af02e952ac49423f2e16f6f191aeb877` |
| `crates/sail-common-datafusion/src/streaming/event/encoding.rs` | `937681e508bb13e5e418ae9fdfaa7fb2c89cebe2d99745181331e580dffc7dc4` |
| `crates/sail-common-datafusion/src/streaming/event/encoding_tests.rs` | `681461d8bcf1fb9dad9ddede4c4700df401da37b40be37b7d7ac38ad126873d9` |
| `crates/sail-common-datafusion/src/streaming/event/mod.rs` | `f2a07810554e76f96f8e5a982512c103acd498dbfb379686ac034c904dc523bc` |
| `crates/sail-common-datafusion/src/streaming/event/schema.rs` | `cd3adf9a96432d4fc2bd48bc1ad106e1acbc67ad7edf5d79e1c3c9d10eb82493` |
| `crates/sail-data-source/src/formats/rate/reader.rs` | `a91d82e2ab0b253d15283020806ae0242a392afff58354153429aad214442a09` |
| `crates/sail-physical-plan/src/streaming/filter.rs` | `3801504f5407a51bc1790c5e0c20e40867cd72daa155a252a7c63767fcb8196e` |
| `crates/sail-physical-plan/src/streaming/filter_tests.rs` | `ab1748fc3d7388cabe2f3a9b96c10f634a49173c7db350a3ab09749dc6ebacbe` |
| `python/pysail/tests/_dev/spark/datasource/test_rate.py` | `4e5b9f749b2e4b408f652a3e1b0b8f829ee67fdfb9709fda5a59d5062612b391` |


## Cumulative code review: failure lifecycle and Connect protocol

Research verdict: no must-fix finding in the reviewed cumulative nineteen-file
patch. This source/API review covers patch SHA-256
`6782613a31c5278296421622c5a5fcea918603506a70de62c0f77671fa0f3376`
at `review-logs/cumulative-four-design-notes.patch` in the implementation
worktree, against `b52144955b629314a000b1fe49eeea97fa3d0c5c`.
All nineteen worktree files matched the patch's resulting Git blob prefixes
when inspected. The worktree HEAD still named the baseline; an immutable
candidate and its execution gates remain a separate acceptance step.

Confirmed rereading of the complete build request, referenced engineering
request, AGENTS.md, LAKESAIL.md, SHEHAB.md, CLARITY.md and WRITING-RULES.md
following compaction. Also reread the applicable upstream development and Rust
review instructions and the failure-propagation and error-protocol decision
notes. No builds, tests, source edits, installations or external posts were
performed by this reviewer. Previously reported test counts and negative
controls are not fresh executions by this review.

### Arrow fidelity and filter assumptions

The previously reviewed decimal, exact run-end type, metadata and zero-column
row-count fixes remain valid against Arrow 59.2.0. The final run-end construction
checks integer conversion before allocating value children and uses the original
DataType with a checked ArrayData builder. Arrow's `arrow-data/src/data.rs:993`
also rejects nullable run-end fields. The changed implementation does not silently
replace an invalid run-end type with a valid one. It does not establish exhaustive
safety for arbitrary invalid nested schemas.

The filter's new direct polling path checks the marker array and invokes the
existing kernel once for an all-data batch, including zero rows. It introduces
no per-batch predicate clone or mixed-batch iterator on that path. The local
batch leaves scope before the poll returns. This is an ownership observation,
not a measured memory or throughput result. The integrated predicate-count tests
exercise the direct path; the explicit weak-reference tests exercise the helper
iterator, not all backing buffers or the direct path's ownership independently.

For mixed batches, marker spans bypass expression evaluation and data spans
preserve encoded column indices. Pinned DataFusion 55.2.0
`datafusion-physical-plan/src/filter.rs:1229` evaluates once, expands scalar
predicates to the input row count and calls Arrow filtering. Arrow 59.2.0
`arrow-select/src/filter.rs:225,445` constructs one selection and applies it
to every column with the original schema and selected row count. That supports
payload/retraction alignment without duplicate predicate evaluation. Markers
preceding a failing span can be emitted first; remaining spans in that input
batch are discarded. The consumer must stop after an execution error, as the
repaired query runner now does. Arbitrary projection isolation, distributed
alignment and batch-sensitive user functions remain outside this proof.

### Terminal state and sink errors

`StreamingQueryState::Stopped(Option<SparkThrowable>)` publishes the stopped
flag and retained cause as one watch value. Status, exception lookup and waits
read that value; the query task returns on its first stream error. This removes
the previous split-publication state and later-error overwrite. It is not a
transactional snapshot across different queries.

Tokio 1.54.1 `src/macros/select.rs:640–749` owns the branch futures in an inner
scope and drops that scope before executing the selected handler. Here both
branches own their futures, so the input future is dropped before the terminal
`state.send`. The drop-observer test directly checks that boundary for error,
end of stream and explicit stop without a timing assumption. This demonstrates
release of the owned stream, not synchronous completion of arbitrary external
work triggered by a stream's destructor.

Tokio `src/sync/watch.rs:907–958` checks the current value before waiting and
retains access to the final value after sender closure. `send` at `:1082`
can fail only when no receiver remains; retained query/await handles are
receivers. The code drops the `wait_for` read guard before taking its final
borrow and does not hold watch guards across await points. Query wait timeout
and manager completion paths recheck retained failures. Manager waits inspect
their existing snapshot of query handles; concurrently registered queries and
a total order among several failures are not established. Reset excludes
already stopped queries from subsequent manager snapshots while preserving
individual failures.

Tokio `src/task/join_set.rs:591` aborts tasks when the JoinSet is dropped.
These tasks own only cloned wait receivers. Timeout or successful completion
of a manager wait therefore cancels redundant waiters, not the query runner.
The existing treatment of a closed running-state channel as termination remains;
query-task panic supervision is explicitly deferred. Explicit stop racing a
ready error still follows select's branch selection, rather than a new
cancellation taxonomy.

The console sink now uses fallible source reads, formatting and writes. Futures
0.3.34 `src/stream/once.rs:42–54` drops its one future after producing the result;
`src/stream/try_stream/try_filter_map.rs:62–87` forwards an error and suppresses
the successful unit value. Thus its first failure becomes one execution-stream
error, followed by exhaustion, without consuming later input. The fixtures cover
source and formatter failures plus writer failures in the header and body.

### Spark Connect source contract

The Spark checkout is pinned at
`617618396087429b5627a86ce933bb0f5d6645cb`, version 4.2.1. Files omitted by its
sparse checkout were read from the pinned Git object, not inferred from absence.
Its [Python query reader](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/python/pyspark/sql/connect/streaming/query.py#L152)
removes the first `: `-delimited class prefix. Its
[server](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/connect/server/src/main/scala/org/apache/spark/sql/connect/planner/SparkConnectPlanner.scala#L3733)
sends `toString()` and `getCondition`; the
[exception implementation](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/common/utils/src/main/scala/org/apache/spark/sql/streaming/StreamingQueryException.scala#L101)
provides that class prefix. Sail's helper now supplies the prefix while preserving
the whole retained cause, including delimiters, Unicode and an empty message.
Its condition field comes from existing structured condition metadata, not the
Java class name. Current retained streaming exceptions have no recorded condition,
so absence is accurate. This does not supply Spark debug offsets, stack traces,
message parameters or complete structured-error parity.

Spark's [execution wait](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/core/src/main/scala/org/apache/spark/sql/execution/streaming/runtime/StreamExecution.scala#L609)
and [manager wait/reset](https://github.com/apache/spark/blob/617618396087429b5627a86ce933bb0f5d6645cb/sql/core/src/main/scala/org/apache/spark/sql/classic/StreamingQueryManager.scala#L113)
support retained failure propagation and reset's manager-specific role. These are
source findings. The Rust protobuf fixture mirrors the delimiter boundary;
the mocked Python fixture invokes the actual client parser; the live-query
fixture covers the server/client path. Inspection of those tests does not
establish that they passed on this candidate. Normal stream exhaustion also
remains distinct from checkpoint-qualified durable completion.

Recorded: 2026-11-05T20:13:53.214923+00:00

Additional inspected dependency sources:

| File | SHA-256 |
| --- | --- |
| `tokio-1.54.1/src/sync/watch.rs` | `034e6769c20b5d053dac6b043fed3bab0b29e6c804ab0bb2a18ed687707ae53b` |
| `tokio-1.54.1/src/macros/select.rs` | `a1f6cb8d20a378653f2dda59d7137567b07896d76051c19e471812aab86e5229` |
| `tokio-1.54.1/src/task/join_set.rs` | `421b2f5af3e877a85fdd8920688f10e05e62cd75d2149c7db997277ffbf3074e` |
| `futures-util-0.3.34/src/stream/once.rs` | `d7b70adabad1f10af711ac3dcef33fd4c287e9852fdb678406e7ff350ba8fd47` |
| `futures-util-0.3.34/src/stream/try_stream/try_filter_map.rs` | `285e7ea875a3ea3e16942c1b1acae5a1cb26b9bac476dce3903547cb99306602` |
| `datafusion-physical-plan-55.2.0/src/filter.rs` | `17ea47712265b2c25d33328a00aaae7b0a3b24a1d994c0f24905296f14342c0b` |
| `arrow-select-59.2.0/src/filter.rs` | `0e2649261b037357eb7ab78887ef3346efc322a73b4699627af98623ee382dc7` |


## Final cumulative source review: reporting costs

Research verdict remains no must-fix finding for the final nineteen-file patch
SHA-256 `bda65fdba075378f3088a2b00681fdf63f57b9d9a66722ec78c8e1f688220163`,
`review-logs/cumulative-final.patch`, against the same baseline
`b52144955b629314a000b1fe49eeea97fa3d0c5c`. All nineteen current source files
match the resulting blob prefixes. The three changed files since the preceding
review are captured in `review-logs/failure-reporting-cost-fix.patch`, SHA-256
`73baa58870461a4b5143a97d24145a5dc86d896e51338a5e42da7075499587f1`.
HEAD at this inspection is `2c9fa84994d317aade0d1c69faa9a378c780127d`;
the matching committed diff had not yet been independently verified at this step.

The console change completes both Arrow formatting and Display rendering to an
owned String before acquiring stdout's lock. Arrow 59.2.0
`arrow-cast/src/pretty.rs:61–64,128–134` returns a Display object; merely moving
its construction before the lock would leave rendering inside the critical
section. The explicit `to_string()` avoids that mistake. The lock now covers
only the partition/batch header and already rendered body, preserving their
contiguity and propagating either write failure. Formatting still precedes
any output and its returned errors still propagate through the sink stream.
The literal helper fixtures now isolate writing; the separate execution fixture
still checks an actual Arrow formatting error. No throughput or lock-contention
measurement was executed by this reviewer.

Active-query listing now borrows each query's state once, excludes Stopped
values, and constructs a status only for included queries using that same borrow.
It avoids allocating inactive query names/messages and preserves each returned
status's consistency with its inclusion decision. The helper does not reborrow
the watch state or hold its guard across an await. This does not create a global
snapshot across queries; the preceding lifecycle and snapshot limits still apply.

Reviewed the complete delta and surrounding final code. No source edits, builds
or tests were performed; only this evidence appendix was written. Prompt and
governance compliance remains confirmed from the preceding reread. Reported
pre-delta gates are not acceptance evidence for this final hash. Immutable
candidate qualification and affected final tests remain the lead's separate gate.

Recorded: 2026-11-05T20:24:26.863422+00:00

Additional inspected source: `arrow-cast-59.2.0/src/pretty.rs`, SHA-256 `04958cbdc3850ed2fd8e16c06b631da947ac377442eec00f42b8f0f0defad7a7`.


## Immutable source-pin confirmation

Verified HEAD `2c9fa84994d317aade0d1c69faa9a378c780127d`, tree
`5d67cdc81cdd9ba7eb18a74eda17d84b9e5d30c7`, and clean tracked source in the
implementation worktree. `git diff --no-ext-diff` from baseline
`b52144955b629314a000b1fe49eeea97fa3d0c5c` to that commit has SHA-256
`bda65fdba075378f3088a2b00681fdf63f57b9d9a66722ec78c8e1f688220163`, exactly
the reviewed final cumulative patch. The no-must-fix Research source verdict
therefore applies to this immutable commit and tree. Corrected the preceding
unsupported statement about whether HEAD contained the cost delta: the committed
diff now verifies that it does. No builds or tests were run by this reviewer;
this confirmation is not a workspace gate-pass claim.

Recorded: 2026-11-05T20:32:02.306051+00:00
