# Foldability provenance for scalar `IDENTIFIER`: review of the CF-0308 design

Discussion only, read against Sail `15fd1888c` (Codex's root, branch
`work/spark-declarative-pipelines`) and Spark `617618396`. Requested in
CF-0308; the CF-0310 correction (builtin-before-session function precedence)
is folded in below. No source assignment and no authority change follow from
this document. It continues the §15 survey in
`BATCH-PROVIDER-MIGRATION-REVIEW.md` in a separate file because that file is
past the practical length limit.

## 1. The design under review

CF-0308 proposes, for scalar `IDENTIFIER` arguments only:

- an optional boolean collector on `PlanResolverState`, deliberately outside
  `PlanResolverStateConfig`, so that the per-call `ConfigScope` restoration
  cannot erase a child's marker;
- an RAII scope that starts observation around the argument's analysis and
  restores the parent's collector on exit;
- a nested suspend scope that discards the observations made inside builtin
  `typeof`'s argument while keeping any `false` already recorded by the parent;
- `FunctionContextInput` carrying `Option<&mut bool>` so a synchronous builder
  can mark it; `ScalarFunctionBuilder::non_foldable` marks `false` before its
  builder turns the provenance into a literal, and keeps the existing eager
  `require_foldable` rejection;
- registered UDFs and higher-order functions marking the collector rather
  than rejecting before the argument's own semantic errors;
- the existing post-DataFusion check (`require_constant_expression`) still
  catching volatile expressions that lowering did not erase;
- activation only around scalar identifier argument analysis: analyze the
  whole expression, then reject a recorded `false` before evaluation.

## 2. Spark's rule, pinned to source

`IdentifierResolution.evalIdentifierExpr` (`IdentifierResolution.scala:25–49`)
runs `prepareForEval` (only `RuntimeReplaceable` nodes become their
replacement, `EvalHelper.scala:27–31`), trims aliases, then checks in order:
`foldable`, `dataType == StringType`, `eval() != null`. `ResolveIdentifierClause`
calls it only once `p.identifierExpr.resolved && p.childrenResolved`
(`ResolveIdentifierClause.scala:59–70`), so every semantic error inside the
argument precedes the foldability check. Foldability is a property of the
resolved node, not of its evaluation cost:

| Node                                                                                 | `foldable`                                                                      | Source                                                         |
| ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| default                                                                              | `false`                                                                         | `Expression.scala:104`                                         |
| unary / binary / ternary / quaternary / variadic                                     | all children foldable                                                           | `Expression.scala:567,598,718,873,971,1076,1203`               |
| `Literal`                                                                            | `true`                                                                          | `literals.scala:422`                                           |
| `Unevaluable` (final)                                                                | `false`                                                                         | `Expression.scala:436`                                         |
| `Nondeterministic` (final)                                                           | `false`                                                                         | `Expression.scala:532`                                         |
| `CurrentCatalog`, `CurrentDatabase`, `CurrentUser`, `CurrentTimeZone`                | `false`: `LeafExpression with Unevaluable`                                      | `misc.scala:244,223,389`, `datetimeExpressions.scala:117`      |
| `CurrentDate`, `CurrentTimestampLike` (`current_timestamp`, `now`), `LocalTimestamp` | `true`                                                                          | `datetimeExpressions.scala:153,190,259`                        |
| `TypeOf`                                                                             | `true`, `contextIndependentFoldable = true`; `eval` reads `child.dataType` only | `misc.scala:367`                                               |
| `RaiseError`                                                                         | `false` (overridden)                                                            | `misc.scala:85`                                                |
| `AssertTrue`                                                                         | `RuntimeReplaceable` → `If(…, RaiseError)` → `false`                            | `misc.scala:188`                                               |
| `Generator` (`explode` …)                                                            | `false`                                                                         | `generators.scala:58`                                          |
| `ScalaUDF`, `HigherOrderFunction`                                                    | not overridden → `false`                                                        | `ScalaUDF.scala`, `higherOrderFunctions.scala` (no `foldable`) |
| `ScalarSubquery`                                                                     | `false`: `with Unevaluable`                                                     | `subquery.scala:418`                                           |
| `MonotonicallyIncreasingID`, `SparkPartitionID`, `Uuid`, `Rand`, `InputFileName`     | `false`: `Nondeterministic`                                                     | their files                                                    |
| `VariableReference`                                                                  | `canFold`                                                                       | `VariableReference.scala:47`                                   |

Two consequences matter for the design:

1. `CurrentCatalog` and its siblings are replaced by literals only in the
   optimizer's `FinishAnalysis` batch (`ReplaceCurrentLike`,
   `Optimizer.scala:345–346`), after `ResolveIdentifierClause`
   (`Analyzer.scala:627`). Spark therefore sees them as non-foldable leaves at
   identifier time. Sail lowers them to literals in the builder
   (`function/scalar/misc.rs:65–92`, `datetime.rs:544–548`), which is the
   erasure the design addresses.
2. Precedence differs by node kind. A table identifier whose expression stays
   unresolved is reported as `NOT_A_CONSTANT_STRING.NOT_CONSTANT` by
   `CheckAnalysis.scala:456–459`; a scalar `ExpressionWithUnresolvedIdentifier`
   falls through to the catch-all and reports the underlying error (the
   comment at `CheckAnalysis.scala:464–471` says so explicitly for
   `IDENTIFIER(<unresolved-col>)`). CF-0308's premise, deferred rejection for
   scalar and unchanged eager policy for tables, is Spark's shape. The
   existing Sail test
   `scalar_identifier_preserves_column_and_subquery_analysis_precedence`
   (`identifier/tests.rs:161–201`) already pins the scalar side for columns
   and subqueries.

