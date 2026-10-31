# Registration error fidelity

This is the user-notified design phase after parser commit14eb7766f.
The full Spark4.2.1 SDP goal remains unchanged. Spark pin is
617618396087429b5627a86ce933bb0f5d6645cb; Sail starts at14eb7766f.
No public Table/Sink, streaming, CDC or new execution surface is enabled here.

## Existing machinery and observed gaps

Sail already has a structured registration_error builder, original SQL spans,
UTF8-aware source slicing, line/file parameters, asynchronous preparation,
short graph-lock phases and draft publication on success. Reuse these. A new
wrapper system or extra source representation is unnecessary for this phase.

The twelve-case actual DefineSqlGraphElements probe on Spark and the parent
Sail confirms that offendingQuery and codeLocation already match for all
registration-wrapper cases tested, including Unicode, embedded semicolons,
comments and a second statement. Runtime cast failure remains a raw typed
CAST_INVALID_INPUT on both engines. The remaining observations are:

| Producer | Spark contract | Current gap / decision |
| --- | --- | --- |
| Parser rejection | Raw ParseException and native condition/params; no filename wrapper | Already qualified; preserve |
| Unsupported ordinary CTAS | Registration wrapper, message names CreateTableAsSelect | Generic Sail unsupported wording; separate unit |
| Unsupported SELECT | Registration wrapper, message names Project in observed fixtures | Generic normalization wording; separate unit, do not invent names for unreviewed shapes |
| Invalid partition transform | Registration wrapper, exact transform text | Generic identity-only wording; separate unit with shared SQL formatting |
| Multipart identity partition | Registration wrapper, Multipart partition identifier not allowed. | Generic identity-only wording; separate unit |
| Multipart named Flow | Raw AnalysisException, MULTIPART_FLOW_NAME_NOT_SUPPORTED,0A000,flowName | Incorrectly wrapped as registration failure; first unit |
| Disallowed INSERT Flow forms | Registration wrapper, distinct policy messages and fixed precedence | One combined message; separate unit |
| Catalog expression analysis | Registration wrapper enclosing the underlying analysis message | Outer fields match; full inner SQLSTATE/origin formatting remains a general SQL obligation |
| Catalog expression evaluation | Raw underlying typed runtime exception | Observed typed cast case matches; preserve |

Reference: SqlGraphRegistrationContext.scala:63–95, processSqlQuery:132–172,
CreateFlowHandler:398–507, SetCatalogCommandHandler:543–560,
PartitionHelper:568–595, and splitSqlFileIntoQueries:637–689.
Original obligations include SqlPipelineSuite.scala:311,386,525,580,599.
Their fixtures and assertions remain authoritative; a probe is extra evidence,
not permission to substitute weaker inputs or erase backend differences.

## First review unit: raw multipart Flow error

Use a small shared Sail error constructor for the condition, class, state,
message template and single flowName parameter. SQL passes the unquoted name;
the protocol passes its original raw string, including identifier quoting. It has no new external
dependencies. Reuse it in SQL normalization and the existing protocol name
rejection, preserving both APIs' existing admission predicates.

For SQL, check the parsed name before inspecting the INSERT policy or lowering
its query, matching Spark's CreateFlowHandler ordering. Parsing itself continues
to accept multipart Flow names: the original parser tests must remain valid.
The separate direct-execution SQL guard still reports its own unsupported
CREATE FLOW condition. This is a registration-policy check, not a grammar ban.

Preserve typed errors from register_statement through PreparedSql.commit rather
than converting them to a string and wrapping them again. Existing untyped
registration failures still use the established source wrapper. Catalog-analysis
wrapping remains explicit in its own producer; evaluation and parse failures
remain raw. Do not turn every AnalysisException into either category globally.

The protocol guard retains its existing implicit-flow name==target exception.
Diagnostic spelling preserves case. SQL uses parsed unquoted parts; protocol
uses the original supplied name string (PipelinesHandler.scala:350–353). Normal
graph-key handling stays unchanged. A quoted dot in a
single component remains a valid single-part name.

Tests must cover the original SQL580 input, exact condition/state/parameter and
message, Unicode/escaped/case-preserved names, name-error precedence before bad
Flow INSERT forms, the protocol route and its implicit-flow exception, no graph
publication on failed Sail registration, and ordinary/direct/parser paths.
Use the existing native tests, a new original-fixture public port on both engines,
unchanged-test production controls and the qualified300+67 regression harness.
No original JVM-on-Sail or complete suite verdict follows from this increment.

## Subsequent units and boundaries

Unsupported-node wording, partition diagnostics and individual Flow policy errors
must be separate commits with exact producer-owned messages. Avoid stringifying
an error enum and then attempting to recover its fields or remove prefixes.
Preserve source spans and lock/ownership ordering; do not add catalog work while
holding a graph guard. A formatter gap belongs in Sail's general formatter when
reusable, with LakeCat only one catalog profile.

The raw multipart constructor does not qualify arbitrary identifier normalization,
full inner catalog diagnostics, all origin fields, complete reference classpath
profiles, full-reset cleanup or streaming/Iggy/CDC. Those remain explicit work.

