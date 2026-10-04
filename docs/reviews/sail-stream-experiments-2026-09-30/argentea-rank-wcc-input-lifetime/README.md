# Argentea input lifetime and lease teardown

Exact local component gate **PASS** at `33adfce1d2ab77c3e108aa542f7eda80dd5f5cf9`, tree `3f4399056199b49708340abf0b4d1205fca860dd`, on `work/argentea-rank-wcc-input-lifetime`. The branch contains two commits after delivered parent `a3462345a6764096024c055dc4d105a3c634e5a4`. This evidence cutoff is **not pushed**; root owns separate delivery verification. It is a fork review component, not an upstream submission or release.

PageRank, residual PageRank and WCC now separate validated, owned CSR preparation from rank/root/protocol-state allocation. The Nutmeg adapters drop actual raw vertex/edge vectors, then their `MemoryAccount`, before finishing initialization. Borrowed `build` remains compatible and delegates to `prepare(...).finish()`. The change preserves options-before-graph validation, vertex/source ownership checks, arc order, exact `1/N` initialization, work charging and protocol code. It does not reuse vertex buffers or alter float-reduction grouping.

Successful BFS, SSSP, residual PageRank and WCC partition teardown now drops admitted storage before `Resources` releases the last host lease. Reference PageRank's emission cursor also drops its sequence vector before its ownership/admission and last host lease. These declaration-order changes follow reproduced controls; other cursor layouts were not changed.

## Refuting controls before fixes

Unchanged `a3462345` production with added sole-owner tests reproduced early host-lease release. No external `Resources` clone masked the last-owner path. The callback observed **688 admitted bytes** for each WCC algorithm, **816** for BFS, **824** for SSSP and **502** for residual PageRank. All cases eventually reached zero usage: these are release-order defects, not permanent leaks, physical-memory measurements or explanations of historical stream failures. Reference PageRank's successful-partition control passed. See [both WCC baseline cases](baseline02-receipt.json), [the three additional partition cases](partition-lease-baseline-receipt.json), and their retained [WCC log](baseline02.log) and [partition log](partition-lease-baseline.log).

The independent [cursor control](../argentea-cursor-lease-control/README.md) observed the one **2,056-byte sequence allocation still live at last-lease release**, even though admitted bytes already read zero. Exactly one matching allocation and one eventual deallocation were tracked. Contribution-alias and completed-emission controls passed before the fix. The same three controls pass after the narrow reorder; its [receipt](../argentea-cursor-lease-control/final-receipt.json) and unchanged test are retained separately and integrated into this component gate. Admission counters alone cannot establish actual allocation lifetime.

## Measured boundary

[All 72 allocation cells](allocation-comparison.json) cover `n = 1, 1,024, 65,536`, degrees `0, 1, 8`, four algorithm variants and both input-lifetime paths. Here `n` is the local vertex count in the one measured owner partition (owner 0), with the operation configured for three partitions. All fixture vertices belong to owner 0; the allocation probe does not build the other owners or measure an aggregate worker/cluster peak. The thread-local allocator records requested sizes while native accounting records admitted bytes and work. Raw allocations are inside the measurement window, so dropping them does not subtract uncounted allocations.

For `n = 65,536`, requested peak reductions are:

| Algorithm | Degree 0 | Degree 1 | Degree 8 |
| --- | ---: | ---: | ---: |
| Reference PageRank | 524,288 B | 524,288 B | 524,288 B |
| Residual PageRank | 524,288 B | 1,179,944 B | 1,179,944 B |
| WCC Reference | 524,288 B | 524,808 B | 524,808 B |
| WCC Star | 524,288 B | 524,808 B | 524,808 B |

Allocation count, allocated-byte volume, retained admission and counted work are identical in every pair. The conservative CSR-build admission peak is unchanged in all 24 pairs at `n = 1,024/65,536`. The 12 single-vertex pairs have small 8–136-byte admission-peak reductions; all are retained, including PR degree eight's 32-byte reduction. This is a memory-overlap change, not reduced allocation volume or a demonstrated speed improvement.

