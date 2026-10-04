# Compact-host closed-result qualification

This is a local review of the frozen logging03 and 16k paired-control protocol.
It does not execute a workload or validate a new result. At the recorded review
cutoff, no closed logging03 collection or six-cell paired ledger was available
locally. The prior compact 16k smoke is functional evidence only; its 15-second
observation cannot be compared with the 289 smoke that overlapped a build.

The large logging02 baseline is now a closed **OOM**, with no correctness result
and no completed execution time. Therefore logging03 can establish its own
certified outcome at the matched envelope, but cannot produce a completion-time
ratio against logging02. Retain time-to-error, OOM events and all failed evidence
as separate observations; do not use failure time as a successful denominator.
The reviewed baseline is [logging02-verification.json](../closed-cell-audit/logging02-verification.json).

## What permits a correctness statement

First obtain a closed, stable collection: configuration, plan, result,
orchestration, receipt, server settings/log, memory JSONL, collection receipt and
archive. The [closed-cell helper](../closed-cell-audit/audit_cell.py) checks the
logging03 profile's source/binary/native/image/arguments/data-manifest/resource
identity, container closure, archive/member hashes and unchanged audit inputs.
Its `integrity_verified` verdict is **not** a correctness verdict; its output
explicitly says `correctness_verification=not_performed`. Missing closure,
receipt, collection or required cgroup evidence is inconclusive. A conflicting
hash, identity, schema or namespace is an integrity error. Do not infer a pass
from the safe runner's exit code: it returns zero after completed non-pass
classifications too (`run_focused_safe.py:126–134`).

A completed certificate/reference check may still be reported as completed if
later cleanup or collection fails, provided its authentic receipt is retained.
The overall trial remains non-pass or incompletely collected and is ineligible
for the paired ratio; preserve these distinct statuses. The pass requirements
below describe a fully qualified completed trial.

For logging03, require mutually consistent final runner/receipt pass, successful
container completion, no OOM or outer timeout, completed result-file inventory,
convergence, and complete producer certificate evidence:

- `rows=unique=16777216`, `parent_tree_checked=true`, and the certificate string
  `all-edge inequalities and rooted tight-edge reachability`;
- the pinned source 13507776, undirected weighted Graph500 edges and canonical
  edge hash `cacd401faca8b8da8cd81fcbedfadce5b355c7029c6c53fc9bec947b60d6649e`;
- `reference=distributed certificate; no precomputed reference vector`,
  `relative_edge_tolerance=1e-12`, reached count, witness rounds, finite maximum
  edge slack and conservative absolute distance-error bound.

The pinned validator checks full vertex coverage, finite nonnegative reached
distances, zero source distance, all-edge inequalities, source-rooted tight-edge
reachability and parent/hop witnesses. Report the accumulated error bound; this
is not bitwise full-vector equality or the 16k Dijkstra reference. The local
review checks the recorded producer proof and its source, not large output
Parquet independently. An interrupted certificate, exhausted witness-round
budget, or execution-only time must not be promoted to a correctness pass. A
round-limit error is incomplete verification, not automatically an answer
mismatch. The classifier's raw category and the last completed phase both stay.

For each 16k cell, require the same closure and identity evidence plus final
pass, `rows=unique=16384`, `parent_tree_checked=true`, and
`reference=independent BFS/heap-Dijkstra`. The source checks exact ID coverage
and reachability, distance error at most `1e-12*(1+abs(expected))`, and rooted
parent/hop edges. It does not require identical parent choices. The frozen
manifest pins 529723 edges, source 0, directedness and reference Parquet bytes.
The closed-cell helper has no six new namespace profiles: its smoke profile
must not be substituted for these cells. The paired runner checks their exact
planned arguments, identities and correctness fields, but archive/collection
integrity and final closure still need review for each collected cell.

Source boundary: controller `3a9028057c6c6c5034492845926fc4bc18f9626f`,
`traversal_cell.py:107–165`, `traversal_certificate.py:14–94`,
`graph_cell.py:338–368,494–561`; all source hashes are retained in `receipt.json`.
The existing prelaunch audit confirms exactly seven logging02/03 configuration
differences, limited to runtime/source and identifiers/paths/notes. Logging03's
completed admission records the same manifest hash `8bad1a94...5007c75c`.

