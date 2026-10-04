# Matched cit Patents WCC diagnostic pilot

This pilot measures the WCC path raised in Sem's review. It uses the original
official Parquet files and the complete canonical component reference prepared
on September 30. The full [day accounting](../sail-stream-experiments-2026-09-30/SEM-REVIEW-2-DAY-ACCOUNTING.md)
distinguishes these completed diagnostic cells from the separate SSSP work.
All four cells passed the full oracle; see [results and phase breakdown](RESULTS.md).

The source is controller `3a9028057`, compact runtime `56194b170`, and native
wheel `ffcfbd569`; full hashes are enforced by [pilot.py](pilot.py).
The existing `randomized` and `randomized_fused` methods remain distinct.
The official `source`/`target` columns are lazily aliased to `src`/`dst`.
No input rewrite or ID normalization is performed by the adapter. The unchanged
public WCC API still performs its own snapshots and validation.

## Declared cells

| Order | Execution mode | WCC method |
|---|---|---|
| 1 | Local | Randomized |
| 2 | Driver and two workers | Randomized |
| 3 | Driver and two workers | Randomized fused |
| 4 | Local | Randomized fused |

Each cell has fresh processes, 16 CPUs, a 32 GiB container cap with no additional
swap, 16 partitions and a fixed seed of 42. The nominal sum of Sail pools is
24 GiB: one 24 GiB local pool, or three 8 GiB process pools. Native quota is
256 MiB per process. Neither pool sums nor quotas are RSS bounds. The
100-round algorithm cap is unchanged between cells. This is one diagnostic
sample per configuration, without performance claims or inferred causal shares.
It is not the repeated external-CLI comparison and does not qualify scale 26.

## Measurement and checks

The timer starts after creating lazy input handles and covers the public WCC
call through the completed full-result Parquet write. Startup, input hashing and independent output
verification are separate. Delegating wrappers time the unchanged schema and
snapshot routines; they remove no action. The snapshot residual includes
validation/count calls and Python/control work. Public call to first round also
contains algorithm setup, and the final round to algorithm-ready interval
contains reverse expansion and final normalization.

Every output ID and minimum-component-ID label is checked with independent
PyArrow reading against the pinned union-find oracle. Missing, duplicate, null,
unknown and incorrectly merged or split components fail. The checker is specific
to this sparse positive-ID dataset; it does not claim a general signed-ID
validation suite. Inputs, helper bytes and output inventory are checked for
changes. Source and binary identities are pinned before and after execution.

Memory sampling and durable round-event logging remain in the timed workload.
Worker debug logs record actual distributed task plans and preparation timing
without extra explain RPCs. Local actual-plan coverage remains incomplete.
This instrumentation must be disclosed in comparisons; its cost is not removed
by subtracting one aggregate number.

The algorithm and verification each have a 1,200-second deadline; startup has
120 seconds. [run_one.py](run_one.py) uses the existing pinned harness to impose
a 2,700-second outer limit and collect container exit/OOM/cleanup state. It
admits one cell only when the Docker context is idle, at least 34 GiB guest RAM
is available, and at least 12 GiB volume space is free. The operator checks
host activity and disk during execution. This wrapper does not automatically
launch the next cell or the separate Graph500 capacity queue.

Full output stays in Morrobay's `sail-extension-targets` volume. Flat diagnostic
files are copied to the host, with receipts for failed attempts retained.
Prepared source and passed offline checker tests are not engine results.

## Remaining qualification

With all four cells closed, compare mode and algorithm observations only within
this profile. Inspect checkpoint counts, contraction sizes, actual worker plans,
round timing, setup and reverse expansion before choosing an optimization.
Run B1's checkpoint-repartition opt-out separately; it is not loaded here.
Matched repeats, an external CLI control, richer spill/pool counters and a
dedicated host remain necessary for broader performance conclusions.

The Morrobay host wrapper requires explicit `/usr/local/bin/python3.12`.
The default macOS Python is 3.9.6 and lacks the required `hashlib.file_digest`
and filtered tar-extraction APIs. The first wrapper attempt failed before
container creation; its logs and the successful interpreter capability probe
are retained. It is a preparation failure, not a WCC result.
