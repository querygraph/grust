# Session cleanup design source audit

This packet supports the [incomplete design checkpoint](../../SESSION-CLEANUP-LIFECYCLE-DESIGN.md).
The Sail source pin is `ec8e74d57de51149a774cd4f9048d82039704d0c`; Spark 4.2.1
is pinned at `617618396087429b5627a86ce933bb0f5d6645cb`. The audit files remain
unchanged from that baseline. Their schedules are source-derived requirements,
not observed runtime fault reproductions or evidence of implemented cleanup.

- [Deletion state and creation ownership](deletion-state-audit.md).
- [Manager, actors and transport shutdown](manager-shutdown-audit.md).
- [Checkpoint mutation and provider effects](checkpoint-effect-audit.md), with
  [exact Sail and dependency source hashes](checkpoint-effect-sources.json).
- [Operation, preparation and executor ownership](operation-ownership-audit.md).

The design selects lifecycle policy in sail-session, one retained cleanup owner
per session, admission closure, cancellation before dependent joins, and manager
Closing while it continues serving required lifecycle messages. It distinguishes
manager cleanup completion from joining the actor future. The operation admission
seam, effect adapter and exact retained cleanup driver remain unresolved. No
generic actor rewrite, complete cluster barrier or CDC recovery implementation
has been selected by this packet.

A final independent source review found no new material architecture blocker after
those ownership and ordering clarifications. It requested that the now-completed
registry prerequisite be identified as subsequent work instead of an outstanding
baseline defect. That status is updated in the design. The separate
[registry packet](../checkpoint-registry-recovery/README.md) records its actual
implementation gates; it does not qualify the remaining effect/lifecycle design.

`provenance.json` hashes every packet file except itself. The design and this
review summary are documentation; no new runtime or Spark-suite coverage follows.
