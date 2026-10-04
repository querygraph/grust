# Ordered Int64 LAST_VALUE allocation probe

Recorded: 2026-09-30T18:47:25.987263+00:00.

This is a bounded component measurement of the public DataFusion 55.1.0 grouped
`last_value(Int64 ORDER BY Int64 DESC NULLS FIRST)` implementation, with Arrow
59.3.0. It is conditional on the source-derived Sail `min_by` rewrite described
below. No optimized Sail plan was captured, no remote workload was launched, and
these results do not establish WCC query memory, throughput, or a stream-loss
cause. Shared-laptop elapsed times remain exploratory raw fields; there is no
performance comparison or speedup claim. A later, separately recorded
[Linux worker control](../wcc-fused-worker-plan/README.md) now confirms the
ordered LAST_VALUE route for Pecan's production representative expression.
Its source bridge and exact task assignments do not turn these component
allocation measurements into whole-query memory measurements.

## Source route and scope

At Sail `b569e75de625885b3d919fa4196b2e0bed14c618`, Pecan
`wcc_fused.py:17–26` groups by vertex and computes `min_by(neighbor, priority)`
alongside `min(priority)`. The relevant inputs are Int64.
[The copied Sail implementation](upstream/sail-max_min_by.rs) at lines 263–288
rewrites the former to ordered LAST_VALUE with descending, nulls-first priority
and `priority IS NOT NULL` as a filter. Sail's default optimizer includes
DataFusion's expression simplifier; the simplifier invokes the UDAF hook.