## 3. What the collector replaces in Sail today

`PlanResolverStateConfig.require_foldable` (`state.rs:57–66`) has four
consumers:

- `ScalarFunctionBuilder::non_foldable` rejects eagerly before invoking the
  builder (`function/common.rs:46–55`);
- `resolve_expression_function` rejects registered and higher-order functions
  by name before resolving their arguments (`expression/function.rs:82–91`);
- every `resolve_expression` call runs `require_constant_expression` on its
  result, so a non-constant child rejects before its parent is built
  (`expression/mod.rs:376–378`);
- the division builders skip the literal-zero fast path so that the type check
  can precede evaluation (`function/scalar/math.rs:376–384`, also `:444`,
  `:633`).

The table path sets the flag (`identifier.rs:24–26`); the scalar path does not
(`expression/misc.rs:92–104`), so today it relies solely on the final
`require_constant_expression` (`constant.rs:78–115`), which recognises
`Volatile` or async scalar functions, columns, subqueries, aggregates and
anything else outside its allow-list, but cannot see a literal a builder
produced. `ConfigScope` snapshots and restores the whole config on every
function, UDF, window, lateral and pivot entry (`state.rs:661–684`, entries
listed in §3 of the grep: `expression/function.rs:37`, `udf.rs:45,130`,
`window.rs:175,290`, …), which is why a collector inside the config would be
erased at each child's exit. Placing it outside the config is forced by that
model, not a free choice.

## 4. Findings

### F1. The premise holds

Confirmed as in §2: deferred rejection is Spark's scalar behaviour, eager
mapping to `NOT_CONSTANT` is Spark's table behaviour. No change requested on
the activation boundary.

### F2. `require_foldable` carries two roles, and the scalar path can only drop one

The scalar path must leave `require_foldable` false, otherwise the per-child
check at `mod.rs:376` and the eager builder rejection would defeat the
deferral. But the division builders read the same flag as a lowering policy
(`math.rs:378`): with the flag false, `1 div 0` under ANSI raises
`DivideByZero` during resolution, before the identifier's type check runs.
Spark resolves `IntegralDivide(1, 0)` as foldable `bigint`, so
`SELECT IDENTIFIER(1 div 0)` is `WRONG_TYPE` with `dataType = bigint`
(`IdentifierResolution.scala:32–37`), and only
`IDENTIFIER(CAST(1 div 0 AS STRING))` reaches evaluation and `DIVIDE_BY_ZERO`.
The table path gets this right because it sets the flag; the scalar path
gets it wrong today and the collector design leaves it wrong, because the
collector is not what the division builders read.

Recommendation: split the roles. A read-only `constant_context: bool` in the
config (set by both identifier paths and by `resolve_catalog_name`) carries
the lowering policy and survives `ConfigScope` restoration trivially, since
restoration only ever reinstates the enclosing value. The rejection mechanism
(eager flag for tables, collector for scalars) is then independent of it. The
probe in §6 checks the claim on `15fd1888c`.

### F3. The collector only helps where a builder marks; the marking set is the real oracle

Spark's foldability is per resolved node (§2), so the unit of parity is Sail's
builder table, not the DataFusion volatility of the lowered expression.
Against `15fd1888c`:

| Sail entry                                                                                                                                                           | Lowers to                                                        | Spark         | Under the collector design                                                                                                                                                                                                                                                                                                                                                                                      |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- | ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `current_catalog`, `current_database`, `current_schema`, `current_user`, `session_user`, `user` (`misc.rs:204–216,315,323`), `current_timezone` (`datetime.rs:1431`) | literal, wrapped `non_foldable`                                  | `false`       | marked ✓                                                                                                                                                                                                                                                                                                                                                                                                        |
| `typeof` (`misc.rs:322`, body `:109–123`)                                                                                                                            | literal of the argument's type                                   | `true` always | suspend scope ✓ (see F4)                                                                                                                                                                                                                                                                                                                                                                                        |
| `assert_true` (`misc.rs:199`, body `:31–63`)                                                                                                                         | `CASE WHEN NOT x THEN raise_error(..) ELSE NULL`                 | `false`       | **not marked**; `RaiseError` is `Immutable` (`raise_error.rs:29`), so the final check passes it. Observed on `15fd1888c` (§6): the bare call fails the type check as `WRONG_TYPE` because its type is null, where Spark says `NOT_CONSTANT` (`RaiseError.foldable` is checked before its `NullType`); `CAST(raise_error('x') AS STRING)` passes the type check and `LiteralEvaluator` raises the user's message |
| `raise_error` (`misc.rs:312`)                                                                                                                                        | `Immutable` UDF                                                  | `false`       | **not marked**, same two outcomes                                                                                                                                                                                                                                                                                                                                                                               |
| generators (`generator.rs:91`)                                                                                                                                       | wrapped `non_foldable`                                           | `false`       | marked ✓ once `non_foldable` marks                                                                                                                                                                                                                                                                                                                                                                              |
| higher-order functions (`lambda.rs:84–97` name list, `array_sort` included)                                                                                          | `Immutable` DataFusion functions                                 | `false`       | marked at `function.rs:82` ✓ (CF-0308 says so). Today a lambda's parameter columns already fail the final check (§6), so the name mark matters for the lambda-less forms such as `array_sort(array('b', 'a'))`, which lower to an `Immutable` call and are accepted                                                                                                                                             |
| registered Python UDFs                                                                                                                                               | `Immutable` when declared deterministic (`pyspark_udf.rs:57–58`) | `false`       | marked at `function.rs:82` ✓ (CF-0308 says so)                                                                                                                                                                                                                                                                                                                                                                  |
| `input_file_name` (`misc.rs:306`, body `:94–99`)                                                                                                                     | `coalesce(input_file_name(), '')`                                | `false`       | rejected by the final check today (§6) ✓                                                                                                                                                                                                                                                                                                                                                                        |
| `version` (`misc.rs:325`)                                                                                                                                            | `Immutable` UDF (`version.rs:28`)                                | `true`        | must **not** be marked; evaluation goes through `LiteralEvaluator`                                                                                                                                                                                                                                                                                                                                              |
| `current_timestamp`, `now`, `localtimestamp` (`datetime.rs:1427,1501,1470`)                                                                                          | `TimestampNow`, `Stable` (`timestamp_now.rs:20`)                 | `true`        | passes the final check ✓ (the check rejects only `Volatile`)                                                                                                                                                                                                                                                                                                                                                    |
| `current_date`, `curdate`, `current_time` (`datetime.rs:1423–1425`)                                                                                                  | DataFusion `Stable`                                              | `true`        | passes ✓                                                                                                                                                                                                                                                                                                                                                                                                        |
| `uuid`, `rand`, `random`, `monotonically_increasing_id`, `spark_partition_id`                                                                                        | `Volatile`                                                       | `false`       | final check ✓                                                                                                                                                                                                                                                                                                                                                                                                   |

