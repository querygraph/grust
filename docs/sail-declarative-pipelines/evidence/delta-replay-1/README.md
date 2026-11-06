# Delta replay descriptor qualification and source design

The [design plan](../../DELTA-REPLAY-SOURCE.md) separates descriptor admission,
manifest capture and continuous reader/control integration. The descriptor is now
implemented and locally qualified. Manifest capture and the continuous reader remain
unbuilt; the earlier bounded Delta reader remains a reference.

`plan-before-code.json` pins the preceding plan. `source-inspection.md` identifies
inspected source revisions and reuse points; it reports no executed runtime tests.
The current request and constraints are retained in [the request record](REQUEST.txt)
and its linked predecessors. `descriptor-plan-before-code.json` pins the descriptor
admission and timestamp clarification before its implementation. These requirements
add no claim that a reader or recovery protocol has been built.

The design keeps descriptor and progress identities separate, uses existing storage
and resource interfaces, and states the limits of incarnation observations. Target
fencing and integrated recovery remain distinct qualification requirements.

## Qualified metadata increment

Local commit `3f741daad57df4bcc22cecfb7802d458b1ad1d06`, tree
`92ca23c5a62bf972e61fd8295a5e48cdfb1d1c89`, passed immutable qualification. Its
parent is `bd1847d8e1afa7b8045799534b0e321f16c2a7f0`; cumulative review and public
regression comparisons use upstream `b52144955b629314a000b1fe49eeea97fa3d0c5c`.
Source remains local and unpushed. The [qualification record](qualification.json)
pins the exact receipts, artifacts, comparisons and seven final specialist reviews.
Newer upstream revisions are outside this qualification.

The descriptor captures source-definition identity, normalized table location,
table ID, complete schema, protocol, partition mapping and a resolved starting
boundary. Canonical encoding and strict decoding preserve this meaning without
reopening the table. Empty snapshots and after-version anchors remain explicit.
Timestamp resolution uses authoritative timestamps and preserves submillisecond
request precision; it does not alter ordinary Delta timestamp behavior.

Internal tests exercise real Delta log and checkpoint formats in an in-memory
object store, golden descriptor bytes, invalid schemas and mappings, and malformed
timestamp properties. Controls demonstrate failures before the Variant, property
and mapping-width corrections. The descriptor exposes no ordinary planner or
reader integration and advertises no replay capability.

Formatting, strict Clippy and Rustdoc passed. Rustdoc retains two link-lint
exceptions confined to the generated Spark protobuf module; handwritten
documentation remains strict. All 384 Delta internal tests and
2,169 workspace tests passed; one existing Rust test remains ignored. Fresh CLI
and native artifacts from the committed revision have exactly the hashes used
in the public comparisons.

## Public behavior and remaining coverage gaps

Upstream, the previous local revision and the candidate have identical outcomes
for 2,170 collected external Delta tests: 2,105 passed, 42 expected failures,
21 skipped tests and two failures. Seventeen external skips passed separately in
native mode. The unchanged concurrency module is also skipped before collection;
it is not included in the 2,170 nodes. The prior 51 rate, streaming and projection
checks passed. Existing assertions, expected-failure markers and skips were retained.

The two failures occur in JVM-generated Parquet-layout preconditions before the
original downstream row assertions. Direct footer and file inspection confirms
that the assumed-absent partition columns physically exist. Separate read-only
probes preserve the original expected Sail rows through both reader modes and pass
on all three revisions, with every retained file unchanged. These probes do not
turn the original failures into passes. Raw failure descriptions and their
comparison-specific explanations remain in the pinned evidence.

## Cost and readiness boundary

The optimized shared-host diagnostic contains 48 records. All 22 paired boundary
captures preserve the metadata loader's request and consumed-byte counts, and no
data-file read was attempted. Timestamp selection through a checkpoint adds 32
metadata HEAD calls in the measured history. Validation and canonical encoding
add CPU work: measured capture/direct-load median ratios range from 1.01 to 2.03
across the representative cases. These are diagnostic costs, not production
throughput or remote-store latency measurements.

The 4 MiB descriptor encoding bound is not a peak-memory guarantee for metadata
loading. Existing loaders can fall back to full replay, and checkpoint projection
can download the full compressed checkpoint. The
[sorted-replay repair plan](../../DELTA-SORTED-REPLAY.md) addresses one concrete
payload-retention problem before bounded manifest capture.

Source-to-table recovery, distributed alignment, enforced target ownership and
native package integration remain separate work. Mixed-marker fragmentation and
short-stream startup costs also remain open. Component qualification and specialist
reviews do not establish production readiness or maintainer agreement.
