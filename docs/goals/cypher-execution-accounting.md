# Execution accounting required for automatic routing

Status: implementation design, 2026-09-14. Extends
[the automatic execution goal](cypher-datafusion-execution.md); no completed
policy mapping or performance improvement is claimed here.

## Observed boundaries

`PreparedReadRequest` owns the admitted AST, parameters, policy and absolute
deadline. The reference executor installs its execution context through a
thread-local stack in `read_budget.rs`. That stack cannot carry limits through
asynchronous DataFusion partitions. `ExecutionContext` already supplies owned,
shared work charges, cancellation and memory reservations.

The reference intermediate limit is cumulative for ordinary bounded reads;
`read_budget_live.rs` separately supports lexical live-memory accounting.
DataFusion's retained-memory pool is a third boundary. Equating those counters
would silently change the caller's contract.

`collect_result` checks rows before decoding and exact JSON output size before
appending, but `decode_result_batch` already owns strings and vectors by then.
Thus output-byte admission alone does not admit materialization. Likewise, a
stream wrapper charging emitted batches cannot account for join candidates
that were inspected and discarded inside an operator.

## Implementation sequence and invariants

1. Admit portable result materialization before copying. Derive checked charges
   from the actual sliced Arrow arrays, null positions, string lengths, column
   names and row/value containers. Share type validation with decoding so the
   admitted representation cannot diverge. Unsupported types fail before row
   allocation. Keep logical-copy accounting distinct from allocator capacity.
2. Carry one execution-owned context from prepared request through input
   capture, planning, operators and consumption. Reuse the original absolute
   deadline; never construct a fresh budget per partition or fallback route.
3. Instrument candidate work before provider scans, joins and expansions, and
   cumulative copies before creating intermediate values. Optimizer rewrites
   must preserve accounting coverage. Unknown operator coverage must prevent
   automatic admission, even if its outputs have a bounded row count.
4. Bind route eligibility to snapshot/provider authority, supported semantics
   and every requested policy field. Preserve semantic errors and execution
   failures; only a pre-execution unsupported outcome may choose another route.
5. Qualify route costs using end-to-end measurements including capture and
   output materialization. Existing prepared-query profiles cannot establish
   those thresholds.

Tests must cover inclusive limits and one-unit excess, sliced UTF-8 buffers,
null versus empty strings, overflow before allocation, shared charges across
partitions, cancellation during pending input, errors without replay, and
optimizer plans whose rejected candidates exceed emitted rows. Independent
small-graph oracles remain required. A result-decoder test alone does not prove
full execution-budget coverage.

## Capture allocation lifetime inspection

`GraphSnapshot::try_new` creates eight logical bytes of relationship identity per
edge in `with_ordinals`. `nodes()` and `edges()` return independent DataFrames,
and planning may retain providers after the snapshot handle is dropped. A
reservation stored only on `GraphSnapshot` would therefore be released too
early. A token on a provider alone is also insufficient if an emitted Arrow
batch survives that provider through a consumer or C Stream handoff.

Admission for added buffers must follow their actual final owner. Before adding
a capture-budget API, establish a buffer-owner mechanism that survives Arrow
array slicing, record-batch cloning, provider removal and exported readers.
Reserve checked bytes before ordinal allocation, retain the token with the
allocated buffer, and release it only when its last owner disappears. Existing
input buffers remain caller-owned unless an explicit ownership transfer admits
them separately. Do not charge a copied snapshot handle as a new buffer.

Qualification must retain a result batch beyond snapshot/provider/stream drop,
then verify that admission remains charged until the last array slice drops.
Cover cancellation during construction and errors after one batch allocates,
plus empty graphs and a one-byte-short ordinal budget. This lifetime proof is
separate from cumulative portable-copy accounting and serialized input size.

The existing algorithm `ArrowResultBatch` retains a reservation beside its batch,
with an explicit caller obligation when cloning raw arrays independently. That
wrapper is useful for controlled consumers but cannot establish the stronger
buffer-lifetime guarantee required above. Do not silently broaden its claim.

The locally resolved Arrow 59 `Buffer::from_custom_allocation` provides an
allocation-owner hook. A reusable adapter could own an immutable existing Buffer
and a reservation together, then expose exactly that buffer's valid byte region
through the custom owner. Keeping the original Buffer alive preserves address,
alignment and storage lifetime without copying data. This needs a narrowly
reviewed unsafe constructor: derive pointer/length from the owned buffer, expose
no mutation, handle empty buffers, and retain ownership across slices and FFI
release. First qualify the shared mechanism across enabled Arrow majors before
using it for capture ordinals or algorithm batches. The source inspection is a
design lead, not an implemented or verified safety claim.