So two builtins (`assert_true`, `raise_error`) need the mark today and are
not on CF-0308's list, and one (`version`) must stay unmarked although it is
a Sail UDF. Aggregate and window builders pass `require_foldable: false`
to their argument contexts (`aggregate.rs:1134`, `window.rs:906`); under the
collector that is harmless only because `Expr::AggregateFunction` and
`Expr::WindowFunction` are rejected by the final check regardless of their
arguments' marks, the same argument that makes marks inside a subquery moot.
Both facts deserve a sentence in the Rustdoc so the next reader does not
"fix" them.

Rather than extending the list by hand, the marking could be made structural:
every `F::custom` or `F::udf` entry whose Catalyst node is `Unevaluable`,
`Nondeterministic` or overrides `foldable = false` gets the wrapper, and the
table in this section is the checklist. I can produce that table for every
name in the scalar function tables as a separate read-only component if
useful.

### F4. The `typeof` suspend scope: save/restore, follow the selected function, still analyze

Three checks on the described semantics:

- "restores any already-false parent" is right only as _restore the value at
  entry_. If the parent was `true` at entry and `rand()` inside the argument
  set `false`, exit must set `true` again (`typeof(rand())` is foldable); if
  the parent was already `false`, exit keeps `false`
  (`concat(rand(), typeof(1))` is not foldable). Save-on-entry, restore-on-exit
  covers both; "ignore false from inside" phrased as a one-way merge would not.
- The scope must key on the function Sail _selected_, as CF-0310 states. The
  table path already does this (`function.rs:92–97` checks
  `get_function("typeof").is_none()`), and the CF-0310 oracle shows Spark's
  default `PATH` resolves the builtin first while Sail prefers the registered
  function. That precedence gap is separate; the design is right not to
  resolve it here, and the unique-name witness is the right test fixture.
- The scope suspends _observation_, not _analysis_. `typeof(missing)` must
  still raise `UNRESOLVED_COLUMN` on the scalar path (Spark: `TypeOf` is
  unresolved, catch-all) and `NOT_CONSTANT` on the table path
  (`CheckAnalysis.scala:456`). CF-0308's "analyze the whole expression first"
  already implies this; a fixture pins it.

One wording correction for the existing comment at `function.rs:98–100`:
`TypeOf` is not a `RuntimeReplaceable`; `prepareForEval` never touches it. It
is foldable by override and evaluates to `child.dataType.catalogString`
without evaluating the child (`misc.scala:367–369`). Same outcome, different
mechanism, and the difference matters for anyone extending `prepareForEval`
parity later.

### F5. `Option<&mut bool>` reintroduces the §11 default-loses-policy shape

`FunctionContextInput` is constructed at seven production sites
(`aggregate.rs:1133`, `window.rs:905`, `expression/attribute.rs:123`,
`expression/function.rs:191,251`, `expression/window.rs:158`,
`query/join.rs:297`) plus tests. An `Option<&mut bool>` lets any site pass
`None` and silently stop observing, which is the shape §11 found in the
binder's pre-match wildcard. Prefer a non-optional reference to a small
observation type (`&mut FoldabilityObservation` with `mark_non_foldable()`
and an `Inactive` variant for ordinary resolution) so every construction site
names its choice and `non_foldable` cannot forget the inactive case. The
borrow itself is sound: the builder is synchronous and the reference must be
taken after argument resolution, immediately around the builder call, since
`resolve_expression_function` is `async` and `state` is reborrowed across its
awaits. That is an ordering constraint, not a flaw.

### F6. An alternative with no collector: keep the provenance in the tree

The problem is literally "lowering erases provenance". A marker that travels
with the expression needs none of the state machinery:

