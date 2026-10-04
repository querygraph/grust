# F2a staged retention and memory admission correction

Written UTC: 2026-10-02T01:21:50.627238+00:00.

Source-only review and arithmetic; no build, native execution, container, payload read, or source edit. Governing Grust HEAD observed `39739f663d12d4d44b4f979fe7914f37d17139c7`, with current staged readiness documents owned by root. Exact Sail controller `f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a`; published Grust dependencies 0.23.0 at VCS `5c41bcb3c69e4cf4d285e6ec3a8ed239473ae1f1`. Relevant local source bytes match those exact Git blobs. Runtime561/nativeffcf identities remain distinct; this does not certify rebuilt or measured code.

## Decision and correction

**Normalized staged Arrow rows, native external IDs/map, original-edge records and CSR coexist.** asStaged skips sorting; it does not replace the staged rows with CSR. Original property-free int64 Parquet batches normally become transient when their structural columns are cast to UTF8; retaining a separate complete original Arrow input is an additional materialized-profile cost. There are no per-row Graph/Props/Value or property maps in this direct Arrow projection path.

The earlier documents `/tmp/sem-f2a-source-admission-plan.md` and `/tmp/sem-f2a-phase-implementation.md` used the native adjacency comment's 32-byte ProjectionEdge figure. **That arithmetic is unsupported by the declared types and must be corrected in readiness ADMISSION.md/PHASE-IMPLEMENTATION.md before publication.** Actual `ProjectionEdge` has three usize fields plus `Option<EdgeId>`; EdgeId wraps `Arc<str>`, a fat pointer. The expected ordinary 64-bit layout is 40 bytes, with NodeId/EdgeId handles 16 bytes. This is a source-layout inference, not an observed Linux `size_of` receipt. The admission/build profile must record actual target/compiler `size_of::<ProjectionEdge>()`, NodeId, EdgeId and Option<EdgeId>; do not qualify fit from a prose comment. A conservative layout calculation uses at least40 rather than32 until that receipt exists.

Using that inferred layout, `40*E = 10,415,180,800` bytes (9.700 GiB), outgoing CSR plus original-edge records is **12.643 GiB**, and adding unweighted incoming CSR gives **13.646 GiB**. These replace the earlier 10.703/11.706 figures; they still exclude staged rows and identity tables. No runtime metrics, timings or frozen A2/B8 evidence change.

## Trace of simultaneous owners

| Structure and lifetime | Source evidence |
| --- | --- |
| Input Parquet stream yields one Arrow batch, immediately normalized by stage | Sail `nutmeg/src/mutation.rs:307–330`: original inputs execute sequentially as streams; stage pushes each batch before asking for the next. Reader/prefetch work may be concurrent. This does not collect all original int64 batches. |
| Private normalized nodes and edges accumulate through the complete two-input stage | `vendor/nutmeg-graph/src/lib.rs:1583–1655`: Staging owns `Vec<RecordBatch>` plus `fresh` reservation tokens. `session.rs:128–205`: GraphStaging owns both parts and commits one Entry after both finish. Nodes remain while all edges are staged. |
| asStaged commit shares batch handles/reservation tokens without copying their buffers | `lib.rs:1708–1774`: staged.extend(normalized.iter().cloned()), retained admission clones share tokens, Entry takes batches and admissions. Transaction handles then drop; no canonical copy/permutation/key array is allocated. |
| Committed Entry retains staged rows and cached projections together | `lib.rs:1074–1091,1338–1407`: Entry has nodes,edges,node_bytes,edge_bytes and projections; GraphProjection is constructed from references to those batches and inserted into the same Entry. Building a projection never clears node/edge batches. |
| Lazy algorithm providers/snapshots pin a revision after graph drop or overwrite | `session.rs:99–122`, `graph_tables.rs:15–48,84–119`: providers share the immutable Entry, cache and pool; snapshots and exported Arrow arrays carry owners. Drop of the graph name alone cannot prove all allocation release while readers/output references remain. |
| Direct Arrow adapter copies selected node IDs, records dense edge endpoints/ordinal/optional ID, then builds CSR | Grust `arrow_input.rs:22–140`: no Graph/Props/JSON/Value materialization; temporary HashMap maps borrowed `&str` to optional dense index. It drops before from_buffers. NodeId strings are new Arc allocations; absent edge IDs stay None but each record still has the Option field. |
| Projection keeps node vector, owning NodeId→usize map, edge vector, outgoing CSR and optional incoming CSR | Grust `projection.rs:65–80,134–208`: node_by_id keys clone NodeId handles sharing the copied Arc strings; no second string payload is created for each key. Reverse CSR is cached on its owner. |
| Kernel result and emitted Arrow batches hold reservations/owner until consumed | Grust `traversal.rs:216–275,290–371`, `pagerank/pull.rs:233–306`, `arrow_output.rs:280–360`; Sail `graph_tables.rs:111–123`. Three same-key calls share graph/CSR, but must release each result/writer/provider before the next; never accumulate three complete result buffers. |

