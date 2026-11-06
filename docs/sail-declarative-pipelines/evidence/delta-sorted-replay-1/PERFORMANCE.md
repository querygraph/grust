# Sorted Delta replay performance review

**Disposition: no performance blocker for this local retention repair, with an
explicit scan cost.** Sparse history at execution batch size 256 was **5.17%
slower** in the final dev-build comparison; all three blocks were slower. The
earlier diagnostic recorded 2.84% for that cell, also slower in every block.
These observations are retained and accepted as a scoped engineering tradeoff
for removing unfunded private payload retention. They are not dismissed as noise,
and this is not a claim that every existing query becomes faster.

The release replay operator used less elapsed time in every measured paired
block. The downstream controls, including the deliberately fragmented batch-one
case, show no large fragmentation penalty on the preserved corpus. That evidence
supports the simple repair without adding a coalescer. It establishes neither a
production performance envelope nor a cumulative streaming performance verdict.

## Reviewed revision and evidence

| Identity | Pin |
| --- | --- |
| Frozen tree | `5181d08ac4b48dca578ea046a0313f572507e30a` |
| Parent commit | `3f741daad57df4bcc22cecfb7802d458b1ad1d06` |
| Parent tree | `92ca23c5a62bf972e61fd8295a5e48cdfb1d1c89` |
| Cumulative base | `b52144955b629314a000b1fe49eeea97fa3d0c5c` |
| Increment patch SHA-256 | `fa6ebb0decc14e981ec75453ed2f602b3b46a0078a132dfec296a88519dc47eb` |
| Cumulative patch SHA-256 | `b355791ad6ca29205a294edfcd1f4f7454c93464d7fe6228a1b5d6e46c79ff2c` |

I verified all 138 frozen source hashes, both patches, the changed production
replay code and its ownership/cost boundaries, the cumulative file inventory and
the preceding descriptor performance assessment. The increment's runtime changes
are confined to the sorted replay helper and its call site. Hash replay,
distribution/ordering, planner metadata and the scan consumer retain their parent
behavior. Earlier cumulative performance limitations remain below.

The raw audit independently matched all 56 operator samples to their stdout and
receipt entries, verified the 20 runtime pins, and recomputed every paired ratio
and output distribution. The final scan audit verified all four client records,
112 exact row/schema reads, four analyzed plans, all 644 preserved corpus files,
and cleanup of all eight owned server groups. The 112 reads comprise 72 measured
reads, 36 warmups and four separate metrics-control reads. Every ratio was
recomputed; no sample was omitted.

## Release replay operator

Both retained probes used Rust 1.98.1, identical probe bytes, matching dependency
features, optimization level 3, fat LTO, one codegen unit and the Rust system
allocator, with separate targets. Candidate executable SHA-256 is
`ca62c276afa4bdbf84953e465db83d8e527c8b0bca44186ff01703bbd220adf4`;
parent is `997ddd17b41b88a83d81a112a50ea590cca0efaf6e1598d785877a872168a073`.

Each case has one warmup per side and three ABBA blocks, with 32 drains per sample.
The actual public Sort operator runs over the same ordered inputs. Action-specific
identities distinguish newest winners from stale Adds; complete identities,
multiplicity, payload bytes, schema and types are checked before timing.

| Case | Median candidate/parent | Block ratios, in recorded order | Output batches per drain, parent → candidate |
| --- | ---: | --- | ---: |
| Dense | 0.08795 | 0.09312, 0.08795, 0.08751 | 4 → 128 |
| Sparse | 0.30718 | 0.30543, 0.30924, 0.30718 | 1 → 128 |
| Sparse-wide | 0.50502 | 0.50502, 0.91048, 0.17314 | 1 → 128 |
| Tombstone | 0.25793 | 0.27896, 0.24647, 0.25793 | 1 → 16 |

Ratios below one mean less elapsed time. Sparse-wide has substantial unexplained
spread; its median does not establish a stable twofold improvement. All blocks
and raw values remain evidence. The repaired dense output has 256 rows per batch;
sparse and tombstone output has one. Parent dense batches average 8,192 rows but
range from 7,937 to 8,447; the other parent cases emit all winners in one batch.
The increase in output batches is a real cost boundary, even when replay is faster.

