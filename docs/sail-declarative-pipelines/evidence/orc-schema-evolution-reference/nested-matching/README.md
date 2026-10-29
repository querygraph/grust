# Spark ORC nested name selection: four-case follow-up

This separate follow-up leaves the preceding 28-case run unchanged. Installed
Spark 4.2.1, source pin `617618396087429b5627a86ce933bb0f5d6645cb`, ran four
observations in one owned UTC local[1] JVM. All four succeeded. Oracle Java was
`20.0.2+9-78`, tzdb `2023c`, FORMAT locale `en-US`, old timezone mapping false.
Case sensitivity was false during reads; both vectorization settings were true.
TIME remained at its observed default false because these files contain integers.
No Sail runtime, repository change, build or production policy choice is included.

| Physical nested fields in order | Requested nested name | Value |
| --- | --- | ---: |
| `Bar=11, bar=22` | `BAR` | 22 |
| `Bar=11, bar=22` | `Bar` | 22 |
| `bar=22, Bar=11` | `bar` | 11 |
| `bar=22, Bar=11` | `BAR` | 11 |

These cases distinguish exact-spelling preference from last normalized name:
the last physical field wins for these nested ASCII names, including when an
earlier field is an exact match. This complements the prior top-level `Foo/foo`
duplicate error; Spark's top-level check must not be generalized into a recursive
ambiguity rejection that contradicts these nested observations.

`results.json` retains supplied/read schemas, output integer values, formatted
pre-execution physical plans, actual settings and the two physical ORC schemas.
The original fixture is an exact copy of the preceding run's nested duplicate
file. Only the reverse-order file was newly written. Input and baseline receipt
hashes were checked before/after. The completed process returned zero, and its
owned JVM PID 83895 exited zero. There were no failed runtime attempts, and no
unrelated process was stopped.

## Installed ORC compiled-artifact evidence

The local PySpark installation contains
`orc-core-2.3.0-shaded-protobuf.jar`. Its embedded Maven properties report
`org.apache.orc:orc-core:2.3.0`. No Java source is embedded, and no local matching
sources jar was found. The retained `SchemaEvolution.javap.txt` and
`CaseInsensitiveMap.javap.txt` are disassembly of the exact installed classes,
**not Java source excerpts**. `source-audit.json` records jar and class SHA-256
hashes, copied class bytes, Maven properties, javap commands/tool and pinned Spark
source excerpts. It does not claim that JVM class-origin instrumentation was run.

In `SchemaEvolution.buildConversion`, the STRUCT-name branch chooses a
CaseInsensitiveMap when case-aware matching is disabled. It inserts physical
field names in physical order (bytecode offsets 380–434), then looks up requested
names (437–508). CaseInsensitiveMap overrides put/get by calling no-argument
`String.toLowerCase()` followed by HashMap put/get. Repeated normalized keys
therefore replace earlier entries. This compiled-artifact behavior agrees with
the four observed results. Spark OrcFileFormat passes its case-sensitive setting
to ORC, while OrcUtils separately rejects duplicate top-level names.

No-argument lowercase uses Java's default locale rather than an explicit
Locale.ROOT. This reference does not qualify Unicode, Turkish-case behavior,
other locales, array/map-contained structs, forced positional evolution,
nonvectorized matching, or every schema shape. The ASCII names here do not settle
a general cross-language normalization policy. Formatted plans report Batched
true but are not captured final adaptive execution plans.

## Files and reproduction

`MANIFEST.json` hashes every retained artifact and records exclusions for generated
`.crc`/`_SUCCESS` and runtime directories. Original absolute receipt paths remain
unchanged; manifest paths are portable relative paths. `finalize_evidence.py`
checks the four observations and exact artifact hashes without running Spark.

To rerun, copy `probe.py` into an empty directory while keeping the preceding
28-case reference available at its recorded path. Existing fixture output is
protected by write mode `error`. Use:

```sh
PYTHONDONTWRITEBYTECODE=1 \
JAVA_HOME=/Library/Java/JavaVirtualMachines/jdk-20.jdk/Contents/Home \
JAVA_TOOL_OPTIONS='-Duser.timezone=UTC -Dsun.timezone.ids.oldmapping=false -Duser.language=en -Duser.country=US' \
/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python probe.py > probe.log 2>&1
```
