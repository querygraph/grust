# Local verifier for the frozen six-cell host pair

This verifier reads a local mirror of the already prepared
`pair16k-20260930201356` study. It does not run Docker, contact a remote host,
execute a graph, fetch a repository, or read result Parquet. Its plan, six
configuration files, original runner and reused integrity helper are pinned
by hashes. Every cell uses its real paired namespace and A/B runtime identity;
the smoke profile is never substituted.

Preserve the remote study directory's layout when collecting it locally:

```text
pair16k-20260930201356/
  sequence.json
  01.result.json ... 06.result.json
  01.preflight.json ... 06.preflight.json
  01.inventory-before.json ... 06.inventory-before.json
  01.inventory.json ... 06.inventory.json
  cells/
    pair16k-20260930201356-01-a/
    pair16k-20260930201356-02-b/
    pair16k-20260930201356-03-a/
    pair16k-20260930201356-04-b/
    pair16k-20260930201356-05-b/
    pair16k-20260930201356-06-a/
```

Each cell directory retains `configuration.json`, `plan.json`, `result.json`,
`cell/orchestration.json`, `host-before.json`, `collection.json`,
`diagnostics.tar`, and the matching extracted `diagnostics/` files. Keep all
other runner logs, errors, inventories and summary files too; this narrow
verifier reads only the evidence listed above. It derives ratios independently
from the ordered original rows and does not trust the incoming summary's ratio.

From this directory, after the local collection is complete:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B audit_pair.py \
  --collection-dir /path/to/pair16k-20260930201356 \
  --output /path/outside-the-collection/pair-verification.json
```

The output path must be new and outside the collected directory. Exit status
0 means eligible for a descriptive shared-host ratio; 1 means integrity error;
2 means incomplete evidence or a retained noneligible benchmark outcome.
`integrity_status` and raw benchmark/producer outcomes remain separate: a
closed, faithfully collected mismatch or OOM can have verified integrity and
still be ineligible. Missing a cell/member/closure is inconclusive unless a
separate contradiction makes the integrity status an error. A false passed
receipt without complete reference/parent fields is an integrity contradiction.

The reused helper checks collection/archive/member bytes, source and native
identity, exact arguments, dataset-manifest pins, Docker/cgroup limits and
closure. A claimed pass also requires the execution-end cgroup snapshot; its
absence on a failed trial does not erase that failure. This verifier additionally
checks the exact plan/config hashes, all
six ordered rows and namespaces, A/B binary assignments, preflight identities,
same VM boot, raw concurrency inventory and copied metrics. Complete recorded
reference checks require 16384 rows/unique IDs, parent-tree checks and the
`independent BFS/heap-Dijkstra` reference. This is a review of the recorded
producer checks under pinned source, not an independent new Dijkstra run or
recomputation of result-file hashes. Recorded result inventory must be present
and well formed; large output Parquet remains in the original volume.

All six original trials, including both warmups, must qualify before the four
measurement rows yield A1/B1, A2/B2 and their geometric mean. Warmups are not
ratio samples. This does not establish dedicated hardware, low/equal steal,
precise instantaneous memory peaks, or runtime-only causality. The timer is
the matched execution-through-final-write timer. Steal is whole-VM/full-trial;
PSS is a sampled execute-phase maximum. The frozen runner lacks per-cell
macOS closure paging/compression deltas. See the
[qualification review](../compact-qualification-review/REVIEW.md).

`test_audit_pair.py` builds tiny synthetic collection envelopes in temporary
directories using retained receipt shapes. These are explicitly fixtures,
not observations of the real pair. Controls exercise the production verifier
for ordered identity/parity, wrong runtime/namespace/plan/order, missing
member/closure/final cell, archive corruption and failed or incomplete
correctness. No fixture binaries, archives or generated collections are
retained publicly.
