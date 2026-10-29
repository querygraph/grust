# Shared cast error identity and transport

This completes the announced execution-error design checkpoint. General SQL
semantics stay in Sail; no LakeCat or pipeline evaluator is introduced. The
[retained evidence](evidence/shared-cast-error-design/provenance.json) pins Sail
992f5bcbf, its fresh CLI hash, Spark 4.2.1 source and all observations. Production
source and engine behavior are unchanged by this design commit.

## What the paired probes establish

Twenty-four ordinary SELECT cases run against each engine. The exact retained
class/condition/state/parameter-or-row assertions pass 24/24 on Spark and 4/24 on
Sail. This is a required failing baseline, not a passing compatibility verdict.
Both original pipeline registration failures remain independently retained in
[992f5bcbf](evidence/992f5bcbf60added5b44596f279ab8801f0c0045/gate.json).

Malformed string-to-integral/floating/decimal input has CAST_INVALID_INPUT,
NumberFormatException and SQL state 22018. INTEGER canonicalizes to INT. Boolean
uses the same condition/state but SparkRuntimeException; DATE/TIMESTAMP use
DateTimeException. Complete parameters name the offending **value**, not its SQL
column/expression, plus canonical sourceType, targetType and ansiConfig. A quote
in the value is backslash-escaped, while a newline remains a newline. Backslash
rendering follows Spark Literal.sql; do not substitute JSON or identifier quoting.

The row-dependent and null-leading row cases identify the actual failing value.
Sail currently reports SparkRuntimeException for those, versus NumberFormatException
for its constant form. The exact loss point on the row-dependent path is not yet
proven; do not infer that its worker transport necessarily preserves new metadata
merely because the enum is serializable. Exercise the actual task/error paths.

Nested CAST and TRY_CAST around an invalid child preserve the **inner** cast
failure. TRY_CAST on the malformed value, legacy INT with ANSI false, typed null
and a valid value return the expected rows on both engines. Child exceptions must
not be caught as errors of the outer cast.

Overflow classification is not uniform. STRING '2147483648' to INT is
CAST_INVALID_INPUT; valid decimal text beyond precision is
NUMERIC_VALUE_OUT_OF_RANGE.WITH_SUGGESTION/22003; BIGINT 1000 to TINYINT is
CAST_OVERFLOW/22003. Do not label every Arrow cast error as malformed input. The
latter two mismatches, and temporal class/metadata mismatches, remain explicit
coverage boundaries.

## Selected shared error representation

Extract the existing StructuredSparkError data record from sail-spark-connect
into a focused module under sail-common-datafusion/error. Keep its name and
Spark metadata fields rather than creating a second condition/parameter model.
Use owned strings for class, condition and SQL state so deserialization has no
static-lifetime constraint. Derive Clone/Serialize/Deserialize in addition to
Error/Debug. Existing dependencies suffice; add no crate, graph or catalog import.

There are nine current constructors, all in Connect session/pipeline code. Their
field values and rendered transport must remain unchanged; adapting literal fields
to owned strings is mechanical. Re-export the record from the existing Connect
error module so callers keep their import paths. Keep gRPC formatting and
truncation in Connect. After the type moves, a local into_status helper replaces
the old foreign From implementation (Rust orphan rules); do not move the Connect
wire formatter into the shared data module.

Add a boxed structured variant to CommonErrorCause. Detect the shared error type
while traversing DataFusion/Arrow external/context/shared wrappers, before falling
back to prose or generic source traversal. Preserve it in RemoteError and the
existing serde task-cause transport. It remains an ordinary retryable execution
error; do not change unknown-commit precedence or retry policy.

Add the corresponding private SparkThrowable structured variant and route it
through the existing structured metadata formatter. Preserve its class, condition,
SQL state, parameters and message on every terminal conversion path. The private
class_name accessor may return &str instead of &'static str. Error-detail fetch
paths also consume message/class; audit those callers. No new global exception
registry or regex-based reconstruction of Spark errors is needed.

## Capture a cast failure while the value is still available

Start with ANSI string-to-integral/floating/BOOLEAN casts in the shared expression
resolver, not a pipeline command. A focused immutable scalar UDF carries the
canonical target DataType and SQL target name. It receives the resolved child
once and uses the same ColumnarValue.cast_to operation/options as DataFusion 55.2
CastExpr for successful conversion. This preserves the vectorized success path;
no row-by-row success validation or separate job is added.

