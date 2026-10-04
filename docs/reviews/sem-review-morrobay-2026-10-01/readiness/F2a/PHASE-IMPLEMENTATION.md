# F2a phase implementation recommendation

Written UTC: 2026-10-02T00:57:59.183347+00:00.

Preparation only: primary-source review and arithmetic, no engine, build, SSH, container, payload scan, or source edit. Governing Grust HEAD observed `39739f663d12d4d44b4f979fe7914f37d17139c7`; `AGENTS.md` and `SEM-REVIEW-2.md` sections 8/9 were read. F2a remains open, after B8. No `AGENTS.md` was found in the pinned Sail checkout, its ancestors, or nested tracked paths. `/tmp/sem-f2a-source-admission-plan.md` is preparation, not governing repository instructions.

## Decision

**Existing diagnostics cannot supply four disjoint wall phases without changing the execution path.** Add a narrow, opt-in observer to the current native stage/read path and a new typed one/three-call harness. Preserve the original child launch→exit and Parquet-in→Parquet-out timers. Publish four clearly defined phase observations plus their overlap, rather than inventing a subtractive decomposition.

If the deliverable specifically requires Sem's *sequential*, additive read/build/algorithm/write brackets, an observer alone is insufficient. Use the explicit benchmark materialization profile described below and declare that I/O protocol. Do not silently change a streamed current-Banda baseline into that profile. This is a source-contract finding, not a measured runtime result.

## Pinned implementation and ABI

- Controller/native integration source `f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a`, checkout `/Volumes/Apo/graph-tests/workspaces/sem-review-20261001/pecan-f3b3ef8fc`.
- Frozen harness `6ae2e43a903c2cee02da170465c922c72b76198e`.
- Retained runtime source `56194b170155301ba91077f0ba3df31fe2c78b6b`, Sail binary SHA `5b7f506c19afd76a28b84c1459397b4ab30ff4cfc761f4195789425b963facec`.
- Retained native source `ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73`, Linux module SHA `eb0be839de652e059799dea3bba22cc0908998bd97cfa2f4cf04c67817e2ee50`.
- Underlying algorithms/procedures are registry **0.23.0**, VCS `5c41bcb3c69e4cf4d285e6ec3a8ed239473ae1f1`, not current Grust HEAD.
- A1 image `sha256:f3518d652fbea8b9b9f9ebf9849277ca3bd39d0c21bb2c6e36fbaeaa2dc2678e`.

A native observer change requires a new wheel/module SHA, actual loader identity and fresh source gate. It does not require changing WCC or PageRank equations or rebuilding Sail if DataFusion55.1/Arrow59.3/MemoryLease ABI and manifests remain identical. Matching one source blob does not qualify the installed package; retain the complete loaded package inventory. Do not modify any frozen A2/B8 source.

## Exact present boundaries

1. `Nutmeg.stage(...,order="asStaged")` eagerly collects the one-row mutation receipt. `Mutation::run` executes each Parquet input as a stream; each yielded batch is immediately normalized/admitted by `staging.push_*`, then `staging.finish` commits the revision. Read and graph staging interleave. `spark.read.parquet` alone is lazy and is not a read timer.
2. `Nutmeg.run` returns a lazy DataFrame. The actual first read calls `Store::projection`, which builds/caches one projection, then `run_on_projection` executes the ordinary kernel and creates its Arrow result cursor. For WCC/PR that kernel is eager; `drain` subsequently builds Arrow batches and emits them.
3. In local streaming mode, `AlgorithmStream::start` emits through `sender.blocking_send` into a bounded channel. Arrow conversion, channel blocking and Parquet encoding/writing overlap. Timing all `run_each` as kernel would include output backpressure.
4. Parallel ordinary PR can lazily build incoming CSR inside `pagerank/pull.rs`, whereas `projection_builds.seconds` covers the initial projection only. The initial PR call may therefore contain a graph-build cost in its kernel interval. Do not reinterpret that interval as iterations alone.
5. The old `graph_cell.py` explicitly runs `projectionStats` before the kernel. That is an additional action, and `GraphProjection::statistics` scans the original edge table to count loops: it is O(E), not a free metadata lookup. Remove that action in the **new F2a harness**, observe actual first-call cache construction, and retain the old evidence unchanged.

