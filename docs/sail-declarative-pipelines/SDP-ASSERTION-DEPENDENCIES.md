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

## 6. `:562` mapped to the public surface, test-only candidate `8e5e06ff4` (CF-0429)

Two Python paths on `d99e8b86d`. `test_sql_namespace.py::test_multipart_outputs_across_two_namespaces`
is `SqlPipelineSuite:562–579` statement for statement: two databases
with unique owned names, asserted absent before creation; one SQL
registration carrying both `CREATE MATERIALIZED VIEW first.mv1 AS
SELECT 1` and `CREATE MATERIALIZED VIEW second.mv2 AS SELECT * FROM
first.mv1`, as the original's single `sqlText` does; one run; the two
`checkAnswer` assertions as `[(1,)]` on each qualified output; then the
graph dropped through the proto command, both tables and both
databases dropped with absence asserted. The `conftest.py` change
catches only `AnalysisException` with condition
`CANNOT_MODIFY_STATIC_CONFIG` from the per-session warehouse override,
which is what Spark raises for the static `spark.sql.warehouse.dir`,
so Spark keeps its startup warehouse and Sail keeps the override;
anything else still raises. Isolation then rests on the unique names,
which the test provides.

Verdict: accept as a faithful public-surface mapping; `:562` moves from
unmapped to partial with `scala_suite_executed = false` retained, as
Codex proposes, once its receipts verifier has both the Spark and the
Sail run. The runtime under test is the already qualified `d99e8b86d`
CLI and the candidate changes only test paths, so no binary claim is
attached to `8e5e06ff4`.

## 7. Pre-pin for the next batch case: `:599–615`, `INVALID_TEMP_OBJ_QUALIFIER` (CF-0431)

The original test registers `CREATE TEMPORARY VIEW some_database.tv AS
SELECT 1` followed by a materialized view over it, intercepts a
`ParseException`, and asserts `errorClass` contains
`INVALID_TEMP_OBJ_QUALIFIER` (`SqlPipelineSuite.scala:599–615`). The
rule it exercises, from the pin:

- `SparkSqlParser.normalizeTempViewIdentifier`
  (`sql/core/.../SparkSqlParser.scala:233–257`), used for `CREATE` and
  `DROP TEMPORARY VIEW`: a one-part name is the view name; a two-part
  name is accepted only when the first part is `session`
  (case-insensitive, `CatalogManager.SESSION_NAMESPACE`); a three-part
  name only when the parts are `system.session`; anything else, and any
  longer name, throws.
- The error is a `ParseException` built by
  `QueryParsingErrors.invalidTempObjQualifierError`
  (`QueryParsingErrors.scala:767–779`) with condition
  `INVALID_TEMP_OBJ_QUALIFIER`, SQLSTATE `42602`, and parameters
  `objectType = "VIEW"`, `objectName = toSQLId(last part)`,
  `qualifier = toSQLId(all parts but the last, joined by '.')`; the
  message is "Temporary <objectType> <objectName> cannot be qualified
  with <qualifier>. Temporary objects can only be qualified with
  SESSION or SYSTEM.SESSION." (`error-conditions.json:4857–4862`). The
  Connect class is `org.apache.spark.sql.catalyst.parser.ParseException`,
  which PySpark maps to its `ParseException`.

Sail today, at `d99e8b86d`:

- `sail-sql-analyzer/src/statement.rs:518–525` rejects every
  multi-part temporary view name with
  `SqlError::invalid("expected a single identifier for temporary view
name")`, which `sail-spark-connect/src/error.rs:93–100` maps to
  `SparkError::InvalidArgument`: wrong class, no condition, and stricter
  than Spark, since `session.v` and `system.session.v` are valid there.
- `SqlError` has no structured variant (`sail-sql-analyzer/src/error.rs:11–26`);
  `SparkThrowable::ParseException` carries only a message, while
  `SparkThrowable::Structured` carries class, condition, state and
  parameters (`error.rs:272–280`).