For actual Graph500 input schema `id:int64` and `source:int64,target:int64`, normalization creates:

- Nodes: UTF8 node_id, empty-string label. The two arrays have offset buffers; copied ID payload survives staging.
- Edges: UTF8 source and target, empty-string label, all-null UTF8 edge_id. There are **four** offset buffers, two endpoint string payloads and the edge-ID validity bitmap.
- No unused property columns exist in the admitted schema, hence no property/presence arrays or property maps here. With additional property columns, normalize_* preserves applicable Arrow columns and may share original whole buffers; include them explicitly in another dataset's contract.
- Because structural integers are cast, their old int64 buffers are not retained by the normalized structural columns. They may overlap during normalization and survive in DataFusion/prefetch/another caller; their absence from Entry is not a process-wide release proof.

## Ledger semantics and construction peaks

`lib.rs:854–877` held_bytes charges distinct Arrow buffer allocations at their **full capacity**, including parents of slices. Normalization reserves its conservative bound before allocation, then `shrink_to(held_bytes(normalized))`; Staging/Entry retain that charge. Bounds include original input-held allocation, possible4x builder/reallocation space, cast defaults, offsets/null buffers. Source `admission.rs:1–15,160–277` explicitly bounds Arrow buffers/builders, **not process RSS or all Rust metadata**. Vec<RecordBatch>, schema/array objects, admitted token vectors, hash bookkeeping and allocator fragmentation require separate physical headroom. Per-batch charging can conservatively charge a shared allocation again across pushes; do not equate ledger bytes to exactly deduplicated process RSS.

Grust Buffer::capacity reserves count*sizeof(T) before Vec::try_reserve_exact. from_arrow_batches temporarily admits a borrowed-ID mapping bound `66*(V+4)` on a64-bit layout (`2*(size_of(&str)+size_of(Option<usize>)+1)`), NodeId/edge vectors and copied-ID bytes. The borrowed map drops before CSR construction. from_buffers subsequently reserves the retained owning mapping estimate `50*(V+4)` (`2*(size_of(NodeId)+size_of(usize)+1)`) plus copied ID payload/Arc headers and fixed projection/identity metadata. The earlier copied-ID reservation is held until from_buffers returns, so **the same copied ID charge overlaps twice during construction**; this is accounting overlap, not two physical string copies.

Projection validation adds a dense ordinal bitset (~E/8 here) and parallel-map bookkeeping; it drops before CSR build. Outgoing build needs offsets, targets, edge_slots, `8*V` insertion positions, plus a temporary parallel count table bounded by `4*min(16,64,floor(E/V)+2)*V = 64*V` with requested concurrency16. This count table is released before target/position allocations; do not add all mutually exclusive temporaries as if they coexist. Admission refusal of the count table falls back to sequential counting; it is not proof of unchanged phase performance. Incoming unweighted transpose has no edge_slots, so its retained size is `4*(V+1)+4*E`, plus transient positions/count table. PageRank starts with score/teleport buffers before lazy incoming; unpersonalized teleport releases after reverse construction; later unweighted scores/shares_now/shares_next total24*V plus bounded partials. Ordinary WCC peak has two per-node usize/atomic arrays, about16*V, with only one result array retained after kernel.

