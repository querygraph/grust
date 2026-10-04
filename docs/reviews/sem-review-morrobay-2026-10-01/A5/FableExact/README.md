# Exact Fable native A2-local results

All 48 original calls completed and passed the separate full physical audit:
six GF reference preparations and 42 full comparisons. The original two
G/P/P/G blocks have four calls per engine and algorithm, with no warmups.
The primary statistic is Pecan median time divided by GF median time.
A ratio below 1 means less Pecan median elapsed time on this shared host.

| Dataset | Algorithm | Pecan/GF ratio of medians |
| --- | --- | ---: |
| cit-Patents | wcc | 1.415399 |
| cit-Patents | pagerank | 1.159243 |
| cit-Patents | bfs | 0.712953 |
| graph500-24 | wcc | 0.795227 |
| graph500-24 | pagerank | 0.861455 |
| graph500-24 | bfs | 0.862452 |

These are ratios on a shared native macOS x86_64 host. Controller and compiled
Sail are `9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3`; GF is
`b4da56dabe20bba8e29563e06acc5179b2113ce3`. The retained optimized build uses
Rust 1.97.1, optimization level 3, full LTO, and one codegen unit. Only the
four original path globals changed; all Fable function bodies, timers,
exports, inline oracles and call order remain unchanged.

Pecan's primary timer excludes its function-local Python imports and includes
server launch, session, inputs, public call, raw export, session stop and
server wait. GF times its CLI subprocess. Local software workers are 16;
Pecan configures a 30-GiB pool and GF receives `--max-memory 30G`.
These settings are not an OS resource cap on the 128-GiB host.
Snapshot inputs are off and repartition checkpoints are on. Whole-script
parent exits and owned groups were observed; per-call PIDs and Sail server
return codes were not recorded by the original script.

Every output has the complete unique original vertex domain. WCC has exact
canonical labels and both partition directions checked. BFS retains all four
Pecan fields; only hops are numerically compared, while distance and parent
have schema and retention checks. PageRank preserves the original strict
inline absolute-error `< 1e-12` checks; the separate full comparison uses the
predeclared `1e-12` binary64 bound. BFS sources are Cit 5795784 and Graph500
798169. Stored directed arcs are used for BFS/PageRank; official Graph500
undirected ground truth is not qualified by this comparison.

[report.json](report.json) preserves all 48 outcomes, raw clocks, diagnostics,
physical schemas and identities. Adjacent-pair geomeans are labelled as
secondary statistics. [evidence.tar.gz](evidence.tar.gz) preserves small
original metadata, logs, configurations, closure proofs, sources and source
archives. Raw Parquet files and binaries remain in the separately audited
SSD/Apo stores and are excluded from this portable metadata package.

The old VM diagnostic was skipped at the user's explicit request. The
original A1 VM was deleted; the exact native script was requested and run.
The original C source is preserved. No causal VM explanation is claimed.

The earlier [MatchedNative report](../MatchedNative/README.md) and
[its source plan](../NATIVE-MATCHED-PLAN.md) retain their separate 70-call d0
controller protocol, Python-inclusive timer and two-field BFS export.
[This exact protocol plan](../FABLE-EXACT-PLAN.md) identifies the new run;
no historical result is relabelled.
