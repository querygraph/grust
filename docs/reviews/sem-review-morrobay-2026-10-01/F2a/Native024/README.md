# Native Grust 0.24 WCC baseline

Eight native series and all sixteen full outputs passed. A separate signed-ID
and isolated-vertex smoke passed all three outputs. This is the current Banda
baseline through the Nutmeg native extension, with `order="asStaged"`.

## Findings

These are observed intervals supporting ratios on shared Morrobay, with one
series per condition and a previously warmed file cache. They are not a
replicated or dedicated-host performance result. The continuous pipeline starts
before the Parquet read/select plans and ends after the last full Parquet export.

| Dataset | Staged IDs | One-call pipeline, s | Three-call pipeline, s | One-call internal projection build, s |
| --- | --- | ---: | ---: | ---: |
| cit-Patents | int64 | 1.71 | 2.37 | 0.71 |
| cit-Patents | string | 7.57 | 8.38 | 6.54 |
| graph500-24 | int64 | 9.82 | 13.00 | 5.15 |
| graph500-24 | string | 98.26 | 102.27 | 92.93 |

| Dataset | Text / int64 one-call pipeline ratio | Text / int64 three-call pipeline ratio |
| --- | ---: | ---: |
| cit-Patents | 4.433 | 3.529 |
| graph500-24 | 10.005 | 7.870 |

Most of the saving is in projection construction. Graph500's internal build
observation falls from 92.928 to 5.154 seconds in the one-call series. Every
series stages once and builds one outgoing projection; the three-call series
records three distinct completed WCC reads using that same cached projection.

## Boundaries and correctness

Each original vertex appears exactly once in every full output: 3,774,768 for
Cit-Patents and 8,870,942 for Graph500-24. Every physical file has the two Int64
columns `id,component`, with no nulls or duplicated IDs. Full canonical numeric
minimum-member partitions agree with the independently closed A5 graphframes-rs
reference: 3,627 and 2,901 components respectively. All sixteen comparisons
have zero mismatched members; validation runs after all benchmark processes exit.

Nutmeg's native public `nodeId,componentId` decimal text fields are explicitly
cast to Int64 in the timed export. Raw persisted labels, physical schemas,
complete file inventories and their hashes remain preserved. This reference
comparison does not establish an independent topology or official Graphalytics
ground-truth certificate.

The saved benchmark JSON uses Sem's layout. Its four exclusive phase fields are
null: staging includes physical input delivery and normalization, and a lazy WCC
executes during its Parquet write. Available observed spans are read-and-stage,
projection-stats action and each WCC-plus-write. The internal projection-build
metric is retained separately. No subtraction invents an exclusive kernel or
sink clock. Parent launch-through-wait includes imports, startup, diagnostics
and cleanup, and remains distinct from the pipeline clock. One-call parent
intervals are 4.424/10.337 seconds for Cit integer/text and 13.990/102.992 for
Graph500 integer/text.

The default outgoing projection answers weak components. It does not establish
parity with Sem's mirrored undirected CSR construction, four-thread setup or
historical repeated-run protocol. There is one observation per condition (n=1);
standard deviation is unavailable, and there are no explicit warmups or cache
flushes in this campaign.

## Source, build and resources

Extension and frontend: querygraph/sail `4b88c8fb4504ab1d2a896c9e49e4a09df4905bbb`,
Grust registry crates `=0.24.0`. A fresh CPython 3.12 macOS x86_64 wheel was built
with `maturin build --locked --release`, Rust 1.97.1, opt3, full LTO, one codegen
unit, debug0, stripping enabled, incremental off and four build jobs. The actual
build and waited owner exited zero; installation and native module-origin checks
passed. The wheel is 15,680,368 bytes, SHA256
`347c41034d2eae6b00e84633d3adf20ddc69a41e4665743b29d8b1cd04b5673b`.

Native Sail executable: optimized `9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3`,
150,472,188 bytes, SHA256
`ee80ac3cf9d028639561f3cf32435985192719d629807fcf6a368324fa84946e`.
The exact diff to extension source `4b88c8fb4` is empty over Rust crates, root
Cargo manifests/lockfile, toolchain and `.cargo/`. Compiled runtime and extension
pins remain separately declared. The oracle's graphframes-rs source is
`b4da56dabe20bba8e29563e06acc5179b2113ce3`.

Set `NUTMEG_WORKERS=16` and request `concurrency=16` for every WCC. Local Sail
uses 16 configured workers, a 30 GiB software pool and a 22 GiB native quota.
The raw x86_64 macOS host has 18 physical cores, 36 logical CPUs and 128 GiB.
The largest sampled Sail RSS is 13.173 GiB across complete process lifetimes;
driver RSS and every 500 ms observation are retained separately. There is no
OS CPU/memory/swap cap, PSS or hard-peak proof. No VM was started for this work.

## Preservation and attempts

[report.json](report.json) binds all eight Sem-format benchmark files under
`benchmarks/`. [evidence.tar.gz](evidence.tar.gz) retains exact small logs, receipts,
helper sources, input/reference provenance and independent closure proofs.
[archive-verification.json](archive-verification.json) binds every archive
member; [INPUTS.json](INPUTS.json) catalogs original and retained payloads.
Original inputs, wheel, native binaries and full Parquet outputs are represented
by verified inventories; large payloads are retained on Apo and not embedded.

The first smoke initialization ran the models file instead of the worker. Its
model-only child exited zero but produced no engine receipt or outputs; the
campaign failed and owned locks were independently released after process
closure. Only the bootstrap basename changed before the successful smoke.
The first retention audit rejected the nested SSD layout before any copy; its
receipt and source remain preserved. These failures do not become passed cells,
and no benchmark or physical oracle was repeated for those helper corrections.

Raw retention: `/Volumes/Apo/graph-tests/results/sem-review-20261001/F2a-native-024-run01/raw/`.
Build: `F2a-native-int64-build01`; producer: `F2a-native-024-main-campaign02`.
The previous 0.23 preparation and native A5 evidence remain separate.
