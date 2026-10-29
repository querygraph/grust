# Independent review of Spark ORC requested-schema probe

Reviewed the retained `probe.py` and `results.json` in
`/tmp/sail-sdp-orc-requested-schema-reference/` against Spark source pin
`617618396087429b5627a86ce933bb0f5d6645cb`. No reruns, builds, or repository edits
were performed. The proposed archive claims are supported with the scope below.

The completed probe records Spark 4.2.1, native ORC, case-sensitive resolution,
UTC SQL session and directly observed UTC reader JVM default, Oracle Java
20.0.2+9-78/tzdb2023c, en-US FORMAT locale, and oldmapping=false. It materialized
24 cases: eight succeeded and sixteen produced retained errors. The owned
gateway exit code is zero. Script and fixture hashes match the recorded values.

## Supported observations

- Supplying the complete schema and then selecting the second `ntz` field
  succeeds, returning `[1623053350654321, null]`. Supplying only a single `ntz`
  field as the reader schema fails. These are distinct operations.
- Swapping scalar LTZ/NTZ requested types, reordering the mixed top-level
  LTZ/NTZ fields despite matching names, and swapping or reordering those kinds
  inside the nested struct all fail with an underlying
  `UNSUPPORTED_FEATURE.ORC_TYPE_CAST`. Their outer Spark error is
  `FAILED_READ_FILE.NO_HINT`, and failure occurs at materialization, after the
  supplied schema can be analyzed.
- Appending an absent LTZ or NTZ field succeeds and produces two null values in
  that field. This observation concerns appended fields, not arbitrary insertion
  or all requested-schema evolution.
- The combined array swaps and combined map swaps reach later timestamp
  conversion and fail with `java.lang.ArithmeticException: long overflow` for
  this fixture. Each case changes both directions together; it does not establish
  either direction's behavior independently, nor a universal rejection policy.

All of these outcomes occur with `spark.sql.orc.enableVectorizedReader` set to
both true and false, and the script records the read-back configuration. That
does not itself prove the executed physical path for every successful case: no
executed-plan artifact was captured. For the array/map failures, the stacks do
provide direct path evidence: true-setting cases pass through
`OrcAtomicColumnVector.getLong`, while false-setting cases pass through
`OrcDeserializer.newWriter` and `RecordReaderIterator`. The scalar/struct errors
arise earlier in the shared compatibility check.

## Source explanation and limits

At the pinned source, `OrcUtils.scala:232-243`
(`sql/core/src/main/scala/org/apache/spark/sql/execution/datasources/orc/`)
zips the physical file's logical field types with the full supplied `dataSchema`
by position before requested-column matching. It rejects LTZ/NTZ mismatches and
recurses only when both positions are structs. It does not recurse into arrays
or maps. Thus the one-field supplied `ntz` is compared to the first file LTZ;
the complete supplied schema passes before a separate required-schema projection
selects the second field. Matching names do not bypass that earlier check.

`OrcUtils.scala:275-299` then matches requested names and marks absent fields as
`-1`. `OrcColumnarBatchReader.java:198-209` materializes missing columns as null
when there is no default. These source paths support the observed appended-null
behavior, without generalizing the fixture into a full evolution specification.

`OrcFileFormat.scala:147-156` combines the configured vectorized-reader flag with
the planner's batch-return option, so configuration alone should not be described
as executed-plan evidence. The retained later-failure stacks point to the pinned
`OrcAtomicColumnVector.java:105-110` and `OrcDeserializer.scala:150-151`, both of
which call Java-timestamp conversion. Those are evidence of actual path entry
for these failing cases, not a promise that every nested mismatch must overflow.

The initial failed attempt remains separate. Its `errorifexists` write mode is
rejected by the installed PySpark Connect client before the requested-schema
read experiment. It must not be counted as an ORC schema-compatibility result.

## Checked identities

- Completed script SHA-256:
  `e0e3156e8f657a74ee930befe41f7896de23e44fc8eeca5e25048e75302000d5`.
- Completed results SHA-256:
  `79461041922be1ae5afb216cb5e5849af0453db93df0cc04b7be84d36314b397`.
- Two-row ORC fixture SHA-256:
  `84d9cfde57daf8f48e33081cfd342decee8488cbcf56469a68af26d47e1f593e`.
- Initial failed-attempt results SHA-256:
  `d915228dd665eb6dd494e7f89de4d05c45ba942100b6250b1a66195bac0c03d3`.

This review qualifies an observed Spark baseline. It does not select Sail's
requested-schema policy or claim that Sail implements these outcomes yet.
