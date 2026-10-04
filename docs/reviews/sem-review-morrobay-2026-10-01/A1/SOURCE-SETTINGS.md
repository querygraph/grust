# A1: graphframes-rs source and settings audit

Read-only source inspection for the Morrobay A1 preparation. This audit did
not build a binary, launch a container, run an algorithm, or change Sail.
Execution and correctness verdicts belong to the separate A1 receipts.

## Pins and build contract

The inspected checkout is detached and clean at
`b4da56dabe20bba8e29563e06acc5179b2113ce3`, the runtime commit recorded by
the published cit-Patents receipts. Root fetched that exact SHA after the
initial clone lacked its historical object. Published reports are at
`ba2fdd8f51fa7fafdca15012d2741f5f8d80c024`.

The adjacent [source-settings-audit.json](source-settings-audit.json) records
SHA-256 bridges: Cargo.toml, Cargo.lock, CLI, WCC, PR, shortest paths, Pregel,
options, and all three benchmark scripts are byte-identical between the two
pins. The checkpointer differs by an added `read_all` method in b4da;
its existing write/read methods are unchanged. This is a scoped source
bridge, not a claim that the whole repositories or historical binaries match.

- [Cargo.toml](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/Cargo.toml):
  package edition 2024; default feature `cli`; binary `graphframes`;
  CLI installs SnMalloc. No repository Rust toolchain or release-profile
  override was found. Upstream CI requests `stable`.
