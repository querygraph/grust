# Constant-context arithmetic lowering

Three native division/remainder builders previously used require_foldable for two
roles: rejecting non-foldable expressions and deferring literal-zero evaluation.
Scalar identifiers must defer rejection until semantic analysis finishes, so that
flag remains false; eager arithmetic then raised before the identifier's type check.

This small follow-up makes those builders consult the read-only constant_context
introduced in25534e8ea. Both identifier paths defer arithmetic evaluation until
foldability/type checks; ordinary queries keep their existing fast path. The native
witness checks division, integral division and remainder under ANSI on/off, proves
TypeOf keeps BIGINT without evaluating division by zero, and checks ordinary-policy
restoration. Reverting only the three predicate changes fails the unchanged test.

The14-case Spark4.2.1 oracle retains the broader error-function/catalog cases that
motivated separate design work. Four arithmetic cases are corrected; behavioral
outcome/condition matching improves2/14→6/14. Complete structured metadata is counted
separately. This does not fix division-by-zero transport metadata, unbound parameter
origins, error-function annotations, or the catalog expression-policy split.

Spark bare SET CATALOG e and SET CATALOG IDENTIFIER(e) have distinct phases, as
Fable's independent55-row025fe2a8 oracle also shows. typeof(raise_error(...)) and
typeof(assert_true(true)) reach catalog void lookup; broad eager annotations would
change that boundary. Bare current_catalog is accepted, while its IDENTIFIER form
is nonconstant. The existing shared catalog helper conflates those policies and
needs a separate design/implementation phase. The probes and failures stay visible.

Exact source/library/control/CLI receipts and all raw rows/errors are archived.
The public300 selected cases and67 upstream Python executions plus4 original
parameter tests remain required; the earlier provenance19/20, validation29/34,
replacement6/7, dynamic13/13, namespace3/3 and SDP helper2/2 are replayed against the
combined source. None of these selections establish full original Scala acceptance.
