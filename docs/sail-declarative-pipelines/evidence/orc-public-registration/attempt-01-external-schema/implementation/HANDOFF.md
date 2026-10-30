# ORC public registration and qualification draft E

This uncommitted source draft depends on the separately owned private ORC ReadFormat/factory D, planning-options/session-default bridge B, and effective-mode guard B2. Root must not activate/commit the registration before those prerequisites pass. No builds, Cargo commands, CLI runs, Spark processes, Python runtime tests or commits were performed by this agent. The existing shared merger C files remain frozen and untouched.

## Owned changes

- `crates/sail-session/src/formats.rs`: register `OrcDataSource::default()` alongside ordinary file sources. Extend the existing ordinary-versus-lake registry test with ORC. Add a registry-level `create_writer` test using Append mode, requiring the exact `DataFusionError::NotImplemented("ORC writing is not implemented")` outcome and no output directory creation. This tests unsupported writing; it does not add a writer.
- `python/pysail/tests/spark/pipelines/test_file_sources.py`: add only `"orc"` to the existing parametrization. The retained PyArrow ORC branch and pipeline result assertions are unchanged.
- `python/pysail/tests/spark/datasource/test_orc.py`: five functions / ten parameterized cases, 151 lines. They use the existing shared Spark fixture and restore all changed settings. There are no Sail-only skips or adjusted expected values.
- Adjacent `datasource/orc_data/`: byte-for-byte copy of the retained 648-byte `time_precisions.orc`, SHA256 `7504f8007af001893ccd60b873ded01bffae4b4cf4af95b1e054e7b07ff92986`, plus extracted provenance/source SQL/reference schema/nanosecond values. No fixture generation took place. The ordinary test functions generate their small known integer/string files with PyArrow when the parent runs them.

## Public cases ready for paired Spark/Sail execution

1. DataFrame `.read.orc`, `.format("orc").load`, and SQL `orc.\`path\`` reads return the exact nullable INT/STRING schema and two known rows (including null).
2. A catalog table `USING orc LOCATION` infers the existing file schema, reads exact rows, and dropping the external table leaves original bytes unchanged.
3. mergeSchema=true reaches the eleventh file and reads its added field, both through the per-read option and the session default. All files share `id` first; the only new field is `extra`, so the expected merged order does not assume Spark chooses a specific first path.
4. Six retained partition-reference cases: supplied alias/omitted/explicit-empty schemas under case sensitivity true/false. Exact schema order and nullability, rows, missing CS alias nulls, alias filtering and physical partition filtering match the frozen Spark packet. Partition values are strings; this is not type-inference or mixed-directory-casing coverage.
5. Retained Spark-written TIME(0/3/6) schema and raw nanosecond values, including fractional TIME(0) storage and null/day boundaries. Requesting TIME(3) for physical TIME(0) preserves stored bits, as observed in the schema-evolution packet. This is a read-schema reinterpretation test, not an SQL cast test.

Public runtime acceptance is still unknown. Root should run these exact assertions first against Spark 4.2.1 and then the candidate Sail server. Failures should be retained and fixed in the responsible implementation instead of changing the reference expectations. The preexisting pipeline file also contains its existing CSV empty-location cases; only its ORC parametrization is newly activated.

## Mode boundary before registration readiness

Source inspection at Spark `617618396087429b5627a86ce933bb0f5d6645cb` confirms:

- `SessionState.scala:147–150` copies every non-null explicitly configured SQLConf entry into a cloned Hadoop configuration, unchanged. `SQLConf.scala:8903–8908` returns these explicitly set entries. Exact session `orc.force.positional.evolution` is therefore effective; arbitrary setting acceptance is not merely a catalog listing artifact.
- `SessionState.scala:121–127` overlays operation options except path/paths. `OrcUtils.scala:243–273` checks timestamps first, then uses forced positional evolution OR automatic all-`_col` field fallback. The latter is already implemented and must remain distinct.
- `DataSource.scala:679–684` selects native versus Hive based on session SQLConf.ORC_IMPLEMENTATION. An operation option named `spark.sql.orc.impl` is not a provider selector.

Fable's separately frozen B only bridges mergeSchema and does not claim mode validation. Fable owns B2 after B advances, using exact installed OrcConf evidence in `/tmp/sail-sdp-orc-read-mode-reference/` for key lookup and Boolean.parseBoolean behavior. E introduces no mode handling and makes no Hive, forced-positional, writer or streaming support claim. The public positive tests explicitly select native mode.

## Source checks and handoff

Nightly rustfmt check, Ruff check/format check, Python AST parsing, owned whitespace checks, and fixture equality/hash checks passed. One initial Ruff-only unused noqa diagnostic was corrected by deleting that directive; no assertions changed. These checks do not establish compilation or runtime success. Exact source copies and hashes are in `source-state.json` and `MANIFEST.json`. Other agents' concurrent worktree changes are outside this unit.
