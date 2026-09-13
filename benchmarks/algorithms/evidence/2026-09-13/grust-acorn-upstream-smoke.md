# Docker benchmark: Icebug, Icecat, Grustcat, Grustcat Cypher, upstream Grust and Neo4j GDS

Neo4j 2026.08.0, official GDS 2026.08.1; algorithm concurrency 1.

Direct native columns are kernel milliseconds including Arrow result construction in Rust; Grustcat Cypher additionally includes query compilation and execution. Neo4j uses reported computeMillis except Dijkstra, which consumes the full-path stream and reports server query time including reconstruction and aggregation. Dijkstra mode: full-path. All included engines construct source-first node and cumulative-cost arrays for every reachable target and consume their entries. Native timers include path construction and aggregation; GDS server query time also includes Cypher execution. Equivalent output work does not imply identical runtimes or allocation strategies. Zero GDS compute times are below timer resolution.

PageRank uses uniform weighted ranks. Native stopping is L1 1e-8; GDS uses per-node tolerance 1e-10. GDS scores are normalized before validation. Equal stopping rules or equal iteration work are not claimed. Graph loading, projection and transport are excluded from compute timers.

| Graph | Nodes | Algorithm | Icebug ms | Icecat ms | Grustcat ms | Grustcat Cypher ms | Grust upstream direct ms | Grust upstream Cypher ms | GDS ms | GDS boundary/status |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| path | 128 | bfs | 0.0170 | 0.0225 | 0.0198 | 0.0647 | 0.0083 | 1.2793 | 0.000 | reported_compute |
| path | 128 | dijkstra | 0.1780 | 0.1150 | 0.0759 | 0.1364 | 0.3036 | 6.8262 | 7.000 | server_query |
| path | 128 | wcc | 0.0261 | 0.0208 | 0.0130 | 0.0488 | 0.0165 | 0.8642 | 0.000 | reported_compute |
| path | 128 | scc | 0.0542 | 0.0330 | 0.0180 | 0.0526 | 0.0330 | 0.9274 | 0.000 | reported_compute |
| path | 128 | pagerank | 0.4784 | 0.1517 | 0.1612 | 0.1724 | 1.1523 | 3.5988 | 45.000 | reported_compute |
| hub | 128 | bfs | 0.0084 | 0.0174 | 0.0173 | 0.0473 | 0.0091 | 1.0813 | 0.000 | reported_compute |
| hub | 128 | dijkstra | 0.0517 | 0.0354 | 0.0278 | 0.0671 | 0.0525 | 1.2616 | 3.000 | server_query |
| hub | 128 | wcc | 0.0283 | 0.0235 | 0.0132 | 0.0482 | 0.0184 | 1.0915 | 0.000 | reported_compute |
| hub | 128 | scc | 0.0408 | 0.0253 | 0.0197 | 0.0591 | 0.0425 | 1.1905 | 0.000 | reported_compute |
| hub | 128 | pagerank | 0.4156 | 0.1487 | 0.1569 | 0.1759 | 1.1644 | 3.9169 | 38.000 | reported_compute |
| clusters | 128 | bfs | 0.0035 | 0.0185 | 0.0153 | 0.0533 | 0.0051 | 1.0564 | 0.000 | reported_compute |
| clusters | 128 | dijkstra | 0.0423 | 0.0342 | 0.0228 | 0.0638 | 0.0354 | 1.1257 | 2.000 | server_query |
| clusters | 128 | wcc | 0.0355 | 0.0130 | 0.0141 | 0.0551 | 0.0243 | 1.1176 | 0.000 | reported_compute |
| clusters | 128 | scc | 0.0648 | 0.0297 | 0.0214 | 0.0567 | 0.0419 | 1.1327 | 0.000 | reported_compute |
| clusters | 128 | pagerank | 0.4764 | 0.1723 | 0.1831 | 0.1912 | 1.3119 | 4.2430 | 48.000 | reported_compute |
| layered | 128 | bfs | 0.0089 | 0.0245 | 0.0201 | 0.0516 | 0.0090 | 1.0630 | 1.000 | reported_compute |
| layered | 128 | dijkstra | 0.0707 | 0.0381 | 0.0361 | 0.0782 | 0.0800 | 1.7111 | 1.000 | server_query |
| layered | 128 | wcc | 0.0353 | 0.0158 | 0.0141 | 0.0451 | 0.0226 | 1.0999 | 0.000 | reported_compute |
| layered | 128 | scc | 0.0527 | 0.0207 | 0.0166 | 0.0573 | 0.0420 | 1.1368 | 0.000 | reported_compute |
| layered | 128 | pagerank | 0.3430 | 0.1277 | 0.1272 | 0.1434 | 0.9343 | 3.3893 | 22.000 | reported_compute |
| uniform | 128 | bfs | 0.0145 | 0.0209 | 0.0169 | 0.0544 | 0.0240 | 2.6376 | 0.000 | reported_compute |
| uniform | 128 | dijkstra | 0.0682 | 0.0439 | 0.0383 | 0.0811 | 0.0794 | 2.9989 | 3.000 | server_query |
| uniform | 128 | wcc | 0.0372 | 0.0265 | 0.0200 | 0.0556 | 0.0644 | 2.7597 | 0.000 | reported_compute |
| uniform | 128 | scc | 0.0540 | 0.0340 | 0.0294 | 0.0613 | 0.1032 | 2.7619 | 0.000 | reported_compute |
| uniform | 128 | pagerank | 0.1622 | 0.0804 | 0.0890 | 0.1215 | 0.6428 | 4.2724 | 51.000 | reported_compute |
| rmat | 128 | bfs | 0.0121 | 0.0267 | 0.0203 | 0.0507 | 0.0177 | 2.0706 | 0.000 | reported_compute |
| rmat | 128 | dijkstra | 0.0548 | 0.0442 | 0.0329 | 0.0753 | 0.0582 | 2.1866 | 2.000 | server_query |
| rmat | 128 | wcc | 0.0359 | 0.0245 | 0.0195 | 0.0549 | 0.0477 | 2.1122 | 0.000 | reported_compute |
| rmat | 128 | scc | 0.0454 | 0.0291 | 0.0298 | 0.0572 | 0.0777 | 2.5306 | 0.000 | reported_compute |
| rmat | 128 | pagerank | 0.1571 | 0.0736 | 0.0666 | 0.1093 | 0.4773 | 3.3303 | 44.000 | reported_compute |

Upstream direct includes kernel/result conversion, with projection separate. Upstream Cypher includes parsing, policy checks, projection and ordinary query execution; full-path distance verification is a separate query outside that timer. Per-phase and process times are retained in native_details. Upstream uses a 256 MiB working allowance; Cypher additionally has a disclosed 24-hour deadline. These boundaries differ from historical participants. No common allocation strategy or timer boundary is implied.

Grustcat Cypher includes Grust parsing, semantic checks, planning, typed Arrow execution and result construction. Its documented query subset uses fused streaming path aggregation; it is not the materializing Grust reference executor or the same query text as Neo4j.

30 recorded cases. See [grust-acorn-upstream-smoke.json](grust-acorn-upstream-smoke.json) for complete validation, configuration, warmups, samples and hashes. Container/VM measurements are separate from the earlier macOS results.
