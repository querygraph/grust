# General native ambiguity diagnostics

`95c32c055712995e06a56fc5c0a86d09bc3c954f` reports structured ambiguity after
Sail's existing root resolution establishes that two different attributes match.
It preserves the qualifier/origin identity distinction, successful bindings,
matching order and nested extraction precedence. Diagnostic collection is allocated
only after the first different match is found.

The existing schema diagnostic identifier formatter moves to the shared error
module and is reused; no parser dependency or new error representation is added.
Schema validation keeps the same formatter behavior. AMBIGUOUS_REFERENCE carries
AnalysisException, SQLSTATE42704, name and referenceNames. References use the
requested root spelling and sort by Java UTF-16 order. Different identities may
therefore produce identical rendered names, which remain in the list.

## Independent reference

`reference-source.json` pins QueryCompilationErrors, AttributeSeq matching,
NamedExpression.qualifiedName and UnresolvedAttribute.name. `spark/` records ten
public SQL observations from installed Spark/PySpark4.2.1; the local source pin is
recorded separately and is not claimed built into those runtime jars.

Seven cases yield AMBIGUOUS_REFERENCE: bare/qualified names, joins, nested roots,
literal dots, supplementary Unicode qualifier ordering and generated aliases.
One raw-backtick request yields INVALID_ATTRIBUTE_NAME_SYNTAX, matching Spark's
identifier diagnostic parsing. Two controls succeed: repeating the same attribute
and exact case-sensitive selection. Native tests require every condition, state,
class and message parameter; public replay also checks actual success rows.
The initial valid eight-case reference is retained under spark-initial/ before the
Unicode/generated-alias expansion, with its original harness and raw log.

## Exact gates and runtime scope

- final/: fmt, strict all-target/all-feature Clippy;139 common-datafusion +240
  data-source +92 Plan +176 Connect library tests pass (647 total).
- native-control/: restoring only attribute.rs from005fcb078 makes the unchanged
  native SQL test fail0/1 (exit101). The shared formatter and test blob are unchanged.
- public/: exact-source fresh CLI build,300 selected public tests +67 upstream
  Python executions pass. This is not original Scala-suite acceptance.
- sail-ordinary/: ten identical ordinary SQL inputs, complete error metadata or
  success rows compared in comparison.json.
- sail-external/: original-byte Parquet replay of the existing seven pipeline/two
  direct metadata cases. All nine condition/row outcomes match. Both formerly
  generic ambiguity errors now match Spark's first-line messages exactly.

No private/session/provider-setting or successful read behavior changes are
claimed by this diagnostic unit. The metadata probe uses the unchanged adaptation
from the preceding packet: copy the original Spark file bytes, retain all SQL and
settings, normalize only the relocated URI during comparison. Owned servers stop
normally and leave no listeners. Original files and every output are hash checked.

## Retained attempts

attempt-01/ (6ca0d9999) fails strict Clippy for a needless borrow; formatter passed.
The redundant borrow was removed. attempt-02/ (bb395f206) passes139 common and240
source tests, then91 Plan pass/1 fail; Connect is not reached. Its nested named_struct
fixture lacked the CatalogManager provided by normal Sail sessions. The memory
catalog fixture was added without changing SQL or assertions. The final code also
preserves the old allocation-free successful ambiguity check before constructing
an error list. Neither failed candidate is represented as passing.

This closes the two comparison gaps retained by the preceding metadata packet.
Other resolver error categories, complete origin/provenance, configured dynamic/
WithRelations binding, CTE equivalence, format inference/evolution, captured
preparation, shutdown, streaming/Iggy/CDC and full original Scala acceptance remain.

Run verify.py for source, gate/control identities and both comparisons.
run-probe.py OUTPUT COMMIT PUBLIC_RECEIPT ordinary|external uses a fresh output
folder and refuses source/binary drift. compare.py defines the precise scope.