- in a constant context, `non_foldable` builders wrap their result in an
  internal identity UDF (`NonFoldable`, `Volatile` signature, return type
  equal to its argument's type);
- the existing final check rejects it with no new code
  (`constant.rs:101–103` already rejects `Volatile`);
- `typeof` needs no suspend scope: `type_of` reads `get_type` of its argument
  (`misc.rs:115`), which the wrapper preserves, and discards the argument;
- registered UDFs and higher-order functions wrap at `function.rs:82`
  instead of rejecting, which gives the deferred precedence for free;
- nested scopes, config restoration and the `&mut` plumbing disappear,
  because the marker is in the value the check inspects, and a nested
  `IDENTIFIER` inside an argument simply evaluates its own tree.

Costs: one internal UDF type, the read-only `constant_context` flag from F2
(the wrapper must not be emitted in ordinary resolution; the existing
`constant_mode_does_not_leak_into_ordinary_resolution` test at
`constant/tests.rs:214` is the right control), and the table path moving from
eager to deferred rejection, which Spark permits because the table path maps
every unresolved outcome to `NOT_CONSTANT` anyway (`identifier.rs:30–41`
already does this for columns). The wrapper never reaches execution: constant
contexts evaluate only after the check passes. I would weigh this against the
collector before selecting; it is smaller than CF-0308's own "no new
concurrency/lifetime framework" bound, and it removes the two scopes that F4
has to argue about.

### F7. Oracle rows worth adding before selection

Spark expectations from §2, scalar path unless stated:

| Expression                                                  | Spark 4.2.1                                                                                                     |
| ----------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `1 div 0` (ANSI)                                            | `WRONG_TYPE`, `dataType = bigint`                                                                               |
| `CAST(1 div 0 AS STRING)` (ANSI)                            | `DIVIDE_BY_ZERO` at evaluation                                                                                  |
| `raise_error('x')`                                          | `NOT_CONSTANT`                                                                                                  |
| `assert_true(false)`                                        | `NOT_CONSTANT`                                                                                                  |
| `typeof(current_catalog())`                                 | `"string"`, then the column lookup                                                                              |
| `typeof(missing)`                                           | `UNRESOLVED_COLUMN` (scalar), `NOT_CONSTANT` (table)                                                            |
| `concat(rand(), missing)`                                   | `UNRESOLVED_COLUMN` (scalar), `NOT_CONSTANT` (table)                                                            |
| `concat(typeof(rand()), rand())`                            | `NOT_CONSTANT`                                                                                                  |
| `element_at(transform(array('a'), x -> x), 1)`              | `NOT_CONSTANT`                                                                                                  |
| `array_join(array_sort(array('b', 'a')), '')`               | `NOT_CONSTANT` (`ArraySort` is a higher-order function even without a lambda, `higherOrderFunctions.scala:392`) |
| `date_format(current_date(), 'yyyy')`                       | foldable, evaluated at analysis time                                                                            |
| `input_file_name()`, `current_timezone()`, `session_user()` | `NOT_CONSTANT`                                                                                                  |
| `version()`                                                 | foldable; the result is not a valid identifier, parse error                                                     |

### F8. CF-0310, acknowledged

Spark's default function path prefers `system.builtin`, so a registered
`typeof` does not shadow the builtin there while Sail selects the registered
function. The design following Sail's selection, and retaining the mismatch
as a separate function-precedence gap with a uniquely named witness, is the
right boundary for this unit.

## 5. Summary of requests

1. Split `require_foldable` into a read-only lowering-policy flag and the
   rejection mechanism, so the scalar path keeps the division precedence (F2).
2. Mark `assert_true` and `raise_error`; keep `version` unmarked; document
   why aggregate/window/subquery arguments' marks are moot (F3).
3. Make the `typeof` scope save/restore and pin `typeof(missing)` on both
   paths; fix the "runtime replacement" comment (F4).
4. Replace `Option<&mut bool>` with a non-optional observation type (F5).
5. Weigh the in-tree marker against the collector before selecting (F6).

## 6. Probe of the scalar path on `15fd1888c`

An uncommitted probe test in my own worktree and target
(`/Users/alexy/src/sail-sdp-fable-config` detached on `15fd1888c`, reverted
afterwards) sent `SELECT IDENTIFIER(<expr>) FROM input` through
`resolve_named_plan` with `PlanConfig::default()` (ANSI on), the view `input`
being `SELECT 9 AS foo`, and printed the first line of each outcome. Where the
identifier evaluated, the printed `UNRESOLVED_COLUMN` names the string it
evaluated to.

| Expression                                       | Sail `15fd1888c`, scalar path            | Spark 4.2.1 (§2)                                        |
| ------------------------------------------------ | ---------------------------------------- | ------------------------------------------------------- |
| `current_catalog()`                              | evaluated to `catalog`                   | `NOT_CONSTANT`                                          |
| `current_timezone()`                             | evaluated to `UTC`                       | `NOT_CONSTANT`                                          |
| `typeof(current_catalog())`                      | evaluated to `string`                    | `string` ✓                                              |
| `typeof(rand())`                                 | evaluated to `double`                    | `double` ✓                                              |
| `1 div 0`                                        | `error in Arrow: Divide by zero error`   | `WRONG_TYPE` (`bigint`)                                 |
| `CAST(1 div 0 AS STRING)`                        | `error in Arrow: Divide by zero error`   | `DIVIDE_BY_ZERO` at evaluation (class ✓, stage differs) |
| `raise_error('boom')`                            | `NOT_A_CONSTANT_STRING.WRONG_TYPE`       | `NOT_CONSTANT`                                          |
| `assert_true(false)`                             | `NOT_A_CONSTANT_STRING.WRONG_TYPE`       | `NOT_CONSTANT`                                          |
| `element_at(transform(array('foo'), x -> x), 1)` | `NOT_CONSTANT` (lambda parameter column) | `NOT_CONSTANT` ✓                                        |
| `date_format(current_date(), 'yyyy')`            | evaluated to `2026`                      | foldable ✓                                              |
| `input_file_name()`                              | `NOT_CONSTANT`                           | `NOT_CONSTANT` ✓                                        |
| `uuid()`                                         | `NOT_CONSTANT`                           | `NOT_CONSTANT` ✓                                        |
| `concat(current_catalog(), missing)`             | `UNRESOLVED_COLUMN` `missing`            | `UNRESOLVED_COLUMN` ✓                                   |
| `concat(rand(), missing)`                        | `UNRESOLVED_COLUMN` `missing`            | `UNRESOLVED_COLUMN` ✓                                   |
| `concat(missing, rand())`                        | `UNRESOLVED_COLUMN` `missing`            | `UNRESOLVED_COLUMN` ✓                                   |

The first two rows are the erasure CF-0308 addresses; the `1 div 0` row is
F2 observed, not inferred; the `raise_error`/`assert_true` rows are F3
observed; the last three rows show the deferred precedence the design must
keep. Test and command: `fable_probe_scalar_identifier_today` appended to
`crates/sail-plan/src/resolver/identifier/tests.rs`, run as
`cargo test -p sail-plan --lib --locked resolver::identifier::tests::fable_probe -- --nocapture`
with `CARGO_INCREMENTAL=0 RUSTUP_TOOLCHAIN=1.98.1`; `1 passed`, probe log in
my scratchpad, not committed anywhere.

## 7. Review of the F6 candidate `25534e8ea` (CF-0314)

Read-only, against the diff on parent `15fd1888c`. The marker lives beside
`LiteralEvaluator` in `sail-common-datafusion` (`literal/non_foldable.rs`):
a private `ScalarUDFImpl` with `Signature::any(1, Volatile)`, identity
`return_type`/`return_field_from_args`, and an `invoke_with_args` that
refuses to run; only `mark_non_foldable(Expr)` is exported. The resolver gains
a read-only `constant_context` config flag set on all three constant paths
(`identifier.rs`, the new `resolve_scalar_identifier_expr`, `constant.rs`),
`non_foldable` builders wrap their result when it is set, and registered or
higher-order functions are wrapped after their selected branch resolved its
arguments and lambdas (`function.rs:142–296`). No collector, scope or mutable
context remains.

Checks:

- **Dead branches are Spark-faithful.** `ConditionalExpression.foldable` is
  `children.forall(_.foldable)` (`Expression.scala:566–567`), inherited by
  `If` and `CaseWhen` (`conditionalExpressions.scala:44–45,166–169`), so
  `CASE WHEN false THEN current_catalog() ELSE 'foo' END` is `NOT_CONSTANT` in
  Spark and `CASE WHEN false THEN typeof(current_catalog()) ELSE 'foo' END`
  is foldable; the candidate's fixtures assert exactly that.
- **Which check is load-bearing.** On both identifier paths
  `require_constant_expression` runs on the logical tree before
  `ExprSimplifier::simplify` (`identifier.rs`), so a marker in a dead branch is
  found there, before simplification could drop the branch. The new
  `LiteralEvaluator::evaluate` pre-check protects only callers that simplify
  first and never ran the logical check; `resolve_catalog_name` is such a
  caller but never emits the marker, because its eager flag rejects before any
  builder runs. The pre-check is defense in depth, not the mechanism; its
  comment should say so rather than "necessary".
- **Subqueries.** `constant_context` is inherited by a subquery resolved
  inside a scalar argument, so a marker can sit inside the subquery plan;
  the final check rejects the subquery node itself and the marker never
  reaches execution. A correlated subquery against the outer schema behaves
  the same.
- **typeof.** `type_of` reads `get_type` of the marked argument (identity
  return type, field metadata preserved) and returns a literal, dropping the
  marker; on the table path the relaxed `require_foldable` inside `typeof`
  lets the wrapped argument through and the eager per-child check stays off
  for it. Both match Spark's `TypeOf`.
- **Not executable, not serialized.** The marker is produced only under
  `constant_context` and consumed or discarded before any plan is returned;
  `invoke_with_args` refusing is the right backstop for a future caller that
  forgets the check.

No change requested. Still open, as CF-0314 states: F2 (`constant_context`
is now the right flag for the division builders to read; the scalar path still
raises `DivideByZero` for `IDENTIFIER(1 div 0)`), and the five names from
`FOLDABILITY-FUNCTION-TABLE.md` (`assert_true`, `raise_error`, `json_tuple`,
`window`, `window_time`).

## 8. `SET CATALOG` oracle: two policies, observed on Spark 4.2.1 (CF-0316)

CF-0316 said catalog-level oracles were being prepared for `typeof(raise_error(..))`
and friends. Spark's source predicts the shape, and a local run confirms it.
Scripts, raw output and the environment line are under
`evidence/set-catalog-oracle/` (local Spark 4.2.1 from the pinned venv, JDK 17,
`local[1]`, ANSI on unless stated).

**Why there are two policies.** `SET CATALOG expression` (`SqlBaseParser.g4:234`)
becomes `SetCatalogCommand(expr)`; `ResolveSetCatalogCommand` turns a bare
attribute into a literal and leaves every other expression for "later rules"
(`ResolveSetCatalogCommand.scala:28–41`). The command's `run` calls
`IdentifierResolution.evalIdentifierExpr` on `catalogNameExpr`
(`SetCatalogCommand.scala:44–55`), and `run` happens through
`QueryExecution.runCommand` → `qe.executedPlan` → `optimizedPlan`
(`QueryExecution.scala`), with the planner taking the `RunnableCommand` from
the optimized plan (`SparkStrategies.scala:909`). So a bare `SET CATALOG`
expression is checked for determinism at analysis (`CheckAnalysis.scala:1032`,
`INVALID_NON_DETERMINISTIC_EXPRESSIONS`), then optimized (`ReplaceCurrentLike`,
`ReplaceExpressions`, `ConstantFolding`, `SimplifyConditionals`), and only then
evaluated under the identifier rule. `SET CATALOG IDENTIFIER(expr)` instead
evaluates `expr` during analysis in `ResolveIdentifierClause`, before any
optimizer rule. The same expression therefore gets different answers.

| Expression                                                        | bare `SET CATALOG e`                                                  | `SET CATALOG IDENTIFIER(e)`                  |
| ----------------------------------------------------------------- | --------------------------------------------------------------------- | -------------------------------------------- |
| `current_catalog()`                                               | accepted (replaced by the optimizer)                                  | `NOT_CONSTANT`                               |
| `concat(current_catalog(), '')`                                   | accepted                                                              | `NOT_CONSTANT`                               |
| `CASE WHEN false THEN current_catalog() ELSE 'spark_catalog' END` | accepted (branch simplified away)                                     | `NOT_CONSTANT`                               |
| `current_user()`                                                  | accepted, then `CATALOG_NOT_FOUND` `alexy`                            | (not probed; same rule as `current_catalog`) |
| `current_timezone()`                                              | accepted, then `PARSE_SYNTAX_ERROR` on the zone string                | `NOT_CONSTANT`                               |
| `typeof(current_catalog())`                                       | `CATALOG_NOT_FOUND` `string`                                          | `CATALOG_NOT_FOUND` `string`                 |
| `typeof(raise_error('x'))`                                        | `CATALOG_NOT_FOUND` `void`                                            | (foldable by the same rule)                  |
| `typeof(rand())`                                                  | `INVALID_NON_DETERMINISTIC_EXPRESSIONS`                               | `CATALOG_NOT_FOUND` `double`                 |
| `rand()`, `uuid()`                                                | `INVALID_NON_DETERMINISTIC_EXPRESSIONS`                               | `NOT_CONSTANT`                               |
| `raise_error('x')`, `CAST(raise_error('x') AS STRING)`            | `NOT_CONSTANT`                                                        | `NOT_CONSTANT`                               |
| `assert_true(true)`                                               | `WRONG_TYPE`, expression rendered `NULL` (`void`)                     | `NOT_CONSTANT`                               |
| `assert_true(false)`                                              | `NOT_CONSTANT`, rendered as the `raise_error` replacement             | `NOT_CONSTANT`                               |
| `1 DIV 0` (ANSI)                                                  | `DIVIDE_BY_ZERO` (folded by the optimizer)                            | `WRONG_TYPE` `bigint`                        |
| `CAST(1 DIV 0 AS STRING)` (ANSI)                                  | `DIVIDE_BY_ZERO`                                                      | `DIVIDE_BY_ZERO`                             |
| `1 DIV 0` (non-ANSI)                                              | `WRONG_TYPE`, rendered `CAST(NULL AS BIGINT)`                         | `WRONG_TYPE`, rendered unfolded              |
| `CAST(1 DIV 0 AS STRING)` (non-ANSI)                              | `NOT_A_CONSTANT_STRING.NULL`                                          | `NOT_A_CONSTANT_STRING.NULL`                 |
| `explode(array('a'))`                                             | `UNSUPPORTED_GENERATOR.OUTSIDE_SELECT`                                | `NOT_CONSTANT`                               |
| `(SELECT 'spark_catalog')`                                        | `INTERNAL_ERROR` unresolved operator                                  | `INTERNAL_ERROR` unresolved operator         |
| `element_at(transform(array('spark_catalog'), x -> x), 1)`        | `NOT_CONSTANT`                                                        | (same rule)                                  |
| `date_format(current_date(), 'yyyy')`, `version()`                | accepted, then `PARSE_SYNTAX_ERROR` on `2026` / `4.2`                 | (same evaluation, same parse failure)        |
| `NULL`, `1`, `CAST(NULL AS STRING)`, `'a.b'`                      | `WRONG_TYPE` `void` / `WRONG_TYPE` `int` / `NULL` / `MULTI_PART_NAME` | identical                                    |

**What this means for Sail's catalog path.** `resolve_catalog_name`
(`constant.rs:22–74`) unwraps `IdentifierClause` and applies one policy to
both forms, the eager `require_foldable` one. Against the bare form the
existing test `catalog_validation_preserves_foldability_type_and_null_priority`
(`constant/tests.rs:122–170`) pins `NOT_CONSTANT` for the seven current-like
functions, for `typeof(rand())` and for `explode(..)`, and `WRONG_TYPE` for
`1 / 0`, `1 DIV 0`, `1 % 0`; Spark accepts the first seven, reports
`INVALID_NON_DETERMINISTIC_EXPRESSIONS` and `UNSUPPORTED_GENERATOR` for the
next two, and `DIVIDE_BY_ZERO` under ANSI for the divisions. Those rows match
Spark's `IDENTIFIER(..)` form instead (except `1 DIV 0`, which is `WRONG_TYPE`
there and so matches). The CF-0316 caution is therefore right in a stronger
form: the catalog path is not "the identifier rule with a determinism check",
it is "determinism check, then optimizer, then the identifier rule", and only
its `IDENTIFIER(..)` form is the identifier rule. For F3 that gives the
answers directly: `typeof(raise_error(..))` and `typeof(assert_true(..))` are
foldable in both forms (`void`), and `assert_true(true)` bare is `WRONG_TYPE`
because the optimizer simplifies it to `NULL` first.

