Recorded: 2026-10-30T00:08:38.428361+00:00
Base: 25524aa551c15b0708711f88776d681cbcd73834

# ORC requested-schema mapper handoff

The frozen draft is a mapping foundation, not a registered source or full Spark
conversion verdict. Root owns independent review, detached gates and commits.
Only the five files in source-state.json were edited; source/opener drafts belong
to the architecture agent. Nightly rustfmt and git diff --check passed. No Cargo
commands, builds or tests ran in this delegated implementation.

## Interface and use

`OrcRequestedSchemaAdapter::try_new(file_schema, full_data_schema,
required_indices, read_case_sensitive)` returns a per-file plan. Both schemas
are complete file schemas, excluding directory partition columns; required
indices address the full requested file schema and may be reordered/repeated.
The constructor performs Spark's positional, STRUCT-only LTZ/NTZ compatibility
check before required-field mapping. Top-level ambiguity is checked only for
required names, as in OrcUtils's requiredSchema loop. The native projection is
sorted/unique; getters are file_projection(), input_schema(), schema().

Opener sequence: validated immutable file metadata -> infer_orc_schema -> mapper
-> OrcSchemaBridge::try_new_reader(..., Some(mapper.file_projection())) -> native
batch -> bridge.adapt_batch -> mapper.adapt_batch -> ordinary ProjectionOpener.
The opener retains the full requested schema and SplitProjection separately;
never replace the former with the native projection. Do not serialize compiled
field mappings or native metadata: rebuild them from each worker's validated
per-file metadata and already transported schema/options/identity.

`nullable_schema(&Schema) -> SchemaRef` preserves names/metadata while making
ordinary file-read fields recursively nullable. Arrow map entries/key wrappers
remain non-nullable; nested key fields can be nullable. The Source/TableSchema
and ProjectionOpener must use this same normalized full file schema. A retained
integer case asked for nonnullable id but Spark returned nullable id. The mapper
also applies normalization internally and retains row counts for empty output.
An empty physical root is a separate Spark no-row rule handled by the opener;
it is not the same as requesting zero columns from a nonempty physical schema.

## Implemented behavior and reuse

- Full-schema timestamp checking zips field types by position and only recurses
  into STRUCT. It is deliberately not a stronger recursive-name validator.
- Required top-level case-insensitive duplicate matches error. Nested ASCII
  matching takes the last normalized physical name, overriding an earlier exact
  spelling. Case-sensitive exact duplicate root names also take the last physical
  field; exact-name matching preserves Unicode strings exactly.
  Case-insensitive non-ASCII sibling/name matching errors explicitly for now.
- Automatic Hive root fallback uses literal starts_with("_col") for all physical
  names, not a numeric suffix regex, and requires full data-schema width >= file
  width even with a narrow/empty projection. Forced positional mode is not added.
- Missing columns become typed nulls; struct parent validity, list/map offsets,
  slices, map key/value roles and requested spelling are preserved. Containers
  rebuild target fields so TIME/interval metadata is not discarded.
- Same-storage TIME precision and interval qualifier changes preserve values.
  Signed integer conversions use the existing Arrow safe cast kernel, nulling
  overflow outside map keys. Integer narrowing anywhere inside a map key is an
  explicit NotImplemented at construction, including nested key children; identity
  and widening keys remain supported. LTZ-to-LTZ display labels reuse Sail's
  timestamp relabel helper.
  No nested LTZ/NTZ conversion is silently delegated to that helper.
- Other unequal leaf conversions error explicitly. Decimal/string/float-cross-
  type evolution and nonstandard Arrow container variants remain open. Equal
  primitive types retain their values; this does not qualify historical calendar
  behavior in the native decoder.

The generic SchemaEvolutionPhysicalExprAdapter is not used as a drop-in mapper:
it matches first exact names, rejects disjoint structs, can synthesize zero/default
values for missing nonnullable top fields, and its relaxed timezone mode erases
LTZ/NTZ distinctions. Generic array::record_batch helpers likewise use exact names
or positional equal-width structs. Reuse their numeric kernels and proven LTZ
relabel operation without changing existing Delta/Parquet/schema-adapter behavior.

Thirteen focused tests cover timestamp check/projection ordering; required-only top
ambiguity, exact duplicate root last-wins and all four nested name oracle cases;
requested duplicates/order and
integer overflow; missing/zero-column/zero-row output; literal _col fallback/full
width; sliced structs/lists/maps and null parents; TIME/interval metadata/value
identity; malformed projection/metadata/map shapes and input-schema mismatch;
map-key narrowing rejection plus sliced identity/widening keys and narrowing
values; and actual Spark fractional TIME bytes decoded by the controlled native builder
then bridge and requested mapper. The tests are authored but not run here.

