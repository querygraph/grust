# Fable reusable columns and CDC schema review

Read-only source review of Grust `1493d8a36ea87b064f382ee3465b82a322dee842`, Sail vendor commit `d07a95c2cb0c749a741a0a1b6fc21bfbfe287347`, and Sail consumer commit `167d577c6567a68d1f94ae039c5793679252102b`. Spark reference is exactly `617618396087429b5627a86ce933bb0f5d6645cb` in `/Users/alexy/src/spark-sdp-4.2.1`, read through Git objects. Grust evidence was read from `/Users/alexy/src/grust-sdp-fable/docs/sail-declarative-pipelines/evidence/fable-cdc-validation/`.

No repository files were changed; no builds, test suites, Spark/JVM probes, fetches, or gates were run. The only written artifact is this requested temporary report. Findings below distinguish source proof from additional runtime checks still needed.

## Findings requiring repair before accepting the advertised parity

### 1. First-match lookup is not Spark StructType lookup

**Source-proven.** Grust `crates/grust-columns/src/lib.rs:29–38` implements `field_index` with `.position()`. Its documentation at lines 9–10 and 21–22 calls this Spark `StructType.getFieldIndex[CaseInsensitive]`, while explicitly choosing the first duplicate. `src/tests.rs:135–142` locks in that choice for `["a", "A", "a"]`.

Pinned Spark uses a map:

- `sql/api/src/main/scala/org/apache/spark/sql/types/StructType.scala:121–124` constructs `nameToIndex` and `nameToIndexCaseInsensitive`; lines 315–320 delegate lookup to them.
- `common/utils/src/main/scala/org/apache/spark/util/SparkCollectionUtils.scala:28–36` inserts every `(name, index)` into an immutable map builder. A repeated exact key overwrites its prior index. Thus exact lookup of `"a"` in `["a", "A", "a"]` returns index **2**, whereas the new kernel returns **0**.
- `sql/api/src/main/scala/org/apache/spark/sql/catalyst/util/CaseInsensitiveMap.scala:33–35` lowercases the keys of that original map. Collisions between distinct names such as `"a"` and `"A"` follow the map transformation, not a first-schema-field search. The kernel's stated exact-name uniqueness contract does not exclude these collisions.
- `sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/autocdc/ChangeArgs.scala:100–120` uses those StructType lookups directly. Sail `autocdc/schema.rs:112–133` delegates selection to the incorrect first-match kernel.

This changes which field an include/exclude selection keeps. No uniqueness validation in the reviewed helper enforces a precondition that makes the difference unreachable. I did not run a Spark duplicate-schema scenario or establish end-to-end reachability through every upstream analyzer path; the helper's claimed equivalence is nevertheless disproved at its stated API boundary.

**Repair/test:** give selection an explicit name-to-index resolver supplied by the caller, or otherwise make the lookup policy accurate and explicit. Do not merely reverse the linear search and assume that reproduces case-insensitive Scala-map collisions. Add a pinned Spark oracle for exact repeated names, case-colliding distinct names, and include/exclude operations; exercise both small and larger schemas because Scala map representation/iteration may affect collisions. Keep duplicate *requested* names and duplicate *source field* names as separate test classes. If a unique-under-lookup precondition is chosen, prove and enforce it at the actual caller instead of claiming universal StructType parity.

### 2. Rust lowercase does not preserve the documented JDK 17 case boundary

**Source-proven relative to Sail's stated JDK 17 policy; new runtime oracle not executed.** Sail `crates/sail-spark-connect/src/pipelines/autocdc/schema.rs:57–66` implements the `Locale.ROOT` lookup comparison as `field.to_lowercase() == name.to_lowercase()`. This uses the Rust toolchain's Unicode version, whereas existing Sail resolver code deliberately preserves Java 17's Unicode 13 boundary: `crates/sail-common/src/utils/string.rs:77–115`, with its JDK oracle case at line 132.

A concrete pair is U+10570 / U+10597 (Vithkuqi). Existing Sail's JDK 17 oracle expects them unequal. Rust's installed 1.85 Unicode 16 source table already lowercases U+10570 to U+10597; the installed current Rust source uses Unicode 17. Therefore the new `field_lookup` recognizes a relationship that the pinned Java 17 mapping does not. U+1C89 / U+1C8A is another newer mapping present in the local Rust tables. This is not an assertion that a new end-to-end Spark probe was run.

The distinction Fable made between `equalsIgnoreCase` resolver semantics and `Locale.ROOT` lowercase-map semantics is correct. Replacing this new comparator with `spark_case_insensitive_name_eq` would introduce different errors, such as dotted/dotless I and final sigma behavior.

**Repair/test:** put any needed Java ROOT-lowercase compatibility in Sail's existing string utility boundary, with the JVM version explicitly pinned. Add direct JVM/Spark oracle cases for newer Unicode characters, `İ` versus `i`, `I` versus `ı`, `Σ` versus `ς`, contextual sigma, and ordinary accented letters. Test lookup and resolver separately, including a case where their answers are intentionally different. The present CDC/kernel case tests are ASCII-only and do not validate this new boundary.

