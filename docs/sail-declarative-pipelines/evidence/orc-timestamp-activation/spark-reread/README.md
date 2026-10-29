# Explicit JVM reader timezone reread

This probe rereads four unchanged earlier ORC fixtures using Spark 4.2.1, source
pin `617618396087429b5627a86ce933bb0f5d6645cb`. It qualifies the reader context
for the retained values. It does not infer reader rules from SQL session timezone.

The first fresh local Connect JVM explicitly selects America/Los_Angeles. The
second, separate JVM explicitly selects UTC and reads the foreign submicrosecond
fixture. Both run with Oracle Java `20.0.2+9-78`, tzdb `2023c`, FORMAT locale
`en-US`, and `sun.timezone.ids.oldmapping=false`. The script reads and asserts the
actual default timezone ID, property, FORMAT locale, runtime and tzdb from the
owned local Spark JVM through its Py4J gateway. The local Connect
startup is the existing default-port pattern; no external server is used.

Results:

- Los Angeles reader: all four fixtures under both UTC and Los Angeles SQL
  session settings match the original numeric or nested Arrow expectations.
- UTC reader: both session settings yield foreign timestamp microseconds
  `[1577934245123456, -1876544, 0, null]`.
- Los Angeles reader yields the previously recorded foreign values
  `[1577963045123456, 28798123456, 28800000000, null]`.
- The UTC SQL Spark-written fixture still reads LTZ source `-1` microsecond as
  `999999`; NTZ stays `-1`. The original file-read expectation is preserved.
- Fixture SHA-256 values and the original expected.json hash are checked before
  and after reading. Nothing writes to those files.
- Both owned JVM process handles exited with code zero. No process unrelated to
  this probe was stopped.

The original collection did not directly record its reader JVM's default ID.
This fresh run proves the selected Los Angeles reader reproduces those values;
it does not retroactively measure the earlier process. Spark Connect `toArrow`
labels LTZ as UTC under both SQL session settings. Sail's existing session-zone
display label is a separate representation choice.

The retained raw logs include local Connect warnings when static launch settings
are replayed as session settings. These do not affect the directly measured and
asserted timezone/runtime settings. There were no failed probe attempts.

## Reproduce

Use the retained reference fixture paths and this workspace's installed PySpark
4.2.1 environment. Run the following sequentially; each process owns and closes
its own local gateway. Keep the existing default local Connect port available.

```sh
PYTHONDONTWRITEBYTECODE=1 \
JAVA_HOME=/Library/Java/JavaVirtualMachines/jdk-20.jdk/Contents/Home \
JAVA_TOOL_OPTIONS='-Duser.timezone=America/Los_Angeles -Dsun.timezone.ids.oldmapping=false -Duser.language=en -Duser.country=US' \
/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python reread.py \
  --reader America/Los_Angeles > la.log 2>&1

PYTHONDONTWRITEBYTECODE=1 \
JAVA_HOME=/Library/Java/JavaVirtualMachines/jdk-20.jdk/Contents/Home \
JAVA_TOOL_OPTIONS='-Duser.timezone=UTC -Dsun.timezone.ids.oldmapping=false -Duser.language=en -Duser.country=US' \
/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python reread.py \
  --reader UTC > utc.log 2>&1
```

`la.json` and `utc.json` retain actual runtime context, owned PIDs, exact projected
rows, expected rows, original fixture hashes, Arrow schemas and assertions.
`summary.json` records the combined result. `MANIFEST.json` hashes this source,
documentation and all result/log files. No Cargo builds or Rust changes were part
of this probe.
