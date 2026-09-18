# Grust Binding Forms Goal — `reduce`, comprehensions and general quantifiers

Status: **PROPOSED, not started.** Written 2026-09-18 on host `grust` for
continuation on Mac. No code has been written for this goal; the only related
work in flight is the deadline-sampling change on `work/algorithms-performance`,
which is unrelated except that it is how the gap below was discovered.

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
will get a query it can express more naturally and will run about 4% faster for
it. Every other reason to want this is a language-completeness reason, and those
are the ones worth arguing.
