# Typed Cypher prepared-scan observations

Clean source `771cb89`, Capitola; exact source, binary hash, host and driver in
`status.json` and `driver.py`. Seven fixture sizes, three trials per route,
alternating order, no warmups or query deadline. All 42 answer checks passed.
Raw trial values, preparation times, stderr and process resource observations
are retained. These routes do not enforce equivalent query-memory policies.

| Nodes | Indexed median query seconds | Typed DataFusion median query seconds | Arrow conversion/registration seconds |
| ---: | ---: | ---: | ---: |
| 17 | 0.000090916 | 0.000629917 | 0.000566084 |
| 100,000 | 0.144597875 | 0.001127250 | 0.049827584 |
| 1,000,000 | 1.476990583 | 0.004989333 | 0.974918291 |

Query time includes parsing, planning and result consumption over prepared
inputs. Index preparation is separate too: 0.007180875 s at 100k nodes and
0.106594833 s at 1M. Fixture creation is separate. Both representations coexist;
process RSS is not per-engine memory. Single-batch input and a four-partition
target do not establish four independent scan partitions. Three-trial medians
are descriptive, not confidence estimates or universal backend performance.

The small fixture favors indexed execution; larger prepared scans favor this
DataFusion route. Conversion costs materially affect one-shot execution. These
observations do not establish an automatic routing threshold, graph-join
performance, backend capture throughput, or policy parity.
