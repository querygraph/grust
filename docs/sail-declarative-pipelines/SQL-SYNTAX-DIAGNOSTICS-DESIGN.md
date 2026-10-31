# Shared SQL grammar and syntax diagnostics

This checkpoint follows Fable CF-0514 and qualified Sail 4fca6f3d4. The user
was notified before this design phase. It does not activate execution effects.
The goal remains complete Spark 4.2.1 SDP compatibility, including the parser
boundary; a native rejection alone does not establish client diagnostic parity.

## Reference evidence

Spark pin 617618396087429b5627a86ce933bb0f5d6645cb,
SqlBaseParser.g4:420 accepts `createPipelineFlowHeader insertInto query`.
The OVERWRITE production at590 admits IF NOT EXISTS only within the optional
partition clause. INTO's corresponding clause is independent in the grammar,
then rejected by AstBuilder:1045; Sail's shared validator already handles that.

[Sixteen endpoint vectors](evidence/flow-grammar-reference/summary.json) use the
DefineSqlGraphElements API against installed Spark4.2.1. They establish:

| Input shape | Observed boundary |
| --- | --- |
| OVERWRITE without PARTITION followed by IF NOT EXISTS | ParseException, PARSE_SYNTAX_ERROR,42601, error=`'IF'`, hint empty |
| Same operation inside Flow, including multipart Flow name | Same raw parse error before name policy |
| Flow body starts SELECT, WITH, CREATE, EXPLAIN or another Flow | Same raw class/condition/state; error is the first body token, hint empty |
| Flow INSERT whose query starts WITH | Registration accepted |
| Ordinary WITH-led INSERT submitted as a pipeline declaration | Registration wrapper: Unsupported plan UnresolvedWith |
| Ordinary partitioned OVERWRITE submitted as a pipeline declaration | Registration wrapper: Unsupported plan InsertIntoStatement |
| Flow OVERWRITE DIRECTORY, USING or Hive storage | Registration wrapper: Unable flow type. Only INSERT INTO flows are supported. |
| Flow REPLACE WHERE true, BY NAME | Same unsupported-flow wrapper |
| Flow REPLACE USING(id) | Registration wrapper: INSERT OVERWRITE flows not supported. |

The last two observations are pipeline-registration results, not ordinary SQL
execution results. Ordinary execution must have its own paired tests. Full
message/query-context parity and multiple-error precedence are not established
by this packet. The initial twelve-vector run is retained. Actual REPLACE
registration contradicts the earlier drop-criteria inference in Fable CF-0517:
AstBuilder sets overwrite=true and converts static targets with toInsertPlan.
Do not implement criterion-dropping acceptance from that inference. No original
inventory site is promoted.

## Current Sail structure and constraints

`Statement::CreatePipelineFlow.statement` parses any recursive Statement.
`Statement::InsertInto` independently parses partition and if_not_exists.
These AST shapes permit the invalid forms. The TreeParser macro derives each
variant from its fields and currently rejects variant-level parser attributes.
Its field parser hooks cannot condition later fields on earlier parsed values.

SqlSource has both ordinary and spanned whole-file parse entry points. Both
currently call SqlError::parser, which formats borrowed Rich errors immediately
into SqlParserError(String). Connect maps this to InvalidArgument. A change that
only restricts grammar would improve admissibility but still fail Spark's raw
syntax-error metadata. Recovering metadata from the formatted string is not a
sound transport design.

Keep AST layout, source spans, existing pipeline wrapper and async ownership
unchanged. The parser crate must remain independent of Spark Connect and the
common StructuredSparkError type. No LakeCat or Grust dependency is needed.

## Implementation sequence

1. Add a variant-level parser-function hook to the existing TreeParser derive.
   Its default expansion remains unchanged. A custom variant parser returns the
   containing enum, allowing named AST fields to remain intact. Test default
   and overridden variants, dependency/options forwarding and invalid attribute
   diagnostics. This is a separate generic macro commit before its SQL use.
2. Factor a focused INSERT parser helper that constructs the existing
   Statement::InsertInto. Parse INTO and OVERWRITE alternatives separately;
   only OVERWRITE couples IF NOT EXISTS to its partition clause. A Flow-body
   helper admits the existing INSERT forms directly, without an outer WITH or
   arbitrary recursive statement. The query parser retains its own CTE support.
   Audit INSERT REPLACE/directory alternatives against the pin rather than
   silently narrowing every Flow body to the currently supported executor node.
3. Preserve parser failures as owned structured diagnostics at the analyzer
   boundary, before their borrowed token input is dropped. Retain the existing
   human Display and all failures, including custom reasons, found tokens,
   spans and contexts. Do not serialize marker text into Rich custom messages
   or infer tokens by parsing Display output. Reuse StructuredSparkError only
   when rendering a qualified syntax diagnostic to the existing transport.
