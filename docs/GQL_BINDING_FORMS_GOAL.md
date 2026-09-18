# Grust Binding Forms Goal — `reduce`, comprehensions and general quantifiers

Status: **COMPLETE — B0–B5 merged to `main` and released in Tadpole 0.21.0
(2026-09-18).** This file is a historical execution record; branch names, test
counts and checkpoints below describe the work as it happened.

## Why

Grust's Cypher has no way to fold a list. `reduce(s = 0, x IN xs | s + x)` is
rejected by the parser with "expected ')' to close a function call, found Pipe",
and list comprehensions `[x IN xs WHERE p | e]` are absent too. The quantifiers
`any`/`all`/`none`/`single` do exist, but only in one hard-coded shape whose own
error message is the grammar: `item IN variable.property WHERE item = value`.

The feature catalog in `crates/grust-cypher/src/gql.rs` tracks 74 features as 69
Supported, 5 Rejected, 0 Planned, 0 Future. None of the five rejections concern
expressions — they are all write-identity safety rules. Binding forms are not
refused by any design principle; they were never built.

**Do not schedule this as a performance fix.** It was found while profiling the
algorithms benchmark, where an ordinary Cypher full-path query is about ninety
times direct execution. Measurement attributed roughly 83% of that to reading the
clock for the deadline on every work charge, and only about 4% to the row
expansion that a fold would remove. A probe measured the same aggregate at 21,721
ms with `UNWIND` and 20,804 ms with no expansion at all. Implement this because
the language is incomplete, not because it is slow.

## Scope

In scope, in this order:

1. `reduce(acc = seed, item IN list | body)`.
2. List comprehension `[item IN list WHERE predicate | projection]`, with either
   clause optional.
3. Generalising the existing `any`/`all`/`none`/`single` to arbitrary lists and
   arbitrary predicates, replacing the hard-coded shape without changing the
   results of queries that already work today.

Out of scope: pattern comprehensions, `FOREACH`, and any binding form over
pattern matches rather than list values.

## The architectural problem to solve first

There are two expression representations, and a binding form has to satisfy
both. This is the real cost of the goal, and the reason it is a unit rather
than a task.

| Layer | Files | Present handling |
| --- | --- | --- |
| General AST | `ast.rs` (`Expr`, line ~354), `parser.rs`, `semantics.rs`, `read.rs` | 24 `Expr::` sites in semantics, 43 in read |
| Classified RETURN catalog | `returning.rs`, `projection.rs`, `eval_rows.rs` | 16 `CypherReturnScalarProjectionKind` variants, ~12 `evaluate_scalar_*_return_expression` functions, 48 `CypherReturnElement::` match sites |
| Read pushdown | `pushdown.rs` | 71 `Expr::` sites |

`Expr::` never appears in `where_clause.rs`, `projection.rs`, `returning.rs` or
`eval_rows.rs`: the RETURN path does not evaluate the general expression tree. It
classifies each projection into a fixed catalog of shapes, each with a bespoke
parse function that slices strings — see `parse_return_list_predicate_projection`
in `returning.rs`, which locates `IN` with `find_unquoted_keyword` on the raw
text between parentheses.

**The decision this goal must make, before writing a line of feature code:**
either give the RETURN path a scoped evaluator over `Expr`, or add a seventeenth
bespoke shape. Adding another shape is how the catalog reached sixteen. A fold
whose body is a general expression (`s + toInteger(x)`) cannot be expressed as a
shape without effectively reimplementing expression evaluation inside it, so the
recommendation is the former: **unify first, then add the forms.**

## B0 decision — shared scoped expression evaluation (2026-09-18)

Use the existing `Expr` evaluator with an immutable lexical scope layered over
row bindings. All recursive evaluation, including property access, element
functions and borrowed list indexing, must consult that same scope. Each binding
form supplies a child scope; it never modifies the candidate row.

Review correction: the general read executor already evaluates RETURN, WHERE
and WITH using `Expr`. The classified RETURN catalog belongs to the writable
query pipeline. Its existing sixteen kinds remain compatibility adapters during
migration; there will be no Reduce-specific catalog kind or body parser.
`returning.rs` will parse general expression targets using `parser::parse_expression`;
`projection.rs` and `eval_rows.rs` will bridge materialized write bindings to the
shared evaluator. `where_clause.rs` need not acquire an independent evaluator.
The existing restricted quantifier adapter will be replaced by the general AST
path, preserving its established results in regression tests.

