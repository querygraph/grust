# Docker benchmark: Icebug, Icecat, Grustcat, Grustcat Cypher, upstream Grust and Neo4j GDS

Neo4j 2026.08.0, official GDS 2026.08.1; algorithm concurrency 1.

Direct native columns are kernel milliseconds including Arrow result construction in Rust; Grustcat Cypher additionally includes query compilation and execution. Neo4j uses reported computeMillis except Dijkstra, which consumes the full-path stream and reports server query time including reconstruction and aggregation. Dijkstra mode: full-path. All included engines construct source-first node and cumulative-cost arrays for every reachable target and consume their entries. Native timers include path construction and aggregation; GDS server query time also includes Cypher execution. Equivalent output work does not imply identical runtimes or allocation strategies. Zero GDS compute times are below timer resolution.

PageRank uses uniform weighted ranks. Native stopping is L1 1e-8; GDS uses per-node tolerance 1e-10. GDS scores are normalized before validation. Equal stopping rules or equal iteration work are not claimed. Graph loading, projection and transport are excluded from compute timers.

| Graph | Nodes | Algorithm | Icebug ms | Icecat ms | Grustcat ms | Grustcat Cypher ms | Grust upstream direct ms | Grust upstream Cypher ms | GDS ms | GDS boundary/status |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| path | 1024 | bfs | 0.0170 | 0.0281 | 0.0258 | 0.0623 | 0.0469 | 5.9388 | 1.000 | reported_compute |
| path | 1024 | dijkstra | 3.5818 | 2.3643 | 2.0676 | 2.2253 | 13.4256 | 198.5933 | 78.000 | server_query |
| path | 1024 | wcc | 0.0456 | 0.0290 | 0.0254 | 0.0650 | 0.1237 | 6.2786 | 0.000 | reported_compute |
| path | 1024 | scc | 0.1830 | 0.0622 | 0.0492 | 0.0789 | 0.2384 | 6.4688 | 0.000 | reported_compute |
| path | 1024 | pagerank | 1.4344 | 1.0079 | 0.9781 | 0.9397 | 7.8276 | 24.7251 | 49.000 | reported_compute |
| hub | 1024 | bfs | 0.0249 | 0.0325 | 0.0376 | 0.0687 | 0.0626 | 7.9369 | 0.000 | reported_compute |
| hub | 1024 | dijkstra | 0.2680 | 0.1144 | 0.1066 | 0.1551 | 0.4729 | 9.4425 | 4.000 | server_query |
| hub | 1024 | wcc | 0.0489 | 0.0291 | 0.0300 | 0.0720 | 0.1382 | 8.0777 | 0.000 | reported_compute |
| hub | 1024 | scc | 0.1090 | 0.0642 | 0.0507 | 0.0869 | 0.3155 | 8.5724 | 0.000 | reported_compute |
| hub | 1024 | pagerank | 1.5218 | 1.1231 | 1.1469 | 1.1565 | 9.2591 | 30.2763 | 38.000 | reported_compute |
| clusters | 1024 | bfs | 0.0038 | 0.0183 | 0.0221 | 0.0623 | 0.0059 | 7.5530 | 0.000 | reported_compute |
| clusters | 1024 | dijkstra | 0.0682 | 0.0386 | 0.0264 | 0.0736 | 0.0642 | 5.4629 | 2.000 | server_query |
| clusters | 1024 | wcc | 0.0611 | 0.0428 | 0.0312 | 0.0666 | 0.1714 | 8.1559 | 0.000 | reported_compute |
| clusters | 1024 | scc | 0.1286 | 0.0961 | 0.0541 | 0.0848 | 0.3106 | 8.4574 | 0.000 | reported_compute |
| clusters | 1024 | pagerank | 1.7018 | 1.2397 | 1.2952 | 1.1888 | 10.2942 | 32.4946 | 52.000 | reported_compute |
| layered | 1024 | bfs | 0.0275 | 0.0344 | 0.0374 | 0.0931 | 0.0829 | 9.9957 | 0.000 | reported_compute |
| layered | 1024 | dijkstra | 0.4132 | 0.2211 | 0.1997 | 0.2401 | 0.7725 | 16.6258 | 6.000 | server_query |
| layered | 1024 | wcc | 0.0667 | 0.0437 | 0.0334 | 0.0783 | 0.2299 | 10.5049 | 0.000 | reported_compute |
| layered | 1024 | scc | 0.1696 | 0.0695 | 0.0564 | 0.0953 | 0.3906 | 11.2309 | 0.000 | reported_compute |
| layered | 1024 | pagerank | 1.5274 | 1.1283 | 1.1788 | 1.1236 | 10.1053 | 34.4948 | 29.000 | reported_compute |
| uniform | 1024 | bfs | 0.0618 | 0.0625 | 0.0548 | 0.0942 | 0.1879 | 21.6047 | 0.000 | reported_compute |
| uniform | 1024 | dijkstra | 0.4649 | 0.2835 | 0.2428 | 0.2954 | 0.7403 | 25.4983 | 4.000 | server_query |
| uniform | 1024 | wcc | 0.1084 | 0.0865 | 0.0747 | 0.1066 | 0.5232 | 22.4654 | 0.000 | reported_compute |
| uniform | 1024 | scc | 0.2053 | 0.1829 | 0.1380 | 0.1497 | 0.8277 | 22.9213 | 1.000 | reported_compute |
| uniform | 1024 | pagerank | 0.6710 | 0.6393 | 0.6706 | 0.6791 | 5.0968 | 35.0532 | 87.000 | reported_compute |
| rmat | 1024 | bfs | 0.0473 | 0.0544 | 0.0392 | 0.0886 | 0.1483 | 18.4714 | 0.000 | reported_compute |
| rmat | 1024 | dijkstra | 0.2977 | 0.1950 | 0.1603 | 0.2185 | 0.4768 | 19.5050 | 3.000 | server_query |
| rmat | 1024 | wcc | 0.1112 | 0.0722 | 0.0682 | 0.1077 | 0.4337 | 19.2283 | 0.000 | reported_compute |
| rmat | 1024 | scc | 0.1686 | 0.1429 | 0.1028 | 0.1417 | 0.7046 | 19.9342 | 0.000 | reported_compute |
| rmat | 1024 | pagerank | 0.5850 | 0.4850 | 0.5145 | 0.5142 | 3.8025 | 28.9544 | 97.000 | reported_compute |

Upstream direct includes kernel/result conversion, with projection separate. Upstream Cypher includes parsing, policy checks, projection and ordinary query execution; full-path distance verification is a separate query outside that timer. Per-phase and process times are retained in native_details. Upstream uses a 256 MiB working allowance; Cypher additionally has a disclosed 24-hour deadline. These boundaries differ from historical participants. No common allocation strategy or timer boundary is implied.

Grustcat Cypher includes Grust parsing, semantic checks, planning, typed Arrow execution and result construction. Its documented query subset uses fused streaming path aggregation; it is not the materializing Grust reference executor or the same query text as Neo4j.

30 recorded cases. See [grust-acorn-upstream-medium.json](grust-acorn-upstream-medium.json) for complete validation, configuration, warmups, samples and hashes. Container/VM measurements are separate from the earlier macOS results.
