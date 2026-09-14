# Fixed-path Cypher profile

Source `100822f2377c6b3a2aa3bf8ba5f7ed8880d110bd`, clean optimized build on
Capitola. Clippy passed with warnings denied. All **84 oracle checks passed**
(two routes × three trials × seven sizes × two path lengths). No query deadline.

Fixture: a directed ring with two physical parallel edges per step. The oracle
accounts for edge reuse on one- and two-node rings. Nodes: 0, 1, 2, 3, 17,
10,000 and 100,000. Each case runs in a separate process; route order alternates
between trials. No separate warmup; these three-trial medians are descriptive.

| Hops | Nodes | Indexed query, s | DataFusion query, s | Arrow preparation, s |
|---|---:|---:|---:|---:|
| 2 | 17 | 0.000092167 | 0.001754917 | 0.000469667 |
| 2 | 10,000 | 0.020899541 | 0.003562625 | 0.006189750 |
| 2 | 100,000 | 0.247736083 | 0.018985167 | 0.069052041 |
| 3 | 17 | 0.000121125 | 0.002500333 | 0.000463625 |
| 3 | 10,000 | 0.043092708 | 0.005821750 | 0.005851292 |
| 3 | 100,000 | 0.460961167 | 0.034406917 | 0.067612417 |

Queries include parsing, planning, execution and portable result consumption.
DataFusion additionally enforces one-row/1,024-byte output limits; indexed
admission is unbounded. DataFusion uses a 256 MiB tracked pool with spill disabled,
not a process RSS cap. Graph, index and Arrow inputs coexist outside that pool.
Arrow preparation includes conversion, graph validation, ordinal allocation and
engine construction; fixture/index costs are separate in raw JSONL. One input
batch does not mean four actual scan partitions despite a target of four.
`/usr/bin/time -l` stderr retains whole-process peak RSS, not per-route memory.

Small-fixture indexed execution is faster; the larger prepared DataFusion queries
are faster in this profile. This does not establish a general routing threshold,
backend comparison, resource-policy parity or arbitrary-path performance.

The archive contains exact driver/commands, status, per-case JSONL/stderr and
build log. Unsupported, mismatch and error outcomes are distinct; the driver
continues all cases and marks final qualification unsuccessful on any failure.
Preserved native binary: `/tmp/grust-cypher-path-runs/20260914T193346Z/cypher_paths`.
SHA-256: `8446f4e5ac7790efd572276b06394dbc402d89bdf79d08f7f1db1382a986f68a`.
The downloaded binary hash was also verified; binaries are not committed.
