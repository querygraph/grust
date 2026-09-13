# Docker benchmark: Icebug, Icecat, Grustcat, Grustcat Cypher and Neo4j GDS

Neo4j 2026.08.0, official GDS 2026.08.1; algorithm concurrency 1.

Direct native columns are kernel milliseconds including Arrow result construction in Rust; Grustcat Cypher additionally includes query compilation and execution. Neo4j uses reported computeMillis except Dijkstra, which consumes the full-path stream and reports server query time including reconstruction and aggregation. Dijkstra mode: full-path. All included engines construct source-first node and cumulative-cost arrays for every reachable target and consume their entries. Native timers include path construction and aggregation; GDS server query time also includes Cypher execution. Equivalent output work does not imply identical runtimes or allocation strategies. Zero GDS compute times are below timer resolution.

PageRank uses uniform weighted ranks. Native stopping is L1 1e-8; GDS uses per-node tolerance 1e-10. GDS scores are normalized before validation. Equal stopping rules or equal iteration work are not claimed. Graph loading, projection and transport are excluded from compute timers.

| Graph | Nodes | Algorithm | Icebug ms | Icecat ms | Grustcat ms | Grustcat Cypher ms | GDS ms | GDS boundary/status |
|---|---:|---|---:|---:|---:|---:|---:|---|
| path | 16384 | dijkstra | 894.7204 | 602.4392 | 562.6431 | 585.0912 | 23565.000 | server_query |
| path | 65536 | dijkstra | 25974.8852 | 9854.6121 | 9349.5023 | 9662.0815 | 441251.000 | server_query |

Grustcat Cypher includes Grust parsing, semantic checks, planning, typed Arrow execution and result construction. Its documented query subset uses fused streaming path aggregation; it is not the materializing Grust reference executor or the same query text as Neo4j.

2 recorded cases. See [grust-frozen-baseline-completion.json](grust-frozen-baseline-completion.json) for complete validation, configuration, warmups, samples and hashes. Container/VM measurements are separate from the earlier macOS results.
