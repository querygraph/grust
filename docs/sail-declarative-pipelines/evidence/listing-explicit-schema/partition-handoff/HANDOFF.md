# Shared listing partition binding: source audit and implementation handoff

This is a read-only design handoff. No repository edits, builds, gates, commits,
or new Spark processes were performed in this task. `source-audit.json` retains
12 source identities and exact hashed excerpts. Spark is pinned at
617618396087429b5627a86ce933bb0f5d6645cb. Sail excerpts use immutable listing-hook
candidate c98af027bce750883393561e47e1976045a6c9a4, whose changed source bytes matched
the worktree at capture; this does not assert its gate passed.

The independent runtime reference is frozen separately at
`/tmp/sail-sdp-orc-partition-schema-reference`, MANIFEST SHA-256
ed8baf764a6472517b2fa927ea6c9eee3c25e281918d170714edc09da8f94f0b. Its author reported
10 cases and 11 filter observations, owned JVM exited zero, and offline validation
passed. This handoff did not run that validator or modify the packet. The source
reasoning below and those finite observations are not general Sail qualification.

## Settled source contract

Spark does not use the supplied schema as a whitelist of directory columns.
DataSource.scala185-188 obtains the discovered partition schema first;221-223
removes matching partition fields from every Some(userSpecifiedSchema), including
Some(empty). Omitted directory fields remain in the partition schema. Only None
falls through to physical file-schema inference. PartitioningUtils.scala126-142
uses the supplied types with the configured case policy and, when case insensitive,
a separate supplied-name map. Lines185-193 build all discovered partition fields
with nullable=true and choose the supplied spelling only for a case-insensitive
match. DataSource.scala435-449 applies file-format nullable policy independently.

For physical directory key `part`, file field `id`, and string values west/east:

| Supplied schema | Case-insensitive read | Case-sensitive read |
| --- | --- | --- |
| `[part,id]` | File `id`, logical partition `part`; output `[id,part]` | Same |
| `[PART,id]` | File `id`, logical partition `PART`, physical key `part`; output `[id,PART]` | File `[PART,id]`, discovered partition `part`; output `[PART,id,part]` |
| `[id]` | Output `[id,part]` | Same |
| Explicit empty | No file fields; output `[part]` | Same |
| Absent | Infer file `id`; output `[id,part]` | Same |

The fresh probe confirms these outcomes, all output fields nullable, three rows
retained for explicit empty, and partition-only ReadSchema struct<>. In the CS
alias case the missing file field PART is null. `PART='west'` is a data filter and
returns no rows; `part='west'` prunes directories and returns the west rows. In CI,
`PART='west'` is a partition filter and returns the west rows. Matching supplied
partition columns were deliberately placed first and nonnullable in the request;
Spark moves them after file fields and makes them nullable. These observations
qualify the tested string paths and configurations, not every partition type.

Pruning follows logical partition names: PartitioningAwareFileIndex.scala184-222
filters predicates by partition schema references and binds them by schema
position. It does not turn the user-facing logical alias back into a data column.
HadoopFsRelation.scala54-59 and PartitioningUtils.scala649-667 describe the final
file/partition schema combination; the supplied-schema path has already removed
its matched partition fields, so discovered partition ordering remains last.

## Concrete current Sail gaps

1. `listing/source.rs` explicit branch filters discovered directory names to names
   present in the prepared schema using eq_ignore_ascii_case, independent of the
   captured case-sensitive flag. Omitted directory fields disappear. CS aliases
   are incorrectly selected as partitions instead of remaining file fields.
2. `get_partition_columns_and_file_schema` prefers exact then unique ASCII-CI
   matches but has no case-policy input. It preserves the selected logical field
   spelling. With directory `part` and selected field `PART`, validate_partitions
   then compares that logical spelling against physical directory keys exactly
   and rejects. Merely relaxing this validation would be incorrect.
3. `listing/planner.rs` passes logical partition field names into DataFusion's
   exact directory parser and prefix-pruning helper. If validation were bypassed,
   an alias could cause files to be skipped, or pruning prefixes to point at the
   wrong directory spelling. DataFusion helpers.rs466-491 requires exact keys;
   262-305 builds prefixes from partition names;385-440 creates its filter schema
   from those same names. Both parser names and predicate references must agree.
4. The new explicit-schema hook makes Some(empty) representable, but returning it
   alone still yields no discovered partitions: the current requested-field filter
   removes every key. Legacy formats continue treating empty as absent by default.
   The hook itself should not be changed to smuggle directory binding policy into
   ORC's file-schema normalization.
5. Existing inferred partition fields are always Utf8 and nonnullable. Supplied
   partition fields retain their existing nullability. The known type-inference
   gap is documented by a skipped Parquet test; Spark config catalog entries exist
   for type inference and validation, but a catalog entry is not runtime plumbing.

## Smallest shared mechanism

Use an explicit ordered binding between each logical partition field and the
physical directory key. A minimal representation is a private preparation result:

    struct ListingPartitionBinding {
        directory_name: String,
        field: FieldRef,
    }

