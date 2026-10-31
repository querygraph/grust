# What the original Spark Declarative Pipelines suites require of the SQL expression work

Read-only scope review requested in CF-0424. Source: the Spark pin
`617618396` at `/Users/alexy/src/spark-sdp-4.2.1`, every file under a
`pipelines` test tree (47 Scala suites under `sql/pipelines`,
`sql/connect/server` and `sql/hive`, and 9 PySpark test modules under
`python/pyspark/pipelines/tests`; the MLlib `Pipeline` suites are
unrelated and excluded). Each construct was counted with a literal
`grep` over every file; the hits were then read in context.

## 1. The count

| construct                             | occurrences | where                                                                                   |
| ------------------------------------- | ----------: | --------------------------------------------------------------------------------------- |
| `IDENTIFIER(`                         |           0 |                                                                                         |
| `CASE WHEN`, `IF(`                    |           0 |                                                                                         |
| `nvl2`, `nanvl`, `typeof`, `try_cast` |           0 |                                                                                         |
| `DIV`, `pmod`, `DECIMAL`              |           0 |                                                                                         |
| `spark.sql.ansi.enabled` (any `ansi`) |           0 | the four `ansi` hits are the word `transient` in `GraphExecutionSuite`                  |
| arithmetic `/` in pipeline SQL        |           0 | every `/` hit is a path or a comment                                                    |
| `SET CATALOG`                         |           3 | `SqlPipelineSuite.scala:673`, `:751`; `PythonPipelineSuite.scala:1412`                  |
| `CAST(`                               |           3 | `SqlPipelineSuite.scala:1049–1050`; `AutoCdcGraphExecutionTestMixin.scala:170`          |
| `nullable` in schema assertions       |          64 | declared table schemas and `RANGE` output, `MaterializeTablesSuite`, `AutoCdc*`, `:552` |

## 2. The sites, and what each actually depends on

- **`SqlPipelineSuite.scala:634–734`, "Use database and set catalog
  works".** `SET CATALOG <bare identifier>` once, `USE DATABASE` twice,
  `USE NAMESPACE` once, a second SQL file that must start back in the
  pipeline catalog, temporary views always created in the pipeline
  catalog, `STREAM(mv2)` over a CTE, `RANGE` sources, and the predicate
  `mv2.id % 2 == 0` (column modulo by a literal; Sail parses `==`,
  `sail-sql-analyzer/src/expression.rs:166`, `:176`). Five
  `checkAnswer` assertions on row values. No constant-expression
  catalog name, no cast, no conditional. The expression work this
  depends on is the bare-identifier catalog directive (recorded as
  policy three in the foldability review, §9–§10) and column modulo;
  everything else is directive scoping and streaming reads.
- **`SqlPipelineSuite.scala:736–757`, the grid.** Exactly two
  expressions, `CONCAT(foo, '1')` and `test.cat`, and one assertion:
  the message contains `Failed to resolve catalog expression`. Spark
  wraps any `AnalysisException` from the analyzed `SetCatalogCommand`
  in that prefix (`SqlGraphRegistrationContext.scala:548–559`); an
  execution-time error would escape unwrapped, and no suite asserts
  one. Sail already produces the prefix
  (`sail-spark-connect/src/pipelines/sql.rs:98`, `:104`, tested in
  `pipelines/sql/tests/preparation.rs:235–322`), the unresolved
  attribute inside a function and the multi-part name both fail
  analysis today (foldability review §9, §10). This site is met; it
  requires nothing from foldability of arithmetic, casts or
  conditionals.
- **`PythonPipelineSuite.scala:1411–1448`.** `SET CATALOG some_catalog`
  is in the list of SQL commands that must be rejected when issued from
  Python with `UNSUPPORTED_PIPELINE_SPARK_SQL_COMMAND`, inside or
  outside a query function. That is a session-mutation guard, not an
  expression test; it depends on the Python pipeline handler, not on
  catalog expression evaluation.
- **`SqlPipelineSuite.scala:1040–1060`.** `CAST(window.start AS LONG)`
  and `CAST(window.end AS LONG)` in a streaming windowed aggregation.
  A timestamp-to-long cast of a column: not a string cast, no laziness
  question, nullability inherited from the child in Spark (no
  `forceNullable` arm for `TimestampType → LongType`). The one thing to
  verify is the value: Spark gives seconds since the epoch (floor), Sail
  lowers timestamp-to-numeric as `(1.0 / multiplier) * CAST(ts AS
BIGINT)` then casts to the target (`resolver/expression/cast.rs`,
  the `Timestamp → numeric` arm), which truncates toward zero and
  differs from floor only before 1970. The test's windows are not.