## Boundary correction: four-part names and unclassified errors

Source review and a twelve-case two-API endpoint probe establish two additional
constraints. Protocol error parameters preserve raw flow_name, unlike SQL's
TableIdentifier.unquotedString; quoted dots/backticks retain each API spelling.
IdentifierHelper.toTableIdentifier rejects four-or-more-part identifiers BEFORE
the standalone-flow policy, even for implicit protocol flows. It throws
java.lang.UnsupportedOperationException without condition, SQLSTATE or message
parameters. Apply this arity rule to Flow names and targets in reference order;
implicit three-part names remain allowed in protocol.

Keep the current structured error String representation and document an empty
condition as absent, as empty SQLSTATE already is. Display unclassified errors
without an invented [] prefix, and omit absent errorClass/messageParameters/
sqlState metadata. Classified errors with empty parameters still carry {}.
Tests must cover both codec paths and the public client's None values. These
transport details qualify the observed Flow boundary, with no new effect path.

## First unit qualified

Commitc864386cc implements the raw Flow identifier unit:279 native tests,
formatting/strict Clippy, fresh300+67,21 public cases on each engine,12 boundary
vectors and4 Unicode vectors per engine, classified direct-execution4 and three
unchanged-test controls all have their intended passing verdicts. The original
Spark SqlPipelineSuite passes43 runtime cases, including580; this is reference
evidence. See [the packet](evidence/registration-error-boundaries/README.md).
Existing coverage580 is strengthened without changing116reviewed87partial399
unmapped. Unsupported-node, partition and individual INSERT-policy producers
remain subsequent implementation units in this design. No full-goal or new
streaming/catalog/effect authority follows.

## Table-as-select producer qualified

Commit18604c01a separately improves original SqlPipelineSuite525. The shared
Sail table-as-select node renders CreateTableAsSelect for Create/IfNotExists and
ReplaceTableAsSelect for Replace/OrReplace, confined to pipeline normalization.
AnalysisError payloads enter the existing wrapper directly.248 relevant native
tests, formatting/Clippy, fresh300+67,6 cases on each engine and both unchanged
controls pass their intended verdicts. Only existing525 coverage improves;
counts remain116reviewed87partial399unmapped. See [evidence](evidence/unsupported-table-as-select/README.md).

Next INSERT oracle refinement: actual Spark rejects INSERT INTO ... IF NOT EXISTS
as raw ParseException INVALID_STATEMENT_OR_CLAUSE/42601, operation parameter,
before Flow name policy. The grammar accepts the token sequence but AstBuilder
rejects it; accepted logical SQL IF NOT EXISTS is limited to overwrite forms,
where earlier partition/overwrite checks win. Therefore the later graph handler's
IF NOT EXISTS text has no reachable SQL fixture. Share the parser/normalization
rule with ordinary Sail SQL; do not invent a pipeline wrapper for it. Remaining
valid INSERT policies keep partition→columns→overwrite→by-name precedence.
The12-case oracle is archived; no INSERT implementation changes occur in18604.


## Shared INSERT validation qualified

Commit cbeec8f93 closes the announced shared-parser checkpoint with a private
mode-only AST validator. Both SqlSource entry points validate the entire parsed
file before registration or catalog evaluation; both AST lowerers also validate.
Flow and Explain recurse through their existing nested statements. No new public
AST, error type, wrapper, dependency or execution path is introduced. Ordinary
SQL and pipeline SQL now reject INSERT INTO ... IF NOT EXISTS with Spark's raw
ParseException/INVALID_STATEMENT_OR_CLAUSE/42601 and operation parameter. Valid
overwrite IF NOT EXISTS retains its command flags.

[Evidence](evidence/insert-mode-validation/README.md) binds252 native tests,
formatting/strict Clippy, fresh300+67 public, paired15 and three unchanged-test
controls. The initial golden failure is retained: its preexisting Spark oracle
already rejected the input. Official regeneration changes only that Sail output
among32 cases, preserving all inputs and recorded Spark exceptions. No original
inventory site is promoted. Query contexts and general mixed-parser-error
ordering remain unqualified. Valid Flow-policy producers are the next unit;
streaming/CDC and public effect admission remain separate required work.


## Flow INSERT producers qualified

Commit 4fca6f3d4 applies partition→columns→overwrite→by-name validation after
Flow-name checks and before target-name resolution. It reuses AnalysisError and
the existing registration wrapper, with no new effects or public APIs. Shared
INTO IF NOT EXISTS validation remains earlier; overwrite IF NOT EXISTS reaches
the partition guard. [Evidence](evidence/flow-insert-policy/README.md) binds254
native tests, formatting/strict Clippy, fresh300+67 public, paired15,12 endpoint
vectors and two unchanged-test controls. Exact metadata checks cover the same
three BDD inputs whose formerly combined message expectation is now corrected.
The selection explicitly migrates those three IDs and retains297 others/all
other source hashes. No original Spark assertion changes or inventory promotion.
Non-INSERT/CTE-wrapped operations, broader parser contexts/order, batch effect
qualification and streaming/CDC remain required work.
