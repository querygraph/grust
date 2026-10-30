# ORC ordinary read-format implementation handoff

Revised frozen D draft at Sail `c01623c184bdf8f688e9153a263283694cd39a2b` after the committed unsupported-mode guard. Root owns immutable Cargo gates, commits, and registration. The implementing agent ran no Cargo builds/tests, committed no code, and started no JVM; root's previous candidate result is retained below. `source-state.json` contains the exact nine code-file and six fixture/provenance hashes and 14 test names. B2 is committed; E registry drafts remain outside this unit.

## Production boundary

- `factory.rs` provides the ordinary `OrcDataSource` alias, factory, and explicit unsupported write marker. Resource and planning options resolve independently from the same layers. The driver captures the host IANA reader zone exactly once through `get_system_timezone`; the pinned Java descriptor is distinct from the independently captured, Arrow-normalized session display label. Lookup errors preserve their original cause. This is Sail's selected host-zone policy, not an observation of a JVM default.
- `read.rs` selects all eligible files, uses their exact listed identities with the current local pool and configured metadata limits, and adds file context while retaining native/merger causes. Sequential traversal follows selected URL/file ordering. Physical empty roots are skipped. With merge disabled the first usable schema ends metadata inference; with merge enabled all eligible roots contribute via the qualified shared Spark semantic kernel. Final recursive duplicate-name validation also applies to single-file/first mode.
- Supplied schemas return recursive read-nullability normalization and no physical inference, including `Some(empty)`. The existing listing machinery then owns partition discovery, alias binding, and preparation. Per-file requested compatibility remains the committed source's job.
- Scan construction preserves the complete table schema, groups and object identities, constraints, statistics, projection, limit, ordering, preserve-order policy, and output partitioning. It binds the current runtime pool while retaining the captured reader descriptor, display label, resource configuration, and source case policy. Outer file compression is explicitly rejected; internal ORC compression remains postscript-driven.
- No ordinary registry entry or writer is enabled here. `OrcFormatFactory::write` and `OrcWriteFormat::sink` return `NotImplemented("ORC writing is not implemented")`.

## Tests and expectations

Fourteen focused tests cover:

1. Both inference modes reach usable schemas after eleven valid physical-empty roots; only merge=true reads the later added-field file.
2. First mode stops before a corrupt later file; merge preserves the underlying native cause and its file path. All-empty physical roots produce an inference error.
3. Retained Spark 4.2.1 `time_precisions.orc` passes through ordinary listing inference, retaining Spark-version and TIME metadata. A later controlled foreign LONG+TIME annotation produces a semantic precision conflict even though Arrow units match. The generated annotated fixture is not represented as Spark-written.
4. Authoritative root case policy, qualified nested recursion, and final recursive duplicate checks, including single-file root/nested duplicates with merge both on and off.
5. Explicit empty schemas do no footer inference but preserve nonempty-file row counts on actual scan; corrupt supplied-schema files fail during execution.
6. Published explicit nullability, missing-column null materialization, actual projected values.
7. Existing hidden/glob filtering, directory partition aliases, partition pruning, object identity preservation, and projected partition/data output on a real listing scan.
8. Exact conditional inference GETs; identityless failure before I/O; replacement failure without HEAD rebinding.
9. Actual encoded/decoded/depth metadata caps, current local pool admission, reservation release, and source binding to a different zero-capacity pool.
10. Configured limits, captured reader/display/case policy, normal scan properties, duplicate physical projection, and actual limit enforcement.
11. Factory capture exactly once, independent display normalization and snapshots, retained lookup failure cause, explicit write rejection.

`read_tests.rs` supplies small native-generated fixture helpers; `read_test_store.rs` records real GET options while delegating to InMemory. The nested schema tests additionally include three tiny PyArrow-written STRUCT fixtures with generator/readback/hash provenance; no new dependencies.

## Validation and integration

Executed only nightly rustfmt on owned files and `git diff --check`; both pass. Runtime assertions are unexecuted until root gates. Suggested immutable gates are the existing `sail-data-source` fmt check, strict all-target Clippy, and complete library test suite. The focused tests match `formats::orc::read::tests::` and `formats::orc::factory::tests::`.

D's `mod.rs` patch is only factory/read declarations and public reexports beyond committed B. The committed `OrcReadSessionModes` reexport is preserved unchanged. D uses resolved options, not an exhaustive generated listing-options literal, so B2 can extend that DTO without changing D tests. The explicit unsupported Hive/forced-positional guard is now committed and qualified separately; this unit does not claim those modes work.

Execution uses the shared listing/cache again; a backend re-list is not guaranteed. Conditional identity protects each phase's supplied object, not an inference-to-execution inventory snapshot. No metadata cache, new executor, custom projection abstraction, inferred-schema worker payload, or worker timezone recapture is introduced. Existing source limitations (including virtual columns, unsupported requested conversions, and no auto repartition) remain.

## Pre-gate source review corrections

The original handoff and all nine exact files are retained under `pre-review/`. Root and the independent reviewer found test-only API/fixture issues before any gate: negative TableSource results must not require Debug; uppercase partition aliases use explicit Column::from_name; explicit panic branches are replaced with matches assertions under the workspace lint. The resource test now asserts both stored full-table partition index1 and the DataSource-advertised projected index0. DataFusion55.2 file_scan_config/mod.rs:218–225 and840–866 establish that distinction. Expectations and production behavior are unchanged. Nightly formatting and diff whitespace checks were repeated successfully; no Cargo was run.

## Attempt 01 and corrected fixtures

Exact candidate `c49c101383` ran under root ownership: 217 library tests passed and three inference tests failed. The failed candidate was not advanced. Root retains raw logs/patches under `/tmp/sail-sdp-orc-readformat-attempt-01-fixtures`; this packet retains its prior handoff, source-state and exact nine candidate blobs under `attempt-01/`.

Two tests tried to construct STRUCT columns with the native writer, whose actual create_encoder branch explicitly lacks STRUCT. They now use three actual PyArrow26 ORCs (251,251,344 bytes), with generator version, hashes and schema/row readback in `tests/fixtures/orc/listing_inference`. A separate regeneration reproduced all three byte-for-byte. The root/nested/CI/CS and duplicate-validation assertions remain unchanged.

The original TIME test inserted files02..11 only after its context had inferred from00/01. Shared listing returns its cached inventory; DataFusion55.2 defaults the file-list cache to1MiB and an infinite TTL. This is the source-supported explanation for missing the conflict, not instrumented runtime cache-hit evidence from attempt01. The successful two-file semantic merge remains in its own fixture; a separate mismatch fixture now creates all12 objects before first listing. The test requires the actual store listing to emit all12 including the exact late ObjectMeta, and requires a conditional non-HEAD GET of11 before accepting the unchanged semantic conflict assertion. Its first-mode control then confirms no late-file GET. No cache behavior or inference implementation was changed.

The narrow cache/writer source audit and generator reproduction result live at `/tmp/sail-sdp-orc-readformat-fixture-correction/source-audit.json`. The read-format documentation was corrected to name shared listing/cache while retaining the no-snapshot boundary. Independent source review passed these corrections. Corrected Rust runtime assertions have not yet run; root owns the next immutable candidate gate.
