# Spark ORC duplicate top names and map-key narrowing

This packet retains four observations from installed Spark **4.2.1**, with
reference source pin `617618396087429b5627a86ce933bb0f5d6645cb`. Both fixtures
were successfully written and independently read by PyArrow **26.0.0**. There
were no failed fixture-generation, startup or harness attempts. The two Spark
read failures are retained as failures, not converted into runtime passes.

| Fixture/read | Observed outcome |
| --- | --- |
| Physical top fields `dup=11, dup=22`; requested single INT `dup`; case-sensitive, vectorized | One value: **22**, the last physical field. |
| Same fixture/request; case-insensitive, vectorized | Materialization fails with `FAILED_READ_FILE.NO_HINT`; nested cause reports duplicate fields `[dup, dup]`. |
| Physical MAP<BIGINT,STRING> keys `1, 2147483648`; requested MAP<INT,STRING>; vectorized; `explode(m)` before Arrow collection | Keys **`1, -2147483648`**, values `one, overflow`. |
| Same map fixture/request/projection; non-vectorized | Materialization fails with `FAILED_READ_FILE.NO_HINT`. `probe.log` retains the native `NullPointerException` in `OrcMapredRecordReader.nextMap` → `TreeMap.put`. |

The map result qualifies only this exact BIGINT→INT fixture, query and reader
mode. It does not establish a general wrapping policy, safe-null policy, null-key
representation, other integer widths, nested key structures, sliced unused entries
or entries hidden by null parents. Those are separate compatibility boundaries.
The requested map schema has non-nullable keys by Spark's type contract. Exploding
before collection avoids asking Arrow to construct a map containing null keys;
the output key schema and its actual values are both recorded.

`results.json` retains requested/read/output schemas, exact ordered physical
columns and values, every actual configuration, failure stages and errors, and
formatted **pre-execution** physical plans. The map plans report `Batched: true`
and `Batched: false`, respectively; these are not final adaptive plans. The
non-vectorized failure also exposes a Spark Connect error-detail serialization
failure caused by a null exception message; the full original JVM cause survives
in `probe.log` even though the Python error message contains only the outer error.

The fresh JVM was owned by this probe: PID **5469**, actual `local[1]`, driver
memory `512m`, Oracle Java `20.0.2+9-78`, timezone UTC, FORMAT locale `en-US`, tzdb
`2023c`, old timezone mapping false. ANSI remained true and TIME remained disabled.
The harness and owned JVM exited zero. `summary.json` records an independent
post-exit `ps` check showing the PID absent. No existing service was changed.

`source-audit.json` identifies five exact Spark source blobs/excerpts and three
classes/disassemblies from the installed Apache ORC 2.3.0 jars. The retained
`SchemaEvolution` bytecode selects a regular HashMap for case-aware matching and
puts physical fields in order, supporting the observed last-wins result. This is
compiled-artifact evidence, not a recovered Java source file or loaded-class
instrumentation. Spark's atomic vector `getInt` source contains a Java narrowing
cast; that supports the observed value but alone does not explain every map/null
conversion path. Apache ORC license/notice and immutable release provenance are
included for the retained class bytes; no Oracle JDK implementation is copied.

`MANIFEST.json` inventories every retained file. `validate_evidence.py` validates
the observations, fixture data, source blobs/excerpts and fresh disassembly of the
retained class bytes without starting Spark or changing the packet. No Sail code,
runtime or acceptance denominator is qualified by these observations.

To reproduce, copy only `probe.py` into a new empty directory and run:

```sh
PYTHONDONTWRITEBYTECODE=1 \
JAVA_HOME=/Library/Java/JavaVirtualMachines/jdk-20.jdk/Contents/Home \
JAVA_TOOL_OPTIONS='-Duser.timezone=UTC -Dsun.timezone.ids.oldmapping=false -Duser.language=en -Duser.country=US' \
/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python probe.py > probe.log 2>&1
```

The probe refuses to replace an existing input directory. The original fixture
bytes, raw receipts and their absolute paths are preserved unchanged here.
