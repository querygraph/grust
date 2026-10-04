# Four-cell WCC diagnostic result

All four declared cells passed the complete cit-Patents component oracle:
3,774,768 distinct vertices, 3,627 components, and zero membership mismatches.
Each converged in 19 contraction rounds, exited cleanly, recorded zero OOM
events, and left no staging Parquet under its verified run root. The official
input and reference hashes remained unchanged. This establishes correctness
for these executions; it does not close the performance question in Sem's review.

The [source and resource profile](README.md) was fixed: controller `3a9028057`,
runtime `56194b170`, native wheel `ffcfbd569`, 16 CPUs, 16 partitions, a 32 GiB
container cap, and 24 GiB nominal total Sail pools. The local and two-worker
profiles divide those pools differently. Each process has 16 Tokio/Rayon
threads and a 256 MiB native quota; aggregate configured threads and native
quotas therefore differ, within the same CPU and memory container caps. This was one sample per configuration
on shared Morrobay, in the declared order, without a dedicated-host timing claim.

| Order | Mode | Method | Full oracle | Peak container memory | Evidence |
|---|---|---|---|---:|---|
| 1 | Local | Randomized | Pass | 2.293 GiB | [Closed bundle](cell01-local-randomized.tar.gz) |
| 2 | Two workers | Randomized | Pass | 3.611 GiB | [Closed bundle](cell02-cluster-randomized.tar.gz) |
| 3 | Two workers | Randomized fused | Pass | 4.010 GiB | [Closed bundle](cell03-cluster-fused.tar.gz) |
| 4 | Local | Randomized fused | Pass | 2.748 GiB | [Closed bundle](cell04-local-fused.tar.gz) |

## What the shared-host comparisons show

| Comparison, numerator / denominator | Public elapsed ratio | Peak container memory ratio |
|---|---:|---:|
| Local fused / local original | 0.7816 | 1.1984 |
| Cluster fused / cluster original | 0.7795 | 1.1104 |
| Cluster original / local original | 1.4463 | 1.5748 |
| Cluster fused / local fused | 1.4423 | 1.4593 |

The fused variant merits controlled repeats: both elapsed observations were
lower, and both memory observations were higher. The cluster observations
also require investigation. These ratios describe these cells, not an isolated
algorithm improvement or a pure cost of distribution. Cache state, run order,
host activity, pool division and instrumentation have not been separated.
There is no matched ratio against the historical hundreds-of-seconds cells or
Sem's external results.

## Where the measured public call spends its time

The public timer starts after lazy input handles are created and includes
unchanged input snapshots and validation, contraction,
reverse expansion/final normalization, and writing every result row. Startup
and independent physical verification are outside it. Fractions below are of
that public timer; small inter-round gaps account for the remaining fraction.

| Cell | Before first round | Contraction rounds | After last round, before export | Export |
|---|---:|---:|---:|---:|
| Local original | 24.80% | 60.45% | 14.05% | 0.44% |
| Cluster original | 12.15% | 74.70% | 12.65% | 0.34% |
| Cluster fused | 9.24% | 73.05% | 16.88% | 0.60% |
| Local fused | 16.63% | 65.76% | 16.89% | 0.48% |

Snapshot and validation are nested within the first column, not an additional
phase. They account for 14.77%, 6.96%, 8.43% and 16.11% of the respective public
timers. Thus removing setup alone cannot explain or remove all the observed
cost. Contraction and final expansion also deserve direct measurement.

System CPU accounts for 83.45%, 73.78%, 72.30% and 75.16% of execution CPU in
these four cells. That is an observed accounting category, not an identified
cause. The process memory sampler scans `/proc`; its scan wall duration is
not its CPU cost and cannot be subtracted from the public timer. No unsampled
control has yet been run.

The same debug filter produced only 1,243-byte local server logs, but 10,497,251
and 6,110,740 bytes in the two cluster cells. Those logs preserve actual worker
plans; their unequal overhead is unisolated. All cells report zero guest CPU
steal, which does not establish an idle macOS host. Host swap remained in use;
interval host paging deltas were not collected for every cell. Raw timers,
round events, effective settings, memory samples and logs remain in the bundles
as shared-host diagnostic evidence, not dedicated speed ratings.

## Next experiments

1. Repeat the four configurations in controlled order. Separate plan capture
   from timing; add sampled/unsampled and logging controls without silently
   changing the public-call boundary. Record host paging deltas.
2. Run the external CLI on the same input, result contract and admitted resource
   profile, with a qualified host for absolute timings. Current results do not
   establish parity or identify Sail, its controller, or instrumentation as the
   sole cause.
3. Qualify the B1 checkpoint-repartition opt-out independently. Count actual
   jobs/exchanges and committed checkpoint writes; preserve the full oracle.
4. Implement borrowed validated inputs and committed writer receipts as separate
   changes, then investigate contraction tail and final expansion. Keep signed
   IDs, seeded representatives, ownership, cancellation and exact answers.
5. Advance WCC through Graph500 scales 24, 25 and 26 with measured phase peaks
   and storage admission. The separate SSSP capacity queue is additional
   capacity evidence, not WCC or multi-host scaling qualification.

Full output Parquet remains on Morrobay. The producer independently read every
row with PyArrow against the canonical union-find reference; the collected
bundles retain result-file hashes and that check's receipt. An offline bundle
audit can verify those receipts, but cannot reread omitted result payloads.
The initial Python-3.9 wrapper failure occurred before container creation and
is retained separately from these four successful engine executions.

[Independent four-cell audit](independent-audit.json) verifies the collected
closure and recomputes these metrics. Reproduce it with Python 3.12 or later:

```sh
python3 audit_closed.py --directory . --output /tmp/wcc-audit-new.json
```

The output path must be fresh. [Audit source](audit_closed.py) operates only on
local archives and does not launch work or read remote result payloads.
