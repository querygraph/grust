# A replayable Delta source for continuous pipelines

A streaming table must resume the same input after failure. A Delta version alone
cannot describe a checkpoint halfway through a file, and reopening that version
under a newer schema can change its meaning. Add a native continuous `StreamSource`
that reads an identified snapshot, then append commits, and reports the next physical
row it will read. A source boundary supplies input recovery; it does not establish
durable target completion. These interfaces are proposed; source inspection identifies
the reuse points, but the replay path has not been implemented or qualified.

## Reuse Sail's reader without inheriting its scheduling

Sail already loads Delta metadata and transaction logs, reconstructs active files,
decodes partition values and column mapping, and reads Parquet through DataFusion.
Its existing bounded streaming reader selects version ranges and builds a table
query. Its bulk file scanner groups and splits files for parallel tasks. Neither
query batches nor task partitions are stable restart identities.

Reuse log discovery, snapshot reconstruction and file-scan construction inside one
long-lived reader. The reader owns discovery, the current file stream, its position
and source controls. Exhausting a file or commit advances that reader rather than
ending a job. Replay adds a durable position to ordered control acknowledgements
bound to the executing source; a handle to the planning descriptor is insufficient.

## Capture the meaning of the read

Create a versioned descriptor when the pipeline first binds this source. Persist:

- A pipeline-assigned source-definition identity, normalized table locator and Delta
  metadata table ID. This distinguishes the declared source, its storage address and
  its current incarnation. A compiled source occurrence ID remains temporary.
- The resolved starting boundary, full effective Arrow schema including nested field
  metadata, Delta protocol and column-mapping metadata, partition columns, and all
  reader options that affect interpretation. Credentials remain runtime configuration.
- The descriptor format version and digest of its canonical encoding. Preserve field
  order and sort map entries; hashing ordinary map serialization is insufficient.

Derive the fixed read schema from the selected snapshot or starting version, not a
later table head. Validate every consumed commit's protocol and schema against it
before emitting that commit's rows. Incompatible changes and unsupported features
receive explicit errors. Supporting additive schema changes is a
reasonable later policy, but requires a specified treatment of missing and extra fields.

With no explicit start, capture snapshot version V and its exact active files, then
tail V+1. An empty snapshot still records V. An explicit starting version begins with
that commit; a timestamp is resolved once and its resulting version is saved. Recommend
that `latest` records an after-V anchor immediately, so later commits are consumed.
It must not be re-evaluated on every restart. This deliberately differs from the bounded
reader's existing empty-first-run behavior; keep its tests and add durable-mode tests.

For timestamp starts, choose the earliest version through the captured head whose
authoritative timestamp is at least the requested UTC instant. Then consume every
subsequent version: this selects a prefix boundary, not a continuing time filter.
Use Delta's enabled in-commit timestamps and legacy log-file modification times;
ordinary `commitInfo.timestamp` is not a substitute. Preserve submillisecond request
precision. Equal or decreasing legacy times require an ordered search, not binary
search. For times 100, 90 and 110 milliseconds, a request at 100 starts at the first
commit; one at 100.5 starts at the third.

An alternative adjusts legacy times upward to form a monotonic history, as existing
history presentation does. Prefer literal authoritative times here: the boundary is
explicit without inventing times. Require timestamp evidence from version zero through
the first match; missing history or no match fails explicitly. Version, snapshot and
latest starts remain available without that history walk. This costs one metadata
search at binding, uses constant auxiliary state and never changes ordinary batch or
bounded-stream timestamp behavior.

## Admit a precise descriptor

The first descriptor admits path-based Parquet tables with no format options. Reject
catalog-managed logs without their commit context, unknown protocol features and
incomplete column mappings. Require globally unique positive mapping IDs and
sibling-unique physical names on mapped fields, including fields inside collections. Collection
wrappers and Variant storage children are not separate mapped columns. Pin the full
schema and normalized protocol feature sets. Initially require exact equality at
consumed versions, even for otherwise harmless writer-only protocol upgrades; a more
permissive compatibility relation needs its own evidence.

Use versioned canonical JSON and a domain-separated SHA-256 digest. Sort object keys
and protocol feature sets while preserving field order. Name the Arrow schema encoding
version and retain golden fixtures across dependency upgrades. Limit descriptors to
4 MiB and JSON nesting to 64 containers. Reject duplicate or unknown fields, trailing
input, unsupported versions and invalid schema structures before conversion. Admit the
logical Arrow types Delta actually produces; lossy conversion of other Arrow layouts
is not a valid descriptor. Credentials belong to runtime object-store configuration:
reject URL userinfo, queries and fragments rather than persisting or silently stripping
them. Fixed-schema, append-only and fail-on-loss semantics are one closed typed policy.

## Identify files and retain the input

Each snapshot or consecutive range of tail commits has an immutable manifest. This
is one input segment. Snapshot files have a stable
order by resolved Delta file path; tail entries are ordered by commit version and file
path. Each entry records the file key, the admitted Delta `Add` action describing that
file, partition values and explicit commit association. Do not rely on serializing
`Add` alone: its in-memory
commit fields are omitted by serialization.

