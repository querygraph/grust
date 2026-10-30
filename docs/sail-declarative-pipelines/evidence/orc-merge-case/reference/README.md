# Spark ORC schema merging and name case

This packet contains **16 file-read observations** and **8 separately labelled direct JVM merge diagnostics** from installed Spark 4.2.1. The reference source pin is `617618396087429b5627a86ce933bb0f5d6645cb`; retained source blobs do not prove the installed jars were built from that commit. Installed Spark SQL jar hashes are recorded separately.

PyArrow 26.0.0 wrote eight small ORCs: two files for each of a root INT field, a STRUCT child, an ARRAY element STRUCT child, and a MAP value STRUCT child. Each upper file contains `id=11` and `Value=111`; each lower file contains `id=22` and `value=222`. Every file was independently read back and hashed before Spark started, and its bytes were checked unchanged afterward. These are foreign PyArrow-written ORCs read by Spark, not Spark-written fixtures.

| File shape | Case sensitive, merge true | Case sensitive, merge false | Case insensitive, merge true | Case insensitive, merge false |
| --- | --- | --- | --- | --- |
| Root `Value`/`value` | Both fields; other spelling is null per file | One field; unmatched spelling is null | One field; both values read | One field; both values read |
| STRUCT child | Both fields; other spelling is null per file | One field; unmatched spelling is null | `COLUMN_ALREADY_EXISTS` at schema analysis | One field; both values read |
| ARRAY element STRUCT child | Both fields; other spelling is null per file | One field; unmatched spelling is null | `COLUMN_ALREADY_EXISTS` at schema analysis | One field; both values read |
| MAP value STRUCT child | Both fields; other spelling is null per file | One field; unmatched spelling is null | `COLUMN_ALREADY_EXISTS` at schema analysis | One field; both values read |

All 13 successful reads returned both source rows. All three schema-analysis failures, messages and Python tracebacks are retained. The successful file reads in this run chose lower-case `value` first; their merged sensitive schemas order `value` before `Value`. This is an observed input enumeration outcome, not a promise that Spark sorts paths lexically or always chooses the lower spelling. `mergeSchema=false` uses the first readable schema in the file enumeration according to `OrcUtils.readSchema`.

Direct JVM diagnostics deliberately merge parsed upper-case schema JSON on the left and lower-case schema JSON on the right. `StructType.merge(other, false)` returns one root `Value` field but retains both nested `Value` and `value` fields for all three container shapes. These are direct type-merge outputs, not successful file relations. They expose the intermediate merged schema that later file relation duplicate-name checks reject.

Pinned source explains the distinction:

- `OrcOptions.scala:62–69` lets the per-read `mergeSchema` option override the session default; `OrcUtils.scala:209–218` selects merge versus first-readable inference.
- `SchemaMergeUtils.scala:59–117` passes session case sensitivity to each outer `StructType.merge`.
- `StructType.scala:592–663` uses the requested case policy for the current STRUCT level, but calls `merge(leftType, rightType)` without passing that flag for matched fields. The default is true. ARRAY and MAP recurse with that resulting merge function.
- `DataSource.scala:455–463` checks inferred data-schema duplicates. `SchemaUtils.scala:85–101,146–155` propagates the session case policy recursively through STRUCT/ARRAY/MAP when checking names. Thus the nested fields preserved by merge become illegal duplicate names in a case-insensitive file relation.

These observations require separate merge and duplicate-validation policies in a compatible ORC inference path. A universally recursive case-insensitive merge would silently coalesce nested fields where this Spark configuration rejects the relation. This packet does not choose a new shared Sail API or claim general Unicode, map-key, duplicate-exact-name, type-conflict, alternate reader-mode or file-ordering parity.

The fresh owned JVM was PID 29949, with Python parent PID 29917. Runtime and process observations confirm `local[1]`, `512m`, Oracle Java `20.0.2+9-78`, UTC, FORMAT locale `en-US`, tzdb `2023c`, and old mapping false. The harness and JVM exited zero without terminate/kill fallback; a separate process check confirmed the JVM absent. Existing Sail services were untouched. Connect emitted warnings about reapplying static settings, but actual SparkConf and the process command line independently confirm the selected master and heap. No probe was retried or discarded.

`results.json` preserves actual settings, options, schemas, field order/nullability, Arrow values, pre-execution formatted plans, all failures and lifecycle evidence. `source-audit.json` indexes exact source blobs and numbered excerpts, with Spark LICENSE/NOTICE copied into `sources`. `MANIFEST.json` inventories this packet. The prior partition probe harness is retained as `harness-reference.py` for lifecycle provenance; it was not executed here.

Run read-only validation without starting Spark:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/alexy/src/sail-pipelines-proposal/.venv/bin/python validate_evidence.py
```

To reproduce the probe, copy only `probe.py` into a new empty directory and run:

```sh
PYTHONDONTWRITEBYTECODE=1 \
JAVA_HOME=/Library/Java/JavaVirtualMachines/jdk-20.jdk/Contents/Home \
JAVA_TOOL_OPTIONS='-Duser.timezone=UTC -Dsun.timezone.ids.oldmapping=false -Duser.language=en -Duser.country=US' \
/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python probe.py > probe.log 2>&1
```

The probe refuses to replace the input directory. This is Spark reference evidence only; it does not claim Sail runtime acceptance or instrument physical file-open counts.
