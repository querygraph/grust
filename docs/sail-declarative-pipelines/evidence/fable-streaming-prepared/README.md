# Fable units 3 and 5: bounded source contract and prepared CDC input

Two pure components on Sail `work/sdp-streaming-cdc-fable`, nothing wired:
unit 3 (`c9a0132cf`) adds `pipelines/streaming` with the source adapter
contract, the run-frontier and batch-intent records and an in-process
deterministic source; unit 5 (`6620ee940`) adds `autocdc/prepared.rs`, the
manifest that binds a batch's input identity, its validation receipt and the
digest of its reconciled rows. `provenance.json` pins commits, gate verdicts,
the reuse check and the one nondeterminism the tests exposed; `logs/` holds
the gate logs and the test run.

## Unit 3: what the contract fixes

| Design point (§5.2) | Where | Enforced by |
| --- | --- | --- |
| opaque cursors and incarnations | `source.rs::{Cursor, Incarnation}` | generic code only stores, compares for equality and serialises them; `DeterministicSource` refuses tokens it did not mint (`ForeignCursor`) |
| frontier captured once per run | `intent.rs::RunFrontier::capture` | later batches read ends from the record; the test appends rows after capture and shows the run never reads them |
| range planning in the adapter | `BoundedSource::plan_end` | `next_intent` decides "caught up" by equality only |
| scan yields exactly `[start, end)` or fails closed | `BoundedSource::scan` → `ScanError` | retention gap, incarnation mismatch, non-contiguous page, unknown partition, each a test |
| replay re-plans nothing | `BatchIntent` serde round trip | recorded intents rescanned after appends yield identical rows |
| partition changes between runs | `next_intent` | new partitions start at `earliest`; a disappeared partition with an unprogressed intent errors; empty partitions add no range |

Error conditions are Sail's own; no Spark parity is claimed for them.

## Unit 5: what the manifest binds

`InputIdentity` = flow identifier + batch id + the unit-3 intent ranges + an
evaluation context (case setting, keys, sequencing text, delete condition,
column selection), digested as SHA-256 of canonical JSON. `ValidationReceipt`
records the unit-2a outcome for that identity, keeping the exact
`AUTOCDC_MICROBATCH_VALIDATION` condition on failure. `seal` refuses a
receipt for another identity or a failed one and digests the reconciled rows
as one Arrow IPC stream after concatenating batches and ordering rows by the
key columns; an empty result seals with its completion obligation. `verify`
is the recovery check and fails closed. The sealed content is the replay
authority; the B12 tie-break and the durable-vs-reconstructed staging choice
remain open C0 decisions that the manifest serves either way.

The first run of the replay test failed: DataFusion returned the two
reconciled rows in different orders on two executions of the same plan, so
the content digest differed. That is exactly the nondeterminism the review
warns about; the canonical key order is the fix, and the test now runs three
times in a row.

## Source-driven path exercised by the unit-5 tests

`DeterministicSource` → `RunFrontier::capture` → `next_intent` → union of
range scans → unit 2a `validate` → unit 2b `deduplicate` → `seal`. The
duplicate-null-key count (`` `id`=2 ``) and the null-sequence-before-null-key
precedence survive this path unchanged; a null-sequence row that would lose
deduplication to a valid row still fails the batch and leaves no prepared
state.
