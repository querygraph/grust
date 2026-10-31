# Expanded original Spark reference execution

Exact tool ebc097027434ab0f053651a90b4e916fe50e3b99 discovers 43 nonempty suites and 595 scoped runtime names from 56 byte-bound source files. Its fixed source scope includes dataset/Flow parsers, inherited DDL cases in both in-memory and Hive profiles, and two session-lifecycle cases. All 99 recorded reference executions passed on Spark 4.2.1. This is reference evidence, with no Sail acceptance verdict.

The static inventory identifies 486 declarations (24 beyond the legacy 462); inheritance and parameters explain why declaration and runtime counts differ. Shared suites retain their complete registration but execute only fixed SDP declarations. Hive SlowHiveTest tags are retained and executed. The initial no-tags postcheck was incorrect; its failed gate and controller remain alongside the corrected gate. No original test was changed or skipped.

Raw output hashes, tool/source/runtime bindings, XML and logs are preserved. Binary JARs and generated JVM temporary files are excluded. The two lifecycle receipts are separate from the original 97-execution controller.
