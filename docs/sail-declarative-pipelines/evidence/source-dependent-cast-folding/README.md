# Source-dependent folding and decimal contract

Product baseline63f5bd3b3f0f8bd9b23607161d5988df853a738c; no production
changes or activation in this packet. Fresh Spark4.2.1 Connect source pin
617618396087429b5627a86ce933bb0f5d6645cb. Both Spark runs and both Sail
servers terminated with no remaining listeners. Each Sail run checks the exact
already-qualified CLI hash before/after; it does not rebuild or change source.

## Folding:56 corresponding queries per engine

Four targets × two ANSI modes × seven shapes. Each records effective ANSI,
SQL/explain/collect phase, rows/schema or structured condition/state/parameters.
Parquet views have one nullable int column containingNULL or0; Spark and Sail
write their own fixtures. This is a source/phase oracle, not a byte-for-byte
Parquet reader comparison. Sail's two input files are retained.

| Shape | Spark ANSI | Spark legacy |
| --- | --- | --- |
| bad literal cast / column from VALUES(NULL) | NULL | NULL |
| bad literal cast / Parquet column, NULL or0 | planning CAST_INVALID_INPUT | NULL |
| fully foldable bad cast / literalNULL, with/without Parquet | NULL | NULL |
| skipped bad cast in CASE over Parquet | selected1 | selected1 |
| IDENTIFIER wrapping foldableNULL arithmetic | NOT_A_CONSTANT_STRING.NULL | same |

The earlier VALUES16 oracle is correct for its exact inputs. Its broad
interpretation as arbitrary rightNULL semantics was wrong. Spark folds a
foldable parent as a whole; below a nonfoldable parent it folds children and
propagates failure except within conditional branches. LocalRelation early
runs ConvertToLocalRelation before ConstantFolding. A deferred typed cast alone
cannot reproduce all these contexts. Exact eager planning failures are required;
a documented lenient runtime result is not full Spark acceptance.

Sail matches34/56 row/condition/state outcomes. Including result schema and
planning-versus-collect phase leaves16/56 matching. SQL versus explain is recorded
but both count as planning; no claim equates the exact API call of failure.
ANSI primitive Parquet errors currently surface at collect instead of explain;
decimal errors can lack Spark metadata and wrongly affect skipped contexts.
These failures, including existing IDENTIFIER diagnostics, stay required.

## Decimal lexical/error contract:192 corresponding queries per engine

Two decimal targets × two modes × CAST/TRY_CAST ×24 inputs. Spark records three
separate failure conditions: CAST_INVALID_INPUT/22018 for malformed input;
NUMERIC_VALUE_OUT_OF_RANGE.WITH_SUGGESTION/22003 for rounded target overflow;
NUMERIC_OUT_OF_SUPPORTED_RANGE/22003 for unsupported integral range. Overflow
parameters retain either the canonical parsed decimal value or original input,
according to the error kind. Legacy and TRY_CAST returnNULL for these failures.

HALF_UP ties, including negative values, already match in the ordinary Sail
examples. The actual Arrow cast path is cast/decimal.rs, whose behavior differs
from the separate public parse_decimal utility; do not infer the execution path
from the similarly named function. Spark also accepts fullwidth/Arabic decimal
digits, Unicode exponent digits, ASCII control-character trim and large zero
exponents, while rejecting non-breaking-space trim. Existing Arrow string cast
semantics do not cover that grammar or error classification. Extreme zero cases
must not allocate an exponent-sized number/string.

Sail matches114/192 outcomes and146/159 common-success schemas. Requiring schema
as well leaves101/192 matching. The checker does not qualify full JVM hierarchy,
complete messages, query origin or every numeric/Unicode boundary; those remain
implementation gates. This192 sample is a contract fixture, not an exhaustive
proof of Java BigDecimal grammar.

## Review reconciliation and implementation boundary

Fable's pinned review snapshot includes accepted validator/decoder/codec/float
units, source/folding and lexical probes, and the reconciled replay policy.
Replay only known raw data errors from an admitted deterministic native body;
keep other errors original. Admission must constrain data types as well as class
and recursively inspect lambdas. Source/token scans support the audit, but do
not prove reachability or automatically pin future edits. Executable per-body,
per-dtype error fixtures plus dependency/source audit invalidation are required.

ExtensionQueryPlanner can rewrite its final logical plan before delegating to
DefaultPhysicalPlanner; it has no native scalar/HOF construction callback.
A physical optimizer plus worker decoder can recompute admission without a wire
eligibility bit, but generic expression visitation is read-only: supported node
rebuild paths and scan projection pushdown still need proof. A final logical
rewrite is another candidate, with later physical rewrites requiring audit.
No planner seat, wire-mode change or optimization default is activated here.

Run verify.py to verify immutable artifacts, source pins, Spark expectations and
the intentionally failing conformance checker. It retains131 combined failures
(40 source/phase/schema +91 decimal/schema); passing artifact verification does
not make conformance green. Archived scripts name original worktrees and /tmp
paths. No new public300/67 run, original Scala SDP acceptance, streaming/CDC,
provider/ownership change, release or push is claimed by this packet.