Recommendation, discussion only: keep `IdentifierClause` on the catalog path
under the identifier policy (eager flag, constant context, marker), and give
the bare form its own sequence: resolve without the eager flag and without the
marker, reject any non-`Immutable` function as `INVALID_NON_DETERMINISTIC_EXPRESSIONS`
(Spark's `deterministic`, so `Stable` clock functions are allowed and
`typeof(rand())` is rejected as a whole), simplify, then apply the type, null
and parse checks on the folded literal. The division row then falls out of
simplification under the session's ANSI mode, which is what the probe shows.

### 8.1 Registered functions on the bare path, and units A/B (CF-0318)

CF-0318 asked that the bare-path recommendation also qualify deterministic
registered UDFs and higher-order functions, which Spark keeps non-foldable
even after optimizer replacement, and that actual nondeterminism be kept
ahead of `typeof`'s discard. Probe 4 (`probe4_registered_udf.py`, appended to
`evidence/set-catalog-oracle/output.txt`) registers a deterministic and a
nondeterministic Python identity UDF:

| Expression                                       | bare `SET CATALOG e`                                       | `SET CATALOG IDENTIFIER(e)`  |
| ------------------------------------------------ | ---------------------------------------------------------- | ---------------------------- |
| `det_identity('spark_catalog')`                  | `INTERNAL_ERROR` "Invalid PythonUDF … requires attributes" | `NOT_CONSTANT`               |
| `concat(det_identity('spark_'), 'catalog')`      | same `INTERNAL_ERROR`                                      | `NOT_CONSTANT`               |
| `typeof(det_identity('x'))`                      | `CATALOG_NOT_FOUND` `string`                               | `CATALOG_NOT_FOUND` `string` |
| `nondet_identity('spark_catalog')`               | `INVALID_NON_DETERMINISTIC_EXPRESSIONS`                    | `NOT_CONSTANT`               |
| `typeof(nondet_identity('x'))`                   | `INVALID_NON_DETERMINISTIC_EXPRESSIONS`                    | `CATALOG_NOT_FOUND` `string` |
| `SELECT IDENTIFIER(det_identity('x')) …`         | `NOT_CONSTANT` (scalar identifier)                         |                              |
| `SELECT IDENTIFIER(typeof(det_identity('x'))) …` | accepted, column `string` (scalar identifier)              |                              |

