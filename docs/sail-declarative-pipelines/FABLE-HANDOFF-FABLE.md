# Fable's supplement to FABLE-HANDOFF.md

Codex wrote [`FABLE-HANDOFF.md`](../../FABLE-HANDOFF.md) (canonical, in the
coordinator worktree) through CF-0044. This file is Fable's own, updated by
Fable's doc commits only, and records what moved after that snapshot plus the
Fable-side facts a successor needs. Read the live log from the last
acknowledged reference before trusting either file.

## Since the CF-0044 snapshot (2026-10-30)

| Item                                                     | State                                                                                                                                                                                                                                                                                              |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `769914891` C5 global phase + incarnation-bound progress | detached VERDICT passed at 09:15:55Z (CF-0045); Codex review pending                                                                                                                                                                                                                               |
| `dc8b7eb31` unit 5 corrections (CF-0043)                 | offered CF-0045; detached VERDICT passed at 09:20:20Z (CF-0046): IPC-canonical schema digest, field-by-field `verify`, strict case labels, keys bound through the C4 lookup for every row count                                                                                                    |
| `d38058973` corpus replay test                           | detached VERDICT passed at 09:05:09Z; both independent corpora replay with zero mismatches (Grust `f13e9b48`)                                                                                                                                                                                      |
| unit-4 design                                            | revised `8b0dc3af` after CF-0044 (read mode bound before resolution, absent vs empty intent, stream-stream joins rejected, volatile expressions evaluated once, evaluation snapshot named as an addition, one runner-owned scope, dry run unchanged, owned adapter calls); no Sail edit for unit 4 |
| unit 6                                                   | Grust `8b0bd605`, `evidence/fable-iggy-harness`: five scenarios on the pinned broker plus 23 pinned Iggy tests; not reviewed by Codex yet                                                                                                                                                          |
| `71e4a94d9` expected-identity verify                     | detached VERDICT passed; `verify` takes the expected identity from the recorded intent (CF-0053 follow-up)                                                                                                                                                                                         |
| `33a883091` move-only extraction                         | `BoundedSource` and its DTOs now in `sail-common-datafusion::streaming::bounded`, Connect re-exports; detached VERDICT passed                                                                                                                                                                      |
| `bc23c8db6`, `105967e17`, `798cd35c9` failure model      | per-flow `FailureReport` (`pipelines/failures.rs`), `carry`/`recover` through `DataFusionError::External`, `SparkError::UnresolvedPipeline` retained up to the Status arm; variant approved in CF-0074; detached VERDICT for `798cd35c9` at 11:08:52Z (CF-0078); loop unwired                      |
| C5 loop proposal                                         | revision 3 (`3a40258a`, CF-0080): availability gated on all producers resolved, nine-phase table, three error shapes, three-structure loop, CF-0074 fixtures; awaiting Codex's (a)–(c) before any `analysis.rs` edit                                                                               |

Ordered Sail commits on `work/sdp-streaming-cdc-fable` (base `779cb136d`):
`d07a95c2c` (vendor), `167d577c6` (original consumer), `49f32b65d`, `29056716b`,
`f4537586b`, `a495cb02d`, `2dcd0eaa9`, `550bb198a`, `1eea0b140`, `b7118b953`,
`f7adb3f05`, `c9a0132cf`, `6620ee940`, `d38058973`, `769914891`, `dc8b7eb31`,
`71e4a94d9`, `33a883091`, `bc23c8db6`, `105967e17`, `798cd35c9`.
Every one after the original two carries a detached verdict in a Grust packet.
The vendor commit precedes the consumer in Git ancestry; CF-0050 corrected an
earlier listing that had them reversed.

## What a successor Fable does first

1. `--since <last Fable Seen-Through>` on the canonical log, then ACK with the
   printed read-through.
2. `git -C /Users/alexy/src/sail-sdp-fable status` and `log -3`; `git -C
/Users/alexy/src/grust-sdp-fable status`. Both should be clean at the
   commits above unless a later entry says otherwise.
3. Do not start unit-4 Sail code until Codex accepts the revised draft; do
   not re-offer integrated work (the reader `2103fb56` is integrated as
   Codex `b7290eb1`).
4. Expect Codex's reviews to arrive as source-derived counterexamples;
   answer each finding as accepted, disputed or investigating, with file
   scope, before editing.

## Known divergences Fable has recorded, not fixed

- Sail merges an output's flow schemas inside the resolution loop; Spark
  infers at demand time inside each reader, in the user-schema phase for
  tables with a same-named flow, and raw in the last phase (C5 proposal §3).
  Fixtured in both declaration orders in `test_autocdc_definition.py`
  (`test_schema_merge_inside_resolution_runs_in_declaration_order`).
- Sail reports the first resolution failure it meets in its own dependency
  order, not Spark's collected `UnresolvedPipelineException`.
- Temporary view identifiers are single-part in Sail's CDC errors; the
  unstructured MV/persisted-view streamingness errors keep Sail's form.
- Reserved-name collision in dedup: DataFusion's duplicate-column error, not
  `AMBIGUOUS_REFERENCE`.
- Dedup ties: last row in sequence order (inside Spark's "undefined"); B12
  tie-break by source position is an open C0 decision.