## When the prepared 16k ratio is usable

The [frozen plan](../host-pair-16k/pair16k-20260930201356-plan.json) specifies one
warmup each (A=289, B=561), then measurements A B B A, fresh processes and no cache
flush. Require all six original cells, their ordered raw outcomes and times,
complete closure/integrity checks, a common VM boot, matched source/data/resource
pins, valid positive execution times, successful execution-memory sampling,
finite recorded guest steal, and no sampled competing container or inventory
error. Keep failures and any unrun suffix; do not retry into these namespaces or
select only successful cells. Warmups and prior smokes are excluded from ratios.

The runner emits A1/B1 and A2/B2 and their geometric mean, with only two measured
samples per host (`run_host_pair.py:138–156,319–324`). Those can be reported as
**descriptive ratios on this shared host** after the evidence above closes.
The automatic `comparison_eligible` flag is not an isolated runtime-effect
qualification: it accepts any finite steal fraction from zero through one and
does not check equal steal. Docker inventory is sampled, not a host-wide lock.

The runner captures macOS swap/compression only before each cell. There is no
matching per-cell host-after snapshot in this frozen pair protocol, so its
files alone cannot establish each cell's host paging/compression delta.
Adjacent cell starts do not supply the final cell's closure and also span
validation, cleanup and gaps. Without separately retained boundary observations,
quiet-host status and attribution of the ratio entirely to compact MIN remain
inconclusive. Raw descriptive shared-host ratios may still be stated with this
limitation; they are not absolute performance results. Zero guest steal or zero
container swap does not establish absence of macOS swapping the VM.

## Timer and memory comparison boundary

Both hosts use exactly the same execution timer: after lazy input DataFrame
handles, through traversal execution and final full Parquet write. It excludes
input hashing, server startup, output evidence hashing, correctness validation
and cleanup (`traversal_cell.py:19–27,90–100`; `graph_cell.py:465–498`). Input
checksum reads warm OS cache before timing; this is not cold-input measurement.
Use `end_to_end_seconds` only from successful closed cells, never
`algorithm_ready_seconds`, container wall time or `elapsed_until_error_seconds`
as a substitute. The verification alarm is separately reset. The outer timeout
covers all phases: 15300 seconds for the large pair, 1350 for 16k; the execution
and verification alarms are respectively 14400 or 600 seconds. A valid execution
timer alone does not prove verification completed within the outer limit.

Resource configuration is matched **within** each experiment, not across sizes.
The large pair uses 32 CPU quota/cpuset 0–31, 100 GiB container memory, two workers
with 64 slots each, and a 96 GiB Sail pool configured per process. The 16k pair
uses 8 CPU quota/cpuset 16–23, 12 GiB container memory, two workers with 16 slots
each and a 3 GiB pool per process. Neither pool setting is an aggregate RSS cap;
native quota settings are not observed native allocations. Require actual Docker
and cgroup limits, event deltas and CPU-throttle counters, not configuration alone.

Compare `memory.phase_peaks.execute` PSS with the same scope on the other host.
It sums visible container processes, including Python/driver/workers; the scan
reads them sequentially. RSS counts shared mappings repeatedly. The 50 ms
setting is a sleep **after** each scan, not a guaranteed sampling cadence.
Retain complete raw scans, scan durations, execute counts, transitions and
sampler errors. A lone valid execute sample passes the runner's sampling test;
it does not establish a precise peak. These are observed sampled maxima, not
allocator bytes or a proven instantaneous peak ratio. Keep the kernel's cgroup
lifetime peak separately: it includes cache/kernel/other phases and can be set
by verification. Steal is whole-VM, whole-trial; it is neither execute-only nor
restricted to the assigned cpuset (`measurement.py:1–5,35–73,130–182,205–220`).

No configuration mismatch blocks the prepared control. The concrete current
blockers are absent closed logging03/six-cell evidence, the failed large-pair
denominator, and—if stronger attribution is requested—missing per-cell macOS
closure pressure observations and unqualified memory-sampling coverage.
