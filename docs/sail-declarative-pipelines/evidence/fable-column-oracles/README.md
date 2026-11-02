# Direct column-lookup and lowercase oracles

Recorded 2026-10-30T05:54:48.882403+00:00. These small standalone programs supplement the
[source review](../fable-cdc-unit1-review/README.md) with direct observations.
They do not construct CDC flows, prove analyzer reachability, or execute Sail.

The [JVM fixture and receipt](jvm/README.md) use Oracle JDK 17.0.8 and the
installed Spark 4.2.1 jars. Their embedded revision exactly matches pinned Spark
`617618396087429b5627a86ce933bb0f5d6645cb`. All 276 classpath jars are hashed;
source, exact commands, versions and raw output are retained. The fixture records
23 StructType lookups and 12 Unicode-pair comparisons.

For fields `a, A, a`, exact lookup of `a` returns index 2, while insensitive
lookup returns index 1. The insensitive winner for `a, A, b, c` is index 1;
adding distinct field `d` changes it to index 0. These specific observations
refute both first-match and last-match linear searches as a general substitute
for Spark's map construction. They are not a replacement map algorithm.

Java ROOT lowercase leaves Vithkuqi U+10570/U+10597 and Cyrillic TJE
U+1C89/U+1C8A unequal; Spark insensitive lookup does not match those pairs.
Dotted/dotless I and contextual sigma also distinguish lowercase-map lookup from
Java equalsIgnoreCase. The original JVM packet correctly states that it did not
run Rust; the separate companion fixture below supplies that additional check.

The [Rust fixture](rust/lowercase.rs) compiles with rustc 1.98.1 and applies the
exact `left.to_lowercase() == right.to_lowercase()` expression used by the offered
CDC schema helper to the same 12 pairs. It reports exactly two differences from
the captured JVM results: Vithkuqi and Cyrillic TJE become equal under Rust.
[Its receipt](rust/receipt.json) hashes the source, generated binary and JVM
input observations; [results](rust/results.json) retain every pair, including
the ten matching observations. This is direct expression evidence, not a Sail
runtime or CDC suite verdict.

Generated class/native binaries remain outside this packet. No packages were
installed and no Spark server was started. These observations support the
request to keep Spark's actual lookup resolver and pinned Java compatibility in
Sail while sharing only generic selection bookkeeping. Integration still needs
phase-correct callers and end-to-end regressions.
