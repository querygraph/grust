# Instrumented CPU diagnosis

The preserved 09fa41e binary ran the 20,000-node, fanout-8 fixture for three
repetitions. The observer sampled its stacks for five seconds; this window is
not a query deadline. The query process finished normally and all answers passed.
Instrumented timings are excluded from the uninstrumented baseline statistics.

The main-thread sample has 2,899 observations; 2,875 are in indexed Cypher.
Relationship expansion and subsequent filtering dominate the captured window.
An expansion subtree has 819 observations in `clone_row`, with property-map
cloning and allocator frames below it. Other large subtrees occur in
`filter_rows`, including candidate disposal. These overlapping stack counts
are diagnostic observations, not additive or full-run CPU percentages.

This motivates sharing immutable node/edge bindings across candidate copies.
It does not prove a proposed optimization faster; that requires a separate
source-pinned run with exact oracle and resource checks.
