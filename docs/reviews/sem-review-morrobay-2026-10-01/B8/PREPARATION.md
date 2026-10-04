# B8: paired UNION and array/explode shapes

Preparation for Sem review remarks 11 and 23a. Measurements and actual guest
execution have not started. Root owns the gate; A2 and A3 precede this work.

## Scope

Use the A1 image and retained runtime/native pins, with controller
`f3b3ef8fc054ce7788ec2b46ec8b034ccec1f98a`. Each cell gets 16 CPUs, 32 GiB,
no swap, a fresh local Sail session and a 30 GiB greedy pool. The configured
native quota is 256 MiB; actual reservations are not yet measured. This is an isolated relational
shape comparison, not a complete WCC measurement.

| Shape | Shared result contract | Interpretation |
| --- | --- | --- |
| Adjacency | Unique directed pairs from E plus reverse(E), retaining loops | Two projections with UNION versus two structs with explode; common DISTINCT |
| Representatives | First contraction map for active non-loop endpoints, signed MIN of affine neighbour/self IDs | The f3 affine rewrite replaced the former fused implementation; no whole-WCC claim |
| Initial min-label round | Minimum of each original vertex ID and its undirected neighbours, including isolates | UNION versus a whole-update LEFT JOIN and array rewrite; report the extra join/repeated-seed work explicitly |

See [reference contracts](REFERENCE-CONTRACTS.md) and
[ownership and measurement boundaries](ORCHESTRATION.md). Full physical
outputs must match independent references outside the engine timer. Before
large cells, both variants of all three shapes run on a pinned tiny graph
containing signed/high-bit IDs, duplicate edges, loops and an isolate.
The f3 whole-WCC signed-isolate defect remains a separate known mismatch;
these shape controls do not qualify that algorithm.

## Order and boundary

Use the same pinned official Parquet inputs for each pair, first cit-Patents,
then Graph500-24. For each shape, retain UNION and array/explode warmups,
followed by `U A A U / U A A U`. Four measured samples per variant and two
blocks limit inference. Report array/explode over UNION ratios on shared
Morrobay, with all outcomes, memory boundaries and steal observations.

The child launch-to-exit boundary includes startup, reads/snapshots, shared
preparation, raw explain capture, full materialization/export and shutdown.
Input validation, reference construction, hashes, the full result oracle and
archival are outside. Raw plans describe the materialized shape before the
write sink; plan capture itself remains inside the timed child. Do not subtract
common phases or extrapolate a shape ratio to complete WCC.

## Storage

The campaign explicitly proposes 64 GiB free guest storage and 120 GiB free
Apo storage, 7200 s for reference construction, 3600 s for the whole cell
and 1800 s for its exact owned artifact copy. These differ from the helper's
defaults and are admission thresholds, not measured peaks or spill bounds.
The small staging helper retains its 600 s deadline.

Graph500-24 must be downloaded from the official links, preserving actual
body hashes, schemas, row counts and row-group sizes. Actual footer-based
admission precedes the separate full reference phase. The
[storage model](GRAPH500-24-STORAGE.md) uses historical counts only as an
illustration; no compression ratio is assumed.

Every passed cell's complete guest inventory is copied to Apo and rehashed.
Only after certain closure and complete archive verification may a separate
owned helper recheck and remove that exact passed cell payload. References,
failed payloads, original inputs and unrelated archives stay preserved.
Unexpected outcomes stop the queue and retain its lock for root review.
