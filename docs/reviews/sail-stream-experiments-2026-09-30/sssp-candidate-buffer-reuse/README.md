# SSSP candidate-buffer reuse

The fork component reuses each non-Done SSSP inbox's candidate vector as the
next immutable label snapshot. It removes one dense allocation and copy at
publication. It preserves the previous snapshot, ordered work checks, candidate
ordering, pending frontier rules, producer/EOF validation and final publication
checks. The full vertex scan remains; completion traffic and CSR construction
are unchanged. These are local allocation/admission controls, not timings, RSS,
distributed execution or cluster-scaling measurements.

Repository: `querygraph/sail`; branch `work/sssp-candidate-buffer-reuse`.
Base: `33adfce1d2ab77c3e108aa542f7eda80dd5f5cf9`.
Component: `fc094a0c25a49edeac2f9f0195aa973421a21a43`.
Tree: `5abc3e30eadb878402b3a90bcbeb0a48ac8c4b25`.
The source remains a fork review component; delivery is recorded separately by
the coordinator. This folder's final receipt records its pre-push cutoff.

## What changes

`sssp/partition/protocol.rs::finish` formerly initialized and copied a new
`Values.labels` while the old labels and inbox candidates were still live.
The replacement takes the inbox vector and merges old labels into it in the
same charged index order. The old `Arc<Values>` is never mutated. A candidate
that improves only the predecessor changes the witness without incorrectly
reactivating outgoing work; DeltaStar retains unselected-bucket activity.

`Values` retains the original inbox reservation alongside a new frontier
reservation. Reservation cloning shares the same charge. The full inbox charge
remains held until its producer arrays have dropped; only then is it reduced
to the surviving label vector's checked capacity in bytes. Both reservations
follow the vectors in destruction order. No Grust dependency or public API
changes are needed. The additional optional token slot adds eight requested
bytes to each `Values` allocation on this tested 64-bit build; it is included
in the reported allocation volume.

Only two production files change. The other five changed files provide the
test allocator watch, deterministic cancellation hook and focused controls.
The [frozen source receipt](frozen.json) and [patch](candidate.patch) identify
the exact content. Source/test files remain below 500 lines.

## Matched measurements

[Allocation comparison](allocation-comparison.json) retains all 36 cells as
18 matched pairs: Reference and DeltaStar, three phase modes, and 1/1,024/65,536
local vertices in the one measured partition (owner 0), with three configured
partitions. All fixture IDs belong to owner 0; the two other owners are empty.
There are five fixed weighted arcs for larger fixtures, including a duplicate,
and a self-loop for the singleton. This is not a whole-graph aggregate across
three equally populated workers.

The two algorithms produced identical allocation counters in these cells.
The table gives each algorithm's result; the JSON retains them separately.

| Local vertices | Phase | Allocation calls, before → after | Requested volume, before → after | Window requested peak, before → after |
|---:|---|---:|---:|---:|
| 1 | Topology | 9 → 8 | 654 → 630 B | 600 → 501 B |
| 1 | Active | 10 → 9 | 675 → 651 B | 600 → 501 B |
| 1,024 | Topology | 9 → 8 | 42,597 → 9,837 B | 42,048 → 9,280 B |
| 1,024 | Active | 14 → 13 | 42,702 → 9,942 B | 42,069 → 9,301 B |
| 65,536 | Topology | 9 → 8 | 2,687,589 → 590,445 B | 2,687,040 → 589,888 B |
| 65,536 | Active | 14 → 13 | 2,687,694 → 590,550 B | 2,687,061 → 589,909 B |
| All three sizes | Done | 3 → 3 | 461 → 461 B | 461 → 461 B |

At 1,024 and 65,536 vertices, a pointer watch seeded with the actual old-label
and inbox-label addresses observes three live buffers before and two after,
and one versus zero new same-size allocations. Every successor retains the
actual candidate pointer. The singleton's same-size allocation counters also
match metadata allocations, so they are retained but are not called label-only
buffer counts. Actual candidate capacity equals local vertex count in every
non-Done cell; Done has capacity zero and keeps its existing label pointer.

