# Repeated nested-schema materialization ports

Recorded 2026-10-30T02:41:33.921674+00:00. Sail `f6f13281929812482529446ce6edcc3eeac0a069` adds two public behavioral ports of Spark4.2.1 MaterializeTablesSuite:735 and780. Three materialized views preserve the original MAP/STRUCT/ARRAY queries, typed integer-array input, join expressions and six exact DDL schemas, checked after two refreshes of the same catalog outputs.

Both cases pass, with no failures/errors/skips; Ruff and formatting pass. This Python-only commit reuses the exact CLI from6d0c4beea (previously298 public/67 upstream executions); the runner verifies the binary hash and proves only the new Python test differs. It does not claim300 tests were executed together. No Rust rebuild was needed.

The first attempt erroneously started the same Connect graph twice. Its two failures and original test remain retained. Pinned SessionHolder.scala rejects a second execution holder for the same graph, so each refresh now registers a new graph against the same output tables. The original Scala test calls internal materializeGraph twice without this Connect lifecycle. These are partial public ports, not execution of the original Scala entry point or proof of all internal metadata behavior. Full source and licenses are retained; no new Spark runtime reference was executed.

All evidence files are inventoried by provenance.json. The full SDP goal, ORC writer, streaming/Iggy and CDC remain open.
