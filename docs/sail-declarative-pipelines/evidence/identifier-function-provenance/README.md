# Identifier function foldability

The committed design uses an expression-local marker, selected after independent
review of a collector prototype. A private type-preserving Volatile UDF retains
non-foldability when native lowering replaces a function with a literal. Its field
metadata and type remain unchanged. Only the mark_non_foldable(Expr) factory is
exported from sail-common-datafusion's literal utility; the UDF is not registered
as a user function and cannot execute. Existing logical constant validation rejects
it before simplification. Builtin typeof reads its child's type and discards it
naturally, preserving valid type-only expressions and a non-foldable sibling.

LiteralEvaluator rejects the concrete marker before physical materialization,
including a marker in an inactive CASE branch. This is defense in depth for the
identifier paths, which already check the logical expression first, and protects
other callers of the shared marker factory. It cannot recover a marker already
erased by a caller's simplifier. Volatility here is a retention device for
foldability, not a declaration that the original function was nondeterministic.

Read-only constant_context in the existing ConfigScope selects preservation;
ordinary query lowering remains unchanged. The older eager require_foldable
contract for table/catalog contexts is retained. Registered UDF and HOF results
are wrapped after the actual selected branch finishes argument and lambda
resolution, so semantic errors still precede scalar constant rejection. There is
no new collector, mutable function-context borrow, observation scope, registry,
dependency, serialized plan field, provider export or output metadata. An admitted
identifier consumes or discards the marker; no worker codec is introduced.

The20-case public oracle improves11→19 matching behaviors; complete structured
metadata remains11/20. The one required difference is generic function precedence:
both engines report functionResolution.sessionOrder=second, but Spark's builtin-first
path chooses builtin typeof despite a registered Python UDF, while Sail selects
the UDF. This unit records that difference and leaves function lookup unchanged.
The native UDF fixture uses a unique name; colliding typeof remains in the public
oracle. Initial16/18 inputs and observations are retained rather than rewritten.

collector-prototype preserves the unadvanced18de98927 design and all its successful
100+177 library/public300+67/parameter4 results and controls. Its state collector
was superseded before any product branch advancement. Archived verifier scripts
there retain their original root-layout assumptions; the current verifier checks
the final packet. attempt-01 preserves the initial Clippy collapsible-if failure;
baseline-setup-failure preserves the runner refusing a terminal failed-candidate
checkout before starting any server. The valid baseline used a fresh directory
after explicitly restoring15fd.

Final qualification includes140 shared +100 plan +177 Connect tests, formatting and
strict Clippy. Four mutations preserve the test blobs: drop the builder marker,
drop the selected-UDF/HOF marker, alter its return field type, or disable the shared
materialization guard. The exact expected pass/fail counts are archived. Fresh
300 selected public +67 upstream Python cases and4 existing parameter tests are
required; earlier dynamic13/13, namespace3/3 and SDP helper2/2 must remain matching.
The wider34-case validation improves28→29 behaviors with11 complete metadata sets;
the7-case replacement oracle remains6/7. No full Scala acceptance is claimed.

Next separate units are the read-only constant-context arithmetic lowering split,
then qualification of five additional non-foldable entries from Fable's437-name
source survey (assert_true, raise_error, json_tuple, window, window_time). Catalog
and typeof policy must be measured before broad annotations. Complete diagnostic
rendering/origins, function SQL PATH, frozen parameters, generic WithRelations and
the full Spark SDP goal remain required work. Fable review532bbdff/fbf22e5e and
function table87f423c0 are independent evidence, not implementation authority.
