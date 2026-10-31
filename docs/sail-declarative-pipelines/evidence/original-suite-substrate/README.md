# Original Scala suite reference substrate

Grust tool commit70a634e2; Sail remains807d66b15, unchanged in this phase.
[Design](../../ORIGINAL-SUITE-EXECUTION-DESIGN.md).

The [exact detached tool gate](qualified/gate.json) passed Ruff, runtime collection
and two original published ScalaTest suites on Spark4.2.1:

- DefaultMaterializeTablesSuite:29/29 passed.
- HiveMaterializeTablesSuite:29/29 passed in a separate JVM.

These58 reference executions are **not Sail passes**. The tool/source/runtime
fingerprints, original XML outcomes and all commands are retained. All47 Scala
sources under the three owned SDP package roots byte-match the Git pin; published
binaries and matching published sources are used, not a claimed local rebuild.

Collection yields36 concrete Suite classes,35 nonempty,554 names, zero unresolved
classes, ignored tags or nested suites in this profile. Source positions/tags are
retained. Static declaration IDs, runtime names and inner-loop assertions remain
different levels of evidence. The legacy inventory stays462 sites/97 reviewed/
68 partial/394 unmapped, and none is promoted by a Spark reference pass.

The [scope expansion](../../spark-4.2.1-scope-expansion.json) identifies20 more
SDP declarations outside those roots: parser/shared-base, direct SQL execution
rejection and pipeline cache lifecycle. Their reconciliation/runtime expansion
is open, so554 is not the whole-goal denominator. The unrelated Hive HQL MV hit
has an explicit source-bound exclusion reason.

Bootstrap attempts retain missing gRPC/Mockito/protobuf class outcomes. Their
registration commands exited successfully while reporting unresolved classes;
we treat them as incomplete, not qualified. The final tool fails collection on
unresolved classes. A combined default+Hive JVM run aborted at Hive initialization
with SparkEnv=null after default passed; Hive-only fresh JVM passed29/29. The
combined profile remains failed. No claim is made that full Connect server
reference execution works on the shaded PySpark runtime; an appropriate profile
is still required.

Bootstrap receipts/logs preserve observed attempts; mutable probe scripts were
snapshotted at the end and do not establish exact historical source bytes for
every bootstrap command. The exact qualified tool is bound to Git70a634e2 and
its recorded file hashes. No binary JARs are committed; artifact URLs, published
checksums and frozen SHA256 pins make the isolated cache reproducible.

Run `python verify.py` with local Grust/Spark Git object stores available.