## Shared listing integration still needed

Current ListingDataSource eagerly infers a physical schema for case-insensitive
explicit-schema reconciliation and rewrites requested names to physical spelling.
Spark's supplied-schema path skips file-schema inference and defers per-file
compatibility failures to execution. The frozen mixed-case oracle preserves foo
and ST exactly. Add a narrow defaulted ReadFormat explicit-schema preparation hook:

    async fn prepare_explicit_schema(ctx, supplied_schema, selected_files,
        compression, read_case_sensitive) -> Result<PreparedExplicitSchema>

The result can contain the logical schema plus optional physical schema for the
existing post-partition validate_explicit_schema hook. Default behavior moves the
current inference/reconciliation block unchanged; ORC returns its nullable supplied
schema and no inferred physical schema. Preserve full field order and metadata.
Do not set ORC requires_explicit_schema_validation merely to force eager inference.

Partition extraction is a separate shared binding concern. The existing helper
already prefers exact then ASCII-insensitive field names, retaining requested
spelling. But validate_partitions compares physical directory names exactly,
and planner.rs passes logical names to DataFusion's exact-name partition parser.
Preserve logical field names separately from actual directory key names, using a
small binding or validated parallel name vector in shared listing configuration.
Use directory names for parsing/validation, logical names for the output schema,
and map pruning filter references consistently. Default legacy bindings stay
unchanged. A partition alias fix cannot stop at skipping file-name reconciliation.

## Remaining reference/compatibility boundaries

These remain on the complete acceptance list; no final scope is reduced:

1. The fresh `/tmp/sail-sdp-orc-duplicate-key-reference` packet records exact
   physical root names dup=11/dup=22 requested as one dup: case-sensitive reads
   yield 22; case-insensitive reads error. The mapper now reproduces these cases.
   MAP<BIGINT,STRING> keys [1,2147483648] requested as MAP<INT,STRING> and exploded
   yield [1,-2147483648] with vectorization enabled, while disabling vectorization
   fails with native NullPointerException in nextMap/TreeMap.put. This does not
   qualify general wrapping or safe-null behavior. The explicit construction-time
   map-key narrowing gap remains until reader-mode policy and additional widths/
   nested key structures are qualified. Future conversion must account for sliced
   MapArray unused entry prefixes and entries hidden by null parents: converting
   all retained keys can surface errors from entries that are not logically read.
   Do not turn this conservative gap into the final acceptance scope.
2. Decimal precision/scale rounding and overflow; string/CHAR/VARCHAR/binary and
   floating-point conversions; DATE/calendar rebasing; direction-isolated nested
   timestamp conversion and selected-away incompatible nested children.
3. Non-ASCII/default-locale lowercasing. Sail's existing JDK17 equalsIgnoreCase
   helper is a different operation from OrcUtils Locale.ROOT string lowercase
   and ORC Java default-locale string lowercase. Do not claim it is interchangeable.
4. Supplied-schema case aliases for directory partitions, including absent user
   partition fields, actual nullable output, pruning and partition-only reads.
5. Existence-default metadata for missing fields; broader duplicate-name cases;
   deeper/forced Hive positional evolution, nested fallback depth and schema width.
   The current missing-field plan is null filling, not a default-expression engine.
6. Semantic schema merging is separate from per-file last-wins matching. Root's
   merge audit notes Spark resets nested matched-type merges to case-sensitive;
   do not carry this mapper's nested policy into mergeSchema.

These are explicit follow-up requirements. Ordinary source integration can now
exercise the implemented contracts through the normal FileSource/Openers; it
must keep unqualified differences visible and does not itself qualify registration,
worker execution, the writer, streaming/Iggy, CDC or the full SDP objective.

## Correction evidence

The duplicate/key packet is frozen with MANIFEST.json SHA-256
`e1183c7f9fbbcfc0fb8366dcb38971e1d4e8956923369d05ab15cb48b730094d`.
Its source-audit.json pins Spark 617618396087429b5627a86ce933bb0f5d6645cb,
OrcUtils required-name duplicate check (lines 275-295), and the retained Apache
ORC 2.3.0 SchemaEvolution class/disassembly. Disassembly lines 836-864 select a
HashMap in case-aware mode and insert physical fields in order, supporting the
observed last-wins mapping. This is source/compiled-artifact evidence plus four
Spark observations, not Sail runtime qualification. The initial immutable mapper
candidate c5a96ea01 predates this correction; root owns its gate receipt and the
replacement candidate. No delegated Cargo commands or tests were run.
