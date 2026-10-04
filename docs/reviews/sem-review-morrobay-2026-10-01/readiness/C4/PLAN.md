# C4 readiness: preserve qualification and close only missing scope

Recorded 2026-10-02T00:47:04.503208+00:00. Grust AGENTS.md governs. Read-only receipt/source review;
no Docker, build, compilation, test/probe execution or source edits. **C4 remains
open for its Linux standalone/min_by scope; this review is not a DONE verdict.**

## Already qualified: compact three-field tuple MIN

- Exact kernel source `ddc251c6a9cb5aaa155b216e2554d0dddcd440ec1f99fda416d394cb5127fdcd`
  at runtime 561 and f3 matches retained `min-struct-comparison/candidate-snapshot.rs`.
  Exact561 commit fmt/clippy/function-plan-execution tests passed, and a Linux x86_64
  release host was built. Keep those gates; no broad rebuild is needed to reassert them.
- Separate macOS arm64/System allocation comparison:1k / 10k / 100k groups, batches 8192,
  original and compact exact source. At 100k first-update retained requested bytes
  204,831,488 versus4,194,304 (about48.8 ratio), excluding group keys/operators/allocator
  usable-size/RSS. Four final differential controls pass (64 seeds × 12 batches, nulls,
  filters, float bits / NaN / signed zero, signed extremes, ties, merge/prefix/metadata).
- Six-cell Linux matched Pecan **SSSP frontier** control: original controller 3a902,
  original native ffcf, warmup A/B then ABBA,2 measurements/runtime. Full independent
  heap-Dijkstra / parent producer checks and later physical-value/domain checks passed.
  Shared-Morrobay median compact/original time0.607803837 and sampled execute
  PSS0.838913334. Timer input DF handles→fullParquetwrite excludes server startup,
  hashing/oracle/cleanup. It is not the new launch→exit timer or general isolated effect.
- Envelope8 CPU/cpuset16–23,12 GiB/noadditionalSwap,2workers,P=4,4 threads,16 task slots
  per worker,greedy 3 GiB per process,native 256 MiB. Paging/compression and shared-host
  confounds retained. ResultParquet stays in historical volume; publication copies
  producer/correctness/hash-bound physical receipts, not raw result payloads.
- Large compact DeltaStar scale24 replay passed certificate/parent and physical
  domain checks at100 GiB cap; observed33.05 GiB whole-container peak **exceeds32 GiB**.
  Original replay OOMed at100 GiB and provides no completed time/uncapped-memory
  denominator. Different generated input than official Graph500-24; no large ratio.

Evidence: `STRUCT-MIN-ALLOCATION.md`, `min-struct-comparison/`,
`compact-min-committed/receipt.json`, `linux-builds/BUILD-HANDOFF.json`,
`host-pair-publication/README.md` and independent-review/receipt.json,
`COMPACT-REPLAY-AND-SSSP.md`. User's named `struct-min-comparison` resolves to
actual retained directory **min-struct-comparison**.

## Binary availability recorded by existing receipts

| Artifact | Recorded path | Source / SHA256 | Scope |
|---|---|---|---|
| Linux compact Sail | /targets/sail-compact-host-56194b170155/sail-linux-x86_64-56194b170155-release | source56194b170155301ba91077f0ba3df31fe2c78b6b / 5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec | existing runtime, same current A2/A3 pin |
| Linux original Sail | /targets/sail-stream-2894a962076d/sail-linux-x86_64-2894a962076d-release | source2894a962076d3cc404dd72ec736ebeb9239901f6 / 40a78182a420152e8e3651f9cdb38a4196eaf8bc7aead092d10e258a17ac3497 | paired control and oldmin_by workerplan |
| Tuple standalone | /private/tmp/min-struct-allocation-target/release/min-struct-comparison | b215ade9bca9acf5dd85da7a07b8ac3cc47cdabb9a2b06808b7aa4b512867568 | recorded macOS arm64 binary, not ELF/Linux |
| Ordered-LAST standalone | /private/tmp/min-by-allocation-target/release/ordered-last-value-allocation-probe | b627737ec653ec990fef98e46549153939f9c287bc66985e326c4ac86e17bf76 | recorded Darwin arm64 binary, not ELF/Linux |