MemoryInfo.used_bytes/peak_bytes is the **native ledger** for staged rows, reservations, cached projections and kernels. ProjectionBuild.admitted_bytes is its live delta and can include concurrent admissions; qualify these only in a serial cell. Sail's prepaid native lease reserves the configured quota from its ordinary pool. These are different counters. A24GiB native quota inside a30GiB Sail pool leaves6GiB accounted capacity for other operators; it does not prove6GiB unused physical memory or2GiB physical cgroup headroom.

## Conditional storage arithmetic for the admitted Graph500 footers

Finalized downloader receipt SHA `9a3cbac80de93dc9fe16989ae4542ac7af7874ac0482a3940f44a6a3920bc4d2` gives V=8,870,942 and E=260,379,520; it does not give actual decimal widths/capacities. No input payload or open reference output was read here.

Let D_N,D_S,D_T be actual total UTF8 decimal lengths of node, source and target IDs; B_N/B_E the actual normalized batch counts. Ignoring capacity rounding and optional unused zero-length payload allocations, packed normalized buffers are approximately:

`stage = D_N + D_S + D_T + 8*(V+B_N) + 16*(E+B_E) + sum_edge_batches(ceil(rows/8))`.

The vertex label and relationship label have empty payload but retain offsets; absent edge IDs retain offsets and a validity bitmap. Formula excludes extra validity for the non-null ID columns, metadata and allocator/capacity expansion. Actual held_bytes is the necessary observation and may be materially greater. Original integer input buffer floor is `8*V+16*E = 3.946GiB`, transient in the streamed profile but additional while a full original-input materialization survives.

For illustration only, uniformly bounding **every** structural decimal ID by w bytes gives the following packed/admitted subtotal. These are conditional arithmetic, not measured retained memory and not sufficient allocation bounds:

| Assumed maximum decimal width w | packed stage GiB | stage + edge40 + outgoing CSR + NodeId vector + retained ID/map charge GiB | same plus incoming CSR GiB |
| ---: | ---: | ---: | ---: |
| 8 | 7.922 | 21.309 | 22.312 |
| 20 | 13.841 | 27.327 | 28.330 |

The subtotal uses `stage(w)=(w+8)*V+(2*w+16+1/8)*E`, `NodeId vector=16*V`, and `retained ID/map charge=50*(V+4)+(w+16)*V`. It omits fixed metadata/batch offsets/rounding, temporary reservations, kernels, result batches, process/reader/writer costs. Source type width20 is conservative for i64 decimal formatting; width8 cannot be assumed from V or the graph's name. Even the packed width20 subtotal already exceeds24GiB before PR transpose/kernel/capacity, so a24GiB admission model cannot be approved from the schema/counts alone. That is **not** a claim that the actual graph has20-digit IDs or actually fails24GiB.

A122,880-row compact non-null int64 edge batch has a source-derived normalization pre-admission illustration of about28.36MiB using width20, default empty label/null edge-ID builders and 4x growth. Summing that deliberately loose bound across all E would be about58.69GiB. Each actual batch shrinks to retained buffers; that loose sum is not actual stage memory. The largest Parquet row group is not an enforced maximum emitted execution batch or a complete reader/prefetch-memory bound.

## Conservative fit/refusal contract for 32GiB

