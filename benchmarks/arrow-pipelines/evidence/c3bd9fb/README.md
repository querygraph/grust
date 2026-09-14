# Initial relational correctness qualification

Source: c3bd9fb64207826346bd05111f892931e4da6eea, clean embedded stamp.
Host: Capitola; debug build, not performance evidence. Three fixture unit tests
and warnings-denied Clippy passed. The debug linker warned about a large
`__eh_frame` section; this does not qualify optimized execution timings.

`explicit-args/` retains actual engine runs for `(nodes, fanout, repeats)` of
`(4,1,1)`, `(4,5,1)` and `(20,1,1)`. Exit statuses were 1, 0 and 1.
Sixteen of eighteen engine answers matched the independent oracle. Both failures
were indexed Cypher two-hop empty sums: actual `(0, null)`, expected `(0, 0)`.
The original harness reports these as errors because it required integer sums;
subsequent harness versions retain nullable answers and classify them as
mismatches. Do not rewrite these original receipts.

The [Cypher 25 aggregate reference](https://neo4j.com/docs/cypher-manual/25/functions/aggregating/)
specifies zero for null-only sums. Source inspection found null-on-empty logic
in both `projection::sum_return_values` and `read::streaming_aggregate`.
This is an outstanding compatibility defect, not an accepted oracle adjustment.

The three JSONL files immediately in this directory are earlier invocation
failures: zsh passed a space-containing argument as one argument. All exited 1
before configuration or engine execution. They are retained separately and are
not engine failures. Explicit positional arguments corrected the invocation.
