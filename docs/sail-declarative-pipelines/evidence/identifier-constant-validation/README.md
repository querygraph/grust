# Native identifier constant validation

This native Sail unit reuses the existing constant-expression checks, private
resolver ConfigScope, expression coercion and literal evaluator. No new dependency,
provider export, global session mutation or streaming activation is introduced.

The Spark4.2.1 public oracle separates table and scalar identifiers. Table-name
subqueries remain unresolved, so NOT_CONSTANT precedes subquery column/table
analysis. Scalar identifiers keep normal semantic expression analysis first:
missing subquery columns remain UNRESOLVED_COLUMN. Foldability precedes type,
which precedes evaluation and null checks. Named and positional values must be
substituted before guarded validation; an unreachable random branch is still
nonconstant.

A further seven-case oracle qualifies runtime replacement: typeof(rand()) in a
dead table-identifier branch may become a type literal, while any unresolved
subquery inside typeof remains NOT_CONSTANT. Missing table-identifier attributes
also yield NOT_CONSTANT. Only builtin typeof takes the type-only exception; a
registered function shadows it. The existing catalog constant context is separate:
SET CATALOG typeof(rand()) is INVALID_NON_DETERMINISTIC_EXPRESSIONS in Spark.
Sail's existing catalog helper instead reports NOT_CONSTANT; this mismatch is
retained, and the patch does not change the catalog guard to admit it.

The initial28 and expanded30 probes are retained. The final34 adds explicit
provenance witnesses. The baseline30 uses its original reference30.py; the final
34 uses reference.py, with all shared SQL/argument inputs compared individually.
Behavioral conditions may be present only in error text; complete structured
condition/state/parameter comparisons are counted separately in comparison.json.
Successful oracles do not establish full error-metadata parity.

attempt-01 retains the deprecated/wrong-arity Placeholder constructor compile
failure. attempt-02 retains a successful97/177 library gate, public300+67 and
parameter4 run whose subsequent runtime-replacement oracle found a false rejection
of valid typeof(rand()). It was never advanced onto the product branch. The refined
unit adds a request-local table-identifier context and preserves the resolved type
replacement while rejecting its unresolved subqueries. All failures remain raw.

The regression tests check validation ordering, a real catalog-backed scalar
subquery, parameter binding, and configuration restoration after both success and
failure. Four independent mutations leave those tests unchanged: bypass the early
foldability requirement, remove post-resolution validation, omit guarded parameter
substitution, or disable the typeof replacement policy. Each must fail one test
while two others pass. The public runner pins source and CLI bytes and owns teardown.

Remaining required work includes full structured identifier diagnostics and source
positions for unbound positional parameters; scalar current_catalog provenance
lost during lowering; the catalog nondeterminism condition; frozen SQL parameter
capture; generic WithRelations binding; and full original Scala-suite acceptance.
The passing public selection and the behavioral comparisons do not close those
requirements. Fable discussion is CF-0302 onward; no new source authority was given.

The final source candidate is15fd1888c3a474a361afe46d235d52051738229c. Exact97+177
library tests, formatting and strict Clippy pass. Fresh300+67 and original parameter4
pass; earlier dynamic13/13, namespace3/3 and SDP helper2/2 match. The baseline30
matches10 behaviors and10 full metadata sets. Final34 matches28 behaviors and11
full metadata sets; replacement cases improve from3/7 to6/7 behaviors. The six
primary behavioral differences are string division by zero, four unbound-parameter
routes, and scalar dead-current_catalog. Replacement's remaining difference is
the catalog nondeterminism condition. See comparison.json for every case.