1. Freeze actual ABI/package/source/target layout and exact original inputs. Keep streamed versus explicitly materialized profile distinct. New instrumentation does not change algorithms, staging order, input property layout or first-call topology work.
2. Establish a **physical** upper-bound model for simultaneously live normalized buffer capacity, NodeId/edge/maps, builder/query/output reservations, bounded reader/writer queues and Rust/process overhead. Require both `native_peak_bound <= configured_native_quota` and `native_physical_bound + bounded_non_native_peak + retained_materialization <= 32GiB - explicit_safety_margin`. Pool accounting alone cannot satisfy the second inequality. If an actual width/capacity/queue bound is unavailable, record `admission_unavailable`/refused rather than predeclare full scale fit.
3. Obtain tighter width and property-layout facts from already finalized outside-timer validation/reference metadata or a separately authorized validation utility; do not add data checks to Banda algorithms. Stage diagnostic retained_bytes and native ledger counters can support a separately declared admission diagnostic, but do not retrospectively call a cgroup near-OOM run a preflight guarantee.
4. Every normalization/native allocation remains fallible and admitted before its controlled allocation. Retain actual ResourcesExhausted/refusal as distinct from OOM, timeout, error and mismatch; no retry with a raised cap under the same run ID. Fix missing metadata/physical coverage or refuse the size before an unbounded full-graph allocation.
5. Within calls=3, one immutable revision/key, one graph+CSR cache, one current kernel/result/write. Release full result and lazy provider references after each write; drop graph/session after the final output, then require read states/owner release/process closure. An overwrite while old snapshots survive may retain two complete revisions; fresh graph/cell namespaces avoid that.
6. Report native ledger live/peak, native configured lease, participating Sail pool limit/reserved where instrumented, sampled process PSS, lifetime cgroup peak and memory.events separately. Native accounting excludes all metadata; PSS sampling can miss peaks; cgroup includes charged page cache and other processes. Low-memory cit success and B8 relational cells do not qualify native Graph500 admission or a lower VM cap.

**Current verdict: no32GiB native Graph500 fit claim.** The streamed representation is materially larger than the earlier CSR+edge floor. A conservatively justified bounded admission profile or an explicitly recorded unavailable/refused outcome is required before full Graph500 F2a execution. Do not change frozen B8 helpers or silently resize the VM.

## Exact source byte identities

- Sailf3 `examples/extensions/vendor/nutmeg-graph/src/session.rs` SHA `9fdb647bda2abdc0119cbd7bd8cbb594ed2b5b6572dddb20cb82b1ff4f3f307d`.
- Sailf3 `examples/extensions/vendor/nutmeg-graph/src/lib.rs` SHA `8117b13ef42d8a3c3ba00816a6c7bda8149da92252b5eb9aa37fcddaf1494b69`.
- Sailf3 `examples/extensions/vendor/nutmeg-graph/src/admission.rs` SHA `2c93d3b21d7dd6dd983d00ccfba3751f54fd0507ab3553213e5520f4ece2f6dd`.
- Sailf3 `examples/extensions/vendor/nutmeg-graph/src/graph_tables.rs` SHA `e073e1bee4fd0cef156dfdb568ed701cf4fe46df2568c0b560e26e5528a21dd1`.
- Sailf3 `examples/extensions/nutmeg/src/mutation.rs` SHA `da01f1582808506c99ed73846e913fa8bf6015e8ed860aa44485f1df169c973b`.
- Grust0.23/VCS5c41bcb `crates/grust-algorithms/src/arrow_input.rs` SHA `8b029418de9f2093d765133f43ecc326d811f237cb45cc1801fb3926a291cc87`.
- Grust0.23/VCS5c41bcb `crates/grust-algorithms/src/projection.rs` SHA `43cc4f510c88a862f642c72a3d268c38603646eec1e17167d41158786499233f`.
- Grust0.23/VCS5c41bcb `crates/grust-algorithms/src/projection/adjacency.rs` SHA `c4ff1b59cb6a6a290dc7969faea0c0e486a8729592f2bca9559c65b819190e0b`.
- Grust0.23/VCS5c41bcb `crates/grust-algorithms/src/buffer.rs` SHA `e62d39739191e6081b7fc8ffcdab68cbb5580ba859b8f1366291589955a7e7cc`.
- Grust0.23/VCS5c41bcb `crates/grust-algorithms/src/pagerank/pull.rs` SHA `b76f5cf26a96e544a1313d8dc400b4b19a125d6f1b3246619e1e713bc66de345`.
- Grust0.23/VCS5c41bcb `crates/grust-algorithms/src/traversal.rs` SHA `30dafd5ee04853f4f20eb73c42597f922c435574dd3f8a98239fffb1bc4d2a52`.
- Grust0.23/VCS5c41bcb `crates/grust-core/src/lib.rs` SHA `66d9e3f83edfbb976576525ae93bf0e016846793063b6be6a35eca459787c623`.

All listed local bytes equal Git blobs at their stated exact pin. Source-layout and reservation arithmetic above remain inference; no target/compiler size observation or runtime memory measurement is asserted.
