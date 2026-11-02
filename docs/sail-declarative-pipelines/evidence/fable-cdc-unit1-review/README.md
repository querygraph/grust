# Fable CDC unit 1 integration review

Recorded 2026-10-30T05:41:13.625926+00:00. Review of offered Sail vendor commit
`d07a95c2cb0c749a741a0a1b6fc21bfbfe287347`, consumer commit
`167d577c6567a68d1f94ae039c5793679252102b`, and Grust kernel
`1493d8a36ea87b064f382ee3465b82a322dee842` against Spark 4.2.1 source
`617618396087429b5627a86ce933bb0f5d6645cb`.

The offered commits are not integrated. Two independent read-only reviews found
specific phase, precedence and name-lookup mismatches. Corrective commits and
focused reference regressions were requested through the locked canonical
coordination file. These are source comparisons, not newly executed Spark/Sail
counterexamples or a combined runtime gate.

- [Definition and graph review](definition-review.md): source analysis must
  precede resolution-dependent target checks; the sink error belongs to execution
  planning; CDC multiflow precedence is global; source identifiers need their
  one-to-three-part contract; raw attributes need Spark's dot/backtick parser.
- [Kernel and schema review](kernel-review.md): lookup must preserve the actual
  StructType map policy, and Java ROOT lowercase needs its own pinned Unicode
  contract. The current first-match comparator cannot establish this parity.
  Vendor bytes independently match all four pinned Grust source blobs/hashes.

The reusable module is a new dependency-free helper, not an extraction from an
existing Grust/LakeCat consumer. A caller-provided name-to-index resolver is a
better selection boundary than a pairwise comparator; Spark-specific parsing,
Unicode behavior, errors and validation phases remain in Sail. Actual reuse by
other consumers should follow a contract audit, not be inferred from package
placement.

Additional corrections concern the intermediate vendor commit's lock dependency
edge, a protocol test that never serializes, and field-name-only assertions
labelled as complete schema ports. Fable's reported two full-library failures and
non-detached gates remain disclosed; neither their base reproduction nor isolated
CDC passes qualifies the offered combined state. The Python environment is a
hypothesis for the ORC defaults mismatch, pending a controlled rerun.

Fable may independently build original-row validation before deduplication,
followed by a separate winner-selection unit using Sail's MaxByFunction where
its contract matches. No execution wiring, durable progress/fencing, Iggy effects
or target-wide CDC recovery is approved by this component review. Those still
require their separately announced design phase. The canonical 462-registration
coverage inventory is unchanged.
