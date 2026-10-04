# Struct MIN allocation investigation

The pinned DataFusion 55.1.0 implementation already specializes grouped struct
MIN. The generic per-group boxed-accumulator hypothesis is false. Its specialized
state nevertheless retains an owned singleton Arrow struct per populated group,
and the isolated allocation probe measured substantial overhead for the exact
`Struct<Float64, Int64, Int64>` used by Pecan.

This is an allocation result, not proof that this operator caused the logged
scale-24 OOM. The probe excludes group keys, joins, shuffle, parallel tasks,
spilling and the Sail process allocator. All runs here used the shared arm64
macOS laptop, Rust 1.97.1 and the System allocator. Times in the raw receipts are
exploratory microbenchmark observations, not production speedup claims.

## Source and representation

The unchanged DataFusion source is
`datafusion-functions-aggregate-55.1.0/src/min_max/min_max_struct.rs`, SHA-256
`af016c06b87e81c554f059abc8b20f1f3a279625a8b3941081bea99137dc8e17`.
`min_max.rs:518–548,630–632` selects this specialized accumulator for structs.
The struct implementation stores `Vec<Option<StructArray>>` at line 161,
deep-copies a winning singleton at lines 193–205, allocates a locations vector
over all resident groups each batch at line 227, slices each input row at line
235 and scans those locations at line 257. Evaluation at lines 110–123 creates
per-group ArrayData and a MutableArrayData while the singleton owners remain
live. Its size report at line 293 uses logical vector length and Arrow's array
memory report, omitting retained vector spare capacity and temporary buffers.

The [singleton layout probe](min-struct-probe/examples/layout.rs) directly
measured **1,912 requested heap bytes** for one owned copied singleton, excluding
the input and the 104-byte stack StructArray. Its retained allocations were
three each of 56, 64 and 112 bytes, and one of 1,216 bytes. Arrow reported 584
bytes. The copied child ArrayData vector had length 3 and capacity 9.
The source conversions through `Vec<MutableArrayData>` (408 bytes per item),
`Vec<ArrayData>` (136 bytes per item), and the StructArray field vector explain
the large retained backing allocation; that capacity propagation is a
source-supported inference, rather than inspection of the private field
vector. See [layout output](min-struct-probe/layout.json) and its
[receipt](min-struct-probe/layout-receipt.json).

## Exact-source comparison

Both source files were copied unchanged into an isolated standalone Rust probe.
The candidate's expected `datafusion::{arrow,common,logical_expr}` imports were
provided by re-exports of the pinned crates, without compiling the whole Sail
server. This tests the kernel, not wrapper/planner/codec integration.

Candidate kernel SHA-256:
`ddc251c6a9cb5aaa155b216e2554d0dddcd440ec1f99fda416d394cb5127fdcd`.
The [snapshot](min-struct-comparison/candidate-snapshot.rs) matches the live Sail
kernel when the final receipt was generated. It stores each group's three
values and validity bits inline in 32 bytes and emits bulk Arrow arrays. Its
size report includes allocated group-vector capacity and fixed schema/instance
overhead; after emitting all groups the observed fixed charge is 426 bytes.

The probe used 1,000, 10,000 and 100,000 groups with 8,192-row batches. Both
implementations received the same inputs and checked the final output. At
100,000 groups:

| Measurement | DataFusion original | Compact candidate |
|---|---:|---:|
| Retained requested bytes after first update | 204,831,488 | 4,194,304 |
| Accumulator-reported size | 68,800,000 | 4,194,730 |
| First-update allocations | 5,000,109 | 70 |
| Repeated identical update allocations | 1,800,104 | 65 |
| Repeated identical update temporary peak bytes | 10,401,232 | 504 |
| Repeated improving update allocations | 5,600,104 | 65 |
| Repeated improving update temporary peak bytes | 13,548,800 | 504 |
| Emit-all temporary peak bytes above prior live allocation | 84,852,196 | 2,400,000 |
| Emit-all allocations | 800,061 | 14 |
| Process lifetime peak RSS, separate processes | 413,171,712 | 18,759,680 |

The dense Arrow input control retained 2,401,010 requested bytes. The compact
group vector had capacity 131,072, accounting for its 4,194,304 bytes. Its
remaining per-batch allocations in this driver are input-wrapper allocations.
Requested allocation sizes are not allocator usable sizes or RSS. The observed
retained-state reduction is about 48.8-fold in this specific probe; multiplying
that ratio into whole-query memory would be unsupported.

