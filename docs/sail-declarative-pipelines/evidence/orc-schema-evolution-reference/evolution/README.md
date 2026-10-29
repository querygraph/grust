# Spark ORC requested and inferred schema reference

This bounded follow-up uses installed Spark 4.2.1 and source pin
`617618396087429b5627a86ce933bb0f5d6645cb`, after Grust `861e5214` and Sail
`27ab945aaa3046d05a1f4aeb1e651fddf11db927`. It records 28 observations in one
owned local[1] JVM: **25 successful reads and three errors**. No Sail runtime,
repository modification, build or production policy selection is included.

Actual JVM: Oracle Java `20.0.2+9-78`, UTC default and session timezone, tzdb
`2023c`, FORMAT locale `en-US`, old timezone mapping false. TIME was observed
**disabled by default**, then explicitly enabled before fixture/read work.
Every case records actual settings. ANSI was true. The process exited zero and
owned JVM PID 81668 exited zero. There were no failed startup/harness attempts.

`results.json` preserves requested, read and output schemas; full errors and
failure stages; formatted pre-execution physical plans; exact Arrow integer
storage; all fixture hashes and physical field metadata. Plans identify Batched
true/false where available, but are not captured final adaptive execution plans.
All read errors are retained; none were converted into expected-success assertions
in the runtime probe. `finalize_evidence.py` independently checks the retained
observations, exact values, source excerpts and hashes without running Spark.

## Observations

| Area | Cases | Observed result |
| --- | ---: | --- |
| TIME | 6 | Fractional TIME(0) baseline; requests as TIME(3)/TIME(6) under each vectorization setting preserve all stored nanoseconds. SQL cast control to TIME(3) truncates, while TIME(6) retains these microsecond-aligned values. |
| Interval qualifiers | 5 | Requests YEAR TO MONTH→YEAR and DAY TO SECOND→DAY under both settings preserve stored months/microseconds. Combined widening also preserves them. |
| Integers | 5 | INT→BIGINT is exact under both settings. BIGINT→INT returns null for values outside i32 bounds under both settings. INT→BYTE likewise nulls out-of-range values in the tested vectorized case. |
| Case and missing fields | 5 | Case-sensitive mismatches return nulls; case-insensitive matching resolves both top-level and nested names. Top/nested missing fields are null and null parents stay null. Top-level Foo/foo ambiguity errors; nested Bar/bar requested as bar succeeds with value 22. |
| 11-file inference | 5 | mergeSchema=false omits the eleventh file's unique field; true includes it. A TIME(0)/TIME(3) conflict only in file 11 fails schema inference. Interval YEAR/MONTH and DAY/SECOND qualifiers merge to their ranges; YEAR/DAY family conflict in file 11 fails. |
| `_col*` fallback | 2 | Spark-written `_col0`/`_col1` fields read under renamed supplied fields by position; projecting only the second supplied field also succeeds. |

The TIME input is an exact copy of the retained `time_precisions` file, whose
TIME(0), TIME(3) and TIME(6) LONG storage all contains
`[0, 45296123456000, 86399999999000, null]` nanoseconds. Requested TIME(3) still
contains those values. The SQL TIME(3) control instead yields
`[0, 45296123000000, 86399999000000, null]`. A read-schema precision change
therefore must not automatically invoke the qualified SQL precision-cast helper.

The interval input is an exact retained fixture copy. Requested INTERVAL YEAR
retains +/-14 total months; requested INTERVAL DAY retains
+/-183845123456 microseconds. Since PySpark cannot directly collect/convert
YearMonth intervals, the probe retains the read schema first, then uses the
previously qualified projection that widens qualifiers and exposes months or
microseconds as integers. Physical input storage and exact SQL projection are
recorded. These are not claims that Python directly exposed raw YearMonth Arrow.

The top-level ambiguity error occurs at materialization, with top condition
`FAILED_READ_FILE.NO_HINT` and nested duplicate-field error. Both semantic merge
conflicts fail at schema access with `CANNOT_MERGE_SCHEMAS`. Full nested causes
remain in `results.json` and `probe.log`.

The nested ambiguity result needs a narrow interpretation: physical fields are
`Bar=11, bar=22`, requested name is `bar`, and the result is 22. This does not
distinguish exact-case preference from normalized-name last-wins, reversed field
order, or other nested container behavior. It does show that a blanket recursive
ambiguity error would reject this Spark-readable case. No such general rule is
selected here.

The 11-file directories contain ten identical first-schema files and one named
`part-00010.orc` carrying the distinct schema. Every member and source fixture is
hashed. The unique field appears in one output row with merge enabled; row order
across files is not a promised contract. The successful interval union is
`INTERVAL YEAR TO MONTH` and `INTERVAL DAY TO SECOND`. TIME precision merging
requires semantic equality, not merely equal Arrow nanosecond storage.

## Evidence and limits

`source-audit.json` captures exact pin/blob/SHA-256 excerpts for annotation
handling, mapping/Hive fallback, reader integer access, SQL cast differences,
semantic merging and TIME configuration. ORC Java's general evolution internals
were not independently audited here; null-on-integer-overflow and nested-name
selection are observations for the retained fixtures, not a complete conversion
matrix or a SQL ANSI policy.

The `_col*` fixtures were written by Spark, not historical Hive. They exercise
the all-`_col` name predicate and observed positional fallback, but not forced
positional mode, omitted full schemas, old Hive writer metadata or complex Hive
nested evolution. Case handling is not an exhaustive Unicode/ambiguity matrix.
No decimal/string conversion, mixed timestamp array/map direction isolation,
calendar rebasing, missing files, corrupt files or resource-limit qualification
is included. Resource defaults/admission and production source activation remain
separate checkpoint decisions.

`MANIFEST.json` maps portable relative paths to exact hashes. Original absolute
paths in raw receipts remain unchanged. Original TIME/interval files and the
older `expected.json` were checked before/after; they were not modified. Generated
`.crc`/`_SUCCESS` bookkeeping and empty runtime directories are excluded, with
exclusions recorded. No unrelated process was stopped.

## Reproduce

Use an empty destination with a copy of `probe.py`; the script uses write mode
`error` and refuses to replace retained fixtures. Original reference paths must
be available as recorded. Run:

```sh
PYTHONDONTWRITEBYTECODE=1 \
JAVA_HOME=/Library/Java/JavaVirtualMachines/jdk-20.jdk/Contents/Home \
JAVA_TOOL_OPTIONS='-Duser.timezone=UTC -Dsun.timezone.ids.oldmapping=false -Duser.language=en -Duser.country=US' \
/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python probe.py > probe.log 2>&1
```
