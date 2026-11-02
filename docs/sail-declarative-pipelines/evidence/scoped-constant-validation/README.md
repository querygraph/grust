# Scoped constant-expression validation

Sail4070e895b69338eb19f22643f0e40815da89ff34 on
036dc6dde5e5111dbfcae94ec8a3afb9f323c84b. Three plan files: the existing
constant entry point, a private visitor, and seven focused tests. The gate passes
114 plan libraries, formatting and strict all-target/all-feature Clippy. Four
production-only controls each fail0/1 with unchanged test blobs.

The [worker codec](../ordered-divmod-codec/README.md) can represent the ordered
three-lambda evaluator, but the old flat constant check rejected every lambda
and bound variable. Simply permitting those node kinds would also admit free
variables and arbitrary higher-order expressions. This unit recognizes only the
exact internal SparkDivModLazy implementation with three direct Lambda arguments.
Each argument opens its own lexical parameter scope; sibling/end-of-body exits
remove that scope. Nested internal evaluators can shadow names and capture outer
bindings. Function names alone do not grant eligibility.

Every body still traverses the old scalar variant allow-list and rejects volatile
or async scalar functions. Non-foldable provenance markers remain effective.
Columns, free variables, arbitrary lambdas and other HOF implementations remain
nonconstant. Type/parameter-arity checking stays with the existing analyzer and
evaluator; this pass checks eligibility and invokes no bodies or field inference.
The existing NOT_A_CONSTANT_STRING.NOT_CONSTANT diagnostic is unchanged.

## What the native fixtures prove

- An internal native4/2 validates, reports its type and evaluates to string2
  through the existing LiteralEvaluator. This integer fixture is not a new
  assertion about Spark SQL `/` coercion or formatting.
- Nested evaluators shadow the operation parameter names, capture an outer
  value, and restore another outer binding, producing6 through real evaluation.
- Bound names do not escape a whole body or an argument sibling. Raw columns,
  free variables and arbitrary lambdas fail both alone and inside the evaluator.
- Volatile and provenance-marked expressions fail in all three argument positions;
  the volatile callback remains at zero invocations.
- An IMMUTABLE AsyncScalarUDF fails eligibility, independently of volatility,
  at the root and in all three argument positions.
- A different HOF implementation with the same name, missing argument, value
  argument and alias-wrapped lambda argument are rejected.
- Eligible ANSI zero arithmetic reports Int32 type before execution, then raises
  DIVIDE_BY_ZERO only when evaluated. Null-left/zero-right and a failing left
  thunk skipped by null right remain typed nulls through real LiteralEvaluator.

## Causal controls

Each control changes only validation.rs on the exact candidate:

| Mutation | Unchanged test that fails0/1 |
| --- | --- |
| Disable the three-argument internal admission | positive constant validation/evaluation |
| Treat any name under a lambda as bound | sibling/out-of-scope rejection |
| Remove volatility rejection | volatile/provenance rejection without invocation |
| Remove async rejection | immutable-async rejection |

All seven new fixtures and the existing107 plan tests pass on the candidate.
The packet verifier also compares the old/new ordinary variant sets and confirms
that lowering, cast resolution, worker converter/proto and evaluator files are
unchanged. There were no failed candidate attempts in this unit; failed control
runs are deliberately retained, not treated as source-gate successes.

## Scope and remaining requirements

Arithmetic lowering and public SQL registration are unchanged. No fresh public
runtime verdict or original Scala SDP-suite acceptance is claimed. Ordinary
computed identifiers continue using their existing representation; the tests
above exercise the actual new internal-HOF eligibility path directly. End-to-end
IDENTIFIER arithmetic and SET CATALOG fixtures must exercise the new lowering
when it is activated; passing old-lowering SQL examples now would not prove that.

The [operand design](../../OPERAND-EVALUATION-DESIGN.md) stays active. Folding of
ordinary internal-evaluator literals, actual Sail optimizer behavior for fallible
conditional bodies, nested/extracted input contexts, CSE and optimized fast-path
performance still need qualification before SQL activation. No replay mode or
streaming/CDC authority is introduced. The prior runtime6/domain2, decimal,
generic CASE and original Scala-suite gaps remain required. Coverage inventory
stays462 sites/97 reviewed/61 partial/401 unmapped. Latest public qualification
remains b857; current CLI is still the parent5a binary from the earlier comparison.

Run `python verify.py` with Python3.12. It checks every manifest hash, source/test
pin, gate count, four controls, unchanged ordinary policy and activation boundaries.
Existing Sail Git objects are required. Scripts preserve historical absolute paths
and fresh-output assumptions; do not rerun them in place or relabel old binaries.
