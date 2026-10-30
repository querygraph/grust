# Independent prepared-component correction review

Exact prepared/lookup/lowercase sources at Sail71e4a94d9 were compiled in an
isolated minimal crate. The driver supplies record-shaped intent, Case and Spark
error adapters, with opaque-token newtypes represented by their identical string
serialization. It does not execute source adapters, original-row validation,
deduplication, MERGE or a production pipeline. Receipts are supplied as fixtures.
The exact offered function bodies and table sources remain unchanged.

Observed passing checks:64 equal schema reconstructions with schema/field
metadata, case-insensitive literal-dot key binding at0/1/2 rows with sensitive
mismatch rejected,9 independent manifest mutations rejected, wrong expected
identity rejected, unknown case rejected, and serde round trip verified. These
resolve the earlier findings on that API/component boundary; full combined
integration and authoritative source/evaluation snapshot wiring remain open.

An additional representation boundary is observed. Two Arrow batches compare
equal with unique non-null ids[1,2] and nullable Int64 payload[10,null], but use111
versus222 for hidden values beneath the null cell. After the offered row-ordering
and IPC encoding, content digests differ and verifying the equal batch fails
with ContentMismatch. The complete raw result is retained, not asserted away.
The current digest is a physical IPC fingerprint after ordering; it is not a
representation-independent logical-value digest. This is not an observed
production recovery failure or proof of data corruption.

C0 must define/version the authority before activation: a supported complete
canonical-value encoding/normalization, or an explicit sealed-byte artifact and
precise reconstruction/verification contract. No mode, B12 tie-break or control
store is selected by this review. Do not infer deterministic reconstruction from
row ordering alone or patch only this one null-slot representation.

The source-level unit4 layering review also found that BoundedSource lives in
private Connect pipeline modules, while Connect depends on sail-data-source.
A data-source Iggy adapter cannot import that trait without a dependency cycle.
A small lower-layer protocol-neutral source contract needs an explicit extraction
proposal, with Spark conversion above it and the SDK in its adapter. The current
coordinator data-source manifest has no iggy feature; the pinned fork does.

Cargo sources/lock, raw output and compiler log are authoritative for replay:
run cargo with --locked on this archived crate. initial-generator.py is the
historical first driver generator; the retained fixture-refinement.patch replaces
its empty-intent placeholder with range-shaped records/literal sequencing and adds
an unknown-case assertion, without changing offered sources or weakening checks.
Both driver runs are preserved. provenance.json hashes every other packet file.
