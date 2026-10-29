# Shared SQL query source preservation

Ordinary SQL and pipeline persisted views must retain the original query text
through Sail's shared analyzer. This is a general Sail SQL feature. LakeCat and
other catalog providers receive the resulting `spec::ViewDefinition`; they do
not reconstruct SQL. No new dependency on Grust or LakeCat is required.

## Observed contract

The [original failing reproduction](evidence/view-source-design-boundary/provenance.json)
retains SqlPipelineSuite:617's exact assertion: `SELECT * FROM range(1, 4)`.
The current analyzer stores reconstructed token text with inserted spaces and a
trailing space. `TreeText` intentionally promises parseable reconstruction and
whitespace for concatenation; retain that contract and the AST-only analyzer API.

[Five Spark 4.2.1 JVM parser controls](evidence/d51777745ec6e3de6d4b261c50237e09ae73fa70/spark-source-reference.json)
establish that persisted-view `originalText` starts at the first query token and
ends at the last query token. Internal whitespace, comments, newlines, hints and
quoted text survive exactly. Surrounding comments and the statement separator do
not belong to the stored query. These are parser controls, not Sail parity tests.
The pinned Spark source uses `SparkSqlParser.visitCreateView` and
`SparkParserUtils.source`, which slice the parser rule's original input interval.

Chumsky 0.13.0 string input advances its cursor by `char::len_utf8()`. Sail
d51777745 pins actual lexer spans for both a multibyte string literal and an
unquoted Unicode identifier, and corrects the old character-offset documentation.
That prerequisite changes no production parsing behavior. Its
[detached gate](evidence/d51777745ec6e3de6d4b261c50237e09ae73fa70/gate.json)
covers six parser library tests, formatting and strict Clippy.

## Selected integration

Add a small source context in `sail-sql-analyzer`, borrowing the complete SQL
string and retaining its existing lexer tokens and spans. Parse through those
same tokens. Source-aware statement lowering receives that context alongside
the typed AST; source-aware pipeline lowering delegates ordinary commands to
the same shared implementation. Keep AST-only entry points for generated ASTs
and callers that intentionally have no original source.

For the current CREATE VIEW grammar, the existing AS keyword span identifies
the start of the query suffix. Find the first and last non-trivia tokens before
the statement's next semicolon token, and slice the original input using their
byte boundaries. Lexer string/comment tokens distinguish embedded semicolons
from statement delimiters; hint punctuation remains part of the query. Avoid
regex extraction, string splitting, or searching for the last textual AS.
Use checked slicing and report inconsistent source spans through `SqlError`.
Do not silently substitute reconstructed SQL when original source was supplied.

Keep one tokenization per SQL input and use ordered spans to locate each query
suffix, so a multi-view pipeline file does not require repeated lexing of the
remaining file. Preserve the current parse-all, then lower/register-in-order
behavior: lowering all declarations ahead of registration could change which
error wins. Preserve file-atomic registration and file-local configuration reset.

Ordinary Spark Connect SQL and SQL command callbacks must use source-aware
lowering when they possess original input. Propagate the context through any
recursive statement lowering that can contain a view. Leave generated SQL and
AST-only call sites explicit and review them individually. Existing query plans,
catalog interfaces and `ViewDefinition` fields suffice; no protocol change,
query evaluator, AST-wide span derive or `TreeText` behavior change is needed.

## Review units and acceptance

1. Lexer span documentation and Unicode regression: committed as d51777745.
2. Shared source context and source-aware analyzer entry points, with tests for
   ordinary persisted views, comments, Unicode, embedded delimiters, CTEs, hints,
   multiple statements, exact typed plan equivalence and the AST-only fallback.
3. Wire ordinary SQL and pipeline callers to the shared API. Restore the retained
   exact pipeline view assertion unchanged, test multiple views in one file,
   and verify failure atomicity and file reset alongside existing batch tests.

The latter two units remain unimplemented. Do not mark SqlPipelineSuite:617
fully qualified until its remaining assertions and relevant execution boundary
are covered. REST catalog view operations are a separate provider capability
gap; correct source text does not establish that LakeCat can persist a view.

Foldable SET CATALOG expressions, unset pipeline namespaces and registration
error wrapping remain the separate architecture checkpoint in the
[SQL catalog handoff](SQL-CATALOG-DESIGN-HANDOFF.md). Notify the operator before
starting that design phase, as requested. The source-context implementation above
can proceed without selecting an expression evaluator or streaming architecture.
