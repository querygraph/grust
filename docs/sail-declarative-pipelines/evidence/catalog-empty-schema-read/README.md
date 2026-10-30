# Empty catalog schemas at named reads

Recorded: 2026-10-30T02:14:22.600752+00:00. Sail `75ac384c4c042a9b81793f41c0df944b5217a91a` changes one shared resolver assignment:
an empty stored catalog schema becomes an absent source schema, allowing runtime
inference. Nonempty schemas, their existing field metadata, constraints and
catalog execution context are unchanged. Direct DataFrame/data-source reads
preserve explicitly empty schemas. There is no ORC-specific branch.

Formatting, strict Clippy and all **37 sail-plan library tests** passed at this
exact commit. No new mock harness was added: the retained real public regression
and explicit-empty controls remain the required runtime validation. This packet
does not claim a passing public retry or full SDP qualification.

## Evidence and remaining catalog work

- [Pinned source audit](source-reference/README.md) shows Spark 4.2.1's named-read
  compatibility rule: empty stored schemas request runtime inference. Delta
  already normalizes empty schemas downstream; Iceberg ignores this carrier for
  data scans and metadata relations.
- [Six same-binary Sail controls](prior-public-failure/catalog-control.json) retain
  the original ORC empty named schema and rows. Parquet/JSON infer named-read
  fields with omitted catalog columns, while DESCRIBE stays empty for all three.
- [Seven fresh Spark catalog observations](spark-catalog-reference/README.md)
  cover omitted/explicit schemas for ORC, Parquet and JSON, plus IF NOT EXISTS
  against an existing table and an embedded missing-path/new-table error control.
  Source hashes, actual settings, unchanged inputs and owned JVM shutdown are
  retained. The installed jars are identified separately from the source pin;
  no claim is made that those jars were built from the checkout.
- [Original public failure](prior-public-failure/public/pytest.log) remains
  **295 passed / 1 failed** at `8ea2c075ed2cccb503c99ece60e18db32a32964c`.
  The unchanged external-table assertion failed; the upstream stage was not run.
  This directory is a deliberate subset of the full failed E packet: its original
  MANIFEST is retained for selected-file verification, not as a completeness claim.
- [Preparation observation](advance-comment/observation.json) records a comment-only
  mismatch refused before branch mutation. Root restored the exact gated comment.
  Both variants and the [earlier handoff](implementation-pre-advance/HANDOFF.md)
  remain retained. No Rust failure occurred; no raw stderr file is claimed.

CREATE-time inference and catalog schema persistence remain a separate shared
catalog checkpoint. This fallback does not populate DESCRIBE or add an arbitrary
field-metadata carrier. Spark's existence guard and prepublication inference
ordering are evidence for that later work, not implemented behavior in this unit.
ORC public registration, writer support, streaming/Iggy and CDC qualification are
unchanged here.

`provenance.json` inventories every packet file except itself. Raw receipts and
the final implementation handoff preserve their original timestamps and scope.
