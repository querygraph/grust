# Shared catalog expressions and pipeline namespaces

This design follows the announced Astra checkpoint. General expression analysis,
identifier interpretation and catalog selection stay in Sail. LakeCat remains one
catalog adapter. The shared resolver prerequisite is implemented in 564738318;
Statement spans and pipeline diagnostics are implemented in 1f281cdfd and
010469d3c. Catalog-expression activation remains pending. The evidence below is a required
failing registration baseline, not a passing SDP verdict.

## Evidence that determines the boundary

The [recorded probe package](evidence/catalog-expression-design/provenance.json)
contains 22 Spark 4.2.1 parser/analyzer expression cases and 13 registration cases
per engine. The same retained assertions pass 13/13 on Spark and 2/13 on the
unchanged Sail engine; eleven Sail failures remain. Registration probes never
start a graph run. They cannot qualify publication or full Scala fixtures.

Pinned Spark sources establish the evaluation path:

- `SparkSqlParser.visitSetCatalog` parses an expression.
- `ResolveSetCatalogCommand` turns a whole unresolved attribute into quoted name
  parts. Attributes nested in other expressions must resolve normally.
- `SetCatalogCommand.getCatalogName` uses `IdentifierResolution.evalIdentifierExpr`:
  require foldability, then STRING type, then a non-null value, parse that value
  as identifier parts, and require exactly one part.
- The pipeline handler analyzes with the session and extracts the name without
  selecting a real catalog provider. It clears the file-local database afterward.

Important observed cases:

- CONCAT and CAST of literal names succeed. Both original invalid grid instances,
  `CONCAT(foo, '1')` and `test.cat`, fail with the registration error and
  `Failed to resolve catalog expression`.
- `'test.cat'` is a multipart name and fails; the string containing the backquoted
  name and the backquoted identifier both yield the single name `test.cat`.
- Numeric and untyped NULL fail the type check. A typed null STRING fails the
  null check. An empty string fails identifier parsing, while the string containing
  an empty backquoted identifier parses to one empty name. Do not add an unrelated
  blanket empty-name check to this shared extraction step.
- `current_catalog()` and a higher-order TRANSFORM expression are not foldable
  here. A volatile RAND expression is rejected. CAST of CURRENT_TIMESTAMP reaches
  identifier parsing and fails on the generated unquoted timestamp; Spark's
  evaluation preparation must not be approximated by a simple immutable-only rule.
- Catalog folding uses **session SQL configuration**, ignoring both file-local
  SET values and graph-default SQL configuration. Opposite ANSI settings prove
  this in both directions. Flow configuration still belongs to the file/graph.
- A malformed ANSI cast propagates `CAST_INVALID_INPUT` directly. Analysis and
  typed-null errors get the pipeline registration wrapper. Wrapping every folding
  failure as a registration analysis error would be wrong.
- Unqualified persistent output after SET CATALOG without USE fails during Spark
  registration with an AssertionError. Explicit namespaces and private views
  succeed. Sail must reject the unset-namespace case without introducing a panic.

## Typed SQL and ordinary catalog commands

Change only the SET CATALOG AST operand to the existing expression AST and lower
it through `from_ast_expression`. Add a sibling typed command,
`SetCurrentCatalogExpression { catalog: spec::Expr }`. Preserve the existing
`SetCurrentCatalog { catalog: Identifier }` command for the direct Catalog API and
existing USE CATALOG behavior. This avoids turning a direct catalog-name string
into SQL text or changing its serialized shape.

Add one shared `PlanResolver::resolve_catalog_name` entry point. It returns a
name; it does not mutate session defaults or verify provider existence. Ordinary
command resolution uses it and then emits the existing `CatalogCommand`.
CatalogManager remains responsible for ordinary session selection and configured
provider checks. Pipeline registration calls the same name resolver and applies
the result only to its file context. Unknown provider names must not trigger
eager REST calls merely because a pipeline file selects a name.

