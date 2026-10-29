# Spark ORC requested-schema timestamp reference

Spark 4.2.1 source pin `617618396087429b5627a86ce933bb0f5d6645cb`;
one fresh owned local[1] Spark Connect JVM for the completed run. Actual runtime
was Oracle Java `20.0.2+9-78`, UTC default and session timezone, tzdb `2023c`,
FORMAT locale `en-US`, old timezone mapping false. Native ORC implementation,
case-sensitive matching and nested vectorization enabled. `results.json` records
actual configurations, supplied/analyzed schemas, exact Arrow timestamp integer
values, full exceptions, fixture hash and owned JVM cleanup.

The 12 cases ran with `spark.sql.orc.enableVectorizedReader=true` and `false`
(24 total). Both settings produced the same outcomes. Successful physical reader paths were
not separately captured. For the failing array/map cases only, retained stacks
show OrcAtomicColumnVector/getLong with true and OrcDeserializer/newWriter with
false. All supplied schemas
analyzed successfully; every error below occurred during `toArrow` materialization.
These are observed file-read results, not predicted SQL cast behavior.

| Case | Result under both settings |
| --- | --- |
| Exact complete schema | Success; scalar and nested LTZ/NTZ microseconds preserved |
| Change scalar LTZ to NTZ | Dedicated `UNSUPPORTED_FEATURE.ORC_TYPE_CAST` cause |
| Change scalar NTZ to LTZ | Dedicated `UNSUPPORTED_FEATURE.ORC_TYPE_CAST` cause |
| Supply only the second, NTZ field | Dedicated LTZ-to-NTZ compatibility error |
| Supply complete exact schema, then select second NTZ field | Success |
| Reorder matching top-level LTZ/NTZ field names | Dedicated LTZ-to-NTZ compatibility error |
| Append a missing LTZ field | Success; appended field is null in both rows |
| Append a missing NTZ field | Success; appended field is null in both rows |
| Swap LTZ/NTZ types within STRUCT | Dedicated LTZ-to-NTZ compatibility error |
| Reorder matching names within STRUCT | Dedicated LTZ-to-NTZ compatibility error |
| Swap ARRAY element LTZ/NTZ types in both arrays | Later `ArithmeticException: long overflow` |
| Swap MAP value LTZ/NTZ types in both maps | Later `ArithmeticException: long overflow` |

The six dedicated errors per mode have top-level condition
`FAILED_READ_FILE.NO_HINT` and retain the nested ORC_TYPE_CAST cause. The two
array/map errors per mode have no exposed PySpark condition and retain their
later Java overflow stacks. They do not demonstrate that every array/map swap
must fail, nor that both conversion directions independently fail: each case
changes both timestamp-bearing containers. No expected success was imposed on
these cases. The two-row fixture contains nonnull scalar/nested values, null
array elements/map values, and a second row of null scalar/container values.

Source evidence in `source-audit.json` explains the difference: OrcUtils compares
physical and full supplied data-schema field types by positional zip, before
name matching, and recurses only through STRUCT. OrcFileFormat passes the full
data schema separately from the pruned required schema. Arrays/maps therefore
reach later readers instead of this dedicated check. Exact numeric successes
are checked by `finalize_evidence.py`; no Sail process was involved.

## Attempts and ownership

The first attempt stopped before file creation or read cases because Connect
rejects the write-mode spelling `errorifexists`. Its exact source/log/results and
fixture SQL are retained under `attempt-01-unsupported-write-mode/`. Only that
spelling changed to the supported `error` for the completed run. Both attempts'
owned gateway processes exited with code zero. The completed Python process
returned zero; its owned JVM PID was 75911. No unrelated process was stopped.

The fixture is retained byte-for-byte. Generated Hadoop `.crc`/`_SUCCESS` files
and empty local runtime directories are excluded from the portable evidence;
`MANIFEST.json` lists exclusions and hashes all retained files. Original absolute
paths in raw receipts remain unchanged; the manifest supplies portable paths.

## Reproduce

Start from a new copy without `data/mixed_timestamps` (write mode `error` prevents
an accidental replacement of the retained fixture):

```sh
PYTHONDONTWRITEBYTECODE=1 \
JAVA_HOME=/Library/Java/JavaVirtualMachines/jdk-20.jdk/Contents/Home \
JAVA_TOOL_OPTIONS='-Duser.timezone=UTC -Dsun.timezone.ids.oldmapping=false -Duser.language=en -Duser.country=US' \
/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python probe.py > probe.log 2>&1
```

This bounded reference settles the observed positional timestamp-check cases.
It does not select Sail production policy, qualify all requested-schema evolution,
TIME/interval/integer conversions, Hive positional mode, case ambiguities,
missing fields inserted at other positions, non-UTC readers or resource defaults.
Those remain explicit next design work. This is not Sail runtime qualification.