The two cost paths run in the same candidate executable: the borrowed builder retains raw input while the split path releases it. Those comparisons prove the lifetime difference and API parity; they are not an independent old-binary versus new-binary performance comparison. Extraction diffs, unchanged existing algorithm tests and independent oracles provide additional semantic evidence.

Actual adapter tests additionally run on unchanged parent production and on the candidate. Split node and edge batches retain duplicate/nonempty arcs. Across all eight kind/size cells, the exactly-sized `n*8` buffer peak changes **3→2** for reference PR and both WCC algorithms, and **4→3** for residual PR, while matching allocation counts stay three/four. The [complete baseline control](baseline-native-extended01/receipt.json) fails the intended assertions and the [candidate control](candidate-native-extended01/receipt.json) passes them. The fixed pointer tracker is thread-local in current-thread async tests, rejects overflow and excludes prebuilt Arrow fixtures. It measures those matched buffers, not total process memory.

## Exact gate and scope

The [final exact receipt](extended-exact-gate/receipt.json) covers all **136 core tests**, all **55 native tests (49 Argentea)**, both ordinary and with all **10 local cores saturated**. Every owned load process was reaped. Core formatting and strict all-target core Clippy passed; all ten changed native Rust files passed formatting. Inherited unrelated full-Nutmeg formatting exceptions remain outside this check. Native inventory comes from a pinned executable's complete `--list` registry plus the unfiltered successful summary, avoiding interleaved receipt-log status counting.

The gates ran in a detached worktree with private APFS-cloned targets, offline Cargo, `CARGO_INCREMENTAL=0`, pinned Python 3.12.8, at least 32 GiB free-disk checks and full tracked source/index/head/tree guards before and after every step. Seeds were copied only after root confirmed the parent union targets idle. Candidate gate, source/receipt guard and commit were joined by `&&`; the exact gate then reran on the resulting clean detached commit. [Target provenance](target-and-baseline-preparation.json), [final frozen source pins](extended-frozen.json), [gate driver](run_extended_gate.py) and [conditional chain](extended_commit_and_gate.sh) are retained.

New controls cover prepared abandonment, cancellation, failed partial allocation, successful final-owner drop, post-CSR admission headroom, malformed inputs/options and their validation order, exact PR/residual message/state float bits, empty owners, signed extremes, duplicate arcs, both WCC protocol traces and independent components. Existing malformed-record/EOF/protocol tests also run in the full gate. The new borrowed-versus-prepared traces compare the two candidate APIs; they do not claim an independent unchanged-binary trace comparison.

No host Rust/CLI, SQL server, Linux, worker/Flight, rebuilt combined native wheel, RSS, elapsed-time, cluster or production performance qualification is implied. Raw input still overlaps CSR construction. The work does not identify the cause of any historical zero-OOM stream failure.

## Retained attempts and cutoff

The first WCC-only failing baseline and the expanded two-algorithm baseline are both retained. The first native baseline stopped after the first size; later complete controls retain all eight cells. New-test authoring errors are retained in `core-preliminary.log` (moved trace value), `baseline-native-control02` and `candidate-native-control01` (deferred assertion placed outside its helper). Corrections fixed the test code, not the lifetime assertions. Later focused controls and both final gates passed. Raw failed logs and receipts were not rewritten.

Commit `a41cbd8dd5cbd6eb9f8c09c7019391999efae6d4` and the original `candidate-gate`/`exact-gate` folders cover only the earlier PR/WCC scope (129 core/54 native). They remain intermediate evidence. The final expanded verdict is exclusively `33adfce1d2ab77c3e108aa542f7eda80dd5f5cf9` and the `extended-*` gates, including residual initialization and additional partition/cursor teardown fixes. Final closure is recorded in [final-receipt.json](final-receipt.json); root's later delivery receipt belongs outside this immutable folder.
