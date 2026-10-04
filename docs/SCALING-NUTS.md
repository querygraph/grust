# Scaling Graph Nuts beyond the synthetic fixtures

## Finding

The optimized Nutmeg PageRank kernel is implemented as a GraphX-style delta
algorithm with a shrinking active frontier. The current large-graph failure is
earlier in the pipeline: Nutmeg cannot stage the graph within its memory
budget, so the PageRank kernel never starts.

These are two separate scaling questions and must be measured separately:

1. Can the graph be ingested and staged within the available memory and file
   limits?
2. Once staged, does the delta/frontier algorithm reduce iteration work as the
   residual shrinks?

## What is implemented

The implementation is in
`examples/extensions/vendor/nutmeg-graph/src/optimized/pagerank.rs` and is
exposed as `pagerankDelta`.

Each round maintains a residual (delta) vector. A tolerance-scaled threshold
selects active vertices. Only active sources traverse their adjacency lists
and emit messages. Target messages are reduced, residuals are updated, and
vertices can be reactivated when later messages exceed the threshold. The
kernel records active vertices, active edges, reactivations and residuals, then
runs a full fixed-point certificate before returning success.

The accompanying tests check that the delta result matches the reference
PageRank result and that frontier work is reduced on suitable fixtures. This
is the intended GraphX-style execution model: work follows the changing
frontier instead of scanning every edge on every iteration.

## What the large-graph failures show

Sem’s c5d.4xlarge runs used a 24 GB Sail memory budget.

- `cit-Patents` has about 3.7 million vertices and 16.5 million edges.
- Relational PageRank completed in about 14 seconds, with roughly 1.2 GB peak
  RSS and 0.7 GB written.
- Nutmeg failed while staging the edges. The error estimated about 11.6 GB of
  sort working space, including permutation storage, sort keys and a sorted
  copy of the edge rows.
- Graph500-24 has about 8.8 million vertices and 260.3 million edges.
- Relational PageRank completed in about 180 seconds, with roughly 7 GB peak
  RSS and 7 GB written.
- Nutmeg again failed during staging, this time while staging nodes and using
  almost the entire 8 GiB `NUTMEG_MEMORY_BYTES` budget.

These failures happen before `pagerankDelta` executes. Frontier sparsity cannot
reduce the temporary sort workspace required by the current staging path.

## Interpretation

The current POC demonstrates the algorithmic idea on its measured synthetic
fixtures, including frontier diagnostics and independent correctness checks.
It does not establish Nutmeg scalability for multi-million-vertex or
hundreds-of-millions-of-edge graphs.

The immediate Nutmeg bottleneck is graph materialization:

- staging sorts the input and creates large temporary representations;
- sort keys and sorted copies dominate the reported workspace;
- the graph is refused before the native kernel can run;
- under strong memory pressure, DataFusion may also create many temporary
  files, so file-descriptor limits must be sized for large runs (`ulimit -n
  30000` is a useful starting point).

The relational path currently handles these inputs within the reported memory
envelope, though Sem’s comparison indicates that its naive relational PageRank
is about two to three times slower than his `graphframes-rs` implementation.
That timing is a separate implementation comparison; it does not invalidate
the staging diagnosis.

## Required next work

1. **Bound Nutmeg staging memory.** Avoid a full sorted copy where graph
   identity permits preserving input order. The staging error explicitly
   identifies `order = asStaged` as a possible no-sort path; it must only be
   used when the resulting graph representation remains deterministic and
   valid.
2. **Stream or partition staging.** Replace one large sort workspace with
   bounded partitions, spill files and deterministic merges. Account for
   permutation, keys, sorted copies and spill buffers separately.
3. **Separate staging from kernel measurements.** Record graph-load time,
   staging peak RSS, staging disk and file count independently from
   `pagerankDelta` iteration time, frontier edges and algorithm working set.
4. **Add real fixtures.** Reproduce `cit-Patents` and Graph500-24 with the
   same graph files and memory envelope. Preserve every outcome: pass,
   mismatch, admission refusal, unavailable memory sample and timeout.
5. **Rerun the optimized kernel after staging succeeds.** Confirm that active
   vertices and active edges shrink, that reactivation remains bounded, and
   that the final certificate matches the reference result.
6. **Keep relational and native paths comparable.** Use the same input,
   output contract, tolerance, correctness check and end-to-end boundary.
   Publish staging and algorithm costs as separate components rather than
   attributing a pre-kernel staging failure to PageRank arithmetic.

## Scope of the current claim

The defensible claim today is narrow: Nutmeg contains a correct
delta/frontier PageRank implementation, but its current graph staging path is
not qualified for large real-world graphs. Large-graph Nutmeg performance is
unavailable until bounded-memory staging is implemented and measured.
