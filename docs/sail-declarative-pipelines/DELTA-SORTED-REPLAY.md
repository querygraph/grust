# Release Delta replay payloads as their input batch is consumed

A Delta snapshot reconstructs the active files from Add and Remove actions. Sail
already supports doing this through an externally sorted stream, which can spill
history to disk. Bounded manifest capture should reuse that operator. The previous
private output buffer let a small number of retained rows keep many large Arrow
input buffers alive.

The repair below is implemented and [locally qualified](evidence/delta-sorted-replay-1/README.md),
including measured downstream scan costs. Manifest capture and the continuous reader remain unbuilt.

This plan concerns `DeltaLogReplayExec` in Sort mode. It changes neither the Delta
reconciliation rule nor the choice between sorted and hash replay. It is an optional
implementation reference for the [Delta source design](DELTA-REPLAY-SOURCE.md).

## Why the previous buffer grew

The child orders actions by logical file key, newest version first, with Add before
Remove on an equal version. The first action for a key therefore decides its result:
emit that Add, or emit nothing for that Remove. Older actions cannot change it.

The previous operator saved a one-row Arrow slice until the key changed, then
accumulated slices until it had at least 8,192 winners. An Arrow slice shares its
parent buffers. For example, retaining one file description from each of many wide
input batches can retain all those batches, even when the useful descriptions are
small. That Sort branch had no memory reservation for this retained payload. A row
threshold does not bound its bytes.

This ownership problem also affected ordinary Delta reads using sorted replay. A
manifest writer that merely paged the eventual output would have left it intact.

## Recommend emitting winners from each input batch

Select the first action for each new key while scanning an input batch. Emit its
payload when it is an Add. Retain only the owned current key, which records that decision,
across batches; discard older actions for that key. Produce one output batch from
the selected rows, or continue reading if none survive. No pending winner or array
slice needs to survive privately while the operator fetches another input batch.

Preserve the declared output schema, nested metadata, logical rows and their order.
Keep existing replay-column validation and tie handling. Batch boundaries and the
time at which a completed batch becomes available may change; neither is a persistent
file identity. EOF needs no deferred winner flush. Errors and cancellation must
release owned state through the normal stream lifecycle.

Fund the owned key and top-level row indices through the task's existing memory
pool, reserving before growth and releasing when ownership ends. Compare borrowed
keys within a batch and copy only its final non-null key. This eliminates private
payload accumulation across batches. A finite task pool also limits the owned key
and index storage. Arrow kernel scratch space and returned output, upstream decoding
and sorting, and downstream consumers have separate resource responsibilities; this
reservation does not establish a byte bound for the whole query.

Use Arrow's existing gather kernel with 64-bit row indices and construct the result
with its declared schema and explicit row count, including zero-column output.
The installed bitmap filter reconstructs child metadata for run-end encoded arrays;
the gather kernel preserves it. A bitmap uses less selection memory, but repairing
or wrapping that dependency adds maintenance cost. Measure the existing gather path
before considering that alternative.

## Alternatives and the performance decision

A byte-accounted accumulator could preserve larger output batches. It would need
compact ownership of retained payload, allocation checks before growth and headroom
for concatenation. Tracking the same shared buffers across many slices adds complexity
that immediate emission avoids.

An existing Arrow coalescer is preferable to a new batching implementation if
measurements require one. However, some coalescer paths also retain slices, and
concatenation temporarily needs additional memory. Adding a coalescer without an
ownership and reservation contract would move the defect.

Start with per-input-batch emission. Compare dense winners, sparse winners after long
histories, wide payloads and tombstone-heavy histories. Measure both replay and a real
downstream Delta scan: sparse survivors can create small batches and increase scan
overhead. A material slowdown requires resolving this batching choice before calling
the repair ready. Shared-host diagnostics establish comparative costs, not production
throughput.

## Evidence required before accepting the repair

Retain a control that demonstrates the old operator keeps prior payload buffers alive
while requesting later input. Release producer and consumer references so the control
isolates ownership inside replay. The repaired operator must release those private
references. Exercise groups spanning batches, empty batches, long runs of older
actions, existing internal tie handling, cancellation and error termination. A valid
Delta commit cannot contain both Add and Remove for the same logical file key;
public fixtures must use valid histories. Verify reservation
release and named resource failure when the key or selection cannot be funded.

Check exact output membership, multiplicity, order and schema under changed input
batch boundaries. Force the public Delta path with `metadataAsDataRead=true` and
`deltaLogReplayStrategy=sort`, retaining ordinary reads and the other replay strategies
as controls. Cover deletion-vector file identity even though the initial continuous
reader will refuse active deletion vectors: this is a shared operator repair.

This increment adds no manifest format, checkpoint position or publication service.
Manifest capture still needs streaming discovery and checkpoint decoding, complete Add
metadata, distinct snapshot-as-of and original-commit provenance, a bounded index, and
artifact durability matching the checkpoint's failure model. Fixing this buffer removes
one concrete obstacle without claiming those contracts are implemented.
