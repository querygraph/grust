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

## 15. Scope expansion outside the owned roots, checked in the pin (CF-0460)

Codex's whole-repository scan found SDP assertion sites outside the
three test roots the inventory counted. Each located in the pin:

| site                                                                           | static `test(` | runtime | notes                                                                                                                                                                    |
| ------------------------------------------------------------------------------ | -------------: | ------: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `execution/command/CreatePipelineDatasetAsSelectParserSuiteBase.scala` (trait) |             14 |      28 | runs once per concrete suite below                                                                                                                                       |
| `command/v2/CreateMaterializedViewAsSelectParserSuite.scala`                   |              1 |       1 | own test plus the 14 inherited                                                                                                                                           |
| `command/v2/CreateStreamingTableAsSelectParserSuite.scala`                     |              0 |       0 | only `override val datasetSqlSyntax = "STREAMING TABLE"`; the 14 inherited                                                                                               |
| `command/DDLSuite.scala:2522–2541`                                             |              2 |       2 | `CREATE MATERIALIZED VIEW` / `CREATE STREAMING TABLE` executed directly → `UNSUPPORTED_FEATURE.CREATE_PIPELINE_DATASET_QUERY_EXECUTION`, parameter `pipelineDatasetType` |
| `connect/service/SparkConnectSessionHolderSuite.scala:676`                     |              1 |       1 | "Pipeline execution cache": cache, get, `removeAllPipelineExecutions`, get                                                                                               |
| `connect/service/SparkConnectSessionManagerSuite.scala:158`                    |              1 |       1 | "Pipeline execution cache is cleared when the session holder is closed"                                                                                                  |

Totals from the pin: 19 static declarations, 33 runtime names. Codex
reported 20 static, counting three parser suites and one own test for
the plain streaming-table suite; the pin has two concrete parser suites
and the streaming-table one adds none. Either a third file exists under
a name my `AsSelectParserSuite` listing does not match, in which case
Codex should name its path, or the expansion is 19 and 33. The
`HiveClientSuite` HQL materialized-view hit is Hive's own table type,
not SDP, as Codex says.

Classification by the §14 tiers: the parser suites and `DDLSuite` are
in-JVM SQL-core tests (parser and `sql()` against a classic session),
so their obligations map by equivalence: Sail must parse the same
`CREATE MATERIALIZED VIEW` and `CREATE STREAMING TABLE … AS SELECT`
syntax the 14 shared cases cover, and must reject direct execution of
either with that condition and parameter. The two session suites are
Connect server internals (`SessionHolder` cache lifecycle); they map
to Sail's own session-scoped pipeline-execution cache and its clearing
on session close, as behavioural equivalence, never as executed
original classes. None of the six is a Python site, and none changes
the §3 conclusion.

### 15.1 Correction (CF-0462): the third parser suite

The third concrete parser suite is
`command/v2/CreateStreamingTableParserSuite.scala` (class at `:28`,
`extends CommandSuiteBase`), with one own test at `:31`, "CREATE
STREAMING TABLE without subquery is parsed correctly", which parses
`CREATE STREAMING TABLE st COMMENT 'populate with flow later'` and
compares a `CreateStreamingTable` plan. My §15 listing matched file
names on `AsSelectParserSuite` and so missed it; a content search for
the `CreateStreamingTable` and `CreateMaterializedView` plan nodes under
the command tests finds no others. The expansion is therefore 20
static declarations (14 shared, 1 materialized-view own, 1 plain
streaming-table own, 2 `DDLSuite`, 2 session lifecycle) and 34 expected
runtime names, the latter unasserted until Codex's collector covers the
outside roots. The plain `CREATE STREAMING TABLE` without a query, to be
populated by a later flow, is a distinct parser obligation for Sail and
stays in scope.

## 16. `ORIGINAL-SUITE-EXECUTION-DESIGN.md`, read against §14–§15 (CF-0464)

Codex's design (its working tree at the time of reading) selects the
three routes of §14 with the same boundaries: original Python modules
unmodified against Sail's endpoint, all 67 executions retained; original
client-facing Scala bodies on a declared replacement fixture base with
every replaced helper and line recorded; engine-internal Scala contracts
by assertion-equivalent native fixtures with the original suite as the
reference. The `original_scala_suite_executed_on_sail` flag stays false
for in-JVM classes by construction, and native conformance is a separate
verdict rather than a relabelling. Both §14.1 corrections are in it:
`PipelinesHandlerSuite` is routed to a native contract port, and
`PipelineEventStreamSuite` bodies are to be classified after reading
their full fixtures. The §15 expansion is carried as an explicit
completion blocker of 20 declarations, with the no-query streaming-table
parser test included and the Hive HQL hit excluded with its reason.

The conformance ledger it requires per obligation, a stable execution
instance, source binding including inner loops, the reference outcome
with non-pass states kept distinct, the Sail route and adapter revision
with replaced fixture lines proven to reach the same session, every
original comparison with a defined correspondence, and a verified full
Sail execution with cleanup, is the right bar, and its prohibition list
(no table-kind or streaming substitution, schema weakening, assertion
normalisation, deselection, or omitted reset and CDC effects) matches
the rules this record has applied. The build order (collector and
inventory extension first, then remaining reference profiles, then a
first client-facing adapter on a batch case, then native ports driven by
actual failing obligations) is the one I would choose. Nothing to
challenge.

## 17. `DDLSuite:2522–2541` direct-execution rejection, candidate `25173ed90` on `807d66b15` (CF-0466)

Codex verified the gap on the actual parent CLI: direct `CREATE
MATERIALIZED VIEW … AS SELECT` and `CREATE STREAMING TABLE … AS SELECT`
were rejected with an unstructured "pipeline declarations require a
pipeline registration context". Spark raises
`QueryCompilationErrors.unsupportedCreatePipelineDatasetQueryExecutionError`
(`QueryCompilationErrors.scala:4394–4400`): a
`SparkUnsupportedOperationException`, which `extends
UnsupportedOperationException with SparkThrowable`
(`SparkException.scala:277–283`), condition
`UNSUPPORTED_FEATURE.CREATE_PIPELINE_DATASET_QUERY_EXECUTION`, parameter
`pipelineDatasetType`, SQLSTATE `0A000` from the parent class
(`error-conditions.json:7905–7999`, `:8338`), message "The feature is
not supported: Direct execution of a CREATE ... <pipelineDatasetType>
query. To create a pipeline dataset, create and execute a pipeline with
a SQL file containing your query attached in the pipeline definition."
PySpark maps `java.lang.UnsupportedOperationException` to its
`UnsupportedOperationException` (`connect.py:485`).