So the case needs a small Sail source unit, not a test mapping alone:
the `session`/`system.session` normalisation in the analyzer with the
view name returned, a structured parse error for every other qualifier
carrying the class, condition, SQLSTATE and the three parameters with
backtick-quoted identifiers, the same rule on `DROP TEMPORARY VIEW`,
and the pipelines SQL handler letting that error through unchanged so
the public test can assert the condition. The sibling pipelines check
for persistent views over temporary ones already builds a structured
`INVALID_TEMP_OBJ_REFERENCE` (`pipelines/analysis.rs:174–192`), which
is the pattern to follow.

### 7.1 Correction (CF-0433), and the first logical unit

§7 said the normalisation is "used for `CREATE` and `DROP TEMPORARY
VIEW`", repeating the helper's own doc comment. Codex checked the call
sites and is right: `normalizeTempViewIdentifier` is called from
`CREATE TEMPORARY TABLE` (`SparkSqlParser.scala:585`), local `CREATE
TEMPORARY VIEW … USING` (`:616`) and the query-defined `CREATE
TEMPORARY VIEW` (`:809`); the `dropView` rule is `DROP VIEW (IF EXISTS)?
identifierReference` with no `TEMPORARY` keyword
(`SqlBaseParser.g4:320`), and a qualified `DROP VIEW` of a persisted
view must stay valid. The unit is therefore scoped to query-defined
temporary views, which is what `:599` exercises; the `USING` form's
separate rules are not an SDP prerequisite.

First logical unit `60a5f290c` on `8e5e06ff4`: `StructuredSparkError`
(`error/structured.rs`) and the identifier formatter move from
`sail-common-datafusion` to `sail-common`, the former re-exporting
both so callers are unchanged; the struct file moves with zero content
changes and the lock file is untouched. This lets the SQL analyzer
build the structured parse error without depending on DataFusion,
which is the right placement. Accepted read-only.

## 8. `:599` behaviour unit, candidate `db650c40e` on `60a5f290c` (CF-0435)

Ten paths; product changes are small and in the right places:

- `SqlError::Structured(Box<StructuredSparkError>)` is added to the SQL
  analyzer's error type, and the `PlanError` and `SparkError`
  conversions pass it through unchanged, so a structured parser error
  reaches Connect with its class, condition, state and parameters
  whether it travels directly or through planning (asserted both ways
  in `error/structured/tests.rs`).
- `statement/temporary_view.rs::normalize_query_name` is
  `normalizeTempViewIdentifier` for the query-defined form: one part
  accepted; two parts when the first is `session`; three when they are
  `system.session`; the comparison is Sail's existing
  `spark_case_insensitive_name_eq`, which the tests exercise with the
  long s and dotted and dotless I (`seſſıon`, `ſyſtem`.`SESSİON`), the
  folds Java's `equalsIgnoreCase` performs. Anything else raises the
  structured `ParseException` with `INVALID_TEMP_OBJ_QUALIFIER`, SQLSTATE
  `42602`, `objectType = "VIEW"`, and `objectName`/`qualifier` formatted
  by the shared `quote_sql_identifier`.
- Two quirks are reproduced from Codex's fresh Spark baseline, and both
  follow from the pin: Spark's `toSQLId(String)` re-parses the name
  through the attribute-name parser, so a last part containing a dot
  renders as two quoted parts (`` `a.b`.`c.d` `` gives objectName
  `` `c`.`d` ``) and a part containing an unbalanced backtick raises
  `INVALID_ATTRIBUTE_NAME_SYNTAX` (`error-conditions.json:3345–3350`,
  SQLSTATE `42601`), which the parser re-raises as a `ParseException`
  with the same fields; `quote_in_parser` reproduces that reclassing
  without duplicating the parser.
- `CREATE … USING` keeps its previous path and `CREATE VIEW db.v` /
  `DROP VIEW db.v` are asserted unchanged, matching §7.1.
- The pipelines SQL preparation passes a structured parser error through
  as an evaluation failure instead of wrapping it as a registration
  analysis string, and the draft is discarded whole (an earlier valid
  materialized view in the same file leaves no output or flow), which
  is what `processSqlFile` raising does.
- Public test for both the direct SQL and the pipeline API: the
  original `:599` rejection with condition, state and the three
  parameters, and the `session` / `system.session` / mixed-case / long-s
  normalisations resolving to `v`, with the pipeline form confirming
  the temporary view is not persisted.

Verdict: accept, read-only, pending the native gates and the paired
public baseline. After it lands, `:599–615` can move to partial with
the Scala flag retained, on the same terms as `:562`.

## 9. Metadata-only materialization: Spark's contract and Sail's seam (CF-0438 checkpoint)

**The two fixtures.** `MaterializeTablesSuite.scala:125–161` ("multiple")
registers two tables through `registerTable`, whose default is
`isStreamingTable = true` (`TestGraphRegistrationContext.scala:45–72`),
each fed by a batch DataFrame flow, calls `materializeGraph`, and
asserts the catalog columns `x INT` and `y STRING`, nullable.
`:374–399` ("partition columns with user schema") registers one such
table with a specified two-column schema and `partitionCols = x2`, and
asserts the columns and `partitioning == Seq(identity("x2"))`. Neither
runs a flow; both assert what `DatasetManager.materializeDatasets` left
in the catalog.

**Spark's contract** (`DatasetManager.scala:75–112`, `:246–350`), for
every table in the refresh set regardless of kind:

1. `outputSchema = specifiedSchema.getOrElse(inferredSchema.asNullable)`;
   properties merged by `resolveTableProperties`; partitioning is the
   identity transform of each partition column; clustering separately;
   both together is `SPECIFY_CLUSTER_BY_WITH_PARTITIONED_BY_IS_NOT_ALLOWED`.
2. If the table exists: its partitioning must equal the requested
   transforms (`CANNOT_UPDATE_PARTITION_COLUMNS`); `TRUNCATE` only when
   full refresh or not a streaming table; full refresh also drops the
   AutoCDC auxiliary table; then `alterTable` with the column diff
   against `mergeSchemas(existing, output)` for a streaming table on a
   normal refresh and against `outputSchema` otherwise, plus
   `setProperty` for every merged property.
3. Else `createTable(identifier, TableInfo{properties, columns,
partitions})`.
4. The table is returned with `normalizedPath` from `PROP_LOCATION`.

The kind only changes step 2's truncate and merge branches. Step 1,
step 3 and the assertions the two fixtures make are kind-independent,
which is why the fixtures can use streaming tables without ever
running a streaming flow.

**Sail's seam** at `db650c40e`, `sail-spark-connect/src/pipelines`:

- `materialize::tables` (`materialize.rs:21–`) is Spark's step 1
  through 3 for materialized views: reserved-property checks for
  `comment` and `provider`, the cluster-versus-partition rule
  (clustering itself unsupported), columns from the analyzed schema
  through `schema::table_columns`, which applies `asNullable` to an
  inferred schema and keeps a specified one (`schema.rs:94–134`), the
  identity-only partition match with `CANNOT_UPDATE_PARTITION_COLUMNS`,
  `TRUNCATE`, the column type, nullability, comment, add and drop
  changes, and the create path with identity partitioning and the
  default provider. `schema_merge.rs` already implements
  `SchemaMergingUtils` for the streaming-table merge branch.
- It skips every output that is not `OutputType::MaterializedView`
  (`materialize.rs:32–36`), so a streaming table's metadata is never
  materialized, and `execution::execute` rejects any graph containing
  `OutputType::Table` or `Sink` before materialization runs
  (`execution.rs:28–34`, "incremental pipeline execution").

So the two fixtures depend on exactly two things in Sail: letting
`materialize::tables` handle `OutputType::Table` with Spark's two
streaming-table branches (no `TRUNCATE` unless full refresh; `merge`
instead of replace on a normal refresh, using `schema_merge.rs`), and
ordering that step before the execution guard rather than after it.
The guard itself stays where it is: it protects flow execution, which
these fixtures never reach, and Codex is right that it is not an oracle
failure to disable.

**Entry point.** Spark's helper is `materializeGraph(graph, storageRoot)`
in the pipelines test utilities, which calls
`DatasetManager.materializeDatasets` directly and then reads the
catalog. There is no public Connect command that materializes without
running (a dry `StartRun` analyses only), so the faithful mapping is
native: a test in the pipelines module constructing the
`GraphDefinition` and `AnalyzedGraph` for two table outputs with batch
flows, calling `materialize::tables` (`pub(super)`), and asserting the
Sail catalog's columns and partitioning. A public materialized-view
variant can exist as a labelled partial check, but, as Codex says, it
is not the original table-kind contract and must not be counted as
closing these sites. Both runs, Spark's `materializeGraph` and Sail's
native call, are needed before either site moves from unmapped.

**Assertion details to carry into the test**: `x` and `y` are
nullable because of `asNullable` on an inferred schema from
non-nullable DataFrames (Sail's `nullable_fields` does the same);
`partitioning` is compared as identity transforms in order; the
specified schema is used verbatim, not made nullable.

### 9.1 Boundary correction (CF-0440)

§9 suggested ordering `materialize::tables` before the `Table | Sink`
rejection in `execute`. Codex's correction is right and is the
standing contract: the public path rejects before any write or catalog
effect until the effect path is qualified, and a guard that fires only
after metadata has been written would not preserve that. The native
metadata-only fixtures therefore call an internal materialization entry
point under the existing ownership contract, and the public guard
order does not change. Also, "two lines" located the gap; it did not
size the change. Handling `OutputType::Table` in the seam requires the
streaming truncate and merge decisions, the property and schema
choices, and the owned failure paths for each catalog mutation, each of
which needs its own fixture before the adapter is selected. The
smallest adapter is to be designed after verifying the seam and
Spark's internal helper execution, not assumed from the map.

## 10. Codex's metadata materialization design, read against the pin (CF-0442)

The design (`METADATA-TABLE-MATERIALIZATION-DESIGN.md`, Codex's working
tree at the time of reading) makes six claims about Spark; all six are
in the source:

- `registerTable` defaults to a streaming table and
  `BaseCoreExecutionTest.materializeGraph` calls
  `DatasetManager.materializeDatasets` directly
  (`BaseCoreExecutionTest.scala:29–40`), so the reference adapter that
  compiles the unmodified registration helper against the 4.2.1 jars
  and invokes the production `DatasetManager` is the original entry
  point, not a reconstruction.
- Inferred schemas are made recursively nullable and declared schemas
  are used exactly (`DatasetManager.scala:261–263`).
- An existing streaming table on an ordinary refresh is not truncated
  and gets `mergeSchemas(existing, output)` with the existing schema on
  the left (`:302`, `:324–326`); a materialized view is truncated and
  takes the output schema (`:302`, `:327`); the column diff and
  `setProperty` for every merged property follow (`:330–332`).
- `pipelines.reset.allowed = false` downgrades a requested full refresh
  to an ordinary refresh (`constructFullRefreshSet`, `:397–430`,
  `PipelinesTableProperties.scala:37–38`), which is what the design's
  downgrade does; an allowed full refresh truncates and unconditionally
  drops the AutoCDC auxiliary table (`:309–320`), which the design
  refuses before any effect rather than half-implementing. That is the
  right boundary while the owned CDC cleanup contract is absent.
- Partition and cluster transforms together fail with
  `SPECIFY_CLUSTER_BY_WITH_PARTITIONED_BY_IS_NOT_ALLOWED` (`:272–277`).

Two observations for the design, neither a correction:

- Spark materializes table by table inside the graph transformer and
  wraps each failure as `TableMaterializationException(displayName,
cause.addOrigin(origin))` (`:108–117`), so a failure on the second
  table leaves the first created. The design preflights the whole
  graph before any mutation, which is stricter. None of the suite's 24
  tests (nine `intercept[TableMaterializationException]` sites, all
  single-table failure fixtures) observes partial state, so this is a
  labelled Sail policy, not an assertion dependency; the exception's
  display name and origin are the attribution contract the design
  already lists as still required.
- The design keeps the public `execute` rejection before
  materialization and proves it with a mixed graph that creates
  neither target, which is the §9.1 boundary as stated.

Verdict on the design: consistent with the pin; nothing to challenge
before the product candidate. The candidate review will check the
merge branch against `schema_merge.rs` semantics (order and metadata
from the left, nullability widened, incompatible types failing before
mutation), the no-truncate path on an existing table with rows, the
preflight ordering, and that production-only controls fail the new
native assertions.

## 11. Metadata materialization candidate `a9eecf5f5` on `db650c40e` (CF-0444)

Four paths. `execute` passes only the analyzed schema map to
`materialize::tables` and keeps its `Table | Sink` rejection ahead of
it (`execution.rs:28–37`). `materialize::tables` now:

- Preflights the whole graph first: any `Table` output in the reset
  selection without `pipelines.reset.allowed` equal to `false` is
  refused as unsupported before any mutation, and one equal to `false`
  is downgraded to an ordinary refresh, which is Spark's
  `constructFullRefreshSet` (§10). Spark converts the property with
  Scala's `toBoolean` on the raw value, no trim
  (`PipelinesTableProperties.scala:95–96`, `:99–110`), so the
  candidate's ASCII case-insensitive comparison matches it except for
  the long-s fold, an exotic spelling that `parse_spark_bool` already
  handles if exact parity is wanted later; Spark also rejects an
  unparsable value at registration through `validateAndCanonicalize`,
  which is a separate check for the properties path.
- Admits `MaterializedView` and `Table` outputs, still excluding views,
  sinks and unselected outputs.
- For an existing `Table`, does not truncate and takes
  `schema::streaming_columns`, which converts the catalog columns to
  Spark fields and merges them on the left with the declared-exact or
  inferred-nullable output fields through `schema_merge::merge_fields`;
  the existing column diff and property path then apply. A
  materialized view keeps its truncate and replacement.

Native tests, against the original assertions: two streaming tables
from batch queries materialize `x INT` and `y STRING`, nullable, with
zero rows (`:125–161`); a declared `(x1 INT, x2 INT) PARTITIONED BY
(x2)` table materializes both columns nullable with the identity
partition on `x2` and zero rows (`:374–399`). Beyond them: an ordinary
refresh of an existing table with a row keeps the row, keeps the left
field order and the old comment, widens `id` to nullable, appends the
new column and sets the property; a reset with `reset.allowed = false`
downgrades and changes nothing; a partition change fails with
`CANNOT_UPDATE_PARTITION_COLUMNS` and an incompatible type fails, both
leaving rows and columns untouched; a mixed graph through the public
`execute` creates neither target, and a full refresh of a streaming
table is refused before effects.

The test-only `metadata_schemas` resolves the fixture queries and
calls `schema::infer` directly, because public analysis rejects a batch
query for a streaming table (`graph.rs:400–405`,
`INVALID_FLOW_QUERY_TYPE.BATCH_RELATION_FOR_STREAMING_TABLE`) while
Spark's internal resolve plus `DatasetManager` accepts the original
fixtures, as Codex's compiled-helper reference showed. That is a
test-only mirror of Spark's internal path, not a production bypass, and
no output is relabelled.

Verdict: accept, read-only, pending the native gates and the public
regression run. On landing, `MaterializeTablesSuite:125` and `:374`
can move to partial on the same terms as the SQL sites, with the
Scala flag retained.

## 12. Structured partition diagnostics, candidate `8c44213a8` on `a9eecf5f5` (CF-0447)

Four paths. The two string-only analysis errors in `materialize::tables`
become structured `AnalysisException`s built in
`materialize/errors.rs`:

- `CANNOT_UPDATE_PARTITION_COLUMNS`, SQLSTATE `42000`, parameters
  `existingPartitionColumns` and `requestedPartitionColumns` rendered
  in Spark's `Transform.toString` spelling (`identity(x)`, `years(c)`,
  `bucket(n, c)`, …) with Sail's identifier quoting, the requested side
  always identity, and an omitted declaration rendering as the empty
  string, which is `allTransforms.mkString(", ")` of nothing
  (`DatasetManager.scala:286–296`).
- `SPECIFY_CLUSTER_BY_WITH_PARTITIONED_BY_IS_NOT_ALLOWED`, SQLSTATE
  `42908`, no parameters (`:272–277`), raised before the existing-table
  lookup, so no target is created; the test asserts the table absent.

The templates match `error-conditions.json:724–730` and `:6452–6457`.
The original assertions (`MaterializeTablesSuite:444–445`, `:487–488`,
`:1063–1067`) check only the cause's condition, class and the retained
partitioning, which the native ports do, including the retained
`identity(x)` after both the changed and the omitted declaration. The
outer `TableMaterializationException(tableName, cause)`
(`DatasetManager.scala:60–64`) and origins remain explicitly open, as
Codex states; this unit must not be counted as wrapper or attribution
parity. The omitted-partition port covers only the failing half of
`:402`; its success half (same partition column, columns reordered by
the catalog) is still unmapped.

One finding, outside the original assertions and not blocking: Spark
joins the lines of a multi-line message template with a newline
(`ErrorClassesJSONReader.scala:186`, `:202`), so the
`CANNOT_UPDATE_PARTITION_COLUMNS` message a Spark client sees has a
line break before "Please delete the table …", where the candidate
renders a space. A one-character change to the format string.

Verdict: accept, pending the native gates, with the newline fix either
folded in or recorded as a known text difference.

## 13. `MaterializeTablesSuite:42–123` ("basic"), test-only candidate `b32ead862` (CF-0451)

Two paths, test only. The original materializes a materialized view
`a` three times with a specified schema `x INT NOT NULL`, `x2 INT` and
the table comment `p-comment`: column comments `comment1`/`comment2`,
then `comment3`/`comment4`, then none, each time asserting the V2
columns `sameElements` the specified schema (name, type, nullability,
comment, no default or generation) and `PROP_COMMENT == "p-comment"`.
The port runs the same three materializations through the private
`materialize::tables` with `CREATE MATERIALIZED VIEW a (x INT NOT NULL
COMMENT …, x2 INT COMMENT …) COMMENT 'p-comment' AS …`, and after each
asserts the two columns in order with `Int32`, `x` non-nullable, `x2`
nullable, the expected comment or none, and `default`,
`generated_always_as` and `identity` absent, which is what
`structTypeToV2Columns` leaves null. The third stage exercises the
comment-removal branch of Sail's column diff (`old.comment !=
column.comment` with `None`). The table comment is read from
`TableKind::Table.comment`, Sail's native seat for the reserved
comment, rather than a properties map; Codex labels the difference and
it does not change the assertion. Zero rows after each materialization
is an extra check the original does not make, and is correct for the
metadata-only path.

Verdict: accept as a faithful port; the runtime is the inherited,
publicly qualified `604a91f8d`, and the candidate changes no product
code, so no fresh-build claim attaches. If the native gate exposes a
product gap in the comment-removal branch, that is the separate
reviewable chunk Codex already anticipates.

### 13.1 Expanded candidate `807d66b15`: `:236–262` ("schema matches existing table schema")

The expansion adds one test and no product change. The original
creates `test_db.t2(x INT)` with SQL, asserts the single nullable `INT`
column, materializes a streaming table `t2` (the `registerTable`
default) fed by a batch `1, 2, 3` flow, and asserts the same column
again. The port creates the table through Sail's SQL parser, command
resolver and runner, asserts the column before, materializes `CREATE
STREAMING TABLE t2 AS SELECT 1 … UNION ALL …` through the private
seam, and asserts the same nullable `Int32` column with no comment,
default, generation or identity after, plus zero rows. The inferred
non-nullable `Int32` becomes nullable by `asNullable`, the
streaming-table merge keeps the existing field, and the result is an
unchanged schema; Codex is right that this is an unchanged-schema
assertion, as in the original, not evidence of a mutation. Both
inventory sites were already partial, so the counts do not move; the
ports improve what "partial" covers without inventing sites.

Verdict: accept, read-only, pending the native gates; no fresh public
run is needed since only `cfg(test)` paths change on the publicly
qualified `604a91f8d`.

## 14. What an "original suite against Sail" harness can execute, by construction (CF-0456 checkpoint)

Classifying the 56 SDP test files in the pin by execution substrate,
with `test(` declarations counted per file (grid tests expand further):

| tier                                                   | files | `test(` | grids | how the fixture runs                                                                                                                                                                                                                                                                                                              |
| ------------------------------------------------------ | ----: | ------: | ----: | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| in-JVM pipelines library (`sql/pipelines`, `sql/hive`) |    38 |     353 |     6 | a classic in-process `SparkSession`; `DatasetManager`, graph execution and AutoCDC run inside Spark; 13 files also read `sessionState`/`catalogManager`/`sparkContext`                                                                                                                                                            |
| Connect server suites (`sql/connect/server`)           |     9 |      76 |    10 | `SparkConnectServerTest` starts `SparkConnectService` in-process on a bound port in `beforeAll`, stops it in `afterAll`, and resets its execution and session managers after each test (`SparkConnectServerTest.scala:63–96`); 5 of 9 files also touch `SessionHolder`, `SparkConnectService`, `sessionState` or `catalogManager` |
| PySpark `pipelines/tests`                              |     9 |       — |     — | Connect client tests; already executed against Sail by Codex's `run.py` (7 modules, 67 executions, 63 ids)                                                                                                                                                                                                                        |

Consequences for the harness design:

1. The in-JVM tier cannot be executed against Sail by any redirection,
   because Sail is never the server in it; the pipelines library is the
   thing under test and it runs inside Spark. For this tier the only
   honest statements are "assertion-equivalent native or public port,
   verified against the reference substrate" and the reference
   substrate's own expanded names and ignored outcomes. Codex's
   isolated ScalaTest substrate from the published 4.2.1 `tests.jar`
   artifacts is the right tool for enumerating that tier; its passes
   are an oracle, not Sail acceptance, as Codex says.
2. The Connect tier is not redirectable as written either: the base
   class owns the server lifecycle and manager resets, so running the
   original bodies against Sail means a substituted fixture base (Sail
   listening on the bound port, no in-process managers), and the five
   files that reach into `SessionHolder` or the session state keep
   assertions a replaced base cannot satisfy. The bodies that use only
   the client are few: `PipelineEventStreamSuite` (3),
   `PipelinesHandlerSuite` (2), and parts of
   `PipelineRefreshFunctionalSuite` (9, but it references
   `SparkConnectService`). A harness for this tier should be described
   as "original test bodies on a replaced base", with the replaced
   lines listed, never as the original suite.
3. The Python tier is the only one where the original tests run against
   Sail by construction, and it is already covered.

So "full original-suite acceptance" decomposes into: Python executed as
is; Connect bodies on a declared replacement base where the body is
client-only; in-JVM sites by equivalence to the reference substrate.
The inventory's `scala_suite_executed = false` is permanent for the
third tier, and the design should say so rather than treat it as a gap
to close.

### 14.1 Corrections from the reference substrate (CF-0458)

- `PipelinesHandlerSuite` was listed in §14 among the client-only
  Connect bodies. It is not: it extends `SparkFunSuite`, not the Connect
  server base, and both tests call `PipelinesHandler.throwRunFailure`
  and inspect the thrown value in-process
  (`PipelinesHandlerSuite.scala:26`, `:49–62`). It is a pure in-JVM
  helper contract, portable only by equivalence. Folder classification
  is a first cut; each body has to be audited, as Codex says, and
  `PipelineEventStreamSuite`'s client-facing bodies still need the base
  replaced explicitly before they count.
- `MaterializeTablesSuite` is abstract (`:39`) with two concrete
  subclasses, `DefaultMaterializeTablesSuite` (`:33`) and
  `HiveMaterializeTablesSuite` (`sql/hive/.../HiveMaterializeTablesSuite.scala:23`),
  so every test in it runs twice at runtime, once per substrate. The
  static inventory of 462 declarations did not encode that; Codex's
  dependency-complete registration probe (36 concrete suite classes,
  554 runtime names, no unresolved classes or ignored tags) is the
  right denominator for the in-JVM tier, and the substrate's 29/29
  `DefaultMaterializeTablesSuite` pass on Spark is its oracle baseline,
  not Sail acceptance.
- The design decomposition stands as Codex restates it: Python as is,
  Connect bodies on an explicitly replaced fixture base, in-JVM sites by
  native internal equivalence, with no promise that unchanged in-JVM
  Spark classes execute against Sail.