Keep references acyclic: canonical descriptor bytes produce identity D; each segment
root references D and its ordered page digests; a position references D, that root and
its cursor. Hash payloads without their own digest fields. Pages never contain the
root digest that depends on them. The descriptor retains its initial anchor; subsequent
segments do not change it. Tail segments cover consecutive commit versions, including
versions with no data, so regrouping segments cannot omit a commit.

Use Sail's existing ObjectStore interface with a caller-owned artifact prefix and
resource limits. Reuse memory accounting and spill for capture and canonical sorting;
write bounded manifest pages and then their root. The admitted backend must supply
the completed-write and restart durability required for these artifacts. The connector
returns a verified reference; the checkpoint owner publishes resumable progress and
retains its referenced artifacts. No connector-owned latest pointer, checkpoint counter
or cleanup service is needed. A barrier cannot name an incomplete root.

Admit storage where committed data paths are immutable and required log and data files
remain retained for every supported restart point. This is an input contract, not a
promise to detect arbitrary mutation. A manifest digest protects saved metadata; it
does not prove unchanged Parquet bytes. Do not hash or copy every data file by default.
Object versions with conditional reads can strengthen identity where available;
immutable input copies are an alternative for storage that cannot provide the contract.
Neither mechanism is required merely to distrust otherwise valid input.

Validate the current table ID through fresh metadata on capture, resume, new segment
discovery and idle boundary capture. A cached snapshot at the same version cannot
detect a table recreated at an equal or lower version. Fresh checks reject observed
changes; they cannot prevent replacement between a check and a read. Admission assumes
the source namespace is not concurrently rebound during capture or reading. A stronger
guarantee needs an enforcing namespace or catalog mechanism, or immutable input copies.
Observe required input failures when opening and reading files, and never advance
past missing input. A complete saved
manifest may remove dependence on old log entries for that segment; it cannot replace
missing data or the metadata needed to establish current incarnation.

Initially reject deletion-vector-bearing input, change data feed (CDF) mode, lossy read
options and commits with data-changing removals. Admit ordinary append files. Validated
commits with no data changes advance the version without re-emitting their files.
Deletion vectors and CDF need separate position and admission tests before support.

## Name a prefix independently of execution

Recommend one ordered logical lane for the first reader. A versioned position binds
the descriptor and manifest identities to either an exclusive next physical row in a
named file or an explicit after-version state. For example, a cut at file B, row 4096
means all preceding manifest files and B's rows 0–4095 have been emitted. Restart begins
at row 4096 even if Arrow batch size changes.

Physical rows are counted before user filtering or projection. Keep the internal row
coordinate when the user requests no columns. Reuse file-scan construction for one
admitted file at a time under the pinned schema
and column mapping, without predicates, limits, byte splitting or row-eliminating
pruning. Require Parquet preserve-order execution. Do not let the ordinary relaxed
schema adapter choose interpretation for a saved position.
Sail already exposes Parquet row numbers, but the reader must prove a contiguous prefix:
seeing row 100 after an out-of-order split does not mean rows 0–99 were emitted.

A file-boundary-only cursor is simpler but makes checkpoint latency depend on file
size. Parallel fixed logical lanes would preserve throughput with a position vector
and alignment. Start with one lane, measure its cost, and add lanes without making task
assignment part of persistent identity. This limitation must be visible in admission.

The current rate receipt contains a live row ordinal, explicitly not a replay offset.
Preserve that distinction. Recommend a common tagged position envelope carrying source
identity, connector/format version and bounded encoded payload, with typed construction
and validation by the Delta codec. Common control code need not depend on Delta types.
Unknown formats and mismatched descriptors fail before execution; arbitrary maps are
not accepted as positions. A generic control API parameterized by connector position
type is the alternative; assess its cost at heterogeneous job and worker boundaries.

The reader services controls independently of idle discovery and pending file I/O.
It encodes the marker and acknowledges the corresponding prefix through the existing
registration checks. Decoded or prefetched rows beyond that prefix remain uncommitted
reader state. Cancellation revokes requests. An idle tail can produce a boundary;
it is not EOF. Captured bounded ends and final durable completion remain distinct.

## Build and verify three connected increments

First implement descriptor types, canonical encoding, start-boundary resolution,
strict decoding and fixed-schema/incarnation admission in the Delta crate. Use real
local Delta fixtures, including persistent empty anchors. This unit needs no checkpoint
store, scheduler or common position framework, and advertises no replay capability.

Next implement bounded segment capture and manifest publication through the caller's
existing storage and resource interfaces. Define the Delta position format against
those manifests. Finally implement the persistent reader, plan codec and control-position
envelope. Its identity, order and input admission contract must precede that integration.
Target-authority work can proceed independently.

Verify exact rows and multiplicities through actual reads: snapshot-to-tail transition,
mid-file restart under changed batch sizes, zero-column output, empty snapshots,
metadata-only commits, idle cuts and cancellation. Recreate tables at equal/lower
versions, remove required files or logs, alter schema, corrupt manifest pages and
exercise every named refusal. Tests must fail when schema/identity validation is
removed, `latest` is re-resolved, or a post-filter count substitutes for physical rows.
Retain ordinary Delta reads and bounded-runtime behavior as controls. Measure ordered
reader throughput and checkpoint latency separately; descriptor tests cannot prove
integrated recovery.

The decisions before the reader are the immutable-input admission contract, one-lane
position semantics and typed replay envelope. The recommendations above give a concrete
first implementation; production admission waits for executed evidence.
