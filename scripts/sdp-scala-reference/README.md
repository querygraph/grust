# Spark SDP Scala reference substrate

This tool registers and executes the original published Spark4.2.1 ScalaTest
binaries **on Spark**, outside Sail's runtime/dependency graph. It provides an
expanded reference manifest and oracle results. It never claims Sail acceptance.

`artifacts.json` pins twenty Maven Central test/framework artifacts by SHA256.
The three published test-source JARs must byte-match every SDP Scala source in
Spark commit617618396087429b5627a86ce933bb0f5d6645cb, including the inherited Hive
materialization suite. Unexpected or changed cached JARs fail verification.
No binaries are committed. The supplied Spark distribution's runtime JAR hashes
are recorded and checked again after execution.

Use the existing Python3.12 environment and Java17. Supply absolute paths:

```sh
python scripts/sdp-scala-reference/run.py \
  --spark-source /path/to/spark-source \
  --spark-home /path/to/pyspark \
  --java-home /path/to/jdk17 \
  --python /path/to/python3.12 \
  --cache /tmp/sdp-scala-artifacts --output /tmp/sdp-scala-collection collect

python scripts/sdp-scala-reference/run.py \
  --spark-source /path/to/spark-source \
  --spark-home /path/to/pyspark \
  --java-home /path/to/jdk17 \
  --python /path/to/python3.12 \
  --cache /tmp/sdp-scala-artifacts --output /tmp/sdp-scala-materialize run \
  --registration /tmp/sdp-scala-collection/suites.json \
  --suite org.apache.spark.sql.pipelines.graph.DefaultMaterializeTablesSuite
```

Output directories must be fresh. Each `run` starts one JVM for one suite.
Reference bootstrap experiments found that combining default and Hive suites
in one JVM aborted at Hive initialization with SparkEnv=null; the same Hive
suite passed all29 tests in a fresh JVM. The combined failure is retained.
The default materialization suite also passed all29 original tests.

Collection inspects every top-level class in the pipelines, Connect-pipelines
and Hive-pipelines test packages. It reports non-suites, abstract suites, concrete
registration, unresolved classes, tags, nested-suite IDs and source positions.
Unresolved classes or unexpanded nested suites fail collection; registration is
not execution. The observed dependency-complete profile has35 nonempty suites
and554 registered names, plus one empty concrete fixture base. These numbers
are distinct from the462 static declaration inventory.

A run requires a successful registration from the identical tool/runtime profile
and verifies its bytes. XML names/count must match all registered tests, with no
failure/error/skipped children. Missing tests or a JVM abort fail qualification.
Timeouts terminate the owned JVM process group and remain failed attempts.

The supplied PySpark distribution contains a shaded Connect server while the
published Connect tests refer to unshaded gRPC/protobuf. Registration succeeds
with pinned test dependencies; full Connect server reference execution has not
been qualified. A suitable unshaded build/profile is still needed before claiming
that tier executes. Source positions inside generic grid helpers also need
explicit mapping to their caller declarations; do not invent a mapping by name.

See the original-suite execution design for the separate Sail conformance routes.
