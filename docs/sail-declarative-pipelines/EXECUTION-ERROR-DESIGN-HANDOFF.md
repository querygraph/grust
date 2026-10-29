# Next design checkpoint: shared execution-error metadata

The operator requested notice before the next design phase to switch to Astra.
The catalog activation gate reaches that boundary. No new error architecture is
selected here. General SQL execution errors belong in Sail; a pipeline-specific
cast-message wrapper would leave the ordinary SQL failure unresolved.

## Required failing behavior

The [activation receipt](evidence/992f5bcbf60added5b44596f279ab8801f0c0045/gate.json)
retains the complete unchanged thirteen-case catalog registration assertions.
Eleven pass. The two failures are graph_default_false and
session_true_file_false: session ANSI true must dominate graph/file false, and a
malformed integer cast must raise NumberFormatException with CAST_INVALID_INPUT
and SQL state 22018. Sail preserves the exception class but omits condition and
SQL state. Other registration analysis errors have the required native wrapper.
No failure or assertion is removed from the retained probe.

An independent ordinary SQL control runs SELECT CAST('not-an-int' AS INT) with
session ANSI true on both engines. Sail likewise returns NumberFormatException
with condition/state/parameters absent. Spark 4.2.1 returns CAST_INVALID_INPUT,
22018 and expression/sourceType/targetType/ansiConfig parameters. The paired
[probe](evidence/992f5bcbf60added5b44596f279ab8801f0c0045/cast-transport-probe.py),
[Sail result](evidence/992f5bcbf60added5b44596f279ab8801f0c0045/cast-transport-sail.json) and
[Spark result](evidence/992f5bcbf60added5b44596f279ab8801f0c0045/cast-transport-spark.json)
record exact observations. The Spark source is pinned at
617618396087429b5627a86ce933bb0f5d6645cb; Sail uses the freshly built 992f5bcbf CLI.

## Existing boundaries to inspect during design

- sail-plan's catalog resolver uses shared expression coercion, simplification
  and LiteralEvaluator. Runtime errors are propagated instead of becoming pipeline
  analysis failures. Keep the validated type/foldability/null ordering.
- sail-common-datafusion's CommonErrorCause identifies Arrow cast errors.
- sail-spark-connect/error.rs maps numeric Arrow casts to NumberFormatException,
  but From<SparkThrowable> supplies no condition/state metadata. Existing
  StructuredSparkError already supports native metadata for other operations.
- Constant simplification may evaluate a cast before a physical query runs.
  Identify the structured information available at the point of failure, and
  preserve it through planning and execution rather than guessing unavailable
  expression details from prose.

## Questions for the next design phase

Determine the smallest shared representation and transport change that can retain
cast error identity and required parameters through both ordinary query execution
and constant-expression preparation. Audit expression provenance, null/ANSI/try-cast
behavior, nested cast attribution, target-type aliases and exception-class mapping
before choosing a boundary. Preserve existing ordinary function behavior and the
pipeline distinction between analysis wrappers and native execution failures.

Add ordinary SQL and pipeline controls that fail on the current engine and pass
unchanged on Spark 4.2.1. Retain all thirteen existing registration assertions.
Separate shared error plumbing, affected evaluator/function callers, transport and
activation into human-reviewable commits as justified by the selected design.
No original Scala, full batch, streaming, CDC or production catalog verdict follows
from this handoff. Remaining catalog adapter acceptance is also still outstanding.
