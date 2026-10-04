# Morrobay typed Pecan execution results

All 14 frozen steps passed: two Linux compatibility smokes, four warmups and eight measured cit-Patents WCC cells. Each of the 12 WCC results matched all 3,774,768 vertices against the pinned exact membership oracle, with zero mismatches, 3,627 components and 19 completed rounds. All containers exited with status 0, without OOM, and were removed; all cell locks were released.

[COMPARISON.md](COMPARISON.md) records every outcome, timing boundary, measured cell, warmup, memory scope and host-pressure observation. [comparison-summary.json](comparison-summary.json) contains the queryable data, full pins and round details. Candidate/baseline median WCC-plus-export ratios were **0.94 locally** and **0.90 for the single-host process cluster**; lifetime cgroup peak ratios were **1.02 in both classes**. Each class has two measured samples per revision on a shared host. This compares Python controllers on one existing runtime binary.

## Evidence

- [Execution identity](execution-identity.json): handoff `6268d229`, controller commits, driver and Apo volume identity.
- [Queue closure](receipt.json): all 14 ordered steps passed with no remaining work in this plan.
- [Supervisor controls](supervisor-controls.json): negative outcome, OOM and incomplete-output controls.
- Each run has a lossless `.tar.gz` bundle, an audit JSON and a bundle manifest. The bundles contain producer and host receipts, raw logs, memory samples, input/output hashes, admission, orchestration and host pressure.
- [Physical output manifest](physical-results-manifest.json): 48 Parquet files across all 12 WCC cells independently matched their producer SHA-256 and byte counts after archival. Physical outputs remain in the guest and are also preserved in a 167,871,923-byte gzip tar archive on Apo.

The Apo archive is `/Volumes/Apo/graph-tests/results/pecan-typed-20261001/`. It contains all returned host evidence including duplicate `diagnostics.tar` collections, plus `physical-results.tar.gz`. Wrapper and supervisor logs are under `/Volumes/Apo/graph-tests/logs/pecan-typed-20261001/`. Grust retains the portable evidence bundles and physical archive manifest; the 168 MB physical payload stays on Apo.

The [independent audit](independent-audit.json) records the review of all outcomes, ratios, evidence mirrors and archived physical payloads before publication. The stopped historical Graph500 container and retained old lock were left in place. This run does not qualify a rebuilt candidate runtime, multi-host scaling, maximum graph scale or a new memory cap.