Linux runtime build receipts identify Linux x86_64/Rust 1.97.1/build imagef3518d...
with16 CPU/48 GiB/noSwap **build** envelope; this is distinct from probe/run limits.
They record exported runtime hashes/versions, not a standalone probe ELF header.
No retained Linux-built standalone allocation-probe receipt was found in the
requested evidence. Current file presence / ELF header must be checked by root's next
admission; this review reads historical receipts only and does not execute binaries.

## min_by is a separate implementation and result contract

Current561/f3 `max_min_by.rs` hash **9ba14aacf6f76afcb4806c6f4d5255d0ce8a0196cc9321c8d2d98b93a4dfd325**
is identical to the source-reviewed probe. The simplify hook lowers min_by(value,key)
to **LAST_VALUE(value ORDER BY key DESC NULLS FIRST)** plus `key IS NOT NULL`
combined with existing filter. With Int64 value/ordered Int64 key, DataFusion 55.1
selects PrimitiveValueState grouped LAST, not generic row-wise two ScalarValue
MaxMinByAccumulator. Generic fallback holds two scalars; it is not a growing row array.
Compact struct MIN only recognizes exactly Struct(Float64,Int64,Int64) grouped state;
scalar/sliding/otherstruct types delegate to DataFusion. Neither ordered LAST nor
plain Int64 MIN is changed by this compact tuple patch.

DataFusion ordered LAST holds typed value vector, orderingVec<Vec<ScalarValue>>,
one scalar buffer per group,scratch indices/validity andseen bitmaps. State is bounded
per group; first update allocates roughly one small scalarvector per group; improvements
reuse capacity. At 100k observed requested retained 11,692,032 versus reported10,946,304;
outer ordering spare capacity omission745,728. It clears/scans residentgroups per batch,
so source-derived work includes O(sum_b G_b); repeated dense100k/13batches1.3M visits,
sparse 8192 rows still visits100k. These are requestedSystem bytes/analytic visits,
not Linux Sail RSS/cycles or querycausality. Prefixstate sizing also reserves byremaining
rather than emitted groups; EmitTo::First relevance must be observed, not assumed.
TupleMIN and min_by produce different values/semantics, so their memory figures
are componentcost evidence, **not a drop-in before/after speed ratio**.

Old Linux 14-edge / 17-endpoint workercontrol onruntime 289 proved Partial and
FinalPartitioned ordered LAST, all 24 successful aggregate tasks onboth workers,
exact signedBIGINT output under a=1,b=0 and2input orders. It did not measure allocations,
resident group counts/RSS or prove prefix emission. Runtime561 current physical route remains
unobserved here despite byte-identical source+lock bridge. f3 randomized WCC now
uses plainGF MIN+least; do not describe this oldmin_by expression as currentWCC.