On kernel failure, inspect only supported malformed-input cases with the already
computed child. For arrays, a safe cast can identify the first non-null input
whose result is null; scalar input is available directly. If needed, replay
single-row casts on that retained array only on the failure path to establish
which row actually fails. Never reevaluate the child expression. Unknown failure
kinds propagate their original typed error instead of receiving invented metadata.

Construct StructuredSparkError at that point using actual input, canonical types,
Spark quoting and the CAST_INVALID_INPUT message/parameters. Numeric targets use
NumberFormatException; BOOLEAN uses SparkRuntimeException. Preserve zero-length,
null, sliced arrays, Utf8/LargeUtf8/Utf8View and scalar behavior. Keep nullability
consistent with the previous cast field; preserve the existing NamedExpr naming
and metadata logic rather than exposing an internal UDF name in output schemas.

Gate that resolver branch on ANSI true and non-TRY casts. Keep the existing
SparkCastStringToInt32 legacy implementation and ordinary TRY_CAST behavior.
A child failure occurs before UDF invocation and propagates unchanged, including
through an outer TRY_CAST. Constant folding and LiteralEvaluator execute the same
UDF, so catalog extraction needs no special error translator or evaluator change.
Preserve existing foldability/type/null validation order in resolve_catalog_name.

The UDF is driver- and worker-executable. Add a typed target-field payload to the
existing ExtendedScalarUdf codec, with a new unused field number (41 is currently
free), following SparkStructRename's target-type pattern. Encode/decode both the
target type and canonical SQL name. Validate malformed payloads; do not silently
fall back to a built-in with the same name. Round-trip tests must execute both
successful and failing scalar/array expressions after decode.

DATE/TIMESTAMP already have dedicated Sail functions and must retain their parsing
and timezone behavior. Decimal range and numeric overflow use different conditions.
Do not route these into the new malformed-input branch. Their retained probe
failures stay visible; migrate the appropriate producers in later focused units
if required by the SDP acceptance crosswalk, using the same shared error record.
This design does not redefine full SDP success as the primitive-cast subset.

## Alternatives rejected

- Prefix matching in Connect cannot reliably recover offending row values, source
  types or nested-cast attribution and would confuse decimal/numeric overflow.
- Pipeline-only metadata repair leaves ordinary SQL and worker failures different.
- Replacing all casts with a new evaluator changes established temporal, decimal,
  struct, variant and legacy semantics unrelated to the required failure.
- A custom physical cast alone misses optimizer constant evaluation through the
  existing default physical expression context; changing all expression planners
  and LiteralEvaluator would be a wider architectural change.
- A new graph/runtime error framework duplicates StructuredSparkError and
  CommonErrorCause, which already provide the required data and transport seams.

## Granular implementation and acceptance

1. Extract the existing shared error record, with mechanical constructor updates
   and unchanged native pipeline transport tests. Keep runtime behavior unchanged.
2. Retain structured causes through wrapper/serde/task-stream paths and Connect
   conversion. Test DataFusion/Arrow context/shared/external wrappers, RemoteError,
   task status and Flight status, plus unknown-commit collection precedence.
3. Add the scalar cast implementation and typed function codec with direct scalar,
   array, slicing/null/empty and decoded execution controls; no SQL activation yet.
4. Activate the selected ANSI casts in ordinary SQL resolution. Add public ordinary
   and nested/pipeline controls that fail before and pass unchanged on Spark.
   Retain all thirteen catalog registration assertions and require 13/13 before
   claiming that gap closed. Preserve opposite session/file and session/graph
   configuration probes.
5. Re-run full affected Rust libraries, strict Clippy/fmt, fresh CLI selected Python
   regressions and the 67 pinned upstream Python executions at immutable commits.
   Record the entire 24-case probe with all remaining failures; no selective
   denominator or historical result replacement. Continue original batch/catalog
   acceptance, then streaming/Iggy and CDC in their planned phases.

No original Scala-suite, distributed-cluster, query-context/stack-trace, full batch,
streaming or CDC verdict follows from this design. The complete thread objective
remains active. This checkpoint is ready for implementation without another error
architecture decision; notify the operator before the next distinct design phase.