- [Cargo.lock](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/Cargo.lock):
  DataFusion 55.1.0, Arrow 59.3.0, SnMalloc 0.7.4, Tokio 1.52.3,
  rand 0.9.2. These are registry dependencies, without a Cargo patch.
  The locked [DataFusion package](https://docs.rs/crate/datafusion/55.1.0/source/Cargo.toml)
  declares minimum Rust 1.94.0.
- Default [SnMalloc build](https://docs.rs/crate/snmalloc-sys/0.7.4/source/build.rs)
  uses CMake and C++20; no `usecxx17` feature is requested here.
  A1 should retain compiler/Cargo/CMake/C++ versions, image digest,
  exact build command and binary hash. A locked release build with its own
  target directory preserves the source pin; historical compiler flags and
  binary hashes are absent from the published receipts.

## CLI resource and input contract

Actual source line numbers below refer to the pinned raw files.

| Setting | Pinned behavior |
|---|---|
| Memory | `--max-memory` defaults to `4G`; `30G` means exactly 30 GiB / 32,212,254,720 bytes. |
| Pool | `FairSpillPool`; this bounds reservations tracked by the pool, not total process RSS. |
| Parallelism | `--num-workers` defaults to 2 and sets DataFusion `target_partitions`; historical receipts use 16. |
| Runtime threads | Tokio main uses its default multithread runtime; `num_workers` does not directly set its thread count. Record container CPU limits and relevant environment separately. |
| Join preference | `GraphFramesConfig::prefer_smj=true` sets `prefer_hash_join=false` in the base and algorithm contexts. This is a planning preference, not physical-plan proof for every join. |
| Scratch | `--checkpoint-dir` defaults to `gf_workdir`; creates `checkpoints/` and `df-spill/`. |
| Spill directory bound | `--max-temp-file` defaults to `200G`, meaning 200 GiB; the published runner supplies no override. |
| Inputs | Parquet default; signed Int64 vertex/endpoint columns. CLI accepts alternate column names; published runner maps `source`/`target` to `src`/`dst`. |
| Output | Caller supplies a directory `file://` URI; results are Parquet. |
| Undirected/weighted input | Symmetrization is opt-in. `--weighted` retains the weight column; the shortest-path implementation does not consume it. |

[CLI arguments and context](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/src/main.rs#L65-L155),
[memory parser and context](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/src/main.rs#L448-L506),
[join options](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/src/utils/options.rs#L5-L20),
[schema-only constructor](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/src/lib.rs#L81-L104).
`SessionConfig::from_env()` admits additional DataFusion environment settings;
resolved configuration belongs in the run receipt.

## Algorithm semantics

**WCC.** CLI requires `--seed`; the published runner supplies 42. The
library's `use_labels_as_components` defaults to true; the CLI exposes no
switch to turn it off. Output is `id, component`, with each component's
minimum original vertex ID and isolates included. Randomized contraction
uses rand `StdRng`, nonzero GF(2^64) affine coefficients, ordinary `MIN`
over hashed neighbor priorities, forward maps and a backward pass.
Seed 42 alone does not match another generator's random work. WCC uses
plain Parquet `push`, rather than the presorted Pregel checkpoints. The
final canonical-label aggregation/write and checkpoint purge are inside
the process boundary. [WCC source](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/src/algorithm/connectivity/connected_components.rs#L154-L197),
[forward and final stages](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/src/algorithm/connectivity/connected_components.rs#L247-L396).

**PageRank.** Published runner requests `--max-iter 10 --tol 0.01`, with
default reset probability 0.15. This is incremental GraphX-style Pregel
PR: accumulate damped incoming deltas, filter sending vertices by delta
greater than tolerance, and normalize the final rank sum. Positive
`max_iter` suppresses early voting but retains the sending filter;
`max_iter=0` uses activity voting. Sinks remain vertices; no uniform
dangling-mass redistribution appears in this recurrence. It does not
implement the LDBC fixed-step power recurrence used in the Pecan semantic
checks. Output is `id, pagerank`. [PR source](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/src/algorithm/centrality/pagerank.rs#L105-L242).

**Shortest paths.** CLI is `shortest-path --landmarks <IDs>`; default
direction is from each landmark along outgoing edges. `--to-landmarks`
reverses edges. Each landmark gets an Int32 `dist_<ID>` column, initialized
to zero at that landmark and `i32::MAX` elsewhere; messages add one hop
and reduce with minimum. This is per-landmark unweighted distance,
not weighted DOUBLE SSSP or one nearest-source distance column.
The runner chooses a single cit-Patents ID 750000 by multiplying rounded
catalog metadata 3,000,000 by 0.25, without looking up a vertex percentile
or verifying membership. Admission of today's source should be recorded
outside the algorithm timer. [Shortest-path source](https://github.com/SemyonSinchenko/graphframes-rs/blob/b4da56dabe20bba8e29563e06acc5179b2113ce3/src/algorithm/connectivity/shortest_paths.rs#L44-L176),
[command construction](https://github.com/SemyonSinchenko/graphframes-rs/blob/ba2fdd8f51fa7fafdca15012d2741f5f8d80c024/benches/python/main.py#L126-L151).

## Historical measurement boundary and A1 evidence

Published cit-Patents WCC/PR/SP receipts all declare b4da, `30G`, 16
partitions, unweighted directed inputs, one warmup and five measured fresh
processes. Their medians are external reported values: WCC 4.708698 s,
PR 4.045853 s, SP 0.900550 s. [WCC receipt](https://github.com/SemyonSinchenko/graphframes-rs/blob/ba2fdd8f51fa7fafdca15012d2741f5f8d80c024/benches/results/wcc/XS/cit-Patents/max_mem_30G_workers_16/benchmark.json),
[PR receipt](https://github.com/SemyonSinchenko/graphframes-rs/blob/ba2fdd8f51fa7fafdca15012d2741f5f8d80c024/benches/results/pagerank/XS/cit-Patents/max_mem_30G_workers_16/benchmark.json),
[SP receipt](https://github.com/SemyonSinchenko/graphframes-rs/blob/ba2fdd8f51fa7fafdca15012d2741f5f8d80c024/benches/results/sp/XS/cit-Patents/max_mem_30G_workers_16/benchmark.json).

The timer starts immediately before `Popen` and stops after `wait`:
startup, input reads, algorithm, output materialization and child cleanup
are included; build/download and post-exit analysis are excluded.
Peak RSS is maximum sampled `VmRSS`, despite the monitor's `VmHWM`
comment. Disk is baseline-subtracted logical workdir file lengths; the
baseline is taken after launch, so early writes may be missed.
[Runner](https://github.com/SemyonSinchenko/graphframes-rs/blob/ba2fdd8f51fa7fafdca15012d2741f5f8d80c024/benches/python/main.py#L174-L187),
[monitor](https://github.com/SemyonSinchenko/graphframes-rs/blob/ba2fdd8f51fa7fafdca15012d2741f5f8d80c024/benches/python/monitor.py#L88-L164).

The historical harness has no timeout or output validation and aborts
before final JSON on a nonzero exit. Future matched algorithm experiments
need durable per-cell failures, closed-container evidence, exact retained
output and input hashes, and an oracle verdict. Matching the CLI tuple establishes settings fidelity;
semantic equivalence and today's timing require separate evidence.
Historical input hashes, binary hashes and compiler flags are unavailable;
shared Morrobay timings cannot become dedicated-host absolute results.
