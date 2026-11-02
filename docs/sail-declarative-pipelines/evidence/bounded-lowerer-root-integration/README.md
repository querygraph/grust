# Pure bounded lowerer integrated

Sail `bc592d7e314614c10da58f183f8bfeb30ce69e5b`, parent `7b008daa1`,
imports Fable `40b979ec98a5d917b8c8555936629eb02404595f`. All five blobs
match: lowerer, tests, module, Cargo.toml and Cargo.lock. The only lock change is
Connect's consuming sha2 edge; package set/versions are unchanged (already used
elsewhere). No SDK dependency or public/runtime activation.

Exact detached actual-parent fmt, strict all-target/all-feature Clippy and
134 common-datafusion + 130 Connect library tests pass (264 total), including
13 lowerer cases. They cover actual in-memory rows for recorded ranges, empty
intent, stream-local graph placeholders/materialized substitutions, static/local
identity snapshots and lossless JSON names. Original lowerer failures/corrections
remain in the separate fable-local-lowering-review packet; this is the combined
root import, not a substitute for those independent controls.

The result is a logical plan, admission evidence and a declared configuration/
binding snapshot. It is not exhaustive replay identity or proof of actual backend
pins. Scope is borrowed but unused; only in-memory bindings are qualified here.
No frontier/checkpoint/target acknowledgement, broker or CDC effects. Standard
LowerError source-chain correction and actual Sail clock tests are later units.
Full original Spark SDP acceptance and ownership/representation decisions remain
open. No new optimized/public CLI verdict at this commit.

SHA256.json covers all packet files except itself. Historical receipt/script
paths are not replay destinations; use fresh outputs.
