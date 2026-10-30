# Spark ORC supplied schemas and discovered partitions

This packet retains ten bounded observations from installed Spark **4.2.1**,
with reference source pin `617618396087429b5627a86ce933bb0f5d6645cb`. PyArrow
**26.0.0** generated two ORCs containing only INT `id`: `part=west/data.orc`
contains 11 and 12; `part=east/data.orc` contains 21. Both files were independently
read back before Spark started. Every Spark read and all eleven filters succeeded.

Supplied nonempty schemas deliberately request partition fields first and mark
all fields non-nullable. Spark returned every field nullable. The observed schema
order and partition values are:

| Supplied schema | Case-sensitive true | Case-sensitive false |
| --- | --- | --- |
| `[part STRING, id INT]` | `[id, part]`, populated partition | `[id, part]`, populated partition |
| `[PART STRING, id INT]` | `[PART, id, part]`; `PART` is null, `part` is populated | `[id, PART]`, populated partition alias |
| `[id INT]` | `[id, part]` | `[id, part]` |
| Explicit empty `StructType([])` | `[part]` only, three rows | `[part]` only, three rows |
| No supplied schema | `[id, part]` | `[id, part]` |

For matching or discovered partition names, filtering for `west` returns two
rows and the formatted plan contains `PartitionFilters`. The case-insensitive
alias `PART` also becomes a partition filter. In the case-sensitive alias case,
filtering the distinct requested file field `PART` returns zero rows and the plan
has `PushedFilters` but no `PartitionFilters`; a separate `part` control returns
the two west rows and has `PartitionFilters`. The empty supplied schema's scan
shows `ReadSchema: struct<>` while preserving the three source rows and their
partition values. Empty supplied schema and absent schema are distinct here.

These are formatted **pre-execution** plans and returned rows. The packet does
not instrument file opens or claim runtime byte counts. It qualifies these two
same-spelling partition directories, one physical INT field, and the native
vectorized V1 ORC read path. Mixed directory-key casing, duplicate partition
keys, alternate partition types, nested partition directories, null markers and
non-vectorized behavior remain outside this packet.

`results.json` records each supplied/read/output schema, order, nullability,
values, actual configurations, filters, stages and plans, plus physical fixture
schemas and hashes. `source-audit.json` retains four exact pinned Spark source
files and seven excerpts supporting schema selection, alias binding, partition
nullability, data/partition assembly and pruning. These are source artifacts,
not loaded-class instrumentation or proof that the installed binaries were built
from that commit. `summary.json` records hashes of the installed Spark SQL jars.

The fresh owned JVM was PID **16218**, actual `local[1]`, driver memory `512m`,
Oracle Java `20.0.2+9-78`, UTC, FORMAT locale `en-US`, tzdb `2023c`, old mapping
false. Harness and owned JVM exited zero; independent `ps` inspection confirmed
the PID absent. Initial process creation targeted a not-yet-created working
directory and failed before any shell, fixture or JVM started; the successful
probe was then launched once. No existing service or repository was changed.

`MANIFEST.json` inventories the packet. `validate_evidence.py` is read-only and
checks hashes, fixtures, all observations and pinned source excerpts without
starting Spark. `freeze_evidence.py` records packet provenance once and refuses
to replace an existing manifest; it is not the validation command.

To reproduce, copy only `probe.py` into a new empty directory and run:

```sh
PYTHONDONTWRITEBYTECODE=1 \
JAVA_HOME=/Library/Java/JavaVirtualMachines/jdk-20.jdk/Contents/Home \
JAVA_TOOL_OPTIONS='-Duser.timezone=UTC -Dsun.timezone.ids.oldmapping=false -Duser.language=en -Duser.country=US' \
/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python probe.py > probe.log 2>&1
```

The probe refuses to replace its input directory. Retained raw results, paths,
fixture bytes and logs are unchanged. This packet provides Spark compatibility
reference evidence, with no Sail runtime acceptance claim.
