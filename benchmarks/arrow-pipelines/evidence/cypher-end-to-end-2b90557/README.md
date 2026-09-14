# Cold-representation Cypher profile

Source `2b90557caecf0870f786b5c79885436ae104b519`, Capitola. Release build and
warnings-denied Clippy passed. All 42 oracle checks passed: seven fixture sizes,
three alternating trials of each route. Raw outcomes, exact commands, binary
hash and qualification logs are retained alongside this file.

Each trial starts from the same immutable row graph and creates only its own
index or Arrow representation. Preparation includes engine creation and Arrow
registration for DataFusion. Query time includes parsing, planning, execution
and portable result collection. Fixture construction and teardown are excluded.
No deadline was applied. DataFusion uses a 256 MiB tracked pool, spill disabled,
four target partitions and one input partition, with a one-row/1,024-byte output
limit. Indexed execution lacks an equivalent memory limit. Neither this profile
nor its ratios establishes a resource-equivalent comparison or routing threshold.

| Nodes | Indexed median total (s) | DataFusion median total (s) |
| ---: | ---: | ---: |
| 17 | 0.000056958 | 0.000664209 |
| 100,000 | 0.136324708 | 0.041599458 |
| 1,000,000 | 1.416441708 | 0.845291083 |

For one million nodes, median preparation is 0.099116375 seconds for the index
and 0.841961916 seconds for Arrow/engine registration. Median query time is
1.323659375 and 0.003329167 seconds respectively. Medians of phases need not sum
to the median total. Prepared-query speed alone would omit most of this
DataFusion route's measured cost. Small-fixture ordering differs, and only this
scan/count workload is measured. Full policy mapping, provider authority,
additional shapes, warm reuse and cost-based routing remain unqualified.