All sizes, allocation counts, phase timings and outcomes remain in
[original results](min-struct-comparison/original-100000-groups.jsonl) and
[candidate results](min-struct-comparison/compact-100000-groups.jsonl), with the
1,000/10,000-group cells and per-cell receipts beside them. The
[build/gate receipt](min-struct-comparison/gate-receipt.json) identifies source,
binary, lockfile, compiler, detached worktree and its base commit. That base
commit does not contain the uncommitted probe snapshot: the source hashes are
the verdict's identity.

## Update work as resident groups grow

For this fixed three-field type, the original update initializes a locations
vector of length `G_b` and scans all of it on every batch `b`, where `G_b` is
the current resident group count. Those two passes add `O(sum_b G_b)` work to
the input-row comparisons. This is source-level work accounting, not a
measurement of cycles or elapsed time. When every row introduces a distinct
group, batch size is fixed at `B`, and `N = mB`, the sum is
`B*m*(m+1)/2 = N²/(2B) + N/2`. The additional work can therefore grow
quadratically in input rows for that schedule. With bounded resident groups it
instead scales with batches times that bound.

The compact update visits input rows and initializes only newly added inline
groups. Between emissions, with monotonically growing group count and the
fixed three-field comparison, vector growth is amortized and update work is
`O(rows + groups)`. It has no full resident-group scratch scan. Prefix emission
and output have their own costs; this statement excludes them, group-key hash
assignment, joins, shuffle and all other query operators. It is not a
whole-pipeline or cluster-scaling claim.

The existing probe's input schedule gives these analytic counts; no additional
timing campaign was run:

| Distinct groups / rows per phase | Batches | Original first-update entries, per locations pass | Original repeated-update entries, per locations pass | Compact newly initialized groups, first / repeat |
|---|---:|---:|---:|---:|
| 1,000 | 1 | 1,000 | 1,000 | 1,000 / 0 |
| 10,000 | 2 | 18,192 | 20,000 | 10,000 / 0 |
| 100,000 | 13 | 738,976 | 1,300,000 | 100,000 / 0 |

Both implementations also visit the listed input-row count each phase. The
original entries column applies separately to initialization and the later
scan; it is not an allocation count. The
[arithmetic receipt](min-struct-comparison/update-work-analysis.json) records
the exact batch boundaries and source hashes. See the unchanged original
`min_max_struct.rs:227,257`, candidate snapshot `update_batch`, and probe driver
`update` for the loops that establish the count.

## Semantic checks and existing oracle limits

The independent [differential tests](min-struct-comparison/tests/differential.rs)
passed **4 tests, 0 failed, 0 ignored**. The final
[log](min-struct-comparison/differential-final.log) and
[receipt](min-struct-comparison/differential-final-receipt.json) supersede the
earlier two-test log without changing the allocation driver or kernel.
Coverage includes 64 seeds × 12 randomized batches, root and child nulls,
false/null filters, bit-exact floating outputs including NaN payloads and signed
zero, extreme signed integers, first-tie behavior, state/merge, prefix emission,
all-unseen groups and field metadata/nonnullable children.

DataFusion's `partial_cmp_struct` skips a child comparison unless both values
are valid; this is not a generic NULLS FIRST/LAST rule. Arrow comparisons use
floating total order. The compact implementation preserves these rules and
keeps the incumbent on a complete tie. It does not change the controller's
separate dominated-overflow rejection contract.

Two pre-existing oracle limitations were retained as explicit controls:

- Original `EmitTo::First` subtracts row counts from a byte counter at lines
  280–287. After emitting half of 100,000 singleton groups, it reports
  63,550,000 bytes instead of 34,400,000 under its own remaining-live formula.
  The compact implementation charges retained vector capacity, so a prefix
  emission need not lower its reported size.
- Original empty `evaluate(All)` and `evaluate(First(0))` panic while constructing
  MutableArrayData from zero sources. The candidate returns a typed empty
  array. This is additional empty-input support, not preservation of a panic.

Read-only wrapper review found no discrepancy in scalar/sliding/unsupported-type
delegation. Full Sail compilation, codec roundtrip and production integration
belong to separate gates owned by the integrating agent; this document does
not replace those verdicts. No registry source was modified.
