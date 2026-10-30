# ORC boolean lexical reference

A finite owned Java 20 process invoked the installed Scala 2.13.18 StringOps.toBoolean on 17 strings, directly and after Java String.trim (34 calls). PID 46333 exited 0 and was absent afterward. No Spark session or service was started.

The retained cases accept ASCII case variants and Java long-s equivalence in `falſe`; reject 1/0 and unrelated text; reject operation whitespace; accept SQLConf trimming of control characters through U+0020; reject NBSP/em-space. Pinned Spark ConfigHelpers explicitly trims SQL configuration, whereas OrcOptions invokes untrimmed toBoolean. Bytecode shows String.equalsIgnoreCase comparisons against true/false. The implementation preserves the tested lexical distinction; this is not a general Unicode comparison claim or a Sail runtime gate.

result.json records exact invocation, source and jar hashes, JVM ownership/exit, all cases and bytecode excerpts. source-audit.json records the pinned Spark sources and installed class identity. The parent owns Rust gates.
