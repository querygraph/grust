# Typed Pecan comparison on Morrobay

Recorded: 2026-10-01T18:05:08.755431+00:00.

All 14 frozen steps passed: two compatibility smokes, four warmups and eight measured cells. Their producer receipts, physical oracle and container closure were checked before this summary.

These are **candidate/baseline ratios on a shared host**, with two samples per revision in each execution class. The medians describe this queue; they do not establish statistical confidence or isolate the contribution of individual controller changes.

The process cluster uses three Sail processes inside one container on one host. This queue tests the two pinned Python controllers with the same existing Linux runtime binary. It does not test a runtime rebuilt from the candidate commit, multi-host scaling or maximum scale.

## Pins and boundaries

- Baseline controller: `cab6bacc0ad0d1fc8b3070e9e4267e99751909fe`.
- Candidate controller: `6ae2e43a903c2cee02da170465c922c72b76198e`.
- Runtime source: `56194b170155301ba91077f0ba3df31fe2c78b6b`; binary SHA-256: `5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec`.
- Native source: `ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73`; Docker image: `sha256:f3518d652fbea8b9b9f9ebf9849277ca3bd39d0c21bb2c6e36fbaeaa2dc2678e`.
- cit-Patents: 3,774,768 vertices, 16,518,947 edges; WCC `randomized_fused`.
- Each cell: 16 CPUs, 32 GiB container memory, no swap, 16 partitions. Local pool 24 GiB; process cluster three 8 GiB nominal pools.

The public timer begins after creation of lazy input handles and includes public WCC plus complete result export and observer overhead. Startup, input hashing and physical verification are outside that timer. Snapshot time is a subset of public time, not an extra phase to add.

Execute PSS is the sampled sum of proportional process memory during execute, with a one-second delay after each scan. The cgroup peak is a container lifetime peak including page cache and allocator overhead; it is not the same scope or phase as execute PSS. Guest steal covers the whole Linux VM during the server lifecycle and does not prove an idle host.

## Measured comparison

A ratio below 1 means the candidate's median is lower for that metric; above 1 means higher. Raw seconds and GiB below are retained diagnostic cells, not dedicated-host performance ratings.

| Execution class | Metric | Baseline median | Candidate median | Candidate / baseline |
| --- | --- | ---: | ---: | ---: |
| local | `end_to_end_seconds` | 45.07 s | 42.47 s | 0.94 |
| local | `input_snapshot_seconds` | 7.90 s | 5.36 s | 0.68 |
| local | `execute_pss_peak_bytes` | 2.38 GiB | 2.31 GiB | 0.97 |
| local | `lifetime_cgroup_peak_bytes` | 2.63 GiB | 2.68 GiB | 1.02 |
| process-cluster | `end_to_end_seconds` | 62.17 s | 55.72 s | 0.90 |
| process-cluster | `input_snapshot_seconds` | 5.35 s | 2.20 s | 0.41 |
| process-cluster | `execute_pss_peak_bytes` | 3.12 GiB | 3.26 GiB | 1.04 |
| process-cluster | `lifetime_cgroup_peak_bytes` | 3.57 GiB | 3.62 GiB | 1.02 |

### Every measured local cell

| Run | Revision | Public/export s | Snapshot s | Execute PSS GiB | Lifetime cgroup GiB | Rounds | Guest steal |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `typed-measured-local-1-baseline` | baseline | 44.98 | 7.68 | 2.36 | 2.59 | 19 | 0.00% |
| `typed-measured-local-2-candidate` | candidate | 42.85 | 5.37 | 2.42 | 2.72 | 19 | 0.00% |
| `typed-measured-local-3-candidate` | candidate | 42.09 | 5.34 | 2.20 | 2.64 | 19 | 0.00% |
| `typed-measured-local-4-baseline` | baseline | 45.16 | 8.11 | 2.41 | 2.67 | 19 | 0.00% |

### Every measured process-cluster cell

| Run | Revision | Public/export s | Snapshot s | Execute PSS GiB | Lifetime cgroup GiB | Rounds | Guest steal |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `typed-measured-process-cluster-1-candidate` | candidate | 56.63 | 2.20 | 3.30 | 3.70 | 19 | 0.00% |
| `typed-measured-process-cluster-2-baseline` | baseline | 62.05 | 5.41 | 3.02 | 3.46 | 19 | 0.00% |
| `typed-measured-process-cluster-3-baseline` | baseline | 62.28 | 5.30 | 3.22 | 3.67 | 19 | 0.00% |
| `typed-measured-process-cluster-4-candidate` | candidate | 54.82 | 2.19 | 3.21 | 3.55 | 19 | 0.00% |

## Warmups

Warmups are retained and excluded from the ratios.

| Run | Revision | Public/export s | Snapshot s | Execute PSS GiB | Lifetime cgroup GiB | Rounds | Guest steal |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `typed-warmup-local-baseline` | baseline | 48.48 | 9.23 | 2.52 | 2.66 | 19 | 0.00% |
| `typed-warmup-local-candidate` | candidate | 41.97 | 5.30 | 2.39 | 2.66 | 19 | 0.00% |
| `typed-warmup-process-cluster-baseline` | baseline | 62.53 | 6.10 | 3.21 | 3.64 | 19 | 0.00% |
| `typed-warmup-process-cluster-candidate` | candidate | 59.02 | 2.52 | 3.28 | 3.62 | 19 | 0.00% |

## Exact physical result and closure

All 12 cit-Patents WCC cells delivered exactly 3,774,768 unique vertices, zero membership mismatches and 3,627 components; the largest component has 3,764,117 vertices. The frozen independent PyArrow oracle requires exactly `id:int64, component:int64`, non-null values and the exact minimum original vertex ID for every component. The two smokes also passed SSSP, BFS and WCC on sparse signed IDs, an isolate and zero-weight ties.