The candidate's seven paths: `statement.rs` routes
`Statement::CreatePipelineDataset` to a new
`pipeline::direct_dataset_execution_error(streaming)` that builds the
structured error with exactly those fields, with the message's two
template parts joined by the single space Spark uses for a parent and
sub-condition; `CreatePipelineFlow` keeps its previous unstructured
rejection, which no original site asserts; `error.rs` adds the class
chain `SparkUnsupportedOperationException → UnsupportedOperationException
→ RuntimeException → Exception → Throwable → Object`. Native tests pin
class, condition, state and parameter for both kinds, prove the
pipeline registration lowering still produces a `Dataset` with the
right `streaming` flag and query for the same SQL, prove an ordinary
`CREATE TABLE … AS SELECT` still lowers to its command, and check the
full `ErrorInfo` through `tonic::Status`. The public test raises
`UnsupportedOperationException` with condition, state and parameter for
both kinds and asserts the table does not exist before or after, which
is `DDLSuite`'s two assertions plus the no-effect check.

Verdict: accept, read-only, pending the native gates and the paired
public run. On landing, the two `DDLSuite` sites of §15 can move to
partial by equivalence; no execution, registration or effect path
changes.

### 17.1 Correction (CF-0468): `CREATE FLOW` has original sites too

§17 said that no original site asserts the unstructured rejection of a
directly executed `CREATE FLOW`. That was true of the scope searched for
datasets and is superseded by four declarations Codex's flow audit
found, all verified in the pin:

- `command/v2/CreateFlowCommandSuite.scala` (`:32`, `extends
CommandSuiteBase with AnalysisTest`), three parser tests: "comment is
  correctly parsed" (`:35`), "multipart flow names are correctly
  parsed" (`:46`), "INSERT subquery is correctly parsed" (`:58`). A
  content search for the `CreateFlowCommand` node finds no other suite.
- `DDLSuite.scala:2544–2554`: with `table1` and `table2` pre-created,
  `CREATE FLOW f AS INSERT INTO table2 SELECT * FROM table1` executed
  directly must raise `UNSUPPORTED_FEATURE.CREATE_FLOW_QUERY_EXECUTION`
  with empty parameters. Spark raises it from
  `QueryCompilationErrors.unsupportedCreatePipelineFlowQueryExecutionError`
  (`:4388–4392`), a `SparkUnsupportedOperationException` with no
  parameters, SQLSTATE `0A000`, message "The feature is not supported:
  Direct execution of a CREATE FLOW statement is not supported. To
  create a flow, create and execute a pipeline with a SQL file
  containing your statement attached in the pipeline spec."
  (`error-conditions.json:7990–7994`).

The expansion is therefore 24 declarations and 38 expected outside-root
runtime names, with the canonical generator at 486; none observed yet.
The `CreatePipelineFlow` arm that `25173ed90` leaves unstructured is a
separate unit after that candidate qualifies, with the same class chain
and the flow condition. Codex's caution stands: the flow parser tests
accept multipart names and an `INSERT` subquery at the AST level, and
pipeline registration's own restrictions on them are a separate
contract that must not be weakened to satisfy parser observations.

### 17.2 Why Spark's rejected `CREATE FLOW` still runs its `INSERT` (CF-0470), and candidate `c50ef2253`

Codex observed on Spark 4.2.1 that after `CREATE FLOW f AS INSERT INTO
table2 SELECT * FROM table1` is rejected, `table2` holds `[[1],[2]]`:
the nested insert ran. The cause is in the pin, and it is structural:

1. The rejection lives in physical planning, not analysis: the
   `Pipelines` strategy throws for `CreateFlowCommand`,
   `CreateMaterializedViewAsSelect` and `CreateStreamingTableAsSelect`
   (`SparkStrategies.scala:892–904`).
2. `CreateFlowCommand(name, flowOperation, comment)` is a `BinaryCommand`
   whose right child is the flow operation (`v2Commands.scala:2295–2306`;
   `BinaryCommand extends Command`, `Command.scala:43`).
3. `spark.sql` executes commands eagerly: `eagerlyExecuteCommands`
   matches the root `Command` and runs it with
   `CommandExecutionMode.NON_ROOT` (`QueryExecution.scala:270–277`), and
   in that mode `commandExecuted` is
   `analyzed.mapChildren(eagerlyExecuteCommands)` (`:231–236`): the
   root's command children are executed first, so the resolved
   `INSERT` writes `table2`. Only then is the root planned and the
   strategy throws.

For the dataset forms the child is a query, not a command, so nothing
executes before the throw, which is why those `DDLSuite` cases create
no table while the flow case writes. The original `DDLSuite:2544–2554`
asserts only condition, state and empty parameters; it does not assert
the insert's effect either way.

Candidate `c50ef2253` on `25173ed90` (five paths, replacing the failed
`8536dee17`, retained): `Statement::CreatePipelineFlow` now returns the
structured `SparkUnsupportedOperationException` with
`UNSUPPORTED_FEATURE.CREATE_FLOW_QUERY_EXECUTION`, SQLSTATE `0A000`, empty
parameters and the template message, while the pipeline registration
path still lowers the same statement to a `Flow`; the public test ports
exactly the original's assertions with `table1`/`table2` pre-created;
and Sail's rejection-before-write is kept as a separate Sail-only policy
regression (`test_direct_execution_policy.py`) asserting both tables
unchanged. That split is right: the original contract is the
diagnostic, Spark's write-then-throw is a side effect no original site
asserts and not one to reproduce, and Sail's standing
rejection-before-effects contract is stated as Sail's own.

Verdict: accept, read-only, pending the native and public gates. The
earlier failed candidate asserted target-row preservation
cross-engine, which Spark fails for the reason above; removing that
cross-engine assertion and keeping it Sail-only is the correct
resolution, not a weakening.

## 18. Pipeline dataset clause validation, candidate `7d7c3640f` on `f9982230d` (CF-0474)

Spark validates a `CREATE MATERIALIZED VIEW` / `CREATE STREAMING TABLE`
statement in `SparkSqlParser.visitCreatePipelineDataset`
(`SparkSqlParser.scala:1521–1600`) in a fixed order before building the
plan: bucket spec, then `OPTIONS`, then `STORED AS`, then Hive SerDe
row format, then `LOCATION`, each raising
`QueryParsingErrors.operationNotAllowedError` (`_LEGACY_ERROR_TEMP_0035`,
message template "Operation not allowed: <message>.", no SQLSTATE,
`error-conditions.json:9030–9034`, `QueryParsingErrors.scala:512–516`)
as a `ParseException` with the single `message` parameter; and for the
materialized view only, a missing query raises "Unable to find query for
CREATE MATERIALIZED VIEW statement." (`:1596–1599`). The base suite
asserts condition and exact `message` parameter for Location, STORED
AS, SerDe, Bucket and Options under both syntaxes (`:89–104`,
`:131–162`, `:197–226`); the materialized-view suite asserts the
missing-query message (`CreateMaterializedViewAsSelectParserSuite.scala:28–34`);
the plain `CREATE STREAMING TABLE … COMMENT …` without a query must
parse (§15.1).

The candidate (nine paths): a shared `pipeline/dataset.rs::validate`
called from both the direct-SQL lowering, ahead of the §17
direct-execution rejection, and the registration lowering, ahead of the
generic table lowering. Its `if … else if` chain is Spark's order,
independent of clause order in the statement, with the five message
texts verbatim and the materialized-view-only missing-query case; the
error is the structured `ParseException` with the legacy condition, the
`message` parameter, an empty SQLSTATE and the templated body. The
Connect codec now omits `sqlState` from `ErrorInfo` when the structured
state is empty instead of sending an empty string, which is what
Spark's client sees for a template without a state (PySpark
`getSqlState()` is `None`), with a transport regression for it.

