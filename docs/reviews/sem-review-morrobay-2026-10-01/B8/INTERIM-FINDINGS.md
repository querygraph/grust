# B8 interim findings: Cit-Patents complete; original Graph500 queue incomplete

This report freezes the original `generated-queues02` plan and its closed receipts. All 30 Cit-Patents cells passed. The first Graph500-24 adjacency UNION warmup reached the 32 GiB container limit and failed; its closure and retained artifacts were audited. The remaining 29 entries in that original queue have no launch or finish timestamps. Any later tail campaign needs its own identities and evidence.

## Cit-Patents paired shapes

The 30 qualified cells comprise six warmups and 24 measured cells. Each shape has one warmup per form, then two measured UAAU blocks, four measured samples per form. Every raw result passed the full signed64 pair/value oracle, uniqueness and cardinality checks. Closed container, export, archive and cleanup evidence is retained for every cell.

Ratios below are `median(array-explode)/median(union)` after excluding warmups. They are ratios observed on a shared Morrobay host. A ratio above 1 means the array/explode form had a higher median elapsed duration for the stated boundary.

| Shape | Engine-child boundary | Host-driver boundary |
| --- | ---: | ---: |
| adjacency | 1.01610 | 1.02068 |
| representatives | 1.11508 | 1.04642 |
| min-label-initial-round | 1.12261 | 1.07706 |

**Engine-child boundary:** the supervisor starts `perf_counter` immediately before the engine child's `Popen` and ends it after the completed `wait`. It includes startup, session, input snapshots, shared preparation, relation explain, staging/result writes and engine cleanup. The full output oracle runs afterwards. This is not kernel-only timing. See `supervise_shape.py:414–458`.

**Host-driver boundary:** the queue's `started_utc` to `finished_utc` around host-driver launch and exit. It also includes host orchestration, the full oracle, artifact copy/archive and closure work. These raw wall-clock timestamps and the engine monotonic timer are distinct measurements.

Block ratios use `geometric_mean(array-explode durations)/geometric_mean(union durations)` within each UAAU block:

| Shape | Block 1 | Block 2 |
| --- | ---: | ---: |
| adjacency | 1.01189 | 1.06517 |
| representatives | 1.10162 | 1.11155 |
| min-label-initial-round | 1.10456 | 1.13839 |

The closed Cit-Patents observations do not show a lower median elapsed duration for the alternatives under these settings. They qualify these isolated relational shapes, rather than a complete WCC or other graph algorithm.

## Semantics and source identities

- Adjacency: original and reversed pairs, with the same final DISTINCT; self loops retained.
- Representatives: the first contraction-round map on non-self-loop endpoints, using the actual f3 seed 42 signed affine GF coefficients `a=-4767286540954276203`, `b=2949826092126892291` and signed BIGINT MIN/least; reduction polynomial `0x1b`. Isolates are omitted by this shape. This is not a complete WCC partition.
- Min-label initial round: the separately named whole-update rewrite uses labels LEFT JOIN adjacency messages and explode; it repeats old labels and retains isolates. It is not a direct replacement for a heterogeneous vertex/message UNION.

| Identity | Exact pin |
| --- | --- |
| Pecan controller | `f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a` |
| Frozen harness | `6ae2e43a903c2cee02da170465c922c72b76198e` |
| Sail runtime | `56194b170155301ba91077f0ba3df31fe2c78b6b` |
| Installed native provenance | `ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73` |
| B8 helper repository | `afad8e2e7fc4af760e1b090ad60dd05f26dd0b6e` |

Actual envelopes were local execution, 16 CPUs, 32 GiB, no swap, 16 partitions and a greedy 30 GiB Sail pool, with a configured 256 MiB native quota. Actual native reservation/prepayment and allocated bytes were not observed; those observations remain pending. See the committed [C3 quota-accounting correction](../C3-NATIVE-QUOTA-CORRECTION.md) at Grust `39739f663d12d4d44b4f979fe7914f37d17139c7`. The native pin is an identity guard; this report makes no native graph-retention fit claim. All 30 Cit-Patents cells recorded guest steal_fraction 0.0; that observation does not establish a dedicated host.

Inputs admitted from actual files: Cit-Patents V=3,774,768/E=16,518,947; Graph500-24 V=8,870,942/E=260,379,520. Source hashes, raw schemas and admission records are in the machine report and evidence index.

## Original Graph500-24 failure

`b8-graph500-24-adjacency-01-union` was a warmup. Its raw host outcome is `error`, supervisor outcome `oom`, engine outcome `error`, and bootstrap outcome `checking` with producer return code 1. The container exited 1 with `OOMKilled=true`. The cgroup reached 34,359,738,368 bytes, with `oom` increasing 0→8 and `oom_kill` 0→1. No Graph500 timing or ratio is qualified.

The allocation cause remains unexplained. The retained pre-write relation plan shows Partial aggregate DISTINCT, a 16-way hash exchange, FinalPartitioned aggregate, and UNION over forward/reverse projections. The explain excludes the Parquet sink wrapper; these observations do not identify which allocation caused the OOM.

The independently retained natural-OOM closure audit confirms owned process/container absence and full collection/archive checks, with original receipts untouched. The failed lock owner directories were preserved with their exact bytes before any later campaign:

- `original-oom-closure-audit01.json`: SHA256 `3d54b21d9440d414d9438c6f673432d615ea10c34ae4e94d7f86140f051c3bbe`.
- `original-failed-locks-preserved01.json`: SHA256 `e273bf60f30fa82180420c164911400b6dea89b19f0e7f20c940526635624d91`.

## Evidence and publication scope

Archive root: `/Volumes/Apo/graph-tests/results/sem-review-20261001/B8-run01`. The 30 Cit-Patents step IDs, roles, blocks, raw boundary diagnostics, oracle counts and metadata references are preserved in [interim-findings.json](interim-findings.json). [interim-evidence-pins.json](interim-evidence-pins.json) records exact byte lengths, SHA256 values and original JSON key schemas for the frozen metadata/source files, including both queues, cell receipts, plans and archived lock owners.

The report kind is `b8_interim_incomplete`, with `incomplete=true` and `all60_done=false`. The source/metadata publication gate rechecks those records and derivations; it does not repeat the already recorded full payload/oracle/archive scans. Frozen complete-publication helpers do not understand future tail mappings or skips and are not a gate for this interim report. No generic 32 GiB admission, absolute performance result, or full-algorithm conclusion follows.