## Commit and evidence corrections

### 3. The vendor-only commit anticipates a later Cargo dependency

**Source-proven tree mismatch; intermediate Cargo behavior not executed.** `d07a95c2cb0c` adds `"grust-columns"` to the `sail-spark-connect` package's dependency list in `Cargo.lock`, but that commit's `crates/sail-spark-connect/Cargo.toml` has no such dependency. The manifest addition arrives only in `167d577c6567`. The final tree has both and is consistent on this point.

Move that lockfile dependency edge into the consumer commit, leaving the new workspace package lock entry in the vendor commit. Validate each offered commit with `--locked`; the reported Clippy gate is for the final consumer tree, not evidence that the intermediate vendor-only tree is independently reproducible.

### 4. One purported protocol test proves neither a round trip nor field numbers

**Source-proven.** `crates/sail-spark-connect/src/pipelines/autocdc/tests/schema.rs:215–224`, named `pipeline_command_with_auto_cdc_details_round_trips_through_the_proto`, constructs a default command and an enum variant and checks the variant. It never encodes or decodes protobuf bytes and cannot establish its comment's field-number claim.

Rename it as a construction smoke test or replace it with real encode/decode coverage. To prove wire compatibility/field numbers, use bytes produced by the pinned Spark/PySpark proto as the fixture, then inspect all meaningful fields. A self-round-trip alone cannot catch shared wrong tags in one generated implementation.

### 5. Scope/evidence needs precise labels

The README and provenance correctly disclose that schema helpers are field-name-only, unactivated, and that the original Scala suites did not execute against Sail. The helper tests are useful for ordered selection, missing-name errors, selected-key preservation, and reserved-prefix checks; the structured-error test helper checks condition, SQL state, and parameters.

However, `assertions.json` marks the successful `ChangeArgsSuite` schema-selection cases as fully `ported` with empty notes, while the corresponding original assertions compare complete StructTypes, including `id INT NOT NULL`. Sail's `tests/mod.rs:20–22,94–97` reduces the source and result to `Vec<String>`. Qualify these entries as field-name/index-selection coverage (or partial until actual schema preservation is checked), as the packet already does for the AutoCdcFlow schema cases. The schema helper's future integration still needs types, nullability, metadata, resolved sequencing type, and metadata-column shape.

Also retain constructor error-ordering limits: Spark `graph/Flow.scala:259–274` selects/validates keys and then resolves the sequencing expression before the SCD branch at 285–296. Sail `autocdc/schema.rs:175–183` has no sequencing resolution and returns SCD2 immediately after the name checks. This is acceptable as an explicitly partial, unwired helper; it must not later be wired as a complete constructor-order oracle. Add an invalid sequencing expression plus SCD2 test when resolution is implemented.

The packet explicitly reports a non-detached worktree gate, two full-library ORC failures reproduced on the base, and no streaming/CDC execution coverage. Preserve those qualifications; the recorded component passes do not establish a clean combined implementation gate.

## Vendor provenance and reuse recommendation

**Independently verified by read-only byte/hash comparison:** all four files named by Sail `vendor/grust-columns/SOURCE.json` (`Cargo.toml`, `LICENSE-MIT`, `src/lib.rs`, `src/tests.rs`) exactly match the Git blobs at Grust `1493d8a36ea87b064f382ee3465b82a322dee842:crates/grust-columns/` and all four recorded SHA-256 digests. The vendor footprint is dependency-free. There is no observed vendor drift.

`scripts/spark-pipelines-tests/verify_vendor.py:10–18` itself checks vendored bytes against the local manifest; it does not retrieve or independently compare the upstream commit. The additional Git-object comparison above supplies that missing provenance check for this review. Neither check establishes Spark semantic correctness.

This is a **new** small helper package, not extraction/refactoring of an existing Grust/LakeCat implementation. The offered Grust commit only adds the package, workspace membership and changelog entry; it changes no existing consumer. The evidence accurately lists `grust-sail` only as a future candidate. Describe it accordingly.

Recommended boundary: retain generic selection bookkeeping (schema order, include/exclude, deduplicated missing requests), required-name checks, and reserved-prefix checking only where contracts remain explicit; keep Spark's name-to-index policy and Java compatibility in Sail. A resolver callback is a stronger boundary than a pairwise comparator for selection. The existing resolver reuse for key/prefix checks is the right direction. Do not force Arrow-specific ALTER TABLE helpers or LakeCat catalog types into this API, and do not migrate a Grust consumer until its lookup/ambiguity semantics have been audited. The dependency-free package can remain reasonable once these semantics and claims are corrected; its present vendored form should not be accepted as a Spark-equivalent kernel.
