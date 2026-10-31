# Public and SDP catalog command phases

This 32-case oracle compares the same eight expressions in public SQL and SDP
file directives, bare and wrapped in IDENTIFIER. Spark source is pinned to
617618396087429b5627a86ce933bb0f5d6645cb; the actual installed 4.2.1 runtime
JAR hashes are recorded separately. Sail baseline is
f0a232af259fa2bf33c089d5439ffb45fa78061e, using the exact CLI qualified by the
[policy packet](../constant-name-policy/README.md). No flows run or data writes.

The observations confirm Fable's fb208427 source review: public bare
current_catalog succeeds, wrapped current_catalog fails NOT_CONSTANT, and bare
SDP current_catalog also fails NOT_CONSTANT. Public bare typeof(rand()) and bare
SDP typeof(rand()) fail nondeterminism; wrapped typeof(rand()) reaches catalog
double lookup publicly and registers successfully as a directive. Bare 1 DIV 0
raises DIVIDE_BY_ZERO publicly but WRONG_TYPE during directive registration.
Thus public bare commands need optimizer-phase evaluation, wrapped identifiers
resolve during analysis, and bare directives analyze/check without optimization.
The proposed directive namespace overlay is unnecessary and has been withdrawn.

Sail matches 13/32 returned/rows/embedded-condition outcomes and 2 complete error
metadata sets (successful cases count as having no error metadata). All 19
behavior differences are retained in comparison.json, including catalog type-only
functions, nondeterminism/generator priorities, assert_true foldability, and
public arithmetic/error transport. This baseline does not qualify full SDP or
Scala-suite acceptance. Both owned servers stopped and left no listeners.

reference.py generated both observations; run-probe.py owns the Sail server and
checks immutable source/CLI identity against the prior public receipt. Spark was
run with `.venv/bin/python reference.py /tmp/sail-sdp-catalog-phases-spark spark`,
redirecting stdout/stderr to spark.log. verify.py checks artifacts, source hashes,
phase distinctions, comparison accounting and teardown. SHA256.json covers files.
