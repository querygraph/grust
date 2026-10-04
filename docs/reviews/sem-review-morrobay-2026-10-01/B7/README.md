# B7 — snapshot versus in-place inputs

Status: **DONE**, six native cells qualified, including two warmups.

The measured in-place/snapshot end-to-end ratio is **0.9121** (geometric mean of
**0.9059** and **0.9184**): **8.8% less time** in this exploratory comparison.
Every cell returned all **3,774,768** unique vertices with **zero membership
mismatches** and **3,627** components against the unchanged full physical oracle.
All six converged in 16 rounds.

## Protocol and limits

One warmup per variant, then snapshot/on–off–off–on: **two measured pairs**,
one ABBA block. Warmups are excluded from ratios; every outcome is retained.
The sole engine option difference is `snapshot_inputs`. WCC uses randomized
contraction, seed42, canonical labels, 100-round cap and repartitioned checkpoints.
The timer covers child launch through waited exit, including startup, input
snapshot or bypass, WCC, full raw Parquet export and cleanup. Full membership
validation and output retention follow engine exit. No A5 profiling wrappers or
extra component-count action are present. `input_snapshot` is a nested span
measuring the actual snapshot or bypass; it is not subtracted from elapsed time.

These are ratios on the shared Morrobay native macOS host. Software settings are
16 threads, 16 partitions and a 30GiB greedy pool, with a 256MiB configured native
quota. The host has 128GiB; these settings do not enforce an OS resource envelope.
This follows Alexy's native-hardware policy and does not reproduce the historical
A2 16-CPU/32GiB image. It supplies no dedicated-host absolute result, general
scaling conclusion or 32GiB capacity proof. Raw clocks and sampled RSS remain
diagnostic machine evidence. Timed graph inputs, staging and output used the
internal SSD; the compiled runtime and admitted native client were on Apo.

## Source identity

Python controller: **b522bf3a9c38d3861a114bf672abe7f7d6c7c491**.
Compiled native runtime: **9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3**, release
opt3/LTO/codegen1, binary SHA `ee80ac3cf9d028639561f3cf32435985192719d629807fcf6a368324fa84946e`.
The compiled Rust source (`crates/`, Cargo manifests/lock and toolchain file) is
identical between these commits, checked before and after every cell.
Frozen supporting harness: **6ae2e43a903c2cee02da170465c922c72b76198e**.
The exact admitted Python3.12 client and selected native/module identities
matched before and after each cell; observation timestamps differ as expected.

## Evidence and closure

[report.json](report.json) lists all six cells and the ratio calculation.
[plan.json](plan.json) is the sealed pre-execution plan.
[queue02.json](queue02.json) records all six waited parent exits.
[root-audit.json](root-audit.json) independently verifies **54 files,
84,582,900 bytes** retained on Apo, plus owned process/group absence and lock
release. Each [cell receipt](cells/measured-01-snapshot.json) retains the full
physical oracle, resource observations and source/client guards. Exact source
archives and admission metadata are in `evidence/`.

All raw output is retained under
`/Volumes/Apo/graph-tests/results/sem-review-20261001/B7-native-pair01/cells/<cell>/raw-output`.
The initial queue stopped after its already-qualified first warmup because the
root launcher read the wrong receipt key (`engine` instead of `child`);
[queue01.json](queue01.json) preserves that failure. The corrected queue
continued the remaining five cells. **No engine cell was repeated.**

The [B9 signed-isolate regression](../B9/README.md) is separately qualified.
Historical A2/A3 receipts and measurements were not rerun or rewritten.