B1 introduces and verifies the scope machinery before grammar changes. Later
milestones must integrate scope-aware semantic validation, aggregate traversal,
resource accounting and conservative pushdown rejection, including nested forms.
A catalog count or source-site count above is a snapshot, not an acceptance test.

Performance figures above are historical observations from the proposal, not
independently reproduced evidence or a prediction for this implementation.
No performance improvement is an acceptance criterion.

## Implementation checkpoint — 2026-09-18

- B1: `read/expression_scope.rs` adds borrowed lexical frames. Recursive
  expression evaluation, property lookup, element functions and list indexing
  share their resolution. The row-facing evaluator remains a compatibility entry.
- Validation: `cargo test -p grust-cypher --lib --tests --quiet` passes before
  and after the refactor (826 unit tests passed after, one ignored; integration
  targets also pass with one existing ignored test). The new test checks nested
  frame lookup, map/list access and isolation from the candidate row.
- B2/B3 and the read portion of B4: added AST/parser forms, immutable scope
  evaluation, semantic shadowing/unbound-name checks, fold seed/body type checks,
  and per-element work charging. Shared list iteration avoids collecting another
  full vector before charging. Every public read pushdown planner declines forms
  anywhere in read clauses, including projections and nested subqueries.
- Nine integration tests cover folds inside aggregates, WITH/WHERE, nested forms,
  empty and NULL lists, NULL elements, optional comprehension clauses, predicate
  three-valued logic, malformed syntax, scope/type errors, fold budget exhaustion
  and pushdown rejection. Full Cypher tests pass with the existing ignored tests.
  `cargo clippy -p grust-cypher --all-targets -- -D warnings` also passes.
- B4 write bridge: `returning/expression.rs` parses any RETURN projection that
  contains a binding form with `parser::parse_expression`, validates it with the
  read scope rules, and stores `CypherReturnTarget::Expression`.
  `read/write_expression.rs` materializes only the free variables of that
  expression into a row and calls the shared scoped evaluator.
  `parse_return_list_predicate_projection`, `CypherReturnListPredicate` and the
  `ListPredicate` kind are deleted; the catalog still has sixteen kinds, one of
  which is now the general `Expression`. The old restricted-quantifier tests keep
  their result expectations. Two error expectations changed deliberately: a
  wrong item variable is now an unbound-name error, and a computed predicate
  evaluates instead of being rejected.
- Compatibility wart, recorded rather than hidden: the old write shape compared
  with exact `Value` equality (`1 = 1.0` is false) and returned NULL for a NULL
  needle even over an empty list, which differs from read three-valued
  semantics. `ExpressionScope::WriteRow` keeps that contract only for the
  formerly admitted shape (`item IN variable.property WHERE item = rhs` with
  `rhs` over the same variable); every other write predicate uses ordinary
  semantics. Removing the divergence is a behaviour change for a person to decide.
- Resources: `read/binding_forms_resource_tests.rs` proves cancellation from
  another thread and deadline expiry stop all three forms mid-evaluation on the
  live `ExecutionContext` path (work admitted is nonzero and below the total),
  and that the thread-local bounded budget's deadline does the same.
- Pushdown: `binding_forms_decline_pushdown_and_match_reference` in the Turso
  oracle checks every planner declines eight queries (RETURN, aggregate, WHERE,
  WITH, segment) and the real store returns reference-identical rows.
- B5: `list-reduce`, `list-comprehension`, `list-quantifier-predicate` in
  `GqlFeature::ALL` (72 supported of 77); ten corpus cases including shadowing,
  unbound-name and malformed-syntax rejections; profile statement, `CLAUDE.md`,
  book manuscript and `CHANGELOG.md` updated.
- Not done: live-service backends were not run (binding forms never reach a
  backend planner, and only the embedded Turso store was exercised); the book
  was not rebuilt; nothing was published.

## Architecture invariants

1. **No new bespoke shape.** If the implementation ends with a
   `CypherReturnScalarProjectionKind::Reduce` that parses its own body by string
   slicing, the goal has failed even if the tests pass.
2. **One evaluator, one scope rule.** A bound item variable is resolved the same
   way in RETURN, WHERE and WITH. Today `Expr::Variable` resolves against the row
   (`read.rs`, `row.get(v)`); binding forms push a scope over that row rather
   than mutating it.
3. **Shadowing is an error, not a silent win.** Binding an item name that already
   exists in the row is rejected in `semantics.rs`, not resolved by precedence.
