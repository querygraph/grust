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