Timing includes stream/context setup, replay, output construction and dropping
outputs. Fixture creation and complete value validation are outside it. Prebuilt
inputs remain held, and there is no downstream scanner in this probe. It cannot
measure private-memory reduction or resolve scan-construction costs.

## Final ordinary Delta scans

Both CLIs use matching unoptimized dev builds with debug information disabled,
default mimalloc and parallelism one. Candidate CLI SHA-256 is
`99360acacc78671397a4bf0832bf2ae471916f300a0309a1daf9e07ba8c6c114`;
parent is `ff12c2b3daa2451417d948bede5e662b44e3069d56212cf92759f925ffb043f9`.
These differ from the release operator's profile and allocator; compare within
each pair, not between experiments.

All scans read the same 64 Parquet files with exact nested values and duplicate
multiplicity. Preserved table bytes, schemas and row digests agree. Forced Sort
plans contain `DeltaLogReplayExec` and `DeltaScanByAddsExec`. Eager and Hash reads
serve as untimed correctness controls. The timed boundary is Spark Connect
`collect`, including execution, transport and client conversion; schema inspection,
explain and exact-value checks are outside it.

| Input batch rows | Snapshot | Final median | Final block ratios | Earlier diagnostic median |
| ---: | --- | ---: | --- | ---: |
| 256 | Dense, narrow v0 | 1.00422 | 0.84602, 1.00422, 1.01680 | 1.03029 |
| 256 | Sparse, narrow v256 | 1.05166 | 1.05177, 1.05166, 1.02003 | 1.02844 |
| 256 | Sparse, wide JSON v256 | 1.00157 | 0.99782, 1.00157, 1.07644 | 1.02693 |
| 8,192 | Dense, narrow v0 | 1.03957 | 1.03957, 0.99700, 1.07391 | 1.00701 |
| 8,192 | Sparse, narrow v256 | 0.99217 | 1.00405, 0.96420, 0.99217 | 1.01155 |
| 1 | Dense, narrow v0 | 0.99343 | 0.99343, 0.99415, 0.98824 | 1.01843 |

Ratios above one mean slower. The 5.17% sparse/256 cost is repeated evidence,
not erased by the faster cells. The 3.96% dense/8,192 median and individual slower
blocks also remain in the record. The batch-one contrast reads only the initial
commit and stresses the smaller replay outputs without 256 historical commits
diluting them. Its results do not isolate scan construction; batch size one also
changes downstream batching on both binaries.

The final four analyzed plans open and process 64 Parquet files each, with no
file-open or scan errors and 64 data output batches. Sort produces one input batch
to replay for dense v0 and 65 for sparse v256. Replay reports no own runtime
metrics. Data output counts and aggregate file-source metrics do not count replay
batches or dynamically created scan groups. Overlapping timers cannot be summed
to attribute the observed slowdown to one cause. Wide JSON statistics are projected
out before replay; that scan measures parsing/history work, while the release
sparse-wide probe covers wide output gathering.

The earlier scans used diagnostic tree `e9e552f4a1a030282397e26eb240d6b27c376691`
and a different CLI hash. They remain intact. The final rerun qualified changed
artifact bytes; it was not a retry chosen to remove unfavorable measurements.

## Qualification boundary

The host is shared Darwin 25.2.0 arm64 with ten CPUs. CPU steal is unavailable;
load varies. ABBA ordering helps balance drift but supplies no dedicated-host
guarantee or statistical confidence interval. The runner's 10% flag is triage,
not the basis for accepting smaller costs. The scoped acceptance rests on the
correctness defect repaired, lower measured release replay work, the bounded
observed scan costs and absence of a large penalty in the tested fragmentation
controls. It does not promise the same ratios on other tables or configurations.

The lifetime and reservation controls own the memory claim: no private payload
references survive an input pull, with owned key and selector charges funded.
Returned Arrow storage, kernel scratch, upstream sorting and total task memory
are separate. Mixed-marker fragmentation, short-stream startup costs, descriptor
binding costs, bounded manifest capture and integrated recovery remain outside
this increment's performance result. The full redesign is not performance-qualified.

The saved task, request and governance were reread; compliance is confirmed.
This review ran no builds, tests, probes or servers and changed no production
source. [Performance audit identity](qualification.json)
and [scan audit identity](qualification.json) pin the raw
evidence and preserve the explicit accepted costs.