Construct TableSchema's partition fields from these bindings, and retain just an
aligned `partition_directory_names: Vec<String>` in ListingTableSourceConfig.
Validate its length against TableSchema.table_partition_cols in try_new. Keeping
field ownership in the preparation result avoids using two independent schemas;
the stored vector is an intentional ordinal mapping, not a second type system.
An equivalent private wrapper around that vector is reasonable. No worker payload
is needed for this mapping in the current flow: listing/pruning runs before scan
construction, and resulting PartitionedFile.partition_values already correspond
positionally to the logical TableSchema fields.

Use physical keys for partition-layout validation and directory parsing. Keep
logical names for table schema, expressions, filter support classification,
output partitioning and scan output. Before calling pruned_partition_list, rewrite
only partition-filter Expr::Column names from logical to physical names, using
the validated ordinal bindings; the planner already unnormalizes these filters.
Pass physical `(name,type)` pairs and the rewritten filters together. This keeps
both equality-prefix pruning and subsequent expression evaluation coherent.
Do not rewrite scan/data filters or expose physical names in the output schema.
For identity bindings the expressions and behavior should remain unchanged.

A small shared `listing/partition.rs` can own binding construction, validation and
filter rebinding; table.rs and planner.rs need the plumbing. Existing
validate_partitions can retain an identity-name wrapper if other callers need its
signature. Keep get_partition_columns_and_file_schema's legacy public contract
unchanged unless its wider callers are deliberately migrated; new preparation
must honor read_case_sensitive instead of using its unconditional CI fallback.

Resolve these two implementation pieces separately:

1. Binding plumbing can preserve existing format selection/inference behavior and
   fix alias routing wherever bindings are supplied. It must not claim omitted
   columns, partition type inference or arbitrary casing variants are solved.
2. Shared partition-schema preparation must discover every directory column, choose
   matched supplied type/name under the actual case policy, make partition fields
   nullable, append omitted discovered fields, and remove only matched supplied
   fields from the full file schema. It must retain directory order, even if only
   an inner partition was supplied. For ORC the existing explicit preparation
   override controls file-field spelling/nullability and skips eager file inference;
   directory partition preparation remains generic, not an ORC decoder feature.

Do not silently replace unknown omitted partition types with Utf8 and describe
that as Spark parity. The new reference has west/east, which legitimately infer
STRING. Current generic Utf8 inference can be retained explicitly in a binding-only
unit, but real partition type inference and captured type-inference/validation
settings remain separate shared acceptance requirements. Whether to migrate all
formats to the new preparation policy at once or introduce it through a defaulted
shared hook is a root decision; the binding representation does not require a new
format-specific option or ORC-only parser.

## Tests for the next reviewable units

- Identity binding retains existing schema, pruning and exact ObjectMeta values;
  inconsistent binding count is rejected before listing.
- Actual two-directory files with logical PART / physical part: unfiltered rows,
  equality-prefix pruning, a non-prefix predicate, and zero matching directories.
  Inspect selected file groups and partition_values as well as final rows/schema.
- Case-sensitive `[PART,id]` retains a null file column and distinct `part` partition;
  PART is not classified as partition pruning while part is. Compare the fresh
  reference's filter results and physical plans without promising identical plans.
- Requested partition-first/nonnullable schemas yield file fields followed by
  nullable partitions; preserve the prepared file-field order and metadata.
- Supplied id-only and explicit-empty append discovered part. Empty has zero file
  columns and correct row count; absent still infers id. The ORC zero-column read
  and requested mapper are already available to exercise this through real files.
- Two directory levels with only the second supplied: preserve both discovered
  partition positions and types; never parse the second key against the first path
  segment. Source supports this requirement; add a bounded paired reference before
  claiming exact coercion/order/error behavior beyond the current packet.
- Shared-format regressions should retain the existing Parquet/JSON defaults until
  their partition preparation is intentionally migrated; avoid weakening their
  existing explicit-schema validation or up-front name reconciliation.

## Remaining boundaries that a single-name binding cannot solve

Spark PartitioningUtils.scala414-439 accepts directory key sequences differing
only by case when caseSensitive=false, using String.toLowerCase without a locale
argument there. Sail currently rejects different exact sequences. A single
physical-name vector supports uniform path spelling, not mixed `part`/`PART`
paths within one URL. General support needs a case-aware per-file parser or
per-layout bindings, and conservative prefix listing when one logical key has
multiple physical spellings. Otherwise an equality prefix can silently omit a
valid spelling. Per-URL binding alone is insufficient. This is source evidence;
the fresh packet intentionally does not test mixed directory casing.

Other preserved requirements: numeric/decimal/date/timestamp/TIME partition type
inference, user-typed cast failures and validatePartitionColumns=false behavior,
Hive default-null markers, escaped keys/values, non-ASCII/locale rules, basePath
and recursiveFileLookup semantics, conflicting layouts and supplied explicit
partitionColumns. Spark unescapes directory keys (PartitioningUtils310) whereas
Sail's current key inference does not. These are visible general listing gaps,
not reasons to declare the narrower string-alias fixture universal parity or to
change ORC temporal profiles. No new guesses are implemented in this handoff.
