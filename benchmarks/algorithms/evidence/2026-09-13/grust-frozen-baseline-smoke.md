# Docker benchmark: Icebug, Icecat, Grustcat, Grustcat Cypher and Neo4j GDS

Neo4j 2026.08.0, official GDS 2026.08.1; algorithm concurrency 1.

Direct native columns are kernel milliseconds including Arrow result construction in Rust; Grustcat Cypher additionally includes query compilation and execution. Neo4j uses reported computeMillis except Dijkstra, which consumes the full-path stream and reports server query time including reconstruction and aggregation. Dijkstra mode: full-path. All included engines construct source-first node and cumulative-cost arrays for every reachable target and consume their entries. Native timers include path construction and aggregation; GDS server query time also includes Cypher execution. Equivalent output work does not imply identical runtimes or allocation strategies. Zero GDS compute times are below timer resolution.

PageRank uses uniform weighted ranks. Native stopping is L1 1e-8; GDS uses per-node tolerance 1e-10. GDS scores are normalized before validation. Equal stopping rules or equal iteration work are not claimed. Graph loading, projection and transport are excluded from compute timers.

| Graph | Nodes | Algorithm | Icebug ms | Icecat ms | Grustcat ms | Grustcat Cypher ms | GDS ms | GDS boundary/status |
|---|---:|---|---:|---:|---:|---:|---:|---|
| path | 128 | bfs | 0.0071 | 0.0197 | 0.0191 | 0.0347 | 1.000 | reported_compute |
| path | 128 | dijkstra | 0.1364 | 0.0685 | 0.0577 | 0.0941 | 14.000 | server_query |
| path | 128 | wcc | 0.0223 | 0.0105 | 0.0186 | 0.0443 | 0.000 | reported_compute |
| path | 128 | scc | 0.0477 | 0.0208 | 0.0198 | 0.0507 | 0.000 | reported_compute |
| path | 128 | pagerank | 0.4454 | 0.1499 | 0.1546 | 0.1739 | 75.000 | reported_compute |
| hub | 128 | bfs | 0.0086 | 0.0155 | 0.0207 | 0.0565 | 0.000 | reported_compute |
| hub | 128 | dijkstra | 0.0497 | 0.0243 | 0.0261 | 0.0821 | 5.000 | server_query |
| hub | 128 | wcc | 0.0297 | 0.0142 | 0.0146 | 0.0492 | 0.000 | reported_compute |
| hub | 128 | scc | 0.0358 | 0.0200 | 0.0190 | 0.0597 | 0.000 | reported_compute |
| hub | 128 | pagerank | 0.4067 | 0.1468 | 0.1754 | 0.1751 | 43.000 | reported_compute |
| clusters | 128 | bfs | 0.0032 | 0.0191 | 0.0165 | 0.0513 | 0.000 | reported_compute |
| clusters | 128 | dijkstra | 0.0400 | 0.0230 | 0.0249 | 0.0644 | 4.000 | server_query |
| clusters | 128 | wcc | 0.0327 | 0.0112 | 0.0126 | 0.0404 | 0.000 | reported_compute |
| clusters | 128 | scc | 0.0428 | 0.0219 | 0.0226 | 0.0552 | 0.000 | reported_compute |
| clusters | 128 | pagerank | 0.4586 | 0.1611 | 0.1752 | 0.1907 | 44.000 | reported_compute |
| layered | 128 | bfs | 0.0086 | 0.0151 | 0.0238 | 0.0572 | 0.000 | reported_compute |
| layered | 128 | dijkstra | 0.0649 | 0.0414 | 0.0392 | 0.0722 | 4.000 | server_query |
| layered | 128 | wcc | 0.0309 | 0.0144 | 0.0142 | 0.0467 | 0.000 | reported_compute |
| layered | 128 | scc | 0.0540 | 0.0215 | 0.0183 | 0.0723 | 0.000 | reported_compute |
| layered | 128 | pagerank | 0.3437 | 0.1234 | 0.1266 | 0.1427 | 20.000 | reported_compute |
| uniform | 128 | bfs | 0.0131 | 0.0212 | 0.0221 | 0.0525 | 0.000 | reported_compute |
| uniform | 128 | dijkstra | 0.0661 | 0.0498 | 0.0403 | 0.0801 | 5.000 | server_query |
| uniform | 128 | wcc | 0.0325 | 0.0240 | 0.0184 | 0.0546 | 0.000 | reported_compute |
| uniform | 128 | scc | 0.0544 | 0.0396 | 0.0270 | 0.0609 | 0.000 | reported_compute |
| uniform | 128 | pagerank | 0.1683 | 0.0816 | 0.0888 | 0.1261 | 52.000 | reported_compute |
| rmat | 128 | bfs | 0.0127 | 0.0187 | 0.0175 | 0.0559 | 0.000 | reported_compute |
| rmat | 128 | dijkstra | 0.0696 | 0.0415 | 0.0346 | 0.0744 | 4.000 | server_query |
| rmat | 128 | wcc | 0.0341 | 0.0221 | 0.0209 | 0.0482 | 0.000 | reported_compute |
| rmat | 128 | scc | 0.0450 | 0.0367 | 0.0428 | 0.0676 | 0.000 | reported_compute |
| rmat | 128 | pagerank | 0.1558 | 0.0705 | 0.0695 | 0.1062 | 96.000 | reported_compute |

Grustcat Cypher includes Grust parsing, semantic checks, planning, typed Arrow execution and result construction. Its documented query subset uses fused streaming path aggregation; it is not the materializing Grust reference executor or the same query text as Neo4j.

30 recorded cases. See [grust-frozen-baseline-smoke.json](grust-frozen-baseline-smoke.json) for complete validation, configuration, warmups, samples and hashes. Container/VM measurements are separate from the earlier macOS results.
