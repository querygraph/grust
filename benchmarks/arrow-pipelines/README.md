# Native Arrow relational profiles

This standalone, unpublished harness profiles the Grust indexed Cypher executor
and the DataFusion 55 foundation on graph-shaped relational work. It does not
change either executor or the active backend benchmarks.

The deterministic fixture has integer properties, selected isolates, self-loops
and distinct edge identities. Fanout larger than the active vertex count also
creates parallel edges. Three workloads measure a filtered node aggregate,
one-hop aggregate and two-hop trail aggregate. Each result must match a separate
integer-coordinate oracle. SQL excludes reuse of the same edge identity in the
two-hop query and coalesces an empty sum to zero to match the reference Cypher semantics. The initial Grust empty-sum
mismatch is retained in [correctness evidence](evidence/c3bd9fb/README.md).
These rewrites are disclosed in every output; this is not automatic Cypher
lowering and does not establish equivalence beyond the fixtures and workloads.

```sh
cargo test --manifest-path benchmarks/arrow-pipelines/Cargo.toml --locked
cargo clippy --manifest-path benchmarks/arrow-pipelines/Cargo.toml --locked --all-targets -- -D warnings
cargo build --release --manifest-path benchmarks/arrow-pipelines/Cargo.toml --locked
benchmarks/arrow-pipelines/target/release/grust-arrow-pipeline-profile 20000 8 3
```

Arguments are positive node count, fanout and repetitions. Preparation events
separate fixture creation, typed indexing, graph-to-Arrow conversion and session
registration. Query timing includes parsing/planning, execution and complete
result consumption; preparation is not silently amortized into that figure.
Engine order alternates by repetition. Retain first-use observations, all errors,
unsupported outcomes and mismatches. A nonzero outcome produces a nonzero exit.
There is no load deadline or outer time limit in the harness.

The graph, typed index and Arrow representation coexist. The 256 MiB DataFusion
working pool (spill disabled) is not a process RSS cap; it excludes retained
input and does not bound the Cypher executor. These are disclosed distinct
execution classes, not equal-memory backend rankings. Use an external monitored
process envelope when increasing fixture size. Record host, toolchain, binary
hash and command alongside the JSON-lines output. No database throughput or
universal speed claim follows from these local profiles.

The binary embeds its build's repository commit and dirty state. Qualifying
measurements require a clean source stamp and a fresh source-pinned build. The
build script watches repository source and Git state, including worktree Git
paths; a runtime checkout hash alone is not binary provenance. Commit Cargo.lock
before collecting qualified optimized measurements.

## Typed Cypher scan profile (unreleased bridge)

The `cypher_scan` binary runs the same parsed-language workload through indexed
Cypher and typed DataFusion 55 lowering:

```sh
cargo build --release --locked --manifest-path benchmarks/arrow-pipelines/Cargo.toml --bin cypher_scan
benchmarks/arrow-pipelines/target/release/cypher_scan 100000 3
```

Arguments are node count and nonzero trial count. The fixture has no edges and
one integer bucket property (`node ordinal % 16`). The query filters bucket 3
and returns count; its expected answer is computed independently from the node
count. Every trial retains its answer, outcome and elapsed time. Engine order
alternates; there is no warmup or query deadline. Errors terminate with a JSON
error record and nonzero exit; preserve stderr and process status externally.

This measures prepared-input queries, each including parsing, planning,
execution and complete scalar result consumption. Fixture construction, index
construction, and Arrow conversion/registration are reported separately. Both
representations coexist in the process. The DataFusion pool admits 256 MiB with
spill disabled; this is not a process-memory cap or equivalent to an indexed
Cypher policy. Target partitions is four, but this fixture registers one batch
and does not imply four scan partitions. Snapshot/backend capture, network
transport, algorithm kernels and automatic route selection are not measured.
Record source, binary hash, host, compiler, process memory and all raw output
with each run; do not combine these receipts with the earlier SQL profiles.

### Fixed-length Cypher path profile

`cargo run --release --bin cypher_paths -- <nodes> <repeats> <hops>` profiles
prepared indexed and typed DataFusion execution for two or three hops on a
parallel-edge ring. An independent count oracle covers physical edge reuse on
small rings. Preparation is separately timed, errors/unsupported/mismatches are
retained, and no query deadline is set. See
[evidence/cypher-paths-100822f](evidence/cypher-paths-100822f) for the first pinned
run and its memory, output-admission and interpretation boundaries.

### Cold-representation Cypher profile

`cypher_end_to_end <nodes> <repeats>` compares preparation plus one scan/count
query from the same immutable row graph. Every trial creates and drops its own
index or Arrow tables and DataFusion engine. Report preparation, query and total
time separately; teardown and fixture construction are excluded. Both routes
return portable rows and are checked against an independent arithmetic oracle,
including output columns. Route order alternates, and errors, unsupported results
and mismatches are retained while subsequent trials continue.

DataFusion uses its 256 MiB tracked pool, no spill, a four-partition target and
one input partition, plus one-row/1,024-byte output limits. Indexed execution has
no equivalent memory admission. Neither route has a deadline. These deliberately
disclosed differences prevent interpreting this profile as resource-equivalent
comparison or an automatic-routing threshold. Existing prepared-input profiles
remain separate and unchanged. Qualify empty/boundary fixtures before large runs.