For a whole unresolved attribute, preserve its name-part boundaries by quoting
the parts before identifier parsing. A whole IDENTIFIER clause evaluates its
operand as identifier text, rather than looking up a column in an empty schema.
All other expressions use normal expression resolution with an empty input
schema. Do not treat nested attributes such as CONCAT(foo, '1') as literal names.
Keep Sail's existing Unicode identifier policy; the
[recorded identifier boundary](evidence/2d54d5a568f8dbac68d2b9ac8519380a25782fd3/gate.json)
is not a new Spark parity claim.

## Preserve foldability before lowering loses it

Reusing LiteralEvaluator alone is insufficient: it evaluates a physical expression
against one empty row and does not enforce Spark foldability. Sail also lowers
current_catalog/current_database/current_user into literals, so inspecting only
the final DataFusion expression loses necessary information.

Use a request-local constant-expression mode in PlanResolverState, defaulting to
off. Keep it out of shared PlanConfig and mutable session configuration. Propagate
it through FunctionContextInput. Seven existing constructors need explicit mode
values; preserve their ordinary behavior. Keep the existing callable scalar
function representation rather than replacing the function registry API.

Add a small scalar-builder annotation/wrapper for non-foldable functions. Mark
context functions whose folding information would otherwise disappear, using
Spark controls and the actual function implementation to audit aliases. Reuse
existing higher-order-function classification and reject generators and registered
or inline UDF execution in the constant mode. Default-off mode must preserve
ordinary SQL function construction and existing IDENTIFIER parameter behavior.
This is function metadata and resolution policy, not a pipeline function evaluator
or a list of allowed CONCAT-like function names.

At expression dispatch, constant mode must reject relation-bearing subqueries,
window/aggregate input and similar non-scalar constructs before descending into
query resolution. This avoids catalog reads and query jobs during preparation.
Reject an unresolved UDF before return-type inference can invoke a worker. Add
canary tests proving that non-foldable and registered-function bodies are never
called. Resolve ordinary arguments in the established order so unresolved nested
columns retain analysis priority.

After those checks, use the existing DataFusion expression coercion/simplification
machinery and LiteralEvaluator for scalar computation. Check the resolved tree
before physical evaluation for remaining row-dependent or volatile nodes. Account
for supported stable time expressions through query-scoped simplification, rather
than invoking TimestampNow directly. Do not change LiteralEvaluator's general
contract for unrelated callers. Validate string type before nullness, then parse
the resulting identifier with Sail's shared parser and enforce one part.

Resolution, foldability and identifier-validation failures are analysis failures.
Scalar execution failures retain the existing execution-error transport; do not
convert an ANSI cast failure into a typed-null or pipeline analysis error.

## Prepare outside the graph lock; commit against current state

PipelineGraph uses a blocking mutex. Do not hold its guard across asynchronous
resolution, replace it wholesale with a Tokio mutex, or install temporary session
catalog/configuration changes to evaluate an expression.

The source and ANSI probes make preparation independent of graph definitions:
catalog folding uses a captured **session** PlanConfig, not graph defaults or
file-local SET overrides. This removes the need to clone a graph outside the
lock and later reconcile or replace it.

1. Look up the graph and briefly check its idle state, retaining existing missing
   graph/busy-graph validation priority.
2. Parse the complete input once with SqlSource. Lower statements in order and
   resolve catalog expressions asynchronously using the shared resolver. Retain
   each prepared statement or its typed failure. Do not return a later lowering
   or folding failure before earlier statements have been registered.
3. Recheck graph membership before commit so a graph dropped during preparation
   is not updated through an orphaned handle. Lock and recheck idle state.
4. Clone the **current** definition into the existing file-local draft, replay
   prepared results and registration in source order, and commit only if all
   succeed. Reset file-local namespace/configuration to graph defaults as today.