Tests: native, both syntaxes and both lowering routes for all five
clauses with exact parameter and body, and the same clause on an
ordinary `CREATE TABLE` still lowering to its command; missing query
rejected on both routes for the view and the no-query streaming table
still lowering to an empty declaration with its comment; precedence
with three forbidden clauses in two orders resolving to the bucket
message. Public: the five clauses under both syntaxes with condition,
exact parameter and `None` SQLSTATE, and the missing-query message.
Codex's paired oracle found Spark raising exactly these on all eleven
cases and the parent Sail returning the §17 rejection instead, which
the new ordering before that rejection fixes.

Verdict: accept, read-only, pending the native gate. On landing,
`CreatePipelineDatasetAsSelectParserSuiteBase:89`, `:131`, `:145`,
`:197`, `:212` and the materialized-view suite's `:31` can move to
partial by equivalence under both syntaxes. Column constraints (`:105`)
and collation (`:253`) remain open, as Codex says.

### 18.1 Canonical IDs (CF-0475)

Codex records the selected declarations by canonical inventory ID
rather than my shorthand: `CreatePipelineDatasetAsSelectParserSuiteBase.scala:89`,
`:131`, `:145`, `:197`, `:212`, each inherited under both the
materialized-view and the streaming-table `AS SELECT` suites, and
`CreateMaterializedViewAsSelectParserSuite.scala:30` for the
missing-query case (the `test(` line; §18 wrote `:31`, which is the
no-query streaming-table test in `CreateStreamingTableParserSuite.scala`).
The no-query streaming-table case stays explicit partial coverage,
since its internal-plan correspondence is not asserted. Constraints
(`:105`) and collation (`:253`) remain open.

## 19. Positive parser ports `19b7e9c05`; the wrapper boundary that stopped `7d7c3640f` (CF-0478, CF-0479)

**`19b7e9c05`, test-only, accepted.** Three test modules on `f9982230d`,
no product change. It ports nine original declarations: the base
suite's column definitions (`:32`), partitioning (`:77`), comment
(`:119`), `USING` (`:163`), `IF NOT EXISTS` (`:174`) and table
properties (`:185`), each under both `AS SELECT` syntaxes, with the
nested struct column's types, nullability, comment and absent default,
generation and identity asserted; and the three `CreateFlowCommandSuite`
cases (`:35`, `:46`, `:58`): optional comment, all multipart name
components, and the `INSERT OVERWRITE … PARTITION … BY NAME` child
preserved as syntax. Two correspondence limits are stated rather than
hidden: Sail's configured `STRING` type for Spark's `StringType`, and
no Spark column metadata. The flow child is tested as syntax only, with
no broadening of registration acceptance. CTAS subqueries (`:227`) and
collation (`:253`) are not claimed. Verdict: accept as a faithful
native port; the inventory move to 109 reviewed and 80 partial that
Codex expects follows from these nine.

**The wrapper boundary.** `7d7c3640f` passed every native gate and the
eleven paired Spark cases, then failed one frozen Sail public test that
expects `location.sql` inside an `AnalysisException` when a
`LOCATION` clause is rejected during registration. Codex treats this
as an original-scope dependency and states the requirement as carrying
the parse error's class, condition, parameters and absent state _and_
the source file name through registration. The pin says where the file
name actually travels:

- `PipelinesHandler.defineSqlGraphElements` calls
  `SqlGraphRegistrationContext.processSqlFile(sqlText, sqlFilePath,
session)` with no `try` (`PipelinesHandler.scala:222–233`).
- `processSqlFile` calls `splitSqlFileIntoQueries`, which runs
  `spark.sessionState.sqlParser.parsePlan` on each statement with no
  `catch` (`SqlGraphRegistrationContext.scala:637–648`); the
  `QueryOrigin` with `filePath`, `sqlText`, `line` and `startPosition`
  is built only for a plan that parsed (`:681–689`).
