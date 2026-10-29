# Next design checkpoint: shared SQL catalog expressions

The operator requests notice before a new design phase so they can switch to
Astra. Shared SET CATALOG expression support now reaches that boundary. This
initial handoff recorded observed behavior and open decisions. The completed
[catalog-expression design](CATALOG-EXPRESSION-DESIGN.md) now selects the shared
resolution and prepare/commit boundaries; implementation remains pending.
General SQL/catalog semantics belong in Sail. LakeCat remains a catalog adapter.

## Evidence

The [paired probe](evidence/catalog-scope-design-boundary/provenance.json) records
nine cases per engine against Sail 39f070e625 and pinned Spark 4.2.1. Four positive
namespace/file/private-view cases match. Separate test commit a2dbec30eb ports
those behaviors with session-default assertions and passes four Spark references.
The probe is exploratory evidence, not nine passing parity assertions.

The probe exposes these gaps:

- After SET CATALOG, an unqualified output without USE fails at registration in
  Spark (UnknownException wrapping java.lang.AssertionError). Sail accepts the
  definition and later fails during the run with an empty database lookup.
- SET CATALOG CONCAT(constant strings) followed by USE and an MV succeeds in
  Spark. Sail's grammar accepts only an identifier or string literal and rejects
  the opening parenthesis.
- Both invalid expressions from SqlPipelineSuite:739 are rejected by both engines.
  Spark wraps them as PIPELINE_SQL_GRAPH_ELEMENT_REGISTRATION_ERROR with Failed
  to resolve catalog expression. Sail reports argument/parser errors instead.
- An unqualified external read after SET CATALOG fails at run time in both
  engines, with different attribution/messages. That overlaps the existing
  [failure/event handoff](BATCH-EVENT-DESIGN-HANDOFF.md).

Pinned source explains that SET CATALOG intentionally clears the current database
inside a SQL file; USE must restore it before implicit name qualification. This
must not be replaced with the session's ordinary default namespace behavior.
File boundaries restore pipeline defaults, and private views remain unqualified.

## Initial design questions

- Determine how the general typed AST/spec and PlanResolver carry and resolve a
  foldable catalog expression. The existing AST and SetCurrentCatalog spec carry
  only static identifier/string values. Avoid a pipeline-only expression evaluator.
- Reconcile that shared resolution with pipeline SQL registration, which is
  currently synchronous and captures per-flow file configuration/namespace.
- Preserve ordinary SET CATALOG behavior separately from pipeline file-local
  database clearing; define explicit invalid/unset namespace handling for output
  registration and reads. Spark's assertion failure must not lead to a Rust panic.
- Define catalog-expression error wrapping, origin and validation priority through
  existing Sail error transport. Include both invalid source-grid values and
  successful foldable expressions; do not special-case only CONCAT.
- Verify full source assertions across multiple configured catalogs, including
  LakeCat where its capabilities apply, while preserving file reset and private
  view lookup. General catalog functionality stays in Sail.

Streaming/checkpoint and CDC architecture remain later phases. No production
parser, catalog or error architecture was changed for this handoff.

## Additional shared source-text boundary

The [retained failing Rust reproduction](evidence/view-source-design-boundary/provenance.json)
ports SqlPipelineSuite:617's exact persisted-view text assertion. Expected
SELECT * FROM range(1, 4); the initial baseline registered SELECT * FROM range ( 1 , 4 )
with a trailing space. ViewDefinition.definition already carries SQL text, but the
AST-only analyzer populates it with query.text(). TreeText intentionally reconstructs
parseable AST text and requires nonempty results to end in whitespace. Its contract
must not be conflated with verbatim source preservation.

The span documentation originally described character offsets. Inspection of the
actual Chumsky 0.13.0 string input and a new Unicode lexer regression establish
UTF-8 byte offsets; Sail d51777745 corrects that documentation. The completed
[source-preservation design](SQL-SOURCE-DESIGN.md) records the shared source
context and Spark 4.2.1 boundary controls. It leaves TreeText's reconstruction
contract intact. Its shared analyzer and ordinary/pipeline caller implementation
are now committed, with qualified gates in that design record. General view metadata
belongs in Sail; LakeCat should store the resulting definition through its normal
catalog adapter, once its applicable provider operations are supported.

The failing test body, initial candidate patch and log remain committed as evidence.
It is now restored in the existing Rust test module and passes unchanged. The
original failed source and log remain historical evidence.

## Existing identifier policy to preserve

The [golden repair and parser
controls](evidence/2d54d5a568f8dbac68d2b9ac8519380a25782fd3/gate.json) establish a
deliberate boundary for the next design. Sail's original word lexer permits Unicode
alphanumeric characters in unquoted identifiers. Optional USE namespace keywords were
added in f52d4f7d8, and now expose the same inherited identifier rule for bare USE.
Spark 4.2.1 rejects the two unquoted Unicode controls and accepts backquoted names. Do
not silently replace Sail's general identifier policy while adding catalog expressions.
The eight-case golden repair retains the original Spark exception metadata and makes no
new SDP parity claim.
