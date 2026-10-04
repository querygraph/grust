# C4: same Struct accumulator allocation control

The six native allocator controls passed on the exact candidate source and
binary. The committed Rust gate also passed on that exact clean detached
source, finishing at `2026-10-04T00:54:00.622363+00:00`. The
[positive owner receipt](committed-runtime/owner-receipt.json),
[actual owner wait](committed-runtime/wait.json), and coordinator outer wait
proof are retained.
The allocator probes were reused rather than repeated. This verdict covers
the standalone Struct allocation control and its committed source only.

## What was measured

This is a single-thread control of the public grouped-accumulator factories,
using the same non-null Struct `(distance DOUBLE, hops BIGINT, parent BIGINT)`
as both payload and complete ordering key. The keys are finite and unique,
the parents are signed, and every filter is true. It compares the copied
native9f compact Struct minimum with DataFusion 55.1.0's ordered accumulator
selected by `min_by` for this full Struct. The original WCC `min_by` with a
Long payload and Long key is outside this control's scope.

Each row below is a fresh process; batch size is 8192. All six complete logs
retain the twelve measured phases and final semantic checks. The controls
check full evaluate, partial/all state emission, and merge outputs. They do
not time a graph algorithm or a DataFusion query.

| Ordered run | Groups | Factory | First-update requested allocations | Additional live requested MB | Cumulative requested MB | Raw first-update seconds |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| 1 | 4,096 | compact Struct min | 1 | 0.131072 | 0.131072 | 0.000092428 |
| 2 | 4,096 | ordered Struct min_by | 266,264 | 6.259712 | 24.888640 | 0.034248205 |
| 3 | 100,000 | compact Struct min | 5 | 4.194304 | 8.126464 | 0.001854949 |
| 4 | 100,000 | ordered Struct min_by | 6,500,283 | 155.815680 | 622.458304 | 19.990415932 |
| 5 | 100,000 | ordered Struct min_by | 6,500,283 | 155.815680 | 622.458304 | 32.566046582 |
| 6 | 100,000 | compact Struct min | 5 | 4.194304 | 8.126464 | 0.001913685 |

MB means decimal bytes divided by 1,000,000. These are requests counted by
the custom `System` allocator wrapper, rather than a physical-memory or
DataFusion pool measurement. The separate process lifetime peak RSS for
runs 4 and 5 is 199,106,560 and 198,778,880 bytes. This is a shared native
host; raw clocks are exploratory, with the two ordered first-update samples
showing substantial variability. They are not a graph-runtime ratio.

The phase clock and counters include the operation plus reported-size and
output-array-size sampling: Rust evaluates `acc.size()` before calling
`Phase::finish`. The selected grouped accumulator's final `size()` sums
cached counters; this source does not establish a final N-times-buffer scan.
The counts include any sampling allocations if made. No physical allocator,
MiMalloc, whole process fit, native Sail pool, or OS 32 GiB bound was tested.

## Reported size and retained buffers

At 100,000 groups, ordered `min_by` reports **240,122,269,952 bytes** of
accumulator size. That value repeats the accounting for full buffers shared
by per-group sliced ordering scalars. It is not 240 GB of unique live or
physical storage. The first update adds 155,815,680 requested live bytes;
absolute live requested bytes at its end are 164,733,758.

The factory source compacts the retained payload value scalar. The ordering
key's Struct scalar preserves a one-row Arrow slice into shared complete
input buffers, and its cached size accounting counts those buffers for each
group. Source witnesses and the supplemental accounting review preserve this
distinction. No isolated causal allocation result for the original WCC
Long/Long expression follows from this Struct control.

## Source and retained attempts

The probe's clean detached commit is
`ef5fc415ab4b182fb3df4e238cf634cc9fc94cd9`, tree
`268779f765b88813ec737beb1b30442eb30a5e72`. The candidate binary is 11,606,864
bytes, SHA-256
`2c541533c5e8c9295b20b2f91d4cb4c094880686b94d4d8a20cafd3450615621`.
The committed gate re-ran Rust versions, fmt, Clippy, tests, and release
compilation and required the unchanged exact binary. It reused the six
closed semantic controls without repeating allocator probes.

Run01 is retained as a failed 120-second **per-probe** cap. Its original
ambiguous error says `gate total timeout expired`; the campaign cap was
14,400 seconds. Its forced cleanup remains unqualified. The independent
closure records all known processes/groups absent and removal of its owned
locks; the timed-out probe's actual exit status is unknown. Run02 used a
900-second per-probe cap; all twelve commands/controls passed, were actually
waited, and closed naturally, followed by the actual owner wait.

The first committed-gate attempt, run03, refused the inherited `GIT_PAGER`
environment variable before any Git, Cargo or allocator command. Both inner
and outer waits closed naturally with failure, and the independent closure
preserves its zero-command state and exact owned-lock removal. It is not a
failed algorithm or a passing Rust gate. Run04 used the unchanged strict
predicate with only the child environment's `GIT_*` values removed. Its
positive committed gate, actual waits and independent root closure are
retained separately; none of the six allocator controls was repeated.

## Portable and external evidence

The planned package copies the eight committed Rust files, both owner
revisions and their controls, the complete run01/run02 logs and receipts,
independent failed-run closure, source and commit admissions, accounting
witnesses, the final committed gate source and runtime proof. Each readable
member is at most 16 MiB; the verified archive is at most 64 MiB. Every copied
file records its original path, SHA-256 and byte count.

The **complete** 21,861,993-byte build seed manifest remains externally on
Apo, because it exceeds the readable member bound. Its retained identity is
recorded by the portable [member manifest](manifest.json):
`/Volumes/Apo/graph-tests/results/sem-completion-20261003/C4-root-seed01/manifest.json`,
SHA-256 `69a66125c5ed4178a456d2386693c57933d35fb1d868068eb3461e5268529c44`.
It is not silently omitted or provided only as compressed data. The native
probe binary and build cache also remain external; this is a metadata/source
package rather than an executable distribution.
