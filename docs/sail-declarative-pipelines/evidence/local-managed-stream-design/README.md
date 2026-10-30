# Local stream design source evidence

This packet pins Sail71f24a87a2 and installed DataFusion55.2.0 source boundaries
for the [selected shared-owner design](../../LOCAL-STREAM-OWNERSHIP-DESIGN.md).
The stop-contract audit distinguishes the one direct runner stop call from the
larger session/cluster lifecycle. Exact source windows and full-file hashes are
in sources.json. No source search or actor acknowledgement is treated as proof
that all effects have stopped.

The supervisor counterexample is reasoning from the Stream polling contract:
dropping a borrowed next() future supplies no cancellation event to a background
owner while the stream is retained. The selected owner polls only on the consumer
call stack; a polling lease permits cancellation to take ownership afterwards.
Implementation tests and gates are separate evidence. This packet itself executes
no runtime tests and establishes no new public SDP or ORC writer coverage.

Read-only peer review required recovery ownership across prior-waker destruction,
resource-cancellation callbacks and discarded-batch destruction. It also required
an explicit interrupted-cleanup report when the runtime drops a cleanup task.
The first implementation is a prepared-stream component; preparation admission,
job retirement, session deletion outcomes and cluster shutdown remain open.
