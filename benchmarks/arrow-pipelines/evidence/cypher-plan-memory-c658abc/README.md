# Physical-plan memory diagnostic

Source `c658abce7ff26101f1ea75474098fac002e21de9`, Capitola. Optimized build
and warnings-denied Clippy passed. Commands, each at nice 10:

```
cypher_plan_memory 1000000 4 10
cypher_plan_memory 1000000 1 10
```

Both processes exited zero and all 20 arithmetic-oracle checks passed. This
instrumented diagnostic supplies no timing comparison. Each execution used the
same 256 MiB tracked memory pool, no spill and a 4,096-row target batch size.

The four-target-partition plan places `RoundRobinBatch(4)` repartitioning before
filtering and partial aggregation; the single-partition plan has no repartition
operator. Both receive one input batch. The complete six-column batch reports
38,076,668 bytes through `get_array_memory_size`; its 4,096-row slice reports
the same amount because the underlying allocations are shared. That full input
measurement is not a measurement of each projected batch inside the plan.

Upstream repartition accounting charges array memory on queue insertion. Shared
capacity and producer/consumer scheduling merit investigation, but this run did
not reproduce the [retained failure](../cypher-conversion-6544dc4) and does not
establish its cause. No memory limit, spill policy or default parallelism was
changed in Grust. Exact plan text and all diagnostic results remain alongside
this file.
