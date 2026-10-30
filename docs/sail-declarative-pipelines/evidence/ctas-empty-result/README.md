# CTAS empty command result

Recorded 2026-10-30T02:38:29.438219+00:00. Sail `6d0c4beea43e426d4d8806563854a5f9dae34256` executes CTAS through the existing BarrierNode and then returns an empty schema with no rows. The write is drained as a precondition; a zero-row limit would risk optimizing away the mutation. Existing write APIs retain their internal results.

The fresh exact-candidate CLI passes 298 selected public cases and 67 upstream Python executions, with zero failures/errors/skips. Two new CTAS cases collect the command result and then verify the created table schema and contents for zero and three input rows. This extends the previous 296-case selection. Formatting, strict Clippy and all 37 planner tests pass. Python formatting passes; the same three pre-existing unused-noqa lint findings occur at the parent and candidate. The initial formatting-only candidate failed and is retained, as is the initial lint comparison whose outside-tree filename changed import classification.

Pinned Spark4.2.1 source `617618396087429b5627a86ce933bb0f5d6645cb` returns Seq.empty[Row] for CTAS; its full source and license are retained. This is source evidence, not a new Spark runtime reference. The prior extra-collect UInt64 failure remains in the public ORC packet as historical evidence. No original Scala registration is newly qualified; the full SDP goal, ORC writer, streaming/Iggy and CDC remain unfinished.

The runtime receipt records the CLI hash, commands, log hashes and owned server cleanup. Full raw logs and original gate receipts are preserved. `provenance.json` inventories all packet files except itself.
