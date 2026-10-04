# F2a: native Grust 0.24 WCC plan

Status: ACK; execution and the final result are pending. Expected evidence is
`F2a/Native024/README.md` under this review directory. Root owns the wheel build,
input admission, engine launches, full physical comparison, retention and final
closure. This document publishes the protocol without a benchmark verdict.

## Sources and execution

- Nutmeg frontend and fresh optimized wheel source:
  `querygraph/sail` `4b88c8fb4504ab1d2a896c9e49e4a09df4905bbb`, tree
  `89f3b77f12391de54afbe7c6cdad1e008d1dc702`, registry Grust `0.24.0`.
- Existing optimized native Sail executable source:
  `9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3`. The exact Git diff from this
  commit to `4b88c8fb` is empty for `crates/`, `Cargo.toml`, `Cargo.lock`,
  `rust-toolchain.toml` and `.cargo/`. Frontend and compiled runtime pins remain
  separate; root binds the actual binary, wheel, client and source hashes.
- The fresh wheel build uses Rust 1.97.1 and the same native host ABI as the
  optimized Sail executable. Build evidence is planned at
  `/Volumes/Apo/graph-tests/results/sem-review-20261001/F2a-native-int64-build01`.
- Released Grust `v0.24.0` peels to
  `d2668ec7c7dbd7dd728e3976bcfaba3ae51d14ad`, tree
  `2674baf6d93109d5b6d1bf49a77a35b4bc7f115a`.
  [The separate Linux functional confirmation](../F1/Linux-v024/README.md)
  is published; it does not supply a native F2a timing verdict.
- Native macOS only. Set `NUTMEG_WORKERS=16` before each fresh process; request
  `concurrency=16` on every WCC call. Record the actual software pool and quota
  configuration, RSS/host observations, tools and client ABI. These declarations
  do not establish an OS memory cap or operation within 32 GiB.

## Inputs and series

Reuse the exact SSD Parquet bytes admitted for
[the completed native A5 campaign](../A5/MatchedNative/README.md), retaining its
[input provenance](../A5/MatchedNative/INPUTS.json). Root checks the full original
vertex domain and input identity once outside all engine clocks.

| Dataset | Vertices | Stored edge rows |
| --- | ---: | ---: |
| cit-Patents | 3,774,768 | 16,518,947 |
| graph500-24 | 8,870,942 | 260,379,520 |

Eight fresh series: two datasets × two ID representations × one or three
identical WCC calls. Every series has one server/session, one eager stage and
one projection; calls in a three-call series reuse that same graph and cache key.
The matrix produces sixteen distinct full Parquet exports.

| ID representation | Stage mapping | Calls per series |
| --- | --- | --- |
| int64 | node and edge mappings both `{"ids": "int64"}` | 1 and 3 |
| string control | decimal text inputs, default text identity mapping | 1 and 3 |

Use native server Parquet scan/select plans and `order="asStaged"`. Stage once,
then call `projectionStats` without an orientation argument, using its default
outgoing cache key. Reuse that key for WCC and record the graph revision,
projection identity/build observation and every read ID. WCC answers weak
components; this outgoing projection profile does not establish parity with
Sem's mirrored undirected CSR construction. Do not insert counts, extra
projections or intervening diagnostic actions into the measured pipeline.

One observed series per condition (`n=1`); this is not a replicated statistical
comparison. The file cache is already warmed by prior native work and is not
flushed. Preserve every result, timeout, error and refused admission separately;
no automatic retry or silent replacement of a cell.

## Clocks and validation

The primary pipeline starts before native Parquet read/select plan construction
and ends after the final complete server Parquet write. Record read-plus-stage,
projection and each call-plus-write span with their actual boundaries. Stage
consumes lazy input; each WCC result is lazy until its export. These observations
do not isolate read, CSR, kernel and sink into four exclusive clocks. The Sem
fields `read_parquet_s`, `csr_and_graph_s`, `algorithm_s` and `write_parquet_s`
remain null when unavailable. Preserve the enclosing clock and available
observations without summing overlapping spans or deriving a kernel by
subtraction. Retain whole-parent launch-through-wait separately, including its
imports and cleanup. Post-pipeline status, all oracles and cleanup are outside
the primary pipeline clock.

For every full output, outside measured clocks, preserve physical schemas and
file identities before adapting decimal text IDs. Require exactly the original
vertex domain, non-null unique IDs, full coverage and bidirectional partition
bijection against the separately closed, passed graphframes-rs A5 WCC reference
for that dataset. Component label representations may differ between text and
int64 staging; compare full partitions rather than requiring identical raw
labels. Retain all raw labels and record the adaptation. This is comparison to
the A5 reference, not a new official Graphalytics ground-truth or topology
certificate. All sixteen outputs must be checked; no sampled or hash-only
correctness verdict.

Root records owned process/server closure, actual input/source/client identity
before and after, full raw retention and its hash verification. Raw temporary
files and outputs use fresh SSD namespaces; their preserved copies and evidence
are planned at
`/Volumes/Apo/graph-tests/results/sem-review-20261001/F2a-native-024-run01`.
Results on this shared host are scoped observations and ratios; no absolute
performance, dispersion or dedicated-host claim follows from this plan.

## Existing evidence

The broader F2a item remains open until this scoped execution and its physical
oracles close. Preserve the historical Grust 0.23 preparation, source-only phase
and numerical studies, failed Rust/build attempts and original receipts. They
are not relabelled as 0.24 results. The old native A5 campaigns and the separate
Linux F1 verdict remain unchanged.