Primary source: [current min_by simplify](https://github.com/querygraph/sail/blob/56194b170155301ba91077f0ba3df31fe2c78b6b/crates/sail-function/src/aggregate/max_min_by.rs#L263-L288),
[compact tuple factory](https://github.com/querygraph/sail/blob/56194b170155301ba91077f0ba3df31fe2c78b6b/crates/sail-function/src/aggregate/struct_min.rs#L19-L76),
[DataFusion grouped state](https://github.com/apache/datafusion/blob/55.1.0/datafusion/functions-aggregate/src/first_last.rs#L478-L517).
Local exactDF first_last SHA8bf9a75a79bb451f2dcbe9794933e670f72a114e55153169710a911336cea2ed;
compact source,wrapper and Cargo.lock byte-identical561→f3, allhashes in
`/tmp/sem-c4-source-evidence.json`.

## Smallest remaining qualification, proposed only

1. New exact frozen standalone probe source namespace, read-only copies of original
   DF 55.1 files and compact kernel; compare with source hashes, lock checksums and
   cachedcrate member. Reuse semantic tests/driver schedules unchanged; do not
   touch registry/frozen evidence. Select new isolated Linux target/output.
2. Linux release gate the two **small standalone crates**, not full Sail. Existing
   tuple build.rs already accepts `DF_MINMAX_STRUCT_SOURCE` and
   `SAIL_COMPACT_STRUCT_SOURCE`; set them to reviewed exact copied files. Oldrunner
   hardcodes `/private/tmp` and existing receipt destinations: **do not rerun it**.
   New owned root runner supplies fresh commands/output and captures every failure.
   Probe-driver format/clippy were not fully claimed by oldtuple gate; any required
   driver-only formatting is a reviewednewidentity, not a kernel/oracle relaxation.
3. After gates, obtain actual LinuxELF architecture + binary SHA + compiler/dependency
   receipts. Fresh1CPU/2 GiB/noSwap/noNetwork cells are a bounded proposed envelope
   for100k controls; retain OOM/refusal instead of assuming fit. Run original/compact
   each G=1000,10000,100000 plus ordered LAST eachG; capture all phase JSON/answers,
   requestedlive/peak/allocation counts/sizeclaims and lifetimeRSS. No millions-group
   scaling or fullgraph replay is necessary to close this standalone scope.
4. One tiny runtime 561 min_by SQL/DataFrame control: id,value,key allBIGINT, actual
   grouped min_by(value,key) plus MIN(key), valid unique priorities / same-value ties for
   an exact distributed oracle, signed extremes/highbit. Null/filter/first-tie/merge/
   prefix behavior remains covered by standalone semantic tests. Capture exact
   physical rewrite+Partial/Final tasks matched RUNNING / SUCCEEDED onboth workers;
   do not infer state factory from displayed alias. No full WCC launch is required.
5. Tuple codec/runtime already qualified; no broad rerun is required. Allocation
   results still exclude key hash/joins/shuffle/allocator usable size. Sail CLI defaults
   to MiMalloc in the recorded build command; counted System standalone is its own
   allocator boundary. Query memory causality, actual EmitTo::First frequency and
   tens of millions high cardinality costs remain separate/unmeasured.

### Future commands (not executed)

In reviewed fresh detached/Linux source+target, with the two required source environmentironment
variables already bound for tuple build.rs and CARGO_INCREMENTAL=0:

```sh
cargo fmt --check --manifest-path /targets/<fresh>/min-struct-comparison/Cargo.toml
cargo clippy --release --locked --offline --manifest-path /targets/<fresh>/min-struct-comparison/Cargo.toml --all-targets -- -D warnings
cargo test --release --locked --offline --manifest-path /targets/<fresh>/min-struct-comparison/Cargo.toml --test differential
cargo build --release --locked --offline --manifest-path /targets/<fresh>/min-struct-comparison/Cargo.toml
cargo fmt --check --manifest-path /targets/<fresh>/min-by-probe/Cargo.toml
cargo clippy --release --locked --offline --manifest-path /targets/<fresh>/min-by-probe/Cargo.toml --all-targets -- -D warnings
cargo test --release --locked --offline --manifest-path /targets/<fresh>/min-by-probe/Cargo.toml
cargo build --release --locked --offline --manifest-path /targets/<fresh>/min-by-probe/Cargo.toml
/targets/<fresh-target>/release/min-struct-comparison 1000 original
/targets/<fresh-target>/release/min-struct-comparison 1000 compact
/targets/<fresh-target>/release/ordered-last-value-allocation-probe 1000
```

Root repeats only the declared 10k / 100k cells after admission, retains all outputs and
cleanup/closure; this plan runs none. Existing traversal pass is preserved, Linux
standalone qualification/current 561 min_by control pending; no automatic C4 DONE.
