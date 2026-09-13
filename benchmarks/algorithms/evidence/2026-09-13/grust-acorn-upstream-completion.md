# Docker benchmark: Icebug, Icecat, Grustcat, Grustcat Cypher, upstream Grust and Neo4j GDS

Neo4j 2026.08.0, official GDS 2026.08.1; algorithm concurrency 1.

Historical direct native columns are kernel milliseconds including Arrow result construction in Rust; Grustcat Cypher additionally includes query compilation and execution. Upstream columns use the separately disclosed boundaries below. Neo4j uses reported computeMillis except Dijkstra, which consumes the full-path stream and reports server query time including reconstruction and aggregation. Dijkstra mode: full-path. All included engines construct source-first node and cumulative-cost arrays for every reachable target and consume their entries. Native timers include path construction and aggregation; GDS server query time also includes Cypher execution. Equivalent output work does not imply identical runtimes or allocation strategies. Zero GDS compute times are below timer resolution.

PageRank uses uniform weighted ranks. Native stopping is L1 1e-8; GDS uses per-node tolerance 1e-10. GDS scores are normalized before validation. Equal stopping rules or equal iteration work are not claimed. Graph loading, projection and transport are excluded from compute timers.

| Graph | Nodes | Algorithm | Icebug ms | Icecat ms | Grustcat ms | Grustcat Cypher ms | Grust upstream direct ms | Grust upstream Cypher ms | GDS ms | GDS boundary/status |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| path | 16384 | dijkstra | 895.8339 | 602.4638 | 570.1278 | 592.8899 | 3410.3669 | 49172.2965 | 24609.000 | server_query |
| path | 65536 | dijkstra | 26421.5672 | 9833.5134 | 9263.7111 | 9646.3618 | 54834.0747 | 817917.3286 | 433659.000 | server_query |

Upstream direct includes kernel/result conversion, with projection separate. Upstream Cypher includes parsing, policy checks, projection and ordinary query execution; full-path distance verification is a separate query outside that timer. Per-phase and process times are retained in native_details. Upstream uses a 256 MiB logical working allowance, excluding caller-owned input, final legacy tables after query return and protocol output conversion buffers; the container limit covers the whole process tree and file cache; Cypher additionally has a disclosed 24-hour deadline. These boundaries differ from historical participants. No common allocation strategy or timer boundary is implied.

Grustcat Cypher includes Grust parsing, semantic checks, planning, typed Arrow execution and result construction. Its documented query subset uses fused streaming path aggregation; it is not the materializing Grust reference executor or the same query text as Neo4j.

2 recorded cases. See [grust-acorn-upstream-completion.json](grust-acorn-upstream-completion.json) for complete validation, configuration, warmups, samples and hashes. Container/VM measurements are separate from the earlier macOS results.