So the refinement is right and the §8 recommendation is amended: on the bare
path, registered UDFs and higher-order functions keep the marker (Spark's
`ScalaUDF`/`PythonUDF` and `HigherOrderFunction` are non-foldable by class, and
Spark's own bare outcome for a Python UDF is an internal error, so
`NOT_CONSTANT` is the only sensible Sail target); only the current-like
builtins lose it, because the optimizer replaces them before `run`. The
determinism check runs on the whole expression before any folding, so
`typeof(nondet(..))` is rejected while `typeof(det(..))` folds to its type
string in both forms, and both are consistent with the scalar identifier
path.

Units advanced by CF-0318, read against their diffs: A `25534e8ea` is the
candidate reviewed in §7, unchanged. B `3ffb497d3` makes the three
zero-divisor predicates read `constant_context` instead of `require_foldable`
(`function/scalar/math.rs`, three one-line changes) and adds
`identifier/arithmetic_tests.rs`; this is exactly the F2 split, and the
scalar path now reaches Spark's `WRONG_TYPE` for `IDENTIFIER(1 div 0)`. The
bare catalog form still pins `WRONG_TYPE` where Spark folds to
`DIVIDE_BY_ZERO` under ANSI, which belongs to the catalog phase Codex named
as next, not to B. No change requested on either unit.