Every container exited with status 0, without OOM, and was removed; every cell lock was cleared. Input, controller, runtime and native identity checks passed. Round durations, hashes, raw host pressure before/after, guest admission and phase memory details are in [comparison-summary.json](comparison-summary.json).

### Host pressure observed

Mac host swap use and free pages are observations, not proof of active paging or a dedicated host. Full `vm_stat`, swap and uptime output remains in each evidence bundle.

| Run | Load before (1/5/15 min) | Swap used before / after MiB | Free pages before / after GiB |
| --- | --- | ---: | ---: |
| `typed-smoke-local` | 2.42/2.13/2.05 | 31055 / 26797 | 42.84 / 38.51 |
| `typed-smoke-process-cluster` | 2.14/2.10/2.05 | 26797 / 24871 | 38.55 / 36.60 |
| `typed-warmup-local-baseline` | 2.00/2.16/2.08 | 24872 / 11494 | 36.61 / 21.71 |
| `typed-warmup-local-candidate` | 2.56/2.84/2.44 | 11494 / 11334 | 21.52 / 21.32 |
| `typed-warmup-process-cluster-baseline` | 6.11/3.84/2.84 | 11334 / 10262 | 21.26 / 19.41 |
| `typed-warmup-process-cluster-candidate` | 9.24/5.46/3.55 | 10262 / 9942 | 19.34 / 18.56 |
| `typed-measured-local-1-baseline` | 9.19/6.21/3.98 | 9942 / 9942 | 18.53 / 18.51 |
| `typed-measured-local-2-candidate` | 9.36/6.88/4.38 | 9942 / 9910 | 18.47 / 18.51 |
| `typed-measured-local-3-candidate` | 9.10/7.29/4.69 | 9910 / 9910 | 18.46 / 18.17 |
| `typed-measured-local-4-baseline` | 8.94/7.62/4.98 | 9910 / 9910 | 18.11 / 18.01 |
| `typed-measured-process-cluster-1-candidate` | 9.00/7.90/5.26 | 9910 / 9846 | 17.96 / 17.87 |
| `typed-measured-process-cluster-2-baseline` | 10.05/8.50/5.70 | 9846 / 9622 | 17.81 / 17.58 |
| `typed-measured-process-cluster-3-baseline` | 10.52/9.04/6.14 | 9622 / 9590 | 17.54 / 17.24 |
| `typed-measured-process-cluster-4-candidate` | 11.25/9.63/6.61 | 9590 / 9590 | 17.20 / 17.24 |

## All frozen outcomes and retained evidence

The lossless repository bundles include raw logs, memory samples, receipts and closure records. The duplicate diagnostics tar is retained separately in the Apo archive.

| Run | Role | Class | Outcome | Evidence |
| --- | --- | --- | --- | --- |
| `typed-smoke-local` | compatibility | local | passed | [bundle](typed-smoke-local.tar.gz), [audit](typed-smoke-local-audit.json) |
| `typed-smoke-process-cluster` | compatibility | process-cluster | passed | [bundle](typed-smoke-process-cluster.tar.gz), [audit](typed-smoke-process-cluster-audit.json) |
| `typed-warmup-local-baseline` | warmup | local | passed | [bundle](typed-warmup-local-baseline.tar.gz), [audit](typed-warmup-local-baseline-audit.json) |
| `typed-warmup-local-candidate` | warmup | local | passed | [bundle](typed-warmup-local-candidate.tar.gz), [audit](typed-warmup-local-candidate-audit.json) |
| `typed-warmup-process-cluster-baseline` | warmup | process-cluster | passed | [bundle](typed-warmup-process-cluster-baseline.tar.gz), [audit](typed-warmup-process-cluster-baseline-audit.json) |
| `typed-warmup-process-cluster-candidate` | warmup | process-cluster | passed | [bundle](typed-warmup-process-cluster-candidate.tar.gz), [audit](typed-warmup-process-cluster-candidate-audit.json) |
| `typed-measured-local-1-baseline` | measured | local | passed | [bundle](typed-measured-local-1-baseline.tar.gz), [audit](typed-measured-local-1-baseline-audit.json) |
| `typed-measured-local-2-candidate` | measured | local | passed | [bundle](typed-measured-local-2-candidate.tar.gz), [audit](typed-measured-local-2-candidate-audit.json) |
| `typed-measured-local-3-candidate` | measured | local | passed | [bundle](typed-measured-local-3-candidate.tar.gz), [audit](typed-measured-local-3-candidate-audit.json) |
| `typed-measured-local-4-baseline` | measured | local | passed | [bundle](typed-measured-local-4-baseline.tar.gz), [audit](typed-measured-local-4-baseline-audit.json) |
| `typed-measured-process-cluster-1-candidate` | measured | process-cluster | passed | [bundle](typed-measured-process-cluster-1-candidate.tar.gz), [audit](typed-measured-process-cluster-1-candidate-audit.json) |
| `typed-measured-process-cluster-2-baseline` | measured | process-cluster | passed | [bundle](typed-measured-process-cluster-2-baseline.tar.gz), [audit](typed-measured-process-cluster-2-baseline-audit.json) |
| `typed-measured-process-cluster-3-baseline` | measured | process-cluster | passed | [bundle](typed-measured-process-cluster-3-baseline.tar.gz), [audit](typed-measured-process-cluster-3-baseline-audit.json) |
| `typed-measured-process-cluster-4-candidate` | measured | process-cluster | passed | [bundle](typed-measured-process-cluster-4-candidate.tar.gz), [audit](typed-measured-process-cluster-4-candidate-audit.json) |

Driver closure: [receipt.json](receipt.json). Summarizer: [summarize_morrobay.py](../summarize_morrobay.py).