4. **Every element charges.** A fold over a list is unbounded user work: charge
   one work unit per element against the caller's `ExecutionContext`, inside the
   loop. A budget that is exhausted mid-fold must fail mid-fold. Note that work
   charges now sample the deadline every 1024 units, so a long fold observes
   expiry within the interval, and an explicit `checkpoint` remains exact.
5. **Pushdown declines rather than guesses.** `pushdown.rs` returns `None` for
   any expression containing a binding form until a dialect lowering exists.
   Reference fallback is correct; a partially lowered fold is not.
6. **Existing quantifier results do not change.** Item 3 is a generalisation:
   every query that works today returns what it returns today, proven by keeping
   the existing cases in the corpus untouched.

## Milestones

### B0 — Decide and record the representation

Write the decision in this document before coding: unified scoped evaluator, or
justified exception. Include which of `where_clause.rs`, `projection.rs`,
`returning.rs`, `eval_rows.rs` gain access to `Expr`, and what happens to the
catalog's existing sixteen kinds. Nothing below starts until this is written.

### B1 — Scope machinery, no new syntax

Introduce the scope that binding forms will push, and make `Expr::Variable`
resolution consult it. No grammar change, no user-visible behaviour change. The
whole suite passes unchanged; this milestone is pure refactor.

### B2 — `reduce`

`Expr::Reduce { accumulator, seed, item, list, body }` in `ast.rs`; parsing in
`parser.rs` (the lexer already emits `Token::Pipe`, `lexer.rs:229`); scope and
shadowing validation in `semantics.rs`; evaluation with per-element charging in
the unified evaluator; `None` in `pushdown.rs`.

Semantics to pin down in tests, not in prose: empty list yields the seed; a
`NULL` list yields `NULL`; a `NULL` element is passed to the body, which decides;
type errors surface as errors rather than `NULL`; nested `reduce` binds inner
names first; `reduce` inside an aggregate (`sum(reduce(...))`) works, since that
is the shape this goal exists to express.

### B3 — List comprehension

`[item IN list WHERE predicate | projection]`, both clauses optional, reusing
B1's scope and B2's charging. `[x IN xs]` is `xs`; `[x IN xs WHERE p]` filters;
`[x IN xs | e]` maps.

### B4 — Generalise the quantifiers

Replace `parse_return_list_predicate_projection` and
`CypherReturnListPredicate` with the general path. Delete the string slicing.
The existing corpus cases stay byte-identical in their expectations.

### B5 — Catalog, corpus, docs

Add features to `GqlFeature::ALL` in `gql.rs` — note
`support_counts_total_matches_catalog` asserts the total matches `ALL.len()`, so
registration is mandatory, not optional. Add cases to
`crates/grust-cypher/tests/gql/portable_read.json` (26 cases today, each with
`id`, `feature`, `requirement`, `statement`, `expectation`, `notes`). Update the
book's Cypher surface chapter and `CHANGELOG.md`; `AGENTS.md` requires both for a
public surface change, and a release additionally requires the book rebuild, a
release blog post and crates.io publication in dependency order.

## Testing obligations

- Parser: each form, plus malformed variants that must produce a syntax error
  naming the form rather than "expected ')'".
- Semantics: shadowing rejected; unbound item names rejected; type mismatch
  between seed and body surfaced.
- Evaluation: the semantics listed in B2, for all three forms.
- Resources: budget exhausted mid-fold fails mid-fold; cancellation during a
  long fold is observed; a deadline expiring during a fold is observed within
  the sampling interval.
- Pushdown: a query containing a binding form falls back to the reference and
  returns reference-identical rows, with a case in
  `crates/grust-turso/tests/read_pushdown_oracle.rs`.
- Conformance: new corpus cases, and the pre-existing quantifier cases unchanged
  through B4.

## Sizing

One to two weeks. B1 is the risk: it touches the boundary between two
representations that have grown apart, and its blast radius is every RETURN
projection. B2–B4 are each one to two days once B1 lands. If B1 is deferred and
the forms are bolted onto the catalog instead, the estimate drops to about two
days and the architecture gets worse; that trade should be made explicitly by a
person, not discovered in review.

## What this goal will not deliver

Measurable benchmark improvement. The algorithms benchmark's Cypher participant
will get a query it can express more naturally. Its runtime effect requires
measurement after implementation; the earlier probe does not establish it. Every other reason to want this is a language-completeness reason, and those
are the ones worth arguing.
