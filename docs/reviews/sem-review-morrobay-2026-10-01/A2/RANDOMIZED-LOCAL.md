# A2 randomized WCC: completed local contrast

Observed 2026-10-01T23:14:59.619384+00:00. A2's other contrasts and A3 remain running/pending.

On Morrobay's shared gate host, Pecan randomized local / graphframes
randomized launch-to-exit median ratio is **3.77**. Adjacent paired
geometric ratios are **3.79** and **3.84** for the two ABBA blocks.
Four measured samples per engine; the two retained warmups are excluded.
These are ratios on a shared host, with guest steal observed as 0.0 for
every measured cell; they are not dedicated-host absolute results.

Same original cit-Patents Parquet, exact A1 image/binary, 16 CPUs, 32 GiB,
no swap, 16 partitions; Pecan local30GiB greedy pool, graphframes30GiB
FairSpillPool. Pecan source `f3b3ef8fc` includes B9. Each output has all
3,774,768 unique vertices and exactly matches independent canonical WCC
membership: 3,627 components. All containers completed, were removed,
and released their owned gate locks; no OOM or forced cleanup. Pecan
converged in 16 rounds in each measured sample; external rounds are not
reported by a structured receipt and are not inferred.

Sampled owned-engine PSS ranges: graphframes1.45–1.49GiB,
Pecan2.19–2.27GiB. Container peaks through engine exit are1.71–1.74GiB
and2.53–2.62GiB respectively; these include prior identity reads and
page cache and are not algorithm-only memory.

The compared timer is fresh engine launch through completed exit,
including reads, snapshots, algorithm, full export and cleanup. Validation,
identity hashing and physical output comparison are outside. Diagnostic
Pecan medians: input snapshot5.02s, public algorithm48.12s, final export
0.23s. Snapshot is nested in public algorithm; durations are not additive
and are not subtracted to relabel a different timing boundary. Raw seconds
and every cell, including warmups, remain diagnostic in randomized-local.json.

See [run04 admission](RUN04-PREFLIGHT.md) for the confirmed signed-isolate
B9 mismatch. This measured dataset has verified zero isolates; the finding
remains a separate known_mismatch and generic signed-ID WCC is unqualified.
Full raw outputs, receipts and immutable plan: `/Volumes/Apo/graph-tests/results/sem-review-20261001/A2-run04`.