No definition snapshot is replaced after an await. Concurrent output/flow
registrations completed during preparation remain in the current draft. Runs
active at commit still reject registration. A completed run follows the existing
idle/lifecycle rules; this work does not invent a new execution lease or revision
system. Add deterministic barrier tests for concurrent additions, drop and active
run, and for an earlier registration failure preceding a later folding failure.

Preparation may retain a failure and stop preparing later statements. It must
still replay earlier registrations before reporting that failure. Pure folding
must not invoke UDFs, mutate catalogs or launch query jobs even for a statement
whose earlier predecessor will ultimately fail registration.

## Source origins, errors and unset namespaces

Extend the existing root parser with a spanned statement entry point and preserve
the current AST-only parser API by dropping spans in its adapter. SqlSource then
exposes original statement intervals without another lexer or regex splitter.
The current repository has one production call to create_parser, in SqlSource.
Do not change TreeText or add spans to every AST node.

Statement origin differs from persisted-view query text: Spark strips leading
trivia but retains trailing whitespace/comments up to the separator. Keep those
boundaries distinct. Use checked UTF-8 byte slicing and count preceding newlines
for the one-based source line. Preserve Unicode and semicolons inside lexer
string/comment tokens.

Build the pipeline analysis wrapper through existing StructuredSparkError, with
the exact parameter keys `message`, `offendingQuery`, and `codeLocation`.
The captured outer class is AnalysisException with SQL state 42000. The malformed
ANSI cast instead retains NumberFormatException, CAST_INVALID_INPUT and 22018.
The retained assertions pin the surrounding newlines and line numbers, including
line two after SET. Catalog analysis failures get the required prefix; execution
failures bypass that wrapper. Preserve other SQL registration error priority.
Do not introduce a new global exception framework for this feature.

Add the unset-database check to graph name qualification for implicit persistent
outputs and flow names. Keep explicit namespace/catalog names and private names
working. Retain the existing empty-string representation during this focused
change; do not refactor every graph and flow field to Option. Existing scoped
read resolution must continue rejecting an unqualified external read with an
unset flow database, without falling back to the session's default namespace.

## Human-reviewable implementation units

1. Shared constant-resolution mode, non-foldability annotations and catalog-name
   resolver, with direct resolver tests and no new dependency. Implemented as
   [564738318](evidence/5647383189ce71dd97d62fbe97b7013b7bd6e038/gate.json).
2. Shared statement spans/origins and structured SQL registration diagnostics,
   with Unicode, trivia, separators, path and line-number assertions. Implemented
   in [1f281cdfd](evidence/1f281cdfddf8dcc1594f9b5e4e5802dbaef7e167/gate.json)
   and [010469d3c](evidence/010469d3c079285d637752c4cde012ef9bad0b75/gate.json).
3. Asynchronous preparation plus locked, file-atomic commit, including the new
   typed expression command and its resolver paths before the parser produces
   it. Preserve config capture, error ordering, source text and concurrency.
4. Activate the SET CATALOG expression AST/lowering and ordinary SQL wiring once
   pipeline preparation can consume it. Preserve direct Catalog API semantics;
   update only affected goldens and run complete library/golden tests.
5. Unset-namespace guard and batch acceptance across ordinary SQL, pipeline files,
   both original invalid-expression grid instances, file reset/private views,
   two memory catalogs and the configured LakeCat REST adapter where applicable.

Use the retained required-assertions script unchanged as a regression baseline;
extend it with the batch publication and concurrency checks above. Registration
success alone is insufficient. Preserve all failures and original source grids.
Only extend LakeCat if a provider operation/capability gap is actually exposed;
do not implement shared expression or namespace semantics in it.

These units are ready for implementation without another architecture selection.
The order above keeps existing pipeline SET CATALOG working at each commit.
Exact metadata/control coverage remains subject to their gates. General SQL
variable/command-parameter support is not silently added through this path.
The original Scala suites, full batch acceptance, ORC, failure/event behavior,
REST views, streaming and CDC remain separate required work.
