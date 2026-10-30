# ORC ordinary read-format implementation handoff

Frozen source-only draft at Sail `26b9461b93092ab99f1d5718fa82c73327970a27`. Root owns immutable Cargo gates, commits, and registration. No builds, test execution, commit, JVM, service change, or dependency change was performed for this draft. `source-state.json` contains the exact nine owned file hashes and 14 test names. Other agents' B2/E drafts are outside this unit.

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

`read_tests.rs` supplies small native-generated fixture helpers; `read_test_store.rs` records real GET options while delegating to InMemory. No copied binary assets or new dependencies.

## Validation and integration

Executed only nightly rustfmt on owned files and `git diff --check`; both pass. Runtime assertions are unexecuted until root gates. Suggested immutable gates are the existing `sail-data-source` fmt check, strict all-target Clippy, and complete library test suite. The focused tests match `formats::orc::read::tests::` and `formats::orc::factory::tests::`.

D's `mod.rs` patch is only factory/read declarations and public reexports beyond committed B. B2's future `OrcReadSessionModes` reexport is held separately so this exact candidate does not depend on an unstaged mode type. D uses resolved options, not an exhaustive generated listing-options literal, so B2 can extend that DTO without changing D tests. Root must gate the explicit unsupported Hive/forced-positional guard before public registration; this unit does not claim those modes work.

Ordinary listing re-enumerates execution files. Conditional identity protects each phase's supplied object, not an inference-to-execution inventory snapshot. No metadata cache, new executor, custom projection abstraction, inferred-schema worker payload, or worker timezone recapture is introduced. Existing source limitations (including virtual columns, unsupported requested conversions, and no auto repartition) remain.