The allocator window starts immediately before `finish` and ends immediately
after it returns. Calls and volume count successful allocator requests. The
window peak is the maximum positive running difference between requested
allocation bytes and deallocation bytes, starting at zero at entry. Deallocations
may include objects allocated before the window. It is neither total process
heap nor RSS. The pointer watch separately proves the dense-buffer overlap.

For admission, a held normalization reservation first makes entry live bytes
and entry historical peak both 67,108,864 B. `finish_peak_admitted_delta` is
**exit cumulative peak minus entry cumulative peak**, not an absolute context
peak. At 65,536 vertices it falls from 2,687,360 to 590,208 B; at 1,024 from
42,368 to 9,600 B; at one vertex from 832 to 800 B. Done remains 536 B.
The normalization reservation is held through publication and then dropped.
The older baseline01 log called this delta `admitted_peak`; its original bytes
are retained, and the later matched logs use the explicit name.

Retained admission and counted work are equal in every matched pair: non-Done
finish charges `n + 1` in this fixture; Done charges zero. All cells, including
the singleton's distinct peak behavior and unchanged Done cells, are retained.
The [analysis script](analyze.py) checks the complete inventory and these
relationships rather than selecting favorable rows.

## Refuting and semantic controls

The detached [unchanged-source baseline](baseline03/receipt.json) adds only
test instrumentation to `33adfce1d`. It retains two passing tests and three
expected regression failures: dense-buffer reuse, one-MiB publication headroom,
and the assertion that a specified late quota failure occurs after merging.
The [candidate control](candidate03/receipt.json) passes all five tests with
the identical test source. At 65,536 local vertices both candidate algorithms
publish with one MiB remaining admission; both baseline algorithms refuse.

The controls also cover:

- A real `SsspRowCursor` retaining the old snapshot and host lease across
  publication and partition drop. This cursor is constructed through a private
  test seam; public `row_cursor()` still requires a sealed result.
- Full ties, worse candidates, parent-only improvements, new reachability,
  distance improvement and DeltaStar bucket carryover. These white-box merge
  operands supplement the existing independent weighted protocol/oracle tests.
- Early quota refusal, late statistics-inbox refusal after all seven fixture
  merge work units, work exhaustion after three units, and pre-cancellation.
- Deterministic cancellation when the next statistics vector is allocated,
  after admission and merging but before the final checkpoint. The one-shot
  allocator hook removes itself before calling cancellation; it uses no timing
  window. Both modes retain the exact previous published `Arc`, labels and phase.
- Sole-owner host-lease callbacks after success and failure, asserting zero
  admitted bytes and no watched storage alive at release.

## Gate scope and retained attempts

[Candidate gate](candidate-gate/receipt.json) and
[exact-commit gate](exact-gate/receipt.json) run core formatting, strict core
all-target clippy, all **141 core tests** and all **55 native tests (49 Argentea)**
in release, both ordinarily and with all ten local cores saturated. Native
counts use the pinned executable's full registry and an unfiltered success
summary. Owned saturators are reaped and owned process groups are checked absent.
There are no Nutmeg source changes; inherited unrelated full-Nutmeg formatting
exceptions remain excluded.

The gates use a detached source, private APFS-cloned targets, offline Cargo,
`CARGO_INCREMENTAL=0`, pinned native Python 3.12.8 and a 32-GiB disk floor.
Full tracked source, modes, logical index, HEAD and tree are guarded around each
subgate. The named commit is conditional on the candidate gate and precommit
guards in one [shell chain](commit_and_gate.sh), followed by an exact-SHA gate.
The [driver](run_gate.py) and [preparation](preparation.json) disclose seed and
environment scope. No host Rust, CLI, SQL, Linux, worker/Flight, combined native
wheel, timing, RSS or cluster verdict is implied.

All earlier observations remain: [baseline01](baseline01-receipt.json),
[baseline02](baseline02/receipt.json), [candidate02](candidate02/receipt.json),
the [test-only formatter include-path failure](authoring-format01.json), and
the [initial named-checkout authoring probe limitation](candidate01-scope.json).
That initial probe has no qualifying verdict and is excluded from the final
matched comparison. The later detached controls and complete exact gate supply
the reviewed evidence.