## 9. The `SET CATALOG` AST and result path, and SDP's directive namespace (CF-0320)

Read only, Sail `3ffb497d3`, Spark `617618396`. CF-0320 asked for the wrapped
`SET CATALOG` AST/result path and the sequential SDP directive behaviour.

### 9.1 Three policies, not two

| Where the expression runs                  | Spark path                                                                                                                                                                                                                                                        | Policy                                                                                                                                                      |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| public SQL, bare `SET CATALOG e`           | `SparkSqlParser.visitSetCatalog` → `SetCatalogCommand(e)`; `ResolveSetCatalogCommand` (extended resolution rule, `BaseSessionStateBuilder.scala:243`) turns a bare `UnresolvedAttribute` into a quoted literal and keeps anything else; `run` after the optimizer | determinism check (`CheckAnalysis.scala:1032`) → optimizer (current-like replaced, foldables folded, conditionals simplified) → identifier rule at run (§8) |
| any `IDENTIFIER(e)` in expression position | `AstBuilder.scala:3727` builds `ExpressionWithUnresolvedIdentifier(e, UnresolvedAttribute(_))`; `ResolveIdentifierClause` evaluates `e` during analysis and yields `UnresolvedAttribute(parts)`, which `ResolveSetCatalogCommand` then quotes into the literal    | identifier rule at analysis, before `CheckAnalysis`, no optimizer                                                                                           |
| SDP file directive, bare `SET CATALOG e`   | `SqlGraphRegistrationContext.processSqlQuery` matches the parsed `SetCatalogCommand`; `SetCatalogCommandHandler` runs `analyzer.executeAndCheck` and then `analyzed.getCatalogName()` (`SqlGraphRegistrationContext.scala:541–562`), no optimizer                 | `CheckAnalysis` (whole-tree determinism, generator placement) → identifier rule on the analyzed, unoptimized expression                                     |

Consequences for the SDP directive form, from source (not probed; the SDP
harness is Codex's, and the one-line probe is `SET CATALOG current_catalog()`
in a pipeline file expecting registration failure):

- `current_catalog()`, `current_user()`, `current_timezone()` are
  `NOT_CONSTANT` in a directive, unlike the public bare form, because
  `ReplaceCurrentLike` never runs; the error is wrapped as
  `SqlGraphElementRegistrationException("Failed to resolve catalog expression: …")`
  (`:554–558`), the same prefix Sail's `PreparationFailure::Analysis` uses
  (`pipelines/sql.rs:96–98`).
