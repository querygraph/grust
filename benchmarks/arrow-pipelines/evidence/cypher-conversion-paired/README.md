# Paired conversion investigation

Three process pairs on Capitola alternate original binary `2b90557` and changed
binary `6544dc4`. Each process performs three alternating indexed/DataFusion
trials at one million nodes. All 36 oracle checks passed. Exact binary hashes,
commands, raw outcomes and execution script are retained here.

| Source | Route | Median preparation (s) | Median query (s) | Median total (s) |
| --- | --- | ---: | ---: | ---: |
| 2b90557 | indexed | 0.087526084 | 1.306310500 | 1.393836584 |
| 2b90557 | DataFusion | 0.846362625 | 0.003527750 | 0.849722125 |
| 6544dc4 | indexed | 0.088325000 | 1.304529500 | 1.383861250 |
| 6544dc4 | DataFusion | 0.715195666 | 0.002758416 | 0.717954082 |

Each median has nine trials. Phase medians need not sum to the median total.
The unchanged workload uses integer properties, so these measurements do not
isolate the separate string-clone removal. Limits and measurement boundaries
match the original profile; indexed and DataFusion memory contracts still differ.
This supports reduced conversion cost for this fixture, not backend throughput
or general automatic routing claims.

The [initial changed-source run](../cypher-conversion-6544dc4) retains one
million-node DataFusion memory-exhaustion error. Passing this investigation does
not erase that outcome or prove it resolved. Upstream DataFusion 55.1
`repartition/mod.rs` charges `batch.get_array_memory_size()` before queueing;
a rejected reservation invokes the spill writer, whose disabled-disk error
matches the observed message. Actual failing-plan and allocation coverage still
need diagnosis. Buffer sharing and queue timing are hypotheses, not findings.
