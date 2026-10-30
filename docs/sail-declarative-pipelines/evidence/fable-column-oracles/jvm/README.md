# Direct Spark 4.2.1 / JDK 17 helper oracle

This standalone Java fixture directly invokes `StructType.getFieldIndex`,
`StructType.getFieldIndexCaseInsensitive`, `String.toLowerCase(Locale.ROOT)`,
and `String.equalsIgnoreCase`. It does **not** start a Spark server, construct
a CDC flow, establish analyzer reachability, or execute end-to-end CDC.
No repository was modified and nothing was installed.

The fixture compiled and ran successfully using Oracle JDK **17.0.8**, runtime
`17.0.8+9-LTS-211`, and the existing PySpark **4.2.1** jars. Spark's embedded
`spark-version-info.properties` records revision
`617618396087429b5627a86ce933bb0f5d6645cb`, exactly matching the pinned source
checkout. The class origins in the raw output confirm the loaded StructType
and Scala jars. The classpath contains Scala **2.13.18**.

There are **23 lookup observations and 12 Unicode-pair observations**. These
are direct oracle observations, not additional Sail test passes.

## Lookup observations

All indices are zero-based. The first/last comparison columns in the raw
results are separately labeled simple linear searches using Java ROOT
lowercasing; they are not Spark implementations.

| Fields | Query | Exact index | Case-insensitive index |
| --- | --- | ---: | ---: |
| `a, A, a` | `a` | 2 | 1 |
| `a, A` | `a` | 0 | 1 |
| `A, a` | `a` | 1 | 1 |
| `a, A, b, c` | `a` | 0 | 1 |
| `a, A, b, c, d` | `a` | 0 | 0 |
| `b, c, d, a, A` | `a` | 3 | 3 |
| `a, b, c, d, e, a` | `a` | 5 | 5 |

The `a, A, a` result proves that case-insensitive lookup can choose neither
the first nor last case-matching source index. Adding an unrelated fifth
distinct name changes the winner for `a, A, b, c`, consistent with the Scala
map representation boundary identified in the source review. These are
observations for these exact pinned jars and inputs, not a proposed general
replacement algorithm.

## Unicode observations

| Pair | Equal after ROOT lowercase | `equalsIgnoreCase` | Spark insensitive lookup |
| --- | --- | --- | --- |
| U+10570 / U+10597 (Vithkuqi) | false | false | missing |
| U+1C89 / U+1C8A (Cyrillic TJE) | false | false | missing |
| `İ` / `i` | false | true | missing |
| `I` / `ı` | false | true | missing |
| `İ` / `i` + U+0307 | true | false | index 0 |
| `Σ` / `ς` | false | true | missing |
| `AΣ` / `aς` | true | true | index 0 |
| `AΣA` / `aσa` | true | true | index 0 |
| `AΣA` / `aςa` | false | true | missing |

The newer Unicode pairs remain unchanged by Java 17 lowercasing, directly
corroborating the JVM side of the source-review finding. Dotted/dotless I
and sigma also confirm why Sail cannot replace the lowercase-map comparator
with its existing `equalsIgnoreCase` resolver comparator. No Rust fixture
was compiled or executed here; the candidate Rust comparison remains
supported by the code and installed Rust mapping tables inspected in the
separate source review.

## Retained evidence and replay

- `KernelProbe.java`: complete standalone fixture. Generated class files are kept outside this archive packet, in `/tmp/sail-sdp-fable-kernel-jvm-probe-classes`.
- `run_probe.py`: exact capture/hash runner.
- `commands.json`: exact argv, shell display, working directory, and exit code for every recorded subprocess.
- `java.stdout.txt`: unmodified JSON-lines result; `java.stderr.txt`: unmodified stderr (empty).
- `results.json`: parsed copy of the JSON-lines result.
- `java-version.*.txt`, `javac-version.*.txt`, `javac.*.txt`: version and compile output.
- `spark-build-properties.json`: embedded jar build metadata, including the exact Spark revision.
- `classpath-jars.json`: names, absolute paths, sizes, and SHA-256 hashes of all 276 jars on the classpath.
- `receipt.json`: scope, versions, build revision match, source/runner/class/raw-output and executable hashes, counts, and commands.

Replay from this directory with the existing environment:

```sh
/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python /tmp/sail-sdp-fable-kernel-jvm-probe/run_probe.py
```

The runner only writes this temporary directory and its sibling compiled-class directory. `/tmp` resolves to
`/private/tmp` on this machine, which is why the captured commands use the
latter spelling.