[DataFusion's exact source](upstream/first_last.rs) at lines 199–236 supports the
grouped implementation when an ordering is present and the value type is Int64;
lines 1143–1151 delegate LAST_VALUE to that factory. Lines 79–123 dispatch to
`FirstLastGroupsAccumulator<PrimitiveValueState<Int64Type>>`. The
[probe constructor](src/main.rs) uses this public factory and checks grouped
support. It does not use Sail's generic scalar `MaxMinByAccumulator`.

The compact MIN patch does not affect this expression: Sail's compact MIN
recognizes exactly `Struct(Float64, Int64, Int64)`; this expression rewrites to
LAST_VALUE, and the separate `min(priority)` is an ordinary Int64 MIN. Casting
the 64-bit priority to Float64 would lose exact ordering and is not a valid
substitute.

At the time of this probe, the production aggregate route, ordering and
execution mode still needed confirmation. The subsequent linked control
confirms ordered LAST_VALUE in partial and final-partitioned task plans and
correlates every aggregate task with its worker's successful status. An alias
displayed as `min_by` alone would have been insufficient evidence.

## Provenance and gate

- [Source receipt](source-receipt.json): exact source/lock hashes, copied upstream
  sources, Rust version, detached gate and isolated target. Every dependency
  shared with Sail's lock has the same version; Cargo built offline and locked.
- [Gate receipt](gate-receipt.json): formatting, two release semantic tests and
  release build passed. This gates the four frozen probe files, not a Sail commit.
  The detached worktree base is `2c3876ba3bdbff46db7c5b51a88edf738982deb3`.
- [Test log](build-test-attempt01.log) and [build log](build-attempt01.log): first
  attempt passed. Tests check null values, excluded/null filters, null priority
  filtering, signed Int64 extremes, equal-key first-winner behavior within and
  across batches, seen flags, prefix emission and state merging.
- [Allocation receipt](allocation-receipt.json): all three cells passed and all
  raw output hashes are retained. Binary SHA-256:
  `b627737ec653ec990fef98e46549153939f9c287bc66985e326c4ac86e17bf76`.
- The target was an APFS clone of the previous isolated component target; the
  original cache was not built into or changed. There was no full Sail build.

## Measurement method

Each cell is a fresh process with 1,000, 10,000 or 100,000 resident groups and
batches of at most 8,192 rows. Inputs, group indices, filters and JSON metadata
are allocated before measurement. The counted System allocator records requested
live bytes, requested peak above the phase start, allocation calls and requested
bytes allocated. These are not allocator usable-size or process RSS. Initial
retained bytes exclude the already constructed accumulator's fixed metadata.

A group's value and key are changed to force strict improvement in one dense
pass and one sparse pass. Equal-key repetition is measured separately. All
answers and emitted/merged states are checked. For `state(First(k))`, each
measurement starts from a fresh accumulator. At 1,000 groups, the `min(8192,G)`
case repeats `state(All)`; both observations are retained.

`size_of::<ScalarValue>()` is 64 bytes, `Vec<ScalarValue>` is 24 bytes, and
`ArrayRef` is 16 bytes on this measured 64-bit build. The meter snapshots before
formatting, printing or querying RSS. The RSS field is process-lifetime maximum,
including inputs and prior phases; it is not phase-specific accumulator memory.

## Retained allocation and repeated work

All figures below are bytes or counts, not MB/MiB.

| Resident groups | First retained requested bytes | Accumulator reported bytes | First allocation calls | Dense repeat calls | Dense repeat extra peak bytes |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1,000 | 104,384 | 104,384 | 1,019 | 13 | 16,560 |
| 10,000 | 1,301,504 | 1,148,288 | 10,042 | 30 | 131,248 |
| 100,000 | 11,692,032 | 10,946,304 | 100,236 | 206 | 131,248 |

Both identical and improving dense repeats retain zero additional bytes and
produce the same allocation counts and peaks in these cells. The source at
`first_last.rs:478–499` clones one one-element scalar vector for each new group,
and lines 512–517 reuse its capacity during updates. Int64 scalar values do not
contain a nested heap allocation. Thus the first update has approximately one
allocation per group; repeated updates do not replace all those allocations.

The resident shape is a typed value vector, a `Vec<Vec<ScalarValue>>` ordering
vector, one per-group scalar buffer, a scratch `Vec<usize>`, and three bitmaps
(value validity, seen and scratch validity). With capacities equal to the group
count, this is approximately `G * (64 + 24 + 8 + 8 + 3/8)` requested bytes,
excluding fixed metadata, allocator overhead, grouping keys, hash tables, the
separate MIN aggregate and the surrounding execution pipeline.

**Accounting omission:** `first_last.rs:739–744` reports the sum of each live
inner vector's size, including its 24-byte header, but does not count spare
capacity in the outer vector. At 100,000 groups, its capacity is 131,072 under
this growth schedule; the measured gap is exactly
`24 * (131072 - 100000) = 745,728` bytes. At 10,000 groups the corresponding gap
is 153,216 bytes. This demonstrates omitted requested capacity in the component
size estimate, not a demonstrated whole-query reservation or OOM failure.

**Resident-group scans:** lines 556–560 clear the scratch validity bitmap and
617–624 inspect all resident groups each input batch to collect the touched
ones. At 100,000 groups, the first pass has a source-derived sum of 738,976
resident-group visits; each 13-batch dense repeat has 1,300,000, and the one
8,192-row sparse pass still visits 100,000. These are analytic loop counts from
the pinned source and input schedule, not hardware performance counters. This
adds `O(sum_b G_b)` work; with new groups growing with input and fixed batch
size, that term can grow quadratically before emission. It is a component
property, not a whole-pipeline complexity claim. The sparse pass allocated
262,280 bytes across 16 calls, with a 131,248-byte extra peak and no retained
increase.

## Prefix state emission

At `first_last.rs:673`, state is removed before capacities are chosen. Lines
674 and 681 then use the **remaining group count** to reserve the output vector
and each temporary ordering column. The result has only three ArrayRefs, and
the ordering column needs space for the emitted groups.

| Original groups | Emit count | Output vector length / capacity | Extra requested peak bytes | Requested live change bytes |
| ---: | ---: | ---: | ---: | ---: |
| 1,000 | 1 | 3 / 1,001 | 80,544 | +16,800 |
| 10,000 | 1 | 3 / 10,001 | 802,848 | +163,104 |
| 100,000 | 1 | 3 / 100,001 | 8,025,376 | +1,625,632 |
| 100,000 | 8,192 | 3 / 91,810 | 7,630,160 | +1,099,336 |

The 100,000-group, one-row output reserves 1,600,016 bytes for the output
`Vec<ArrayRef>` alone; a temporary scalar column reserves another 6,399,936
bytes. The displayed Arrow array memory field excludes the output vector's
capacity. This is an allocation-sizing defect with a direct public-API
reproduction. Whether, how often and at what group count this prefix route
occurs in Pecan's actual distributed WCC plan remains unmeasured. Unordered
WCC aggregation alone does not establish that `EmitTo::First` is used.

For comparison of emission modes within this component, `evaluate(All)` at
100,000 groups allocates 280 requested bytes over four calls and raises no
peak above its starting level; it transfers the typed value buffer and frees
ordering state. `state(All)` must additionally construct ordering arrays: it
allocates 18,874,752 requested bytes over 42 calls, with a 3,146,064-byte extra
peak. Both leave 16,384 bytes reported in the accumulator, from retained scratch
bitmap capacity. These are different APIs and output requirements, not a
before/after optimization comparison.

## Narrow next steps

1. Capture the concrete aggregate on the exact Sail host with a tiny fixture.
2. Fix reserve dimensions independently: output-vector capacity should depend
   on ordering-column count, and temporary-column capacity on emitted rows.
   Add prefix/All capacity checks while preserving state schemas and answers.
3. Correct the grouped size estimate to include outer-vector spare capacity,
   without double-counting live vector headers. Test growth and prefix emission.
4. A typed Int64 ordering state plus touched-group list could remove the
   per-group scalar allocation and resident-group scan. That is a separate,
   unimplemented change requiring differential tests for filter/null handling,
   signed ordering, ties, state merging and every emission mode.

No optimizer, implementation or default was changed by this probe.

## Reproduce

The retained [runner](run_probe.py) refuses to overwrite the existing receipt
and raw cells. For a fresh run, use a fresh artifact destination, freeze the same
four source files in a detached worktree, set an isolated `CARGO_TARGET_DIR`
and `CARGO_INCREMENTAL=0`, then run:

```sh
cargo fmt --check --manifest-path /path/to/frozen/min-by-probe/Cargo.toml
cargo test --release --locked --offline --manifest-path /path/to/frozen/min-by-probe/Cargo.toml
cargo build --release --locked --offline --manifest-path /path/to/frozen/min-by-probe/Cargo.toml
/path/to/isolated-target/release/ordered-last-value-allocation-probe 1000
/path/to/isolated-target/release/ordered-last-value-allocation-probe 10000
/path/to/isolated-target/release/ordered-last-value-allocation-probe 100000
```

Raw cells: [1,000 groups](groups-1000.jsonl),
[10,000 groups](groups-10000.jsonl), [100,000 groups](groups-100000.jsonl).