4. Qualify the raw ParseException/condition/state/error/hint contract for these
   grammar forms through ordinary SQL and pipeline APIs. Keep general recovery
   hints, arbitrary malformed SQL, Unicode query-context offsets and mixed-error
   ordering explicit until each is tested. Broader generic syntax diagnostics
   are required eventual compatibility work; these vectors do not prove them.

Steps2–4 may need to land together if intermediate parser-only behavior cannot
meet the required public gate. Keep the generic macro hook independently
reviewable. Grammar admissibility and error transport need separate assertions
even if they share an integration commit.

## Verification and rejected shortcuts

Preserve original positive Flow fixtures, the valid WITH-query example, normal
WITH-led INSERT, valid partitioned overwrite flags, raw multipart-name ordering
and shared INTO IF NOT EXISTS behavior. Test both SqlSource routes, low-level
grammar and externally built AST lowering where relevant. Add malformed earlier
and later statements without claiming full error-order equivalence prematurely.

Run exact detached native gates and fresh public regression on the integrated
commit; pin paired endpoint test sources. Production-only controls must restore
the permissive Flow body and decouple overwrite IF NOT EXISTS, while unchanged
tests fail. Preserve failures and original Spark assertions. Only official
golden generation may change old Sail expectations after checking all inputs
and recorded Spark exceptions remain unchanged.

A post-parse filter over a completely parsed Statement would report the end of
the body rather than its first invalid token. A token-prefix regex would mishandle
comments, quoted identifiers and nested queries. Neither is the grammar fix.
A global unconditional mapping from all parser strings to a classified Spark
error would invent metadata and leave lexical/custom failures unexplained.
No full conformance claim, inventory promotion or streaming/CDC admission follows.


## Step1 qualified

Generic hook8a1a2378b is implemented without a production SQL consumer yet.
[Evidence](evidence/variant-parser-hook/README.md) binds65 unit tests, formatting,
strict Clippy, the syntax golden and two unchanged-test controls. The earlier
stale syntax snapshot is separately corrected in062dc4136 after the previous
accepted baseline also failed and official generation with/without the hook
produced identical bytes. Failed test-harness inference gates are retained.
No grammar, diagnostic transport or public runtime claim follows. Steps2–4
remain required; Fable CF-0520 accepts the design with whole insertInto grammar
and per-vector recovery-hint qualification.

Standing parser-related gates include sail-sql-macro/sail-sql-parser libraries
and the explicit sail-sql-parser syntax integration, in addition to analyzer
and affected downstream consumers. Fable CF-0523 confirms the hook/default
expansion and attributes the stale snapshot to earlier AST changes. TreeSyntax
and TreeText still reflect AST fields; after custom grammar helpers, an unchanged
syntax graph is not proof that the accepted grammar stayed unchanged.


## Owned diagnostic retention qualified

Commita690e2ce9 implements step3's owned retention before grammar integration.
[Evidence](evidence/owned-parser-diagnostics/README.md) binds394 native tests,
formatting/strict Clippy, syntax integration and three unchanged-test controls.
ExpectedFound/Custom, expected/token strings, EOF, UTF8 byte spans, contexts,
failure order and existing Display survive without a SQL-source lifetime.
Plan/Connect retain existing string behavior in this refactor; structured
propagation/rendering are still required. Two fixture-only native failures are
retained: SQL grammar did not emit the assumed contexts, and an explicit Chumsky
context covers consumed prefix0:1 separately from unexpected token1:2. Final
assertions pin both exact ranges; no production/golden change fixed the fixtures.
Whole INSERT/Flow grammar, raw Spark metadata and broader contexts/hints/order
remain integration work. No public CLI or original-site promotion follows.

Fable CF-0527 accepts retention and confirms Chumsky0.13 context-prefix semantics.
Rendering additionally needs the original SQL: convert UTF8 byte offsets into
one-based line and zero-based UTF16 column, and obtain error-token text from
the matching source slice. Token Display uses placeholders for whitespace;
hidden trivia must not become a reported ANTLR-style error token. Retention
alone does not supply source text or qualify those renderer requirements.


## Grammar and source-backed metadata increment qualified

Commitd598f4da8 has400 native+syntax,fmt/strictClippy,300+67 public,paired24
and four controls. [The packet](evidence/insert-flow-grammar/README.md) retains
all failed gates and audited133-message golden delta; no inputs/Spark exceptions
or outcomes changed. Source-backed mismatches propagate through both conversions;
a typed EndOfInput expectation conservatively excludes trailing-token recovery.
Full16-vector replay matches12: two ordinary unsupported-node names and two
REPLACE forms remain explicit backlog, alongside recovery hints, empty statements,
lexical errors, full UTF16 query summaries and mixed-error order. No full SDP
or original-site promotion. Fable independently owns CDC implementation.