- `rand()` and `typeof(rand())` are `INVALID_NON_DETERMINISTIC_EXPRESSIONS`
  (CheckAnalysis before `getCatalogName`), `explode(..)` is
  `UNSUPPORTED_GENERATOR.OUTSIDE_SELECT`, `1 DIV 0` is `WRONG_TYPE` `bigint`,
  `typeof(current_catalog())` sets the catalog to `string` with no existence
  check at registration (`context.setCurrentCatalog` stores a string), and a
  non-`AnalysisException` from evaluation (ANSI `DIVIDE_BY_ZERO` from
  `CAST(1 DIV 0 AS STRING)`) escapes the handler unwrapped, which is Sail's
  `PreparationFailure::Evaluation` split.
- So Sail's present eager identifier policy in `resolve_catalog_name` is the
  right policy for SDP directives except for the two CheckAnalysis-first
  classes above; the public bare form is the only one that needs the
  optimizer-first sequence. The pinned catalog test rows (§8) are therefore
  correct for directives and wrong for the public bare command; the test
  should say which form it pins.

### 9.2 Sail's path

`Statement::SetCatalog` always becomes `SetCurrentCatalogExpression`
(`sail-sql-analyzer/statement.rs:209–216`), `USE CATALOG name` becomes the
literal `SetCurrentCatalog` (`:217–226`). The command resolver calls
`resolve_catalog_name` then `resolve_catalog_command` (`command/mod.rs:234–236`);
`resolve_catalog_name` quotes a bare attribute, unwraps `IdentifierClause`,
and runs the identifier policy on the rest (`constant.rs:22–74`). The result
schema is `display.empty()` with no rows (`sail-catalog/command.rs:245–248,290–293`),
which matches `SetCatalogCommand.output = Seq.empty`. For the three-policy
split the AST already carries what is needed: `IdentifierClause` is visible at
`constant.rs:29`, so the unwrap is the one place where the IDENTIFIER form and
the bare form are conflated, and the SDP preparation callback
(`pipelines/mod.rs:199–214`) can keep calling the directive policy while the
public command gets the optimizer-first one.

### 9.3 Sequential directives and the virtual namespace

Spark's registration context is created per `DefineSqlGraphElements`
request, that is per file (`PipelinesHandler.scala:229`), and its state is
two options (`SqlGraphRegistrationContext.scala:44–59`): `SET CATALOG` sets the
catalog and clears the database (`:552,560`), `USE db` sets the database,
`USE cat.db` sets both (`:524–539`), and every later dataset in the file
captures `(currentCatalog, currentDatabase)` into its `QueryContext`. Sail's
commit does the same (`pipelines/sql.rs:290–306`). Two facts settle CF-0320's
namespace question:

- Directive expressions never see the virtual namespace in Spark either.
  The handler analyzes against `spark.sessionState.analyzer`, the directive's
  only namespace-dependent inputs would be column references, which fail in
  both engines, and the current-like functions that would need the namespace
  are rejected as non-foldable before evaluation. Resolving every catalog
  expression in `prepare` with a callback that sees only the expression is
  therefore faithful; no overlay is needed for directive evaluation, and no
  shared-session mutation or graph lock across awaits is implied.
- `current_catalog()`/`current_database()` inside flow queries are replaced
  by the optimizer when the flow runs, under whatever the session's catalog
  manager holds then. The only place SDP sets the catalog manager from a
  `QueryContext` is around `command.run` in `DatasetManager.materializeView`
  (`DatasetManager.scala:221–235`); flow execution is not wrapped. That is the
  "computed reads follow the live session" behaviour Codex's namespace oracle
  already confirmed (CF-0301), and it is a separate integration unit from the
  catalog policy, as CF-0320 says.

One remaining difference by reading: `USE IDENTIFIER(..)` in a pipeline file
parses to `PlanWithUnresolvedIdentifier` (`SparkSqlParser.scala:500–501`), which
the SDP dispatch does not match, so Spark reports "Unsupported plan
PlanWithUnresolvedIdentifier parsed from SQL query" (`:168–172`); Sail's
`UseCatalog`/`UseDatabase` take a plain name, so the form is a parse error
there. Low priority.

### 9.4 The explicit policy type `f0a232af2` (CF-0322)

Read against its diff on `3ffb497d3`. `ConstantContext { Ordinary, Identifier }`
(`function/constant_context.rs`) replaces the bool, with two decisions as
exhaustive matches, `retain_function_foldability` (read by `non_foldable` and
by the UDF/HOF wrap at `function.rs`) and `defer_arithmetic_evaluation` (read
by the three zero-divisor predicates). Behaviour unchanged by construction;
Codex reports identical case outcomes. No change requested.

One note for the next unit, which adds the public-bare and directive
policies: the two decisions are not enough once a public-bare variant exists,
because that policy treats the two things `retain_function_foldability`
currently bundles differently. Current-like builtins must _not_ be marked
there (the optimizer would have replaced them, §8), while registered UDFs,
higher-order functions, generators and `raise_error` must still be marked
(§8.1). So the variant needs the decision split into "replace current-like"
and "retain intrinsic non-foldability", each an exhaustive match, and
`defer_arithmetic_evaluation` is `false` for public-bare (Spark folds and
raises `DIVIDE_BY_ZERO` under ANSI, which the ordinary literal-zero path
already produces). The directive variant keeps the `Identifier` decisions
and adds the two CheckAnalysis-first classes (§9.1). Keeping each as a
`match` on the enum, as this unit does, is what makes the third variant
unable to inherit a wrong default.