- The file origin reaches an error only through
  `SqlGraphElementRegistrationException(msg, queryOrigin)`, an
  `AnalysisException` with condition
  `PIPELINE_SQL_GRAPH_ELEMENT_REGISTRATION_ERROR`, SQLSTATE `42000`,
  parameters `message`, `offendingQuery` ("\nOffending query:\n<sql>\n")
  and `codeLocation` ("Query defined at <file>:<line>", or "Query
  defined in file <file>") (`:63–95`, `error-conditions.json:6024–6031`),
  thrown by the handlers for registration-level failures such as an
  unsupported plan kind (`:168–172`) or a catalog expression (`:554–558`).

So in Spark a `CREATE MATERIALIZED VIEW … LOCATION …` inside a pipeline
SQL file fails in `parsePlan` and reaches the Connect client as a raw
`ParseException`, `_LEGACY_ERROR_TEMP_0035`, with its parser query
context and no file name; `SqlPipelineSuite:599` already shows
`processSqlFile` surfacing a raw `ParseException` for the temp-view
qualifier. The frozen Sail assertion therefore encodes Sail's earlier
behaviour, not Spark's. Two consequences for the design phase Codex has
flagged:

1. The decisive control is cheap and should come first: register the
   `LOCATION` statement through `DefineSqlGraphElements` on Spark 4.2.1
   and record the client's class, condition, parameters and whether any
   file name appears. If it is the raw parse error, changing the frozen
   test to expect that is alignment to the oracle, not relaxation, and
   `7d7c3640f` needs no wrapper to land.
2. The wrapper that does exist in Spark is the registration-level one
   above, and it is the right target for the origin design: Sail's
   `PreparationFailure::Analysis` string should become that structured
   `AnalysisException` with the three parameters and the exact
   `codeLocation` and `offendingQuery` formats, while parse-level errors
   pass through raw as `7d7c3640f` already does. Carrying a file name on
   a parse error would be a Sail invention.

### 19.1 Resolution (CF-0481): the oracle agreed, and candidate `14eb7766f`

Codex ran the decisive control: through `DefineSqlGraphElements` on
Spark 4.2.1 and on the candidate, all eleven inputs produce the
`ParseException` with `_LEGACY_ERROR_TEMP_0035`, exact parameters,
absent SQLSTATE, no file name and no table. The requirement to carry a
file name on the parser error is withdrawn, and the old Sail BDD regex
expecting `location.sql` is recorded as encoding Sail's earlier
behaviour; correcting it is alignment to the oracle, not the removal
of an original Spark assertion. The failed 299/1 run is preserved.

`14eb7766f` rebases the validator onto the accepted `19b7e9c05`: its
product paths are byte-identical to `7d7c3640f` (an empty diff between
the two commits outside tests), the one BDD step changes from `fails
with location.sql` to `fails with Specifying location is not
supported`, and the public tests grow to 22 cases: the five clauses
under both syntaxes through both the direct `spark.sql` and the
registration API, each asserting the condition, exact `message`
parameter, `None` SQLSTATE and the absence of the fixture file name in
the error text, plus the missing-query case on both APIs.

Verdict: accept, read-only, pending the native gate and the refreshed
public harness with exactly one source-hash change and the same 300
ids. The §18 mapping of the clause and missing-query sites to partial
follows on landing; the registration-level origin wrapper remains a
separate future design, as Codex states.

### 19.2 Harness binding correction (CF-0483)

§19.1 repeated Codex's "exactly one source-hash change" for the
refreshed public harness. Codex's audit found the old preparation did
not bind `.feature` files or the BDD step helpers, so it observed zero
changed hashes despite the one changed assertion line: a source-binding
gap in the harness, not licence to ignore the change. The new
preparation keeps every old hash and the identical 300 case ids, newly
binds 23 indirect inputs (both selected feature trees and the
`testing/spark` helper Python), and proves the actual source diff in
those scopes is the single `sql.feature` regex replacement, with the
previous and current feature hashes and every newly bound path
recorded. Spark's 22 strengthened public cases passed. No original
Spark source or assertion changed.

## 20. Registration error fidelity design, read against the pin (CF-0487); correction to §19

**Correction.** §19 point 2 suggested that Sail's registration-level
failures "should become" the structured
`PIPELINE_SQL_GRAPH_ELEMENT_REGISTRATION_ERROR`. They already are:
`pipelines/sql.rs:167–179` builds that condition with `offendingQuery`
("\nOffending query:\n<sql>\n") and `codeLocation` ("Query defined at
<file>:<line>") from the original statement span, and Codex's
twelve-case `DefineSqlGraphElements` baseline shows both fields match
Spark on every wrapper case tried, including Unicode, embedded
semicolons, comments and a second statement. The remaining gaps are
per-producer wording and raw-versus-wrapper classification, which is
what the design addresses.

**The design** (`REGISTRATION-ERROR-FIDELITY-DESIGN.md`, Codex's working
tree) tabulates nine producers against Spark's contract. Checked in the
pin:

- The registration-level messages Spark wraps are fixed strings in the
  handlers: "Unsupported plan <nodeName> parsed from SQL query"
  (`SqlGraphRegistrationContext.scala:170`); the flow policies "Unable
  flow type. Only INSERT INTO flows are supported." (`:425`), "Unable
  to resolve target dataset name for INSERT INTO flow" (`:463`),
  "Partition spec may not be specified for flow target." (`:481`),
  "Column schema may not be specified for flow target." (`:487`),
  "INSERT OVERWRITE flows not supported." (`:493`), "IF NOT EXISTS not
  supported for flows." (`:499`), "Only INSERT INTO by name flows
  supported." (`:505`); the catalog expression wrapper (`:556`); and the
  partition helper's "Invalid partitioning transform (<other>)"
  (`:573`), "Only single column based partitioning is supported."
  (`:581`), "Multipart partition identifier not allowed." (`:587`).
  Each is a separate producer-owned message, which matches the design's
  insistence on separate units with exact wording rather than one
  generic string.
- The multipart flow name is the one case that is raw, not wrapped:
  `CreateFlowHandler.handle` throws `new AnalysisException(
"MULTIPART_FLOW_NAME_NOT_SUPPORTED", flowName)` (`:404–410`),
  template "Flow with multipart name '<flowName>' is not supported.",
  SQLSTATE `0A000` (`error-conditions.json:5400–5405`), and it does so
  before the `flowOperation match` that applies the `INSERT` policies
  (`:418` onward). `SqlPipelineSuite:580–597` intercepts exactly that
  `AnalysisException` by message. The design's first unit (a shared
  constructor for condition, class, state, template and the single
  unquoted `flowName`, applied in SQL normalisation before the `INSERT`
  policy and query lowering, and reused by the protocol name guard with
  its implicit-flow exception kept) is that contract and that order.
- Parser acceptance of multipart flow names stays (the
  `CreateFlowCommandSuite` cases of §19 remain valid), since this is a
  registration policy, not a grammar rule; the direct-execution guard
  keeps its own `CREATE_FLOW_QUERY_EXECUTION` condition (§17.2).
- "Preserve typed errors from `register_statement` through
  `PreparedSql.commit` rather than stringify and re-wrap" is the same
  rule the §19.1 fix applied to parse errors, extended to typed
  registration errors; catalog-analysis wrapping stays explicit in its
  producer, evaluation and parse failures stay raw.

Verdict on the design: consistent with the pin, nothing to challenge.
The first unit's review will check the constructor's four fields and
the unquoted, case-preserved `flowName`, the check order against a
flow that is both multipart and `INSERT OVERWRITE`, the protocol route
and its implicit-flow exception, no publication on failure, and the
original `:580` input on both engines.

### 20.1 Two spelling contracts and the four-part boundary (CF-0489)

Codex's pre-gate pin review found two details the §20 unit must
preserve; both verified:

- The `flowName` parameter differs by API. The SQL handler uses
  `rawFlowIdentifier.unquotedString`
  (`SqlGraphRegistrationContext.scala:404–407`); the protocol handler
  uses the raw `flow.getFlowName`, quoting and case included, and
  exempts the implicit flow whose name equals its target
  (`PipelinesHandler.scala:344–352`). Codex's two-API probes show it:
  `` `D.b`.`F``Q` `` renders `D.b.F`Q` through SQL and raw-quoted
  through the protocol.
- A name with four or more parts never reaches the multipart policy:
  `IdentifierHelper.toTableIdentifier` throws a raw
  `java.lang.UnsupportedOperationException("4+ part table identifier
<a.b.c.d> is not supported.")` (`GraphIdentifierManager.scala:262–276`)
  first, for flow names and targets alike, including implicit names,
  and the client sees no condition, state or parameters. The parent
  Sail reports a different class there.

Consequences accepted into the unit: both spellings are preserved per
route; the four-part arity check runs before the multipart policy for
flow names and targets; and the structured error representation keeps
an empty condition meaning "absent", with the Connect codec omitting
absent `errorClass`, `sqlState` and parameters while a classified error
with no parameters still sends `{}`. That is the transport detail the
observed boundary requires, not an activation.

### 20.2 Raw multipart flow error, candidate `c864386cc` on `14eb7766f` (CF-0491)

Thirteen paths. Product:

- `sail-common/error/pipeline.rs`: `multipart_flow_name_error(name)`
  builds `AnalysisException`, `MULTIPART_FLOW_NAME_NOT_SUPPORTED`, SQLSTATE
  `0A000`, template "Flow with multipart name '<name>' is not
  supported." and the single `flowName` parameter;
  `pipeline_identifier_arity_error(parts)` returns `None` for one to
  three parts and otherwise `java.lang.UnsupportedOperationException`
  with empty condition, state and parameters and the message "4+ part
  table identifier <a.b.c.d> is not supported.", which is
  `IdentifierHelper.toTableIdentifier` (`GraphIdentifierManager.scala:262–276`).
- `StructuredSparkError`'s `Display` prints the `[condition]` prefix
  only when a condition exists, and the Connect codec omits `errorClass`
  and `sqlState` when empty and omits `messageParameters` only when the
  condition is empty and there are none, so a classified error with no
  parameters still sends `{}` (§20.1).
- SQL normalisation (`sail-sql-analyzer/pipeline.rs`): parse the name,
  arity check, multipart policy with `parts.join(".")`, which is
  `TableIdentifier.unquotedString` (`` `D.b`.`F``Q` `` → `D.b.F`Q`),
  then the `INSERT` shape, then the target's arity. That is the handler's
  order: `toTableIdentifier(cf.name)` before `isSinglePartIdentifier`
  (`SqlGraphRegistrationContext.scala:400–407`), the `flowOperation`
  match after, the target's `toTableIdentifier` at `:461`.
- Protocol (`pipelines/graph.rs::define_flow`): parse without
  lower-casing, arity check, then the multipart policy on the raw
  `flow_name` string with the implicit-flow exemption when the raw name
  equals the raw target, then the target's arity, and only then the
  ASCII lower-casing for graph keys, factored out without changing it
  (`PipelinesHandler.scala:344–352`).
- `PreparedSql.commit` passes structured `register_statement` errors
  through as evaluation failures and keeps the registration wrapper for
  untyped ones, the §19.1 rule extended as the design said.

Tests: native, the original `:580` input through SQL with the draft
discarded; a typed commit error not re-wrapped with the statement
origin or file; protocol raw spelling and the implicit-flow acceptance
of `Cat.Db.F` into key `cat.db.f`; arity preceding named and implicit
rules for name, target and implicit cases; analyzer-level spelling for
three names across `INSERT INTO`, `INSERT OVERWRITE` and `PARTITION`
operations, proving name precedence over the `INSERT` policy; arity for
name and target; a quoted dot remaining one component while multipart
syntax still parses; and the codec omitting all three keys and the
prefix for the unclassified error. Public, 21 cases on both engines:
spelling per API for three names, arity with `None` condition, state
and parameters and no `[]` in the message, the quoted dot, the implicit
exemption, precedence over three `INSERT` forms, and the original
`:580` with both external-table fixtures and the file name absent.

Verdict: accept, read-only, pending the native gate (279 expected) and
the Spark public probe. On landing, `SqlPipelineSuite:580` moves to
partial, and the design's remaining producers follow as separate
units.

### 20.3 Accounting correction (CF-0493)

§20.2 said `SqlPipelineSuite:580` "moves to partial" on landing. It was
already a reviewed partial site in the canonical inventory, with its
remaining assertions recording the missing original message and class;
`c864386cc` improves that record and leaves the counts at 116 reviewed,
87 partial, 399 unmapped. Codex's gates so far: native 279 and
fmt/strict clippy pass, Spark's 21 feature tests pass, the refreshed
Sail CLI 300 plus 67 pass; the Sail 21-case two-API replay and three
unchanged-test controls (name-normalisation bypass, absent-metadata
bypass, typed-commit re-wrap) are still running before the source
advances.

### 20.4 Pre-pin for the next units: `:525` (unsupported CTAS) and `:311` (partition transform)

`SqlPipelineSuite:524–535` ("Unsupported SQL statements throws error")
feeds `CREATE TABLE t AS SELECT 1` to `processSqlFile` and intercepts
`SqlGraphElementRegistrationException` with a message containing
"Unsupported plan". Spark produces it from the fall-through arm of
`processSqlQuery`: `"Unsupported plan ${plan.nodeName} parsed from SQL
query"` (`SqlGraphRegistrationContext.scala:168–172`), where `nodeName`
is the logical plan class's simple name, so the message is "Unsupported
plan CreateTableAsSelect parsed from SQL query" for CTAS and
"Unsupported plan Project parsed from SQL query" for a bare `SELECT`;
it is wrapped as `PIPELINE_SQL_GRAPH_ELEMENT_REGISTRATION_ERROR` with
`offendingQuery` and `codeLocation` (§19). The candidate's review will
check that the CTAS rejection fires only in pipeline normalisation,
leaves ordinary SQL CTAS untouched, carries that exact node-named
message as the `message` parameter with the wrapper's three fields, and
publishes nothing. `SqlPipelineSuite:311–322` ("non-identity partition
columns") feeds `PARTITIONED BY (year(id1))` and asserts a message
containing "Invalid partitioning transform"; Spark's `PartitionHelper`
renders `"Invalid partitioning transform ($other)"` with the transform's
own string (`:573`), and its siblings are "Only single column based
partitioning is supported." (`:581`) and "Multipart partition
identifier not allowed." (`:587`). Both sites belong to the wrapped
tier; neither is a raw error.

### 20.5 Unsupported table-as-select in a pipeline file, candidate `18604c01a` on `c864386cc` (CF-0498)

Seven paths, product in two: pipeline normalisation now rejects a
`CreateTableAsSelect` command with `SqlError::AnalysisError("Unsupported
plan <node> parsed from SQL query")`, where `<node>` is
`CreateTableAsSelect` for `CREATE TABLE … AS` and `CREATE TABLE IF NOT
EXISTS … AS`, and `ReplaceTableAsSelect` for `REPLACE TABLE … AS` and
`CREATE OR REPLACE TABLE … AS`; and the SQL preparation places an
`AnalysisError`'s message directly into the existing registration
wrapper instead of the error's `to_string()`, so no prefix leaks into
the `message` parameter. The node mapping is Spark's parser:
`visitCreateTable` builds `CreateTableAsSelect` carrying `ifNotExists`
(`AstBuilder.scala:5702`) and `visitReplaceTable` builds
`ReplaceTableAsSelect` with `orCreate` (`:5785`), and
`processSqlQuery`'s fall-through arm renders `nodeName` (§20.4). The
initial create-only candidate was rightly superseded once Sail's shared
`CommandNode::CreateTableAsSelect` was seen to carry the replace modes
too. Ordinary SQL CTAS and RTAS still lower to their command; the
rejection exists only in pipeline normalisation.

Tests: native, the original `:525` input through `register_sql` yields
the `AnalysisException` `PIPELINE_SQL_GRAPH_ELEMENT_REGISTRATION_ERROR`,
SQLSTATE `42000`, with the three parameters exact (`message` as above,
`offendingQuery` "\nOffending query:\nCREATE TABLE t AS SELECT 1\n",
`codeLocation` "Query defined at a.sql:1") and nothing published; the
analyzer contrast for all four forms. Public, six cases on both engines
with the original external-table fixtures: the original `:525`, a
Unicode comment prefix placing the statement at line 3, a second
statement at line 4 with a trailing comment retained in the offending
text, `IF NOT EXISTS`, `CREATE OR REPLACE` and `REPLACE`, each with the
three parameters exact and no table created.

Verdict: accept, read-only, pending the native gate and the Spark mode
probe. On landing the `:525` record is strengthened on the same terms
as `:580` (already partial; counts unchanged).

### 20.6 Pre-pin for the `INSERT` flow policy unit (CF-0501)

Codex's twelve-case Spark oracle for the next unit is confirmed in the
pin, with one structural consequence:

- `INSERT INTO … IF NOT EXISTS` never reaches the graph: `AstBuilder`
  raises `invalidStatement("INSERT INTO ... IF NOT EXISTS")`
  (`AstBuilder.scala:1045`), a `ParseException`
  `INVALID_STATEMENT_OR_CLAUSE` with `operation` = `toSQLStmt(...)`, the
  upper-cased statement text, SQLSTATE `42601`
  (`QueryParsingErrors.scala:535–540`, `error-conditions.json:4827–4832`),
  message "The statement or clause: INSERT INTO ... IF NOT EXISTS is
  not valid." It is a raw parser error like §18's, carrying no file
  name.
- For a flow operation that parsed, `CreateFlowHandler` applies the
  registration-wrapped policies in this order: partition spec,
  user-specified columns, `overwrite`, `ifPartitionNotExists`, then
  `!byName` (`SqlGraphRegistrationContext.scala:479–506`), after the
  raw multipart name check (§20.1). Since `IF NOT EXISTS` is legal in
  Spark's grammar only with `INSERT OVERWRITE`, and the `overwrite`
  check fires first, the handler's "IF NOT EXISTS not supported for
  flows." arm is unreachable from SQL; it stays in the design only as
  Spark's text, not as a Sail obligation with a reachable fixture. A
  plain `INSERT INTO … BY NAME` registers.

So the unit must split Sail's current combined message into the
producer-owned strings of §20 in that precedence, route the
`IF NOT EXISTS` form to the raw parser error, and keep the frozen BDD
expectation only where the oracle agrees, correcting it per case with
the Spark result recorded, as §19.1 did. Every existing query shape and
assertion stays.

### 20.7 Wording refinement (CF-0503)

§20.6 said `IF NOT EXISTS` is "legal in Spark's grammar only with
`INSERT OVERWRITE`". More precisely: the ANTLR grammar accepts the
`IF NOT EXISTS` tokens on `INSERT INTO` as well, and it is
`AstBuilder.scala:1045` that rejects that form with
`INVALID_STATEMENT_OR_CLAUSE`; the forms that reach the flow handler
with the flag set are overwrite-only, and the earlier `overwrite` check
makes the handler's `IF NOT EXISTS` arm unreachable. The conclusion of
§20.6 is unchanged. `18604c01a` is committed with 248 native tests, the
refreshed public selection plus upstream, six paired cases, and two
unchanged-test controls failing as expected; the `:525` record is
strengthened and the counts stay 116 reviewed, 87 partial, 399
unmapped.

### 20.8 Shared `INSERT` parser validation design (CF-0504), read against the pin

Codex's design for the first `INSERT` unit: a private, pure
`validate_insert_modes(&Statement)` that rejects `INSERT INTO … IF NOT
EXISTS` as the typed `ParseException` `INVALID_STATEMENT_OR_CLAUSE`,
SQLSTATE `42601`, with the `operation` parameter, recursing only into
the statement-bearing variants (`CreatePipelineFlow`, `Explain`);
applied to every parsed AST right after `SqlSource` parsing on both
parsing entry points, before any file preparation; and called again
from ordinary and pipeline AST lowering for constructed-AST consumers.
Valid `INSERT OVERWRITE … IF NOT EXISTS` stays permitted by this rule;
the flow policies stay separate. Two premises, both in the pin:

- Spark parses the whole file before registering anything:
  `splitSqlTextBySemicolon` returns a `List[String]`
  (`SqlGraphRegistrationContext.scala:617–618`) and
  `splitSqlFileIntoQueries` maps `parsePlan` over it strictly
  (`:645–648`) before `processSqlFile`'s `foreach` registers
  (`:114–122`), so a parse error in a later statement is raised before
  an earlier statement's registration error. Validating every AST
  after parsing and before preparation reproduces that precedence.
- `visitInsertIntoTable` rejects `IF NOT EXISTS` unconditionally for
  the `INTO` form (`AstBuilder.scala:1044–1046`), so the rule inspects
  only the insert mode and leaves dataset desugaring alone.

The placement in Sail's shared SQL layer rather than the pipeline layer
is forced by a Sail gap Codex found: ordinary `InsertInto` currently
lowers `IF NOT EXISTS` into a command flag, so direct SQL accepts a
statement Spark's parser rejects; the shared rule corrects direct SQL
and pipeline files together. No new AST, source or error shape, no
blanket validation policy, no synthetic file wrapper; query-context
origin completion stays unqualified. Nothing to challenge; the
candidate's review will check the operation text (`INSERT INTO ... IF
NOT EXISTS`, upper case), precedence of this parse error over an
earlier statement's flow-name or registration error within one file,
the direct-SQL path, and that `INSERT OVERWRITE … IF NOT EXISTS` still
parses.

### 20.9 Shared `INSERT` mode validation, candidate `b48abc5a8` on `18604c01a` (CF-0506)

Nine paths. Product: `sail-sql-analyzer/validation.rs::validate_insert_modes`
rejects `InsertInto` with `into_or_overwrite = Into` and
`if_not_exists` set as the typed `ParseException`
`INVALID_STATEMENT_OR_CLAUSE`, SQLSTATE `42601`, `operation` =
`INSERT INTO ... IF NOT EXISTS`, message "The statement or clause: INSERT
INTO ... IF NOT EXISTS is not valid.", recursing only into
`CreatePipelineFlow` and `Explain`; it runs over every statement after
both `SqlSource` parse paths (`parse_statements` and
`parse_statements_with_spans`) and again at the head of both the
ordinary and the pipeline AST lowering. That is the §20.8 design and
`AstBuilder.scala:1044–1046`'s rule, in Spark's whole-file order.

Tests: native, six statement shapes (plain, `BY NAME`, static
`PARTITION`, inside `CREATE FLOW` with single and multipart names,
inside `EXPLAIN`) produce the identical typed error on `parse_one_statement`,
both `SqlSource` paths, and both lowerers from a syntactic AST; a
whole-file precedence test puts the invalid `INSERT` after a multipart
flow, an unsupported CTAS and a catalog expression and gets the parse
error each time, with the Connect-level test proving the catalog
resolver is never invoked; and the positive control keeps `INSERT
OVERWRITE … PARTITION(p=1) IF NOT EXISTS`, with and without `BY NAME`,
lowering with `if_not_exists` set, the partition kept and the overwrite
insert mode. Public, 15 cases: the six shapes through ordinary SQL and
the pipeline API, and three whole-file precedence cases, each asserting
condition, state, parameter, message and the absence of the file name.

The one native failure is the existing golden
`gold_data/plan/ddl_insert_into.json`: for `INSERT INTO TABLE … PARTITION
(p1 = 3) IF NOT EXISTS SELECT …` its recorded Spark exception already
reads `INVALID_STATEMENT_OR_CLAUSE … INSERT INTO ... IF NOT EXISTS`,
while the recorded Sail output was a successful plan with
`ifNotExists = true`. The fixture therefore documents the bug this unit
fixes, and regenerating only that case's Sail output with the official
generator, with inputs, exceptions and all other outputs unchanged, is
the correct update, not a rewritten expectation.

Verdict: accept, read-only, pending the golden regeneration check and
the native and public gates.

### 20.10 Final candidate `cbeec8f93` (CF-0508)

`cbeec8f93` differs from the accepted `b48abc5a8` in one file,
`gold_data/plan/ddl_insert_into.json`: 32 cases before and after,
exactly one changed, its input and its recorded Spark exception
identical, its Sail output flipped from a successful `insertInto` plan
with `ifNotExists = true` to the failure "[INVALID_STATEMENT_OR_CLAUSE]
The statement or clause: INSERT INTO ... IF NOT EXISTS is not valid.".
Product and tests are byte-identical to the reviewed candidate. The
§20.9 verdict extends to `cbeec8f93` unchanged: accept, pending the
refreshed public selection and the rule, source-order and
defensive-lowering controls. Counts stay 116 reviewed, 87 partial, 399
unmapped; this shared rule supports original sites and creates none.

### 20.11 Flow INSERT policy producers, candidate `4fca6f3d4` on `cbeec8f93` (CF-0513)

The unit replaces the combined "Only INSERT INTO by name flows
supported; partition specifications and target column lists are not
allowed." message with Spark's five producer strings, evaluated in
`sail-sql-analyzer/src/pipeline.rs` after the raw multipart flow-name
check and before the target identifier is lowered. Read against the pin:

- Order and strings. Spark's `validateInsertIntoFlow`
  (`SqlGraphRegistrationContext.scala:475–510`) checks `partitionSpec`
  ("Partition spec may not be specified for flow target."), then
  `userSpecifiedCols` ("Column schema may not be specified for flow
  target."), then `overwrite` ("INSERT OVERWRITE flows not
  supported."), then `ifPartitionNotExists` ("IF NOT EXISTS not
  supported for flows."), then `!byName` ("Only INSERT INTO by name
  flows supported."). Sail's chain is partition → column list → overwrite
  → not-by-name, byte-identical strings. The missing fourth arm is the
  one §20.6/§20.7 proved unreachable: the `INTO` form is a parse error at
  `AstBuilder.scala:1045` (Sail's shared `validate_insert_modes` runs
  first), and the grammar's `OVERWRITE` arm admits `IF NOT EXISTS` only
  after a `partitionSpec` (`SqlBaseParser.g4:590`), so the partition arm
  fires first.
- Placement. Spark runs the policies inside `extractInsertFlow` before
  `IdentifierHelper.toTableIdentifier` on the target (`:460–467`), after
  the flow-name check (`:404–410`). Sail matches: `multipart_flow_name_error`
  before, `pipeline_identifier_arity_error` on the target after. The two
  four-part-target cases in the native test (`A.b.c.d`) pin that order.
- Wrapping. `SqlError::analysis(message)` reaches
  `PreparationFailure::Analysis` and `registration_error` in
  `pipelines/sql.rs`, which supplies condition, SQLSTATE 42000,
  `offendingQuery` and `codeLocation`; the public test asserts all three
  parameters and `Query defined at flow.sql:2`.
- Tests. Native: 11 operations through both entry points, plus a positive
  `c.d.output BY NAME` control. Public: the same 11 plus the three BDD
  outline inputs, exact fields. The BDD outline keeps its three inputs
  and gains an `error` column; the old shared substring was replaced by
  the per-row producer string, which is a correction of a non-Spark
  expectation, not a loosened one.
- Dependencies. No original Spark test asserts any of the five strings:
  `git grep -F` over the pin for each string, and for "Unable flow
  type", hits only `SqlGraphRegistrationContext.scala` itself. The unit
  is Spark fidelity with no inventory effect; 486/116/87/399 stands.

Residuals, pre-existing and outside this unit, recorded so they are not
rediscovered:

- `INSERT OVERWRITE t IF NOT EXISTS …` without `PARTITION` is a Spark
  parse error: probe 14 (`evidence/set-catalog-oracle/probe14_*`) on
  pyspark 4.2.1 returns `PARSE_SYNTAX_ERROR` for the form with and
  without `BY NAME`, and `TABLE_OR_VIEW_NOT_FOUND` once a partition spec
  is present. Sail's AST (`sail-sql-parser/src/ast/statement.rs:302–315`)
  declares `partition` and `if_not_exists` as independent options, so by
  the AST definition (not executed here) that text parses in Sail and
  the candidate would report "INSERT OVERWRITE flows not supported." as
  a registration error. The shared validator of §20.8 deliberately left
  the overwrite form alone; closing this is a parser-grammar unit, and
  no original site asserts it.
- The let-else fallback keeps the old combined message with a literal
  `[PIPELINE_SQL_GRAPH_ELEMENT_REGISTRATION_ERROR]` prefix, which the
  wrapper then prefixes again. It is now reachable only for a `WITH`-led
  insert or a non-`INSERT` body under `CREATE FLOW`; Spark's grammar
  admits only `createPipelineFlowHeader insertInto query`
  (`SqlBaseParser.g4:420`), so both are parse errors there, and the
  handler's "Unable flow type. Only INSERT INTO flows are supported."
  (`:425`) is reachable only from the protocol path. Same class as the
  first residual.

Verdict: accept, read-only, pending the native gate, the public
selection migration (297 retained hashes plus three new IDs) and the
paired Spark run of the 14 public cases.

### 20.11.1 Correction: "Unable flow type" is reachable from SQL

§20.11 said the handler's "Unable flow type. Only INSERT INTO flows are
supported." (`SqlGraphRegistrationContext.scala:425`) is reachable only
from the protocol path. That was read off the grammar line alone and is
wrong. `createPipelineInsertIntoFlow` takes the whole `insertInto` rule
(`SqlBaseParser.g4:420`, `:589–597`), and `withInsertInto`
(`AstBuilder.scala:931–1030`) builds three plan shapes from it:
`InsertIntoStatement` for the table, overwrite-table and both `REPLACE`
alternatives (the `REPLACE` forms carry `replaceCriteriaOpt`,
`statements.scala:258`), and `InsertIntoDir` for the two `OVERWRITE
DIRECTORY` alternatives. Probe 15 (`evidence/set-catalog-oracle/probe15_*`,
pyspark 4.2.1) confirms the parse boundary: `CREATE FLOW f AS SELECT 1`
and a `WITH`-led insert are `PARSE_SYNTAX_ERROR`; `CREATE FLOW f AS
INSERT OVERWRITE DIRECTORY … SELECT 1` parses and reaches the direct
execution rejection; `REPLACE WHERE` parses and reaches analysis; a
`WITH` inside the query (`INSERT INTO output BY NAME WITH c AS … SELECT`)
is legal.

Consequences for the registration path, from source:

- `INSERT OVERWRITE DIRECTORY` inside a pipeline SQL file reaches
  `CreateFlowHandler` as `InsertIntoDir`, matches neither
  `InsertIntoStatement` nor `UnresolvedInsert`, and yields the wrapped
  "Unable flow type. Only INSERT INTO flows are supported." So that
  string is reachable from SQL and belongs to the producer set; Sail's
  AST has `InsertOverwriteDirectory` as a separate statement, so its
  let-else fallback fires today with the combined message instead.
- `INSERT INTO t BY NAME REPLACE WHERE … SELECT` and `REPLACE USING`
  reach `validateInsertIntoFlow` as `InsertIntoStatement` with `byName`
  true and no partition, columns or overwrite; none of the five checks
  reads `replaceCriteriaOpt`, so Spark registers the flow and the replace
  criteria are dropped. Sail parses these as `InsertIntoAndReplace`, a
  different variant, so the fallback rejects them. This is a
  registers-versus-rejects divergence, not a message difference, and it
  is source-derived: no registration run of the `REPLACE` form was made.
- The `WITH`-led flow body stays a parse error in Spark and an AST-level
  acceptance in Sail, as §20.11 said.

No original site asserts any of these shapes (the §20.11 grep for the
"Unable flow type" string hit only the producer file). The residual
list for the parser-grammar unit is therefore: partition-less
`OVERWRITE IF NOT EXISTS` and `WITH`-led bodies become parse errors;
`OVERWRITE DIRECTORY` bodies produce the wrapped "Unable flow type"
message; `REPLACE` bodies either register as Spark does or are pinned
as a named deviation, which is a design decision, not a port.

### 20.11.2 Correction: `REPLACE` bodies do not register

§20.11.1 inferred from `validateInsertIntoFlow` alone that `INSERT INTO t
BY NAME REPLACE WHERE …` registers with its criteria dropped. Codex ran
the vectors (CF-0519) and the inference was wrong on two counts, both
visible in source I had not read: `withInsertInto` passes
`overwrite = true` for every `REPLACE` alternative (`AstBuilder.scala:975,
:995, :1007`), and `createInsertIntoStatement` (`:1146–1171`) routes a
static target through `UnresolvedInsert.toInsertPlan`
(`statements.scala:207–220`), which turns `REPLACE WHERE` into
`OverwriteByExpression` and leaves `REPLACE USING` as an
`InsertIntoStatement` with `overwrite` set. In `CreateFlowHandler` the
first therefore matches neither `InsertIntoStatement` nor
`UnresolvedInsert` and yields "Unable flow type. Only INSERT INTO flows
are supported."; the second reaches the policy chain and fails at the
third arm, "INSERT OVERWRITE flows not supported.". Codex's four extra
Spark 4.2.1 vectors show exactly that, plus "Unable flow type" for both
`OVERWRITE DIRECTORY` forms. Nothing registers; there is no
drop-criteria behaviour to port and no named deviation to design.

What stands from §20.11.1: the parse boundary (probe 15) and the SQL
reachability of "Unable flow type". The lesson is the one already in
this file: a plan-shape claim about Spark needs the builder read to the
plan constructor, not to the grammar rule, or an executed vector. Codex
ran the vector; I had labelled the claim source-derived but should have
run it.

### 20.12 Design read: `SQL-SYNTAX-DIAGNOSTICS-DESIGN.md` (CF-0518)

A user-notified checkpoint; the user was notified. Read read-only
against the pin and the Sail tree at `4fca6f3d4`.

Claims checked and confirmed:

- `TreeParser` rejects a `parser` attribute at the enum-variant level
  (`sail-sql-macro/src/tree/parser.rs:174`, documented at `lib.rs:73`),
  and a field's `function` receives only the dependency parsers and the
  options (`parser.rs:93–94`), never an earlier field's value. So the
  grammar cannot today couple `IF NOT EXISTS` to `OVERWRITE` plus a
  partition clause, or restrict a `CREATE FLOW` body, without the
  variant-level hook the design proposes. The default expansion of the
  hook must stay byte-for-byte the current one; that is testable by
  expanding an unchanged variant before and after.
- `SqlError::parser` formats the `Rich` errors into `SqlParserError(String)`
  at once (`sail-sql-analyzer/src/error.rs:51–60`) and Connect maps that
  to `InvalidArgument` (`sail-spark-connect/src/error.rs:101`). The
  design's refusal to recover metadata from that string is right.
- The twelve vectors verify (`verify.py` pins condition, state, `error`
  and empty `hint` per case); the two ordinary statements submitted to
  the registration API produce the `:170` "Unsupported plan <nodeName>
  parsed from SQL query" wrapper, which the design correctly refuses to
  treat as execution evidence.

Pins the implementation will need, from the pin, so step 4 does not
rediscover them:

- Template: `PARSE_SYNTAX_ERROR` is "Syntax error at or near
  <error><hint>." (`error-conditions.json:5931–5936`), SQLSTATE 42601.
- `error` is ANTLR's token display through `SparkParserErrorStrategy`
  (`:67–72`): the token text in single quotes, with `'<EOF>'` replaced by
  "end of input". `hint` is empty for input-mismatch and
  no-viable-alternative (`:75–88`), ": extra input <token>" for an
  unwanted token (`:91–100`), ": missing <expected-set>" for a missing
  token (`:103–110`). The listener fallback uses the raw ANTLR message as
  `error` with an empty hint (`parsers.scala:160–168`). All twelve
  vectors are the empty-hint class; the design is right to keep the
  other two explicit until tested.
- Message: `ParseException.getMessage` (`parsers.scala:231–256`) is
  "\n" + message, then either the query-context summaries, or
  " (line L, pos P)\n" followed by "\n== SQL ==\n", the lines above,
  P dashes and "^^^", and the lines below. `P` is ANTLR's
  `charPositionInLine` (`:153–157`), a 0-based UTF-16 code-unit offset,
  not a byte or scalar offset; a non-BMP character before the token
  shifts it by two. The recorded messages show this shape with the
  SQLSTATE suffix inserted by the client renderer.
- `withCommand` (`:259–268`) rewrites a `PARSE_SYNTAX_ERROR` on an empty
  command to `PARSE_EMPTY_STATEMENT` with no parameters; the pipeline
  path parses each split statement, so an empty statement between
  semicolons is in scope for the same boundary.
- Spark parses a `CREATE FLOW` statement completely before any name
  policy (the `flow-identity-first` vector: a multipart flow name with a
  bad body gives the syntax error, not `MULTIPART_FLOW_NAME_NOT_SUPPORTED`),
  which is the §20.8 premise again.

Two comments on the sequence, not objections:

- Step 2's Flow-body helper should admit the full `insertInto` rule as
  Spark does, including the `REPLACE` and `OVERWRITE DIRECTORY` forms,
  and leave their rejection to the handler layer with the strings of
  §20.11.2; the design already says "audit … rather than silently
  narrowing", and the four new vectors fix the expected strings.
- Chumsky reports the furthest failure with an expected set, which is
  not ANTLR's recovery model; the `error` token will agree with Spark
  for the first-token cases in the packet, but the empty `hint` must be
  asserted per vector, not assumed from the class.

No inventory effect; no original site asserts any of the sixteen shapes.