Source sites: [stage loop](https://github.com/querygraph/sail/blob/f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a/examples/extensions/nutmeg/src/mutation.rs#L290-L335), [projection](https://github.com/querygraph/sail/blob/f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a/examples/extensions/vendor/nutmeg-graph/src/lib.rs#L1338-L1407), [kernel dispatch](https://github.com/querygraph/sail/blob/f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a/examples/extensions/vendor/nutmeg-graph/src/lib.rs#L1460-L1570), [drain](https://github.com/querygraph/sail/blob/f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a/examples/extensions/vendor/nutmeg-graph/src/lib.rs#L2342-L2358), [bounded sender](https://github.com/querygraph/sail/blob/f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a/examples/extensions/vendor/nutmeg-graph/src/lib.rs#L3098-L3132), [old extra action](https://github.com/querygraph/sail/blob/f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a/examples/extensions/benchmarks/graph_cell.py#L149-L160).

## Small observer patch: three focused native sites

Use typed aggregate records, not per-row logs or a telemetry platform. Enable only for the F2a diagnostic profile. Disabled execution takes the current branch unchanged. Use monotonic begin/end and outcome; a failed interval has an end/failure record and never becomes zero. Every stage/read names graph, revision, projection key, ordinary method/options and unique read ID.

| Published observation | Exact scope | Site and change |
| --- | --- | --- |
| Read delivery | Accumulated awaits of `stream.try_next()` for both original input plans, including EOS/error; upstream scan/decode/wait seen by the staging consumer | `nutmeg/src/mutation.rs::Mutation::run`: clock immediately around each await; retain rows/batches/stream count and stage wall span |
| Graph build | Stage normalization/admission/schema/commit intervals, plus initial projection build span; incoming CSR remains explicitly identified as included in first PR kernel unless separately instrumented | Same mutation loop around `push_nodes/push_edges/finish`; `Store::projection` extends existing `ProjectionBuild` with start/end/cache-hit/read ID |
| Algorithm and result setup | Entry/exit of ordinary `run_on_projection`, after initial projection/view creation and before `drain` | `vendor/nutmeg-graph/src/lib.rs::Store::run_kernel`; includes lazy incoming build for parallel PR and result-cursor setup, not Arrow batch conversion/blocked emission |
| Write/export | Original write action wall span, plus separate native Arrow-conversion and emit/block intervals | Parent harness brackets actual `.write.parquet`; native `drain` aggregates cursor `next_batch` and downstream emit separately. The action is inclusive of its lazy upstream; report this overlap |

Read-delivery time is **not** total Parquet CPU or filesystem time: background partitions/prefetch can work while normalization runs. Write-action time is **not** a pure exporter duration. Do not sum inclusive spans, subtract projection seconds from write, derive "exclusive kernel" by arithmetic, or claim identical phase semantics to icebug's worker. The four requested headings can contain these qualified observations; whole-run Parquet in/out remains the meaningful baseline.

Extend existing diagnostics JSON (`nutmeg/src/diagnostics.rs:112–134`) with a dedicated phase record. Existing `ReadInfo.id`, state, rows/batches/work and memory admission already give lifecycle/correlation. Keep aggregates bounded; at most stage parts and three read IDs, with counts and bounded first/last samples rather than thousands of events. Native status collection occurs after the data action; disclose its cost in overall child launch→exit. Store aggregate records on the session, so graph drop or a failed query does not erase retained diagnostic evidence before collection. Source/query failures and observer-collection failures remain distinct.

Incoming-CSR alternatives: observing it precisely at `GraphProjection::incoming` requires an instrumented 0.23 algorithm dependency. Precalling `view.prepare_incoming()` in the native wrapper reuses existing API but **moves work and reservation lifetime**, especially initial PR vector allocations/cancellation/refusal order. That is an explicit prepared-build profile, not observation-only; do not introduce it silently just to improve a kernel column.

## If four sequential wall brackets are mandatory

Declare a separate `materialized-phases` benchmark protocol using the same ordinary Banda kernels and asStaged order. The smallest honest boundaries are:

1. **Read:** consume original Parquet into admitted server-side Arrow batches, preserving arrival order. No Python row conversion and no input-validation job in the timer. This deliberately introduces an original-input buffer of at least `4,237,039,856` bytes (3.946 GiB) for this graph, plus validity/capacity and scan buffers.
2. **Build:** normalize/admit those batches and commit the same asStaged revision; construct the selected projection. For parallel PR explicitly prepare incoming CSR on the same query view under the original pool owner, preserving work/deadline/cancellation accounting. Record the preparation policy. Release original input references as soon as stage takes each batch.
3. **Algorithm:** execute the ordinary method; buffer the complete Arrow result on the server until a distinct read-only result handle is sealed. Include Arrow conversion in this phase if aligning with Sem's worker, which includes Python vector conversion and PR final normalization in its algorithm bracket. Do not add normalization to Banda silently; declare any postprocessing adapter and prove equivalence separately.
4. **Write:** stream only the sealed result handle into a fresh Parquet directory, ending on completed writer/action. A second action must never rerun the kernel. Drop the sealed result after each write before starting the next call.

The pinned client exposes no such sealed-result handle, and current `.persist`/cached-local-relation support cannot be assumed (`sail-plan/src/resolver/query/mod.rs:243` is unsupported). Merely setting `ReadExecution::Materialized` is also insufficient: it executes during scan/planning and buffers a result **within that one action**; a later write action can replan/rerun it. Implement a benchmark-specific native input/result handoff with exact owner/lease lifetime and eager receipts if this protocol is selected. It requires a small additional control path, not new algorithm formulas. Refuse if both buffers cannot be admitted. Never retain three full result buffers together.

This protocol gives actual disjoint brackets with useful leftover startup/control/cleanup overhead; it is explicitly a materialized I/O baseline and must not be described as unchanged streaming execution. Root should select it only when strict Sem phase parity is required. An observer-only implementation is smaller and preserves the present execution path, but cannot honestly claim that parity.

## One versus three calls

Use separate fresh cells for calls=1 and calls=3, with identical pinned original inputs/options, one stage/revision, one projection key and one server/session per cell. Within the three-call cell invoke the **same ordinary method three times**, writing every full result to its own fresh directory. Separate WCC and PR series; mixed algorithms/orientations are another workload. Retain per-call state and full output oracle; cache-reuse evidence is actual key/revision/build count, not graph name or the claim that calls 2/3 were warm.

WCC raw component labels are minimum projection row identities, not necessarily minimum signed numeric IDs with asStaged arrival order. Compare full partition equivalence and exact membership using a declared lossless decimal-to-i64 adapter. PR uses damping .85/f64/maxIterations10/tolerance0; report actual iterations/residual/converged because tolerance0 can stop at an exact fixed point. Retain isolates, parallel edges and loops. There is no qualified icebug ratio without identical input pins, full reference semantics and envelope/execution-class agreement. External icebug receipts remain separately labeled prior observations.

## Actual input identity and arithmetic admission

Observed finalized downloader receipt `/Volumes/Apo/graph-tests/results/sem-review-20261001/B8-run01/downloads/graph500-24/download-receipt.json` has outcome `downloaded_and_admitted`, finished `2026-10-02T00:38:16.180926+00:00`; SHA-256 `9a3cbac80de93dc9fe16989ae4542ac7af7874ac0482a3940f44a6a3920bc4d2`. This is original download/footer admission, **not native Banda fit admission** and not completed B8 algorithm qualification. No payload was read in this review.

- Actual V=8,870,942, E=260,379,520; maximum edge row group 122,880 rows; vertices `id:int64`, edges `source:int64,target:int64`.
- V file 9,119,859 bytes, SHA `f186f0fac502106454ceae29a57c7f350ae60699b5a5087b3001cfd054983428`.
- E file 837,233,354 bytes, SHA `da4f324e619c97d68190c0eba4e2f9e59ebcd492d84c3e1bafe7624fdc7e2453`.
- Existing u32 targets and row offsets: directed arcs E and undirected upper bound2E=520,759,040 are below u32::MAX; this is a representability check, not memory-fit proof.

| Scoped storage, inferred 64-bit layout | Bytes | GiB |
| --- | ---: | ---: |
| original_i64_buffers_floor | 4,237,039,856 | 3.946 |
| outgoing_unweighted_CSR | 3,160,038,012 | 2.943 |
| incoming_unweighted_CSR | 1,077,001,852 | 1.003 |
| insertion_positions | 70,967,536 | 0.066 |
| ProjectionEdge_inferred_40E | 10,415,180,800 | 9.700 |
| outgoing_plus_original_edge_table | 13,575,218,812 | 12.643 |
| parallel_PR_both_CSR_plus_edge_table | 14,652,220,664 | 13.646 |
| undirected_CSR_upper_bound | 6,284,592,252 | 5.853 |

Unweighted incoming CSR has **no edge-slot buffer** (`Adjacency::transposed_split`, edge_slots=None), so it is 4*(V+1)+4*E, not another 12*E. The declared three usize fields plus `Option<EdgeId>` (EdgeId wraps `Arc<str>`) imply an ordinary 64-bit `ProjectionEdge` layout of 40 bytes/edge. This layout is inferred; require actual target/compiler `size_of` evidence before admission. These are packed structural estimates only. Normalized staged Arrow rows, ID strings/map, original-edge records and CSR coexist; for the property-free integer input the original int64 stream batches are generally transient after casting. There is no Graph/Props/Value or per-row property-map materialization in the direct Arrow adapter. The [staged retention audit](STAGED-RETENTION.md) records owner lifetimes and conditional stage+projection accounting (27.327 GiB at a 20-digit bound before reverse/kernel/capacity), with a conservative 32 GiB fit-or-refusal contract. UTF8 staged IDs/offsets/null fields, NodeId copies/maps, growth capacity, edge validation/build temporaries, allocator overhead, native kernels, Arrow result buffers, DataFusion input/prefetch and process/transport overhead are additional. `CsrEstimate` explicitly is not peak admission.

For unknown actual ID text widths the conservative signed/unsigned i64 conversion width is20bytes. The original footer alone does not prove eight-digit IDs or contiguous0..V membership. Stage admission already bounds normalization (builder growth4x, input-held bytes, optional missing fields) per batch and shrinks to actual retained allocation. Outside-timer input validation may record maximum decimal width and original property layout for a tighter model; do not perform a data check inside algorithms.

Use the existing16CPU/32GiB/noSwap envelope and greedy pool30GiB. Root must bind an explicit native quota and bounded row-group/prefetch footprint; B8's256MiB is inapplicable. A24GiB driver-native quota is only a **candidate**: it is reserved from the ordinary30GiB pool, leaving6GiB accounted capacity for relational work, not a proof of6GiB physical headroom. The generic20-digit/string/map construction model does not establish24GiB fit. Admission must include simultaneously retained stage+CSR+kernel/output and any new materialization buffers. Retain ResourcesExhausted/refusal, timeout, OOM and mismatch separately. All three calls must release output before the next; graph+CSR remain until after final write. Refuse or report unsupported/admission-unavailable before an unbounded full-graph allocation. Low-memory cit-Patents success cannot qualify Graph500 fit.

Keep no silent32GiB resize. If a conservative physical/native budget cannot be justified, retain the refusal/unavailable F2a outcome and perform an explicitly separate admission diagnostic, owned by root after B8. Exact native pool live/peak, PSS/cgroup/pagecache boundaries and allocation refusal are needed; a pool cap alone is accounting, not physical peak proof.

## Narrow verification before any large run

1. Observer disabled versus enabled on one signed/high-ID tiny graph: identical raw output pairs/vector/schema, method/options and staged revision; no extra kernel or projectionStats action. Exactly1 and3 read IDs, one stage, one cache build for a same-key series; new-key/restage control rebuilds explicitly.
2. Partial input/error/cancel/refusal control: records failed intervals without publishing complete phase verdict; original error and cleanup/cancellation contract preserved. Deterministic fake-clock controls verify nesting/missing coverage, not fragile elapsed thresholds.
3. For a materialized profile only: one call produces one sealed result then one write, writer never reruns the kernel, borrowed batches keep the owner lease, and failure/drop releases input/result reservations. A small quota rejects before retaining an unadmitted buffer; no3-result accumulation.
4. Full ordinary WCC partition/PR semantics tests on existing tiny official/oracle graphs, including isolates/loops/duplicates/high signed IDs; equality under observer enabled/disabled. Strict typing/Ruff on new harness; Rust fmt/clippy/test for affected native crates in an exact detached source gate and separate target. Existing frozen gates remain unchanged.
5. First run new-source loader/identity,16CPU32GiB resource closure and small admitted cit profile, then root decides full Graph500 admission. Every raw output/receipt/log remains archived. These controls qualify instrumentation/ownership, not generic scalability or a safe lower cap.

## Source byte identities

The following local source bytes were compared with Git blobs at f3 before hashing. Source links above specify the exact controller revision; installed runtime/native pins remain distinct.

| Relative source | SHA-256 |
| --- | --- |
| `examples/extensions/nutmeg/src/mutation.rs` | `da01f1582808506c99ed73846e913fa8bf6015e8ed860aa44485f1df169c973b` |
| `examples/extensions/nutmeg/src/diagnostics.rs` | `6439e5131f6d8f4ebe22c0ca69d138edc172a0ba7e1a4a1f00c25d66366bcbe6` |
| `examples/extensions/nutmeg/src/lib.rs` | `51f6444aed662d7d4df6800539c65334432d5a17c44d0fda21cfecf3e0a8edf1` |
| `examples/extensions/nutmeg/python/sail_nutmeg/client.py` | `0e184de1daf55d1ea483c7153ea9df6951445b6e1206bd29027e3283a2ed803e` |
| `examples/extensions/vendor/nutmeg-graph/src/lib.rs` | `8117b13ef42d8a3c3ba00816a6c7bda8149da92252b5eb9aa37fcddaf1494b69` |
| `examples/extensions/vendor/nutmeg-graph/src/admission.rs` | `2c93d3b21d7dd6dd983d00ccfba3751f54fd0507ab3553213e5520f4ece2f6dd` |
| `examples/extensions/benchmarks/graph_cell.py` | `22abe8a233038bf474320aaae0a8e437660d7a6595379792d2630cd69ff9f2da` |
| `examples/extensions/benchmarks/runtime.py` | `27a76460792bac9668e18c8e32961f34a936060dc15cd3fe06f115124757b6e4` |

Registry source observed locally at `~/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f/`; published VCS5c41bcb3 remains distinct from current Grust:

- `grust-algorithms-0.23.0/src/projection.rs`: `43cc4f510c88a862f642c72a3d268c38603646eec1e17167d41158786499233f`.
- `grust-algorithms-0.23.0/src/projection/adjacency.rs`: `c4ff1b59cb6a6a290dc7969faea0c0e486a8729592f2bca9559c65b819190e0b`.
- `grust-algorithms-0.23.0/src/statistics.rs`: `168bd3c96be081a761113e815bf0acd329df77dd8cb6c5df5441d7a5526af299`.
- `grust-algorithms-0.23.0/src/pagerank/pull.rs`: `b76f5cf26a96e544a1313d8dc400b4b19a125d6f1b3246619e1e713bc66de345`.
- `grust-algorithm-procedures-0.23.0/src/lib.rs`: `875a7acdc688607cca4304be921cc134c7b3cc84389bd9f7e1cfd9a61031746e`.

Arithmetic correction recorded UTC: 2026-10-02T02:47:15.179378+00:00. Original generated preparation is retained unchanged at `/tmp/sem-f2a-phase-implementation.md`; the correction changes source-layout arithmetic, with no runtime or benchmark evidence change.