- **`AutoCdcGraphExecutionTestMixin.scala:170`.** `CAST(NULL AS
BIGINT)` and `CAST(<long> AS BIGINT)` in an `INSERT … SELECT`.
  Numeric literal casts; trivially met.
- **The 64 `nullable` assertions.** They compare materialized table
  schemas built from declared columns (`x INT NOT NULL COMMENT …`,
  `MaterializeTablesSuite.scala:50–93`), from `RANGE` (`id` long,
  non-nullable, `SqlPipelineSuite.scala:552`), or from AutoCDC key and
  sequence columns. None is the nullability of a `CASE`, `IF`, cast
  from string or arithmetic expression.

## 3. What no original assertion requires

Nothing in the 56 files exercises `IDENTIFIER(...)` for a catalog or a
table, a string-to-numeric cast in any mode, a decimal cast, `CASE`,
`IF`, `nvl2`, `nanvl`, `typeof`, integer division, `pmod`, division by
zero, the ANSI configuration, or a constant expression whose evaluation
order matters. Therefore none of the following is a prerequisite for
any original SDP assertion:

- the source- and conditional-aware folding pre-pass and its proof
  boundary (operand review §6.15, §6.17, §6.18);
- the batch-then-replay fast path, the error vocabulary and the planner
  seat (§2, §6.1, §6.6, §6.9);
- the decimal string cast (§6.8–§6.11), its config capture (§6.13), and
  the resolver routing still pending;
- the `nvl2`/`IF`/`CASE` coercion and nullability units
  (conditional review §1–§6) and the `NaNvl` component (§6.16);
- the ANSI and legacy string cast nullability and legacy integer and
  boolean casters (conditional review §3, §6).

They are real Sail parity gaps, found while settling the catalog
directive policy, and every conformance failure Codex retained should
stay visible as a general backlog. They are not on the SDP acceptance
path, and further SQL parity prerequisites should not be opened on the
SDP ticket.

## 4. The next direct acceptance gap

By Codex's own inventory the two unmet original sites are the mixed
graph fixture (`SqlPipelineSuite.scala:44–88`: `STREAM` reads of
external tables, `CREATE FLOW f AS INSERT INTO st BY NAME SELECT * FROM
STREAM …`, resolved-graph assertions on flows, tables, views and
external inputs) and the multi-catalog test (`:634–734`). The second
one's expression needs are met (§2); what remains for it is directive
scoping across files, temporary-view qualification, `STREAM` over a CTE,
and the per-file reset. The cheapest next step that moves acceptance is
to run that test's two SQL files verbatim against Sail as a direct
probe and record which of the five `checkAnswer` results and which
directive fails first, before any further cast or conditional work.

## 5. Correction to §4 (CF-0427): the multi-catalog test is already qualified

§4 said the multi-catalog test's remaining needs were directive scoping
across files, temporary-view qualification, `STREAM` over a CTE and
the per-file reset. That was inferred from the fixture, not checked
against the record, and the record says otherwise: Codex's
`CATALOG-ACCEPTANCE.md`, section "Combined catalog, CTE and file-scope
fixture", records that `scripts/spark-pipelines-tests/catalog_scope.py`
preserves `SqlPipelineSuite:634`'s two SQL files and all five output
assertions, including the batch CTE read through `STREAM(mv2)`, the
join, private-view resolution after catalog changes, two-part output
reads and the namespace reset, with a passing receipt on Sail
`8d044db386` for the memory/memory and memory/LakeCat profiles and a
retained parent run that fails specifically at `STREAM(batch CTE)`.
The site is qualified on the public Connect surface; what remains
unqualified there is execution of Spark's own Scala suite and its
two-catalog JVM substrate, which no expression work changes.

The genuinely unmapped original batch site is therefore
`SqlPipelineSuite:562–579`, "Multipart table names supported": two
databases, `CREATE MATERIALIZED VIEW db1.mv1 AS SELECT 1` and
`CREATE MATERIALIZED VIEW db2.mv2 AS SELECT * FROM db1.mv1`, with
`checkAnswer` `Row(1)` on each; pure batch, one cross-namespace
dependency. The mixed sites remain `:44–88` and `:403–432` (an external
table in a database read once as a materialized view and once through
`STREAM`, plus a temporary view, with `1, 2, 3` on both). Codex's
sequencing, the `:562` fixture first with both Spark and Sail runs
before it is mapped even partially, is the right order, and the
conclusion of §3 is unchanged by this correction.
