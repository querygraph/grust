# Sail pipeline review units

The operator requires small, logically scoped Sail changes that preserve Sail's
existing design. Work is on `work/spark-declarative-pipelines`, based on Sail
`0ba425c0331aee4dd4e9a280c6a793926fd0876e`. These are local commits; no upstream
pull requests have been opened or branches pushed.

Current batch source `24533f1f0d` publishes table and persisted-view metadata
before batch writes and refreshes existing tables through catalog operations.
Its detached gate passed 124 selected Sail cases and 67 unchanged upstream Python
executions. These counts do not establish full SDP parity. Diagnostics, remaining catalog
properties, publication failure events, and the remaining acceptance crosswalk
are still open; streaming and CDC follow batch acceptance.

## Review the batch implementation

The original batch commit `52aa203b0790027e3d39c598e0bd1995c4c89d72` was split
into the units below. The final tree at
`4880409f693abb1c012751c67e7445e94f2f24b4` is identical. The original commit is
retained on `backup/sdp-batch-before-review-split`.

| Commit | Boundary and manual review |
| --- | --- |
| `9ae9418a83` | Add an optional caller-owned relation scope to `PlanResolver`. Check CTE precedence, catalog fallback, unique resolver fields, and the explicit blocked-relation error. Existing callers supply no scope. |
| `5cadd32316` | Add typed command/event outputs to the existing Connect executor. Check that buffering, cancellation, reattachment, and completion still use the same executor task and response handling. |
| `20b638ea23` | Import only Grust's dependency-free topology kernel. Run `python scripts/spark-pipelines-tests/verify_vendor.py`; compare the files with the source revision and hashes in `vendor/grust-topology/SOURCE.json`. |
| `a5762919c8` | Define pipeline registration and structural validation. Check qualified identifiers, duplicate outputs/flows, missing targets, and flow kinds. No query execution belongs here. |
| `0365354ede` | Resolve graph dependencies and refresh selection. Check forward references, stale catalog shadowing, private views, cycle witnesses, and explicit selection semantics. |
| `200410c356` | Publish batch outputs in dependency order through Sail table writers and `JobService`. Check analysis before writes and downstream reads of committed outputs. |
| `4880409f69` | Wire graph lifecycle into `SparkSession` and Spark Connect. Check session ownership, cancellation, protocol response types, and per-flow configuration copies. |
| `030d9578cf` | Route pipeline writes through Sail's shared resolution, optimization, streaming rewrite, and physical planning helper. The optional relation scope is the only new input; execution still uses `JobService`. |

Registration, analysis, and execution files are preparatory source units until
the final wiring commit. The verification verdict covers the combined final
tree, not a claim that each intermediate commit independently exposes a feature.

The combined tree passed strict Clippy for `sail-plan` and `sail-spark-connect`,
the CLI build, 17 batch execution tests, and 67 unchanged Spark 4.2.1 Python test
executions. The Python count includes inherited/client-only cases; it does not
establish streaming or Scala engine parity. The detached verification checkout
has its own target directory. Test inventory and remaining coverage are tracked
separately from these passing results.

The follow-up planning fix at `030d9578cf80c44e2dc31654c23bfaaab78b6e4a` passed
nightly formatting, strict Clippy, CLI compilation, 17 execution tests, and 67
upstream Python test executions in the detached Sail gate checkout. Formatting
of the initial pipeline modules was aligned with Sail's nightly formatter in
the same commit.

## Review the SQL implementation

| Commit | Boundary and manual review |
| --- | --- |
| `6dacfb7d6d` | Move DataFrame pipeline tests into Sail's Python test tree and reuse its session factory. Check that scenarios still use independent sessions and that error assertions use specific exception types. |
| `a22b849eb3` | Include parameterized Spark test registration calls in the static inventory. The inventory remains a source index, not an expanded runtime test count. |
| `2ffbbdb1d9` | Add typed AST nodes and pipeline-specific lowering for dataset declarations, standalone flows, and streaming table references. Ordinary SQL execution rejects pipeline DDL outside registration. |
| `f4f879890c` | Capture a catalog/database per flow and qualify external reads without changing shared session defaults. Graph-private views continue to take precedence. |
| `644c346229` | Parse Python-declared schemas and compare them with inferred schemas before execution. Includes DDL-string and `StructType` API tests. Declared schema publication remains a separate deliverable. |
| `b76b3d929c` | Register SQL files atomically as graph definitions, retaining per-file `USE`/`SET` context. Includes BDD coverage for dependency resolution, queries, rejection, and side effects. |
| `004e527037` | Add BDD cases for namespace/configuration capture, private-view columns, standalone flow syntax, and duplicate output declarations. |

The final source at `004e527037c63283d05c0660aac544c30378fe02` passed nightly
formatting, strict Clippy for the parser/analyzer/planner/Connect crates, CLI
compilation, 43 Sail pytest cases, and 67 unchanged upstream Python test
executions. Vendor hashes and Python lint also passed. The source was tested in
the detached gate checkout with its own target directory; pytest used its CLI
server through Spark Connect.

The 43 cases cover 17 existing batch scenarios, three Python schema cases, and
23 SQL BDD cases. The SQL run still rejects persisted-view execution and declared
schema/comment publication before writes. Incremental execution, recovery, and
CDC are also outstanding. Do not infer full Spark engine parity from these
counts. The static source inventory currently has 462 registration call sites,
including shared helpers and parameterized declarations; it is not a denominator
for a completion percentage.

## Review persisted views

| Commit | Boundary and manual review |
| --- | --- |
| `f52d4f7d8e` | Accept `USE database` without requiring `DATABASE` or `SCHEMA`. Check that `USE CATALOG` retains its distinct parse. |
| `56fc0ee93c` | Store and restore a persisted view's creation namespace using Spark's catalog properties. Check qualified-name resolution, old views without properties, and malformed namespace metadata. This is shared catalog behavior. |
| `aabdda2a8d` | Publish pipeline persisted views through the existing catalog view command. Check that the output remains a view, resolves in its creation namespace, retains comments, and rejects references to private pipeline views. |

The combined source at `aabdda2a8d786b58854c03e82718a07a2312d473` passed
nightly formatting, strict Clippy, and CLI compilation in the detached gate.
All 49 pipeline tests passed through that CLI server. The initial combined
pytest invocation also selected 20 catalog cases, which their custom-server
fixture skipped under `SPARK_REMOTE`. Those 20 cases were then run separately
with `SPARK_REMOTE` unset and a native extension from the same source tree:
20 passed, none skipped. The 71 deselected cases belonged to the unrelated
remainder of the catalog suite. All 67 unchanged upstream Python executions
also passed. The [receipt](evidence/aabdda2a8d786b58854c03e82718a07a2312d473/gate.json)
records the two test modes separately; there is no claim that 69 tests ran
against the remote CLI server.

At this milestone, declared schema/comment publication remained open; the later
publication unit below adds that behavior. Full batch acceptance remains open.
The next phases are streaming and CDC, in that order; see the
[Iggy source review](STREAMING-REUSE.md) before implementing streaming.

## Review declared-schema constraints and the version guard

| Commit | Boundary and manual review |
| --- | --- |
| `9e909f0f4c` | Enforce Spark's post-merge equality with a declared schema. Reject undeclared inferred columns and nullable input for a non-nullable declaration before writes. Verify six Python schema cases, including an extra nullable declared field. |
| `57734881a1` | Require the compatibility runner's server to report Spark 4.2.1 before collecting tests. This closes a gap where the client version was pinned but the standalone server's embedded Python could not find PySpark. |

The schema source passed nightly formatting, strict Clippy, CLI compilation,
and all 52 pipeline tests with no skips in the detached gate. The server's
version and a 4.2-specific configuration key were verified explicitly. The
runner then passed all 67 unchanged upstream Python executions and rejected a
control server whose Python environment lacked PySpark before test collection.
Receipts are under `evidence/9e909f0f4cb81b41133dfd721fbea1fb6af036e7` and
`evidence/57734881a197e38438df026d5c35a5a3b4a9ed0d`.

Earlier CLI receipts did not verify the server's Spark configuration version.
The native fixtures found the installed PySpark 4.2.1, while the standalone
process needed its Python path set explicitly. The new nullable-input case
exposed that difference before entering pipeline validation. Historical
receipts now disclose this limit; their recorded outcomes are retained.

## Review schema merging, comments, and the dry-run boundary

| Commit | Boundary and manual review |
| --- | --- |
| `3221b8ab68` | Resolve all output publication plans before executing the first write. Check an invalid provider on a later output. `0393db9226` corrects dry runs; `038f28f95e` replaces preflight with Spark's metadata materialization sequence. |
| `8dccd5a6e4` | Merge schemas using Spark field order, metadata precedence, nullability, recursive containers, decimal precision, and interval bounds. Normalize through Sail's existing Spark/Arrow type conversions. Check the 18 schema cases, including rejection of untyped null as a wildcard. |
| `fd93eb6ef4` | Carry declared table comments through the shared write specification, builder, and catalog create operation. Check replacement of an existing comment and that dry runs create no output. |
| `0393db9226` | Restrict publication preflight to real runs. A dry run with an unknown output provider succeeds without creating the table, matching Spark 4.2.1. |

Each unit passed detached nightly formatting, strict Clippy, CLI compilation,
and the unchanged upstream Python runner with its server reporting 4.2.1.
The Sail case counts were 54, 66, 74, and 68 respectively; the 74 included
68 pipeline cases and six shared-writer regressions. All had zero failures or
skips. Each source has its own receipt under `evidence/<full commit>/gate.json`.
The schema-merge receipt retains the failing baseline; it does not claim all
Spark type representations or the full engine suite are covered.

### Live Spark 4.2.1 reference

The [reference scripts and results](evidence/spark-4.2.1-schema-reference/README.md)
ran against the PySpark 4.2.1 JVM with a local Connect server and isolated
warehouses. They establish the following behavior:

- Dry run resolves and validates the graph without creating outputs or resolving
  the output provider. The earlier preflight assertion was stricter than Spark;
  the dry-run correction follows the reference and `PipelineExecution` source.
- A declared wider decimal accepts a narrower decimal result during execution.
- Missing declared columns pass dry-run schema validation when nullable, but
  real batch writes fail for missing top-level or nested fields. Do not synthesize
  null values to make those writes succeed.
- Spark creates the target tables before those failed writes. The preflight at
  this milestone did not reproduce those catalog side effects; `038f28f95e`
  now covers the observed cases.
- Spark rejects a second `StartRun` on the same graph ID, even after a dry run.
  The lifecycle unit below corrects the repeated-run fixtures and behavior.

The subsequent units address declared schema publication and execution-entry
lifetime. Broader diagnostic parity and the remaining batch crosswalk stay open.
The static 462-call-site inventory is still not a runtime acceptance count.
Streaming and CDC follow batch acceptance.

## Review execution-entry lifetime

Commit `12664ae7ee` retains a graph's execution entry after successful or failed
analysis/execution. A subsequent start returns Spark's structured condition,
`graphId` parameter, and `XXSC0` SQL state. Command-option validation and empty
or duplicate registration checks happen before reservation, so a corrected
request can still start the graph. Refresh fixtures now register fresh graphs
while preserving the same published tables and pipeline storage location.

Review the short registration lock, the separation of selection validation from
dependency expansion, and the Connect error metadata helper. The helper leaves
ordinary exception conversion intact; it does not parse error conditions from
messages. The [receipt](evidence/12664ae7eee787e1d70bc5a9d78934869da95af0/gate.json)
records 75 Sail pipeline cases and 67 unchanged upstream Python executions,
all passing without skips, plus nightly formatting, strict Clippy, CLI build,
and Python lint. Nine identical lifecycle assertions passed against a live
Spark 4.2.1 JVM. The initially failing reference probes are retained with the
corrections they caused. Broader analysis-error wrapping remains outstanding.

Before beginning the next design phase, notify the operator so they can switch
to Astra. This applies to streaming checkpoint/recovery design, CDC design, or
a batch issue that requires reconsidering the architecture. Routine batch
implementation and compatibility fixes continue within the agreed design.

## Review catalog schemas and table materialization

| Commit | Boundary and manual review |
| --- | --- |
| `789d28ac30` | Expose catalog column comments in Spark schema metadata when canonical Spark metadata is absent. Check ordinary and quoted comments and precedence of existing canonical metadata. |
| `29eeb6546c` | Reject missing or extra nested fields on the standard table append-by-name path before DataFusion can synthesize or discard fields. Check nested structs, arrays and maps, reordered fields, and explicit typed nulls. Top-level column-count failures now use an analysis exception. |
| `038f28f95e` | Create or update selected table metadata before batch queries run. Use declared schemas or recursively nullable inferred schemas, preserve column comments, truncate existing complete tables, and apply schema changes without replacing their location. Batch flows append through the shared writer. |
| `bbda0c14d5` | Remove the now-unused `WriteTo.table_comment` and writer builder extension. Metadata publication uses the existing catalog comment operations, so the common write specification no longer needs a pipeline-specific addition. |

The [materialization receipt](evidence/038f28f95eebfb78edf1ae8a76d0fbd27adf4366/gate.json)
and preceding receipts record separate detached gates: 77 selected cases for
column comments, 89 for append validation, and 101 for materialization.
Each also passed the 67 unchanged
upstream Python executions, nightly formatting, strict Clippy, CLI compilation,
and Python lint. The final selection includes 87 pipeline cases and 14 shared
writer/catalog regressions, with no failures or skips. Receipts for the shared
fixes are under [column comments](evidence/789d28ac301ce646fdb4e15d73e4954e687709ae/gate.json)
and [append schemas](evidence/29eeb6546c4d5353fe4b0d611f14dbd1fb9ecdf9/gate.json).
The [writer cleanup](evidence/bbda0c14d59920b650618cb8682fc68261106079/gate.json)
passed the same 101 and 67 executions, formatting, Clippy, and build; it changes
no Python files and introduces no new tests.

Eight identical shared-writer/comment assertions and nine identical pipeline
publication assertions passed against a live Spark 4.2.1 JVM. The publication
reference used candidate `738107ab3`; its test and fixture blobs are identical
to committed `038f28f95e`, which only relocates a Rust import. Separate probes
confirm that a later unknown provider can leave an earlier target created but
empty. Preserve that side effect rather than asserting all-or-nothing output
metadata. The initial failed Sail gate and reference fixture are retained.

Review `pipelines/materialize.rs` alongside Spark `DatasetManager` and
`MaterializeTablesSuite`. It issues existing catalog command specifications
through Sail's shared planner and `JobService`; there is no new physical node
or pipeline-specific table writer. Normal and full refresh use the same complete
table behavior. Existing column order and table location survive refresh;
declared order governs initial creation. The add/drop/type refresh cases follow
the upstream V2 test catalog and were not run against Spark's default V1 catalog,
which lacks those alterations.

The comment-removal fixture now checks the CatalogV2 semantic value: Spark's
session catalog returns `comment: null`, while Sail omits the key. Byte-for-byte
metadata JSON parity is not claimed. Existing-table truncation, schema changes,
and properties use separate commands, so they are not an atomic catalog update.
The nested-field guard covers the ordinary append-by-name path; Delta and
generated/default-column paths need their own coverage. At this milestone,
persisted views still published during flow execution; the next unit corrects
that sequence. Clustering, pipeline property validation, structured diagnostics,
and complete batch acceptance remain outstanding.

## Review persisted-view materialization ordering

Commit `a007290e7a` publishes all persisted views in dependency order after table
metadata materialization and before executing any batch write. Table refresh
selection does not filter view publication. A view definition is materialized
against the analyzed graph, so its excluded upstream table need not already exist.
Actual catalog inputs are loaded when an executing flow consumes them. This keeps
view-only refreshes free of unnecessary table reads and gives selected consumers
fresh producer data through their views.

The [receipt](evidence/a007290e7a628c0b9da373b4490431147134e94e/gate.json) records
106 passing Sail cases: 92 pipeline cases and 14 shared writer/catalog regressions.
The 67 unchanged upstream Python executions, formatting, strict Clippy, CLI build,
and Python lint also passed in the detached gate. Five focused SQL scenarios
were observed against Spark 4.2.1: unselected view publication, a view surviving
a failed table write, selected producers/consumers connected through an unselected
view, an absent excluded upstream table, and a view-only refresh. The reference
records Spark's original exception; the Sail BDD failure scenario still uses
Sail's existing diagnostic text, so these are behavioral comparisons rather than
identical error-message assertions.

The three-case failing baseline, initial five-case probe (four passed, one failed),
and subsequent full gate (105 passed, one failed) are retained. The last failure
exposed an eager read of an excluded table during a view-only refresh; the final
unit moves that read to the consuming flow. Review the small changes in
`pipelines/execution.rs` and `pipelines/materialize.rs` alongside the five BDD
scenarios. No new physical plan or catalog API was introduced. Handling multiple
view-publication failures, independent flow progress, and exact event/error
semantics still require dedicated acceptance work.

## Review pipeline table property validation

Commit `e4d578ce06` validates the exact canonical reset key after query/schema
analysis, including dry runs. A small private module filters unknown pipeline
properties, canonicalizes recognized keys at publication, and logs unknown or
suspiciously unprefixed keys through Sail's existing logger. It preserves Spark's
observed mixed-case value lookup asymmetry and rejects surrounding whitespace in
canonical boolean values.

The [receipt](evidence/e4d578ce0658f94884753e3bfdadb3f2208f5af6/gate.json) records
112 selected Sail cases (98 pipeline and 14 shared regressions), 67 unchanged
upstream Python executions, nightly formatting, strict Clippy, CLI build, and
Python lint, all passing. Six new API assertions failed on the previous Sail
source and passed unchanged against both this source and Spark 4.2.1. The
[six SQL probes](evidence/spark-4.2.1-properties-reference/README.md) remain a
separate reference for the behavior motivating this change.

Streaming reset-policy graph constraints, duplicate case-variant keys, and warning
event parity still need acceptance coverage. This unit adds no new catalog API,
physical plan, dependency, or streaming behavior.

## Review structured temporary-view rejection

Commit `5a5e256328` returns `INVALID_TEMP_OBJ_REFERENCE`, SQL state `42K0F`,
and all four message parameters through the existing structured Connect error
helper. It preserves the AnalysisException class and derives quoted identifiers
from the registered graph. The existing BDD case now checks the whole parameter
map. Its current-catalog placeholder reflects the engines' different native
catalog names rather than changing Sail's default.

The [receipt](evidence/5a5e256328406b6dcbffd0db83dd39d6f9746553/gate.json) records
112 selected Sail cases and 67 upstream Python executions, nightly formatting,
strict Clippy, CLI build and Python lint, all passing. Spark 4.2.1 dry and real
reference runs returned the same temporary-view error metadata. The initial
111-pass/one-failure gate is retained with its catalog-fixture correction. This
strengthens an existing scenario rather than increasing the test count.

The companion streaming probes encountered a missing source during resolution;
their null structured condition does not establish streaming-query validation
behavior. Error priority, exact wording, direct-failure attribution, and failure
events remain separate acceptance work.

## Constraints for subsequent units

The [acceptance crosswalk](CROSSWALK.md) now audits every ViewSuite registration
at assertion level. Seven partial behavioral ports and four unmapped cases are
explicit; no full-suite qualification is inferred from the regression count.

The property-validation unit is grounded in a
[six-case Spark/Sail comparison](evidence/spark-4.2.1-properties-reference/README.md).
It exposes unknown-key filtering, canonical key storage, dry-run validation, and
an upstream mixed-case lookup asymmetry. The unit above covers those six observations; broader property coverage remains open.

- Keep pipeline declarations in Sail's typed SQL AST and analyzer. Registration
  produces definitions; it must not execute DDL or rewrite SQL strings.
- Use the same resolution, optimization, streaming rewrite, physical planning,
  and `JobService` path as ordinary Sail commands. The scoped execution helper
  removes a bypass found during review of the initial batch code.
- Publish tables and views through existing catalog/provider operations. Do not
  replace the catalog or silently materialize a persisted view as a table.
- Keep graph registration locks short and synchronous. Do not hold them across
  query execution. Any concurrent control plane must follow Sail's existing
  actor/service design rather than introduce a second query scheduler.
- Use Sail's object-store and transactional writer interfaces for durable
  streaming state. LakeCat's reusable commit/replay mechanisms belong behind a
  small dependency boundary; no dependency on `lakecat-sail` is permitted.
- A new physical plan, expression, or function needs Sail's distributed codec
  support and corresponding distributed validation. The batch units add none.
- Put SQL behavior in Sail's normal `.feature` tests and DataFrame API behavior
  in its Python test tree. Keep pinned upstream compatibility runners separate.
- Follow Sail's nightly formatting and strict Clippy conventions. Run relevant
  pytest tests, not just compiler checks. Keep gates attached to an immutable
  source revision and distinguish tested commits from pending work.
- Separate parser/lowering changes, SQL registration, schema publication,
  persisted views, incremental state, and CDC into reviewable units. Each unit
  must state its behavior and verification; broad scaffolding is not evidence
  of completed compatibility.

All design and review documents stay in Grust. Preparing these local units
does not authorize opening an upstream PR or publishing shared crates.

## Model-switch design checkpoint

The next batch work needs a focused failure/event design review. The operator has
been notified to switch to Astra before this phase begins. The
[handoff](BATCH-EVENT-DESIGN-HANDOFF.md) records source observations, a Sail baseline,
and open decisions. No replacement event architecture has been selected.

The materialization crosswalk now covers all 27 registrations in addition to the
11 view registrations. Eight materialization ports are partial and 19 remain
unmapped. The operator authorizes updating LakeCat catalog coverage and reusing
that support in Sail so it does not require a separate later implementation.

## Catalog ownership clarification

General catalog support and reusable catalog semantics are implemented in Sail,
with LakeCat as one supported provider. Shared DDL/schema/partition/property
behavior needs catalog-neutral Sail acceptance tests. LakeCat-specific changes
implement its adapter, catalog-state persistence, authorization, and commit/CAS
integration through the existing seams. They must not duplicate generic Sail
catalog logic or make pipeline planning depend on LakeCat. The operator explicitly
clarified this ownership after authorizing LakeCat coverage updates.

## Review shared partition-field validation

Commit `9031373d0d` checks declared partition fields in Sail's shared CREATE TABLE
resolver before catalog creation. Missing fields and identical duplicate fields
fail; valid fields use the schema's canonical spelling. Typed partition definitions
respect case-sensitive identity, so id and ID can coexist in catalog metadata.
Schema-less external definitions retain provider inference. This is shared Sail
behavior; pipeline materialization consumes the existing CREATE TABLE command.

The [receipt](evidence/9031373d0dfbf5c7a876a113a0a273ec933e6ccd/gate.json) records
121 selected cases: 98 pipeline, 14 existing shared regressions and nine partition
DDL cases (six new and three existing). All passed, together with 67 upstream
Python executions, formatting, strict Clippy and CLI build. Seven targeted Spark
4.2.1 DDL observations establish the reference outcomes; they are not nine
identical BDD executions on Spark. No Python files changed.

The failed baselines and two failed intermediate fixture sets remain recorded.
Absence is now checked by executing SELECT rather than calling the lazy SQL API.
The case-distinct catalog fixture uses DESCRIBE because broader read/write checks
exposed two existing shared bugs: get_partition_columns_and_file_schema folds
case even when an exact field exists, and table append-by-name ignores the session
case-sensitivity setting. Their failing fixtures are retained as candidate patches;
fix these next and restore the read/write assertions. Catalog creation alone does
not qualify that data path. Structured DDL errors, CTAS/other writer paths and
LakeCat provider integration remain acceptance work.

## Review exact partition identity during scans

Commit `0a84375381` prefers an exact schema name when resolving physical partition
fields, retaining the existing unique case-insensitive fallback when no exact
name exists. The file schema removes only the resolved partition field, preserving
case-distinct non-partition fields and their types. This shared DataFusion utility
is independent of pipeline and catalog-provider implementations.

The [receipt](evidence/0a84375381236786f66f09ada7578c9c8efef0c7/gate.json) records
121 selected Sail cases, 67 upstream Python executions, four focused schema-utility
tests, nightly formatting, strict Clippy and CLI build, all passing. The restored
case-distinct BDD schema read fails at the preceding committed source and passes
here. A Spark 4.2.1 reference returns the same id/payload/ID schema. The four utility
tests verify exact matching, unique fallback, ambiguous/missing/duplicate-field
rejection, and preservation of file fields. Their other 59 crate tests were not run.

The first candidate's tests used unwrap, rejected by Clippy; the final tests
return Result. Its patch is retained. The initial partition unit's failed read
fixture is now restored. The by-name writer still folds case; restore its retained
INSERT/result fixture in the next shared writer fix. Empty-table schema analysis
does not qualify a persisted-row round trip or LakeCat integration.

## Review case-sensitive appends by name

Commit `eb417941e8` makes the standard table append-by-name resolver honor its
PlanConfig case-sensitivity setting. Exact matching is required when enabled;
case-insensitive matching is retained when disabled. The change uses the existing
resolver and writer paths and adds no catalog dependency.

The [receipt](evidence/eb417941e86dfe18cbdc141d7a55a675ea0e26e6/gate.json) records
122 selected Sail cases and 67 upstream Python executions, formatting, strict
Clippy and CLI build, all passing. The retained case-distinct INSERT/result fixture
is restored in the partition scenario: creation, insert, schema analysis, and
SELECT distinguish ordinary id=1 from partition ID=2. A new insensitive control
writes an ID input to an id target. The parent source failed the first and passed
the control; both SQL round trips return identical values on Spark 4.2.1.

Together with the preceding shared scan fix this closes the two failures retained
from partition validation for these fixtures. It does not establish general
coverage of generated/default/identity or Delta-special write paths. LakeCat
integration remains pending. The next catalog check should exercise the existing
standard catalog protocol path as well as assessing the optional embedded adapter.

## Review shared Iceberg comments and LakeCat REST integration

Commit `24533f1f0d` exposes Iceberg field documentation through the existing common
Arrow comment key while retaining the Iceberg doc key. This fixes the shared
Iceberg read path for all catalogs and direct location reads; it adds no LakeCat
dependency or special case. The conversion round-trip test now asserts both
comment presence and absence, and two DataFrame API cases cover ordinary and
quoted comments using the existing PyIceberg SQL-catalog fixture.

The [receipt](evidence/24533f1f0d32621b54d3f0f78f353be673dc493c/gate.json) records
124 selected Sail pytest cases, 67 upstream Python executions, one conversion
unit test, formatting, strict Clippy, CLI build and Python lint, all passing.
The new API cases both failed at the preceding source. Four additional live
pipeline checks pass through LakeCat's standard Iceberg REST path: initial MV
publication, refresh replacing rows, declared column-comment refresh, and column
replacement. The initial integration passed the first two but failed its comment
assertion; raw LakeCat metadata already contained the correct doc, locating the
bug in Sail's read conversion.

LakeCat was built unchanged at 27e18f390c450c187a34b1c3bb2037c26d107699 with its
existing sail-local metadata engine pinned to Sail 9f6f8065. Client Sail and server
LakeCat communicate over the standard REST boundary, so their different Rust
Sail/Arrow dependency versions need no shared ABI. This does not qualify the
optional embedded provider adapter. The isolated profile uses memory catalog
state, allow-all test governance and local files; its build receipt is under
[evidence](evidence/lakecat-27e18f390c450c187a34b1c3bb2037c26d107699/build.json).
No LakeCat production code changed for these table behaviors.

Persisted-view support remains open on both sides. Source inspection shows Sail's
general Iceberg REST provider rejecting replacement of an existing view. LakeCat
standard POST view-create probes return 404 on the unprefixed route and 405 on the
warehouse-prefixed route. These are optional catalog capabilities needed for
persisted pipeline views, not evidence of completed REST view support. Reuse the
existing view storage, metadata and governance machinery during the focused
Astra review rather than introduce a pipeline-only catalog interface.

## Review the reusable catalog acceptance runner

Commit `7fd30c4187` adds scripts/spark-pipelines-tests/catalog.py. It uses the
pinned PySpark 4.2.1 client directly, creates a unique table name and fresh graph
per refresh, and verifies rows, column names/types/nullability/comments, stable
table location and final cleanup. Catalog and database are selectable; the
provider is explicit. JSON captures outcomes and setup/run failures. Optimized
Python is rejected so its assertions cannot be disabled.

Its [receipt](evidence/7fd30c4187be2e1c735bf84af583b9fff82b540f/gate.json) records
four passing cases plus cleanup on each of memory/parquet and LakeCat/Iceberg,
Python lint/format, two invalid-invocation controls, and an injected answer
mismatch that fails acceptance while cleaning its table. The runner source is
7fd30c4187; both live servers use the previously verified engine binary 24533f1f0.
Only the Python script differs between those source trees. No Rust or upstream
Python-suite rerun is claimed for this unit. The [usage note](CATALOG-ACCEPTANCE.md)
keeps these focused checks distinct from full SDP acceptance.

## Review structured errors for missing pipeline graphs

Commit `6c87cd39de` uses Sail's existing structured-error transport when graph
lookup fails. Define-output, define-flow, define-SQL and start-run now expose
Spark's DATAFLOW_GRAPH_NOT_FOUND condition, graphId parameter and KD011 SQL
state as SparkException. Dropping an absent graph remains idempotent; dropping
a graph still preserves its published tables.

The [receipt](evidence/6c87cd39de51f925221fbc97ed475810f655b188/gate.json)
records 129 selected pytest cases, 67 upstream Python executions, formatting,
strict Clippy, CLI build and Python lint, all passing. The six focused lifecycle
assertions also pass against Spark 4.2.1. The preceding Sail build failed five
of them and passed the absent-drop control; that baseline is retained. Tests
omit the define-flow once option, whose validation priority is separate. This
unit does not establish complete session isolation or command error precedence.
The static Scala crosswalk is unchanged; these checks do not constitute a
Scala-suite execution.

General catalog behavior continues to belong in Sail. LakeCat remains one
supported catalog; the earlier shared Iceberg-comment fix and reusable catalog
runner demonstrate that boundary. Failure/events and persisted REST views still
need the focused Astra design review before architectural implementation.

## Review once-option validation priority

Commit `a587b7e6d8` rejects any explicitly supplied DefineFlow.once value in the
command handler before graph lookup or required flow-field validation. This
matches Spark 4.2.1 for true and false, existing and missing graphs, and omitted
and named flows. The existing structured-error transport now provides
AnalysisException, DEFINE_FLOW_ONCE_OPTION_NOT_SUPPORTED, the flowName parameter
and SQL state 0A000. The later graph guard is removed rather than duplicated.

The [receipt](evidence/a587b7e6d86d734a816d6455ad922d2a1faf7258/gate.json)
records eight matching Spark reference assertions, 137 selected Sail pytest
cases and 67 upstream Python executions, plus formatting, strict Clippy, CLI
build and Python lint. All pass. All eight new assertions failed on the parent
Sail build; that baseline is retained. This protocol validation change adds no
new execution architecture and makes no streaming/CDC support claim.

The Connect server assertion audit now covers its 19 static registration sites,
including the true/false once grid and four identifier grids. Three have partial
behavioral ports and 16 remain unmapped. The [crosswalk](CROSSWALK.md) keeps
internal registry checks, protocol responses, streaming fixtures and absent
assertions explicit. Across the audited suites 57 registrations are reviewed;
405 remain unaudited. No whole Scala suite has run against Sail.

## Review quoted graph database defaults

Commit `900925b7d0` parses the graph database default before setting the shared
CatalogManager namespace, reusing the SQL analyzer's existing object-name parser
as the ordinary SetCurrentDatabase command does. The graph's original default
string remains available for Spark-compatible resolved-identifier responses.

The [receipt](evidence/900925b7d0a01ea118fa6e3fd0d1d3bf8d5d1b2d/gate.json)
records 143 selected pytest cases, 67 upstream Python executions, six matching
Spark 4.2.1 output-identifier checks, formatting, strict Clippy, CLI build and
Python lint. All pass. The parent baseline failed the quoted-database case and
passed the other five. The broader initial ten-case probe also exposed four
unresolved-table-function failures, retained for the separate following unit.
The output grids register a TABLE but do not execute it; no new streaming or
quoted-database materialization qualification follows from these checks.

## Review Connect table-function relations

Commit `f064fb2709` translates UnresolvedTableValuedFunction into Sail's existing
ReadUdtf spec using the existing object-name and expression translators. Both
built-in table functions and generators continue through the shared resolver,
optimizer and physical planner. There is no pipeline-specific evaluator or
new physical node.

The [receipt](evidence/f064fb2709e14d3064c93a9c03b25dbcd8d40ec5/gate.json)
records 157 selected pytest cases and 67 upstream Python executions, formatting,
strict Clippy, CLI build and Python lint. Four original flow-identifier grid
instances and three ordinary DataFrame explode_outer API cases also pass on
Spark 4.2.1. All seven failed on the parent Sail engine; failures are retained.
Seven existing SQL range cases remain passing as shared-path controls. Null,
empty and nonempty array API cases verify schema and physical result rows.
The protocol flow grid verifies registration responses for raw range relations;
it does not execute a pipeline containing those relations. Qualified table
functions and untested function families retain the shared resolver's existing
capabilities and limitations.

All ten public identifier-grid instances now have explicit ports in the server
crosswalk: seven of its 19 registrations have partial behavioral ports and 12
remain unmapped. Original Scala-suite execution and the broader SDP goal remain
outstanding. The Astra failure/event and REST-view design checkpoint is unchanged.

## Review session ownership and coexisting graphs

Commit `2075468608` adds protocol-level regression checks without changing runtime
code. Raw ExecutePlan requests use fresh session IDs and both same-user and
different-user pairs. Each graph accepts its owner's output, rejects the other
session's graph ID and survives a foreign-session drop. A separate batch test
registers two SQL materialized outputs in one session, verifies that starting
one does not publish the other, then drops the first graph and executes the
second while preserving the first table's rows.

The [receipt](evidence/2075468608cccc0d8e3581b2f235154e557a56b8/gate.json)
records 160 selected pytest cases, 67 upstream Python executions, Python lint
and three matching Spark 4.2.1 reference checks. The same three checks already
pass on parent engine f064fb2709; no production defect is claimed. The CLI hash
matches that engine's verified receipt. This test-only unit claims no additional
Rust compilation or native-extension gate.

The server crosswalk now has ten partial ports and nine unmapped registrations.
Nonempty graph IDs, session ownership and multiple-graph results are observable
protocol assertions. Spark's internal registry sizes, retained-holder graph
cleanup after close, and session-manager absence remain unqualified. A shared
session ID across users is also outside these checks. The total reviewed call
sites remain 57, with 405 awaiting assertion audit. Batch acceptance is incomplete;
the Astra event/REST-view architecture checkpoint remains ready.

## Review captured graph defaults and deferred SQL response shapes

Commit `9f96b534dd` adds four assertion ports. A graph with inferred or explicit
database defaults keeps them after a session database switch; the explicit case
also checks current catalog/database. Two raw ExecutePlan cases pack the original
PipelineAnalysisContext extension with/without a flow name and compare the first
sql_command_result Relation with the input using protobuf equality.
The named-table query remains unresolved, as the Spark server fixture requires.

The [receipt](evidence/9f96b534dde38228ab7e1eba7d4a383c93a6c8cb/gate.json)
records 164 selected pytest cases, 67 upstream Python executions, Ruff and four
matching Spark 4.2.1 reference checks. All four also passed on the prior Sail
engine; runtime remains verified engine f064fb2709 with matching CLI hash. No
Rust/native-extension rerun or new runtime fix is claimed. The graph checks
observe public responses rather than internal fields. SQL response shapes do
not qualify server-side side-effect restrictions under analysis context.

The server crosswalk now has 14 partial ports and five unmapped registrations.
The two failure-handler registrations are newly audited and both unmapped,
bringing the reviewed inventory to 59 and the unaudited remainder to 403.
The cause-present identity requirement and cause-absent PIPELINE_RUN_FAILED
message requirement are added to the Astra handoff without choosing a design.
Full batch acceptance, persisted REST views, streaming and CDC remain incomplete.

## Review structured empty-pipeline rejection

Commit `8ef94cb7dd` returns the existing StructuredSparkError form for
RUN_EMPTY_PIPELINE, mapped to AnalysisException with SQL state 42617 and empty
parameters. The message follows the pinned Spark error definition. Validation
still precedes graph execution reservation, so callers can add a missing output
and start the same graph after an empty-registration failure.

The [receipt](evidence/8ef94cb7dd09b1cade4d62afa7fe19cb9272b877/gate.json)
records formatting, strict Clippy, CLI build, Ruff, 170 selected pytest cases and
67 upstream Python executions, all passing. Nine focused assertions also pass
on Spark 4.2.1; all nine failed on the preceding Sail engine's missing structured
metadata. Six SQL instances cover empty files, temporary-only definitions and
flow-only definitions, each with dry/real starts. Three strengthened API tests
cover empty registration, temporary-only registration and correction followed
by successful start. The failed baseline is retained.

Only the three corresponding SQL registrations are newly audited, bringing the
reviewed inventory to 62 and the remaining unaudited call sites to 400. The
other 35 registrations in SqlPipelineSuite are not qualified by this unit. Full
batch acceptance, Scala-suite execution, failure/event design, persisted REST
views, streaming and CDC remain outstanding. No new architecture is selected.

## Review duplicate-output categories and structured metadata

Commit `b145ed12d9` validates duplicate outputs with Spark's table/view/sink
category order. Streaming tables and materialized views are TABLE; persisted
and temporary views are VIEW. For a collision, the first two category-grouped
entries determine the types, which are sorted lexicographically in the error.
This matters when views were registered before a table with the same name.
The error uses existing StructuredSparkError transport for AnalysisException,
PIPELINE_DUPLICATE_IDENTIFIERS.OUTPUT, SQL state 42710 and outputName/outputType1/
outputType2 parameters. Validation still precedes execution reservation.

The [receipt](evidence/b145ed12d92fb98b0e484b101be17b24f8ec38fc/gate.json)
records formatting, strict Clippy, CLI build, Ruff, 184 selected pytest cases and
67 upstream Python executions, all passing. Fourteen new assertions match Spark
4.2.1; all fourteen failed on parent Sail's missing structured metadata. The
matrix includes reversed table/view order, materialized pairs, streaming versus
materialized, persisted pairs, private temporary pairs and two views followed
by a table. Every case checks dry/real starts, exact metadata and no publication
of an independent valid output. Sink collisions and first-error selection among
multiple distinct duplicate identifiers are not qualified by this matrix.

The first reference-script run failed before assertions because a test-function
variable was rebound to the case lambda; script, log and report are retained
separately. Correcting the runner left the tests and candidate unchanged and
produced the passing fourteen-case Spark reference result.

One additional SQL registration is audited: total reviewed 63, remaining 399.
Only four of SqlPipelineSuite's 38 registrations have been reviewed. Missing-
producer structured errors, full batch acceptance, original Scala-suite execution,
Astra failure/event and persisted-view design, streaming and CDC remain open.

## Review missing-producer structured metadata

Commit `39f070e625` uses existing StructuredSparkError transport for
PIPELINE_DATASET_WITHOUT_FLOW, mapped to AnalysisException, SQL state 0A000 and
the quoted identifier parameter. It preserves existing validation order and
execution behavior. Two SQL cases retain the original empty streaming-table
fixture; six protocol cases cover tables, materialized views and temporary
views with an identifier containing both a dot and an escaped backtick. Each
runs dry/real and checks that no output, including an independent valid producer,
is published.

The [receipt](evidence/39f070e62540eacdb260ee2c241027e53838899f/gate.json)
records formatting, strict Clippy, CLI build, Ruff, 192 selected pytest cases and
67 upstream Python executions, all passing. Eight focused assertions also pass
on Spark 4.2.1. All eight failed on the preceding Sail engine's missing structured
metadata; the baseline is retained. These are registration/validation checks,
not streaming execution qualification.

## Review scalar-subquery, nested-CTE and rollup assertion ports

Commit `e856e58465` adds three batch query tests with the original SQL-suite
assertions: scalar-subquery output Row(4), nested-CTE output Row(1), and group-by
IDs plus rollup cardinality and total row. Dataset names are renamed to avoid
collisions between reference cases; nested query structure and aggregate
expressions are retained. The port also checks exactly one rollup total row.

The [receipt](evidence/e856e584652dfcc9f444ce67fd71ef440cf9af8b/gate.json)
records Ruff, 195 selected pytest cases, 67 upstream Python executions and three
matching Spark 4.2.1 reference cases. All three already pass on parent engine
39f070e625; this is regression coverage, with no new runtime defect claimed.
The CLI hash matches the engine receipt. No additional Rust/native gate is
claimed for the test-only commit.

Four additional SQL registrations are audited in these units, bringing the
reviewed inventory to 67 and the unaudited remainder to 395. Eight of the SQL
suite's 38 registrations are reviewed. Full batch acceptance, original Scala
suite execution, Astra failure/event and persisted-view design, streaming and
CDC remain outstanding. No new architecture is selected by these units.

## Review SQL file-local catalog scope and shared expression boundary

Commit `a2dbec30eb` adds four namespace regression cases: explicit namespace after
SET CATALOG, USE after SET, reset between SQL files, and a private view after a
catalog/namespace change. They verify persisted rows, session defaults remaining
unchanged by registration, private-view absence and owned-table/database cleanup.
The [receipt](evidence/a2dbec30eb48a15040798049b9e81e9606ff1d5f/gate.json) records
Ruff, 199 selected pytest cases, 67 upstream Python executions and four matching
Spark 4.2.1 reference checks. Parent engine 39f070e625 already passes all four;
its CLI hash is unchanged. No additional Rust/native gate or runtime fix claimed.

The separate nine-case paired probe retains real gaps: a missing namespace after
SET fails too late in Sail; foldable catalog expressions are unsupported; invalid
expression errors differ; external-read attribution overlaps the event design.
The [SQL catalog handoff](SQL-CATALOG-DESIGN-HANDOFF.md) records the typed general
SQL design boundary without selecting an architecture. Operator notified to
switch to Astra before that design phase. General catalog changes belong in Sail.

Two additional SQL registrations are audited, with one partial port and one
unmapped expression grid. Total reviewed 69; unaudited 393. SQL suite reviewed
10 of 38. Full multi-catalog/streaming source fixture and original Scala suite
remain unexecuted. No full batch or SDP acceptance claim.

## Review duplicate-flow metadata and registration priority

Commit `bbf438c066` groups destination identifiers by flow name, then validates
in original registration order. This matches Spark's first-registered duplicate
identifier even when another flow reaches its second occurrence earlier. Error
parameters use the fully qualified unquoted flow name and only the first two
quoted destinations, preserving their order and removing a repeated destination.
The existing StructuredSparkError transport now carries AnalysisException,
PIPELINE_DUPLICATE_IDENTIFIERS.FLOW and SQL state 42710. Validation remains before
execution reservation and flow analysis.

The [receipt](evidence/bbf438c0661cdfa4a3fab3af70439f7f788615d8/gate.json)
records formatting, strict Clippy, CLI build, Ruff, 211 selected pytest cases and
67 upstream Python executions, all passing. Twelve new dry/real assertions also
pass on Spark 4.2.1; all twelve failed on the prior Sail engine and that baseline
is retained. The matrix covers same-target deduplication, implicit/explicit
collision, reversed destination order, three targets with only the first two
reported, first-registered duplicate priority and escaped identifiers. Declared
external STREAM sources are absent to verify duplicate validation precedes
analysis; no streaming execution claim follows from these fixtures.

Two additional SQL registrations have partial assertion ports: total reviewed
71, remaining unaudited 391. The SQL suite has twelve reviewed registrations
and 26 awaiting audit. Original Scala-suite execution, private/sink collision
variants, full batch acceptance, shared SQL catalog expressions, failure/event
and REST-view architecture, streaming and CDC remain open. Astra handoffs remain
ready; no new architecture or publication was introduced in this unit.

## Review basic SQL execution ports and complete SQL assertion audit

Commit `efc21f2c53` adds six tests: static range rows with comment syntax,
hyphenated publication and resolution as separate cases, a forward four-view
persisted dependency chain, modulo/max aggregation and a private-view join.
Original row assertions are retained; some dataset names are changed to avoid
collisions between reference cases. Stronger checks include private-view absence,
non-streaming published DataFrames and actual Sail reads of hyphenated outputs.

The [receipt](evidence/efc21f2c53b0d8c886b31928ed67131a1de7c6db/gate.json)
records Ruff, 217 selected pytest cases, 67 upstream Python executions and five
matching Spark 4.2.1 reference checks. Runtime is unchanged engine bbf438c066
with matching CLI hash; no additional Rust/native gate is claimed. The first
reference attempted hyphen publication, which Spark's default V1 catalog rejects
as INVALID_SCHEMA_OR_RELATION_NAME. The original Scala test only resolves its
graph. That failed publication script/report/log and initial candidate patch are
retained. The original stronger Sail publication assertions remain unchanged;
a separate dry-resolution test matches the source phase and passes on Spark.

All 38 SQL registrations now have an assertion-level audit: 24 partial ports and
14 unmapped. Newly reviewed records spell out graph metadata, exact partition/
property/config/schema/parser requirements, cross-catalog combinations and
streaming/window behavior. File-format, bad-read, multipart-flow and six
namespace-pair instances are explicit. Existing behavioral BDD ports are mapped
with their exact missing original assertions rather than counted as full parity.

The total reviewed inventory is 97 of 462 static registration sites; 365 remain
unaudited. This is not an expanded test denominator or a completion percentage.
Original Scala suites, full batch acceptance, shared SQL catalog expressions,
failure/event and REST-view architecture, streaming and CDC remain outstanding.
Astra handoffs remain ready; this unit selects no new architecture.

## Review internal SQL registration metadata fixtures

Commit `35565f49d1` adds a cfg(test) child module to pipeline SQL registration.
Three Rust tests preserve the original SQL fixtures and inspect registered state:
identity partition order id1/id2; streaming-table output kind and exact prop1/
prop2 map; and the three original arbitrary per-flow configuration maps. The
configuration test also checks reset for the next file. No runtime behavior,
public API, dependency or catalog integration changes.

The [receipt](evidence/35565f49d1f4666255b431c63f1e4f8cabdf3ecf/gate.json)
records formatting, strict Clippy and three passing Rust library tests (24 other
tests filtered), plus 217 selected pytest cases and 67 upstream Python executions.
The Rust test binary is built/executed at this commit; the remote CLI remains
verified engine bbf438c066 with matching hash. No new CLI or Python native-extension
build/execution is claimed.

This closes the direct registered metadata assertion gaps without replacing the
streaming-table fixtures with materialized views. Original Spark tests inspect
resolved graphs; these tests stop at registration, preserving that remaining
entry-point distinction. The SQL inventory now has 26 partial ports and twelve
unmapped registrations. Overall review counts remain 97 reviewed and 365
unaudited; no case becomes fully qualified. Rust identifiers/evidence are separate
from Python nodes/XML. Original Scala-suite execution, full batch acceptance and
Astra architecture checkpoints remain outstanding.

## Review resolved query nullability and source-text design evidence

Commit `cb27f1a9db` adds a Rust test resolving the original declared LONG/RANGE(5)
fixture through PlanResolver and shared declaration validation. It asserts the
exact id Int64/non-nullable query schema before and after validation, without
confusing it with nullable catalog publication. The isolated context follows
Sail's session factory: Python initialized, memory CatalogManager, SparkSession
and PlanService extensions, and no DataFusion default functions. The existing
memory-catalog crate is a dev-dependency only; no production dependency changes.

The [receipt](evidence/cb27f1a9dbd0fd888e4d5d8babff18bb349478cc/gate.json)
records fmt, strict Clippy and four passing Rust library tests (24 filtered),
217 selected pytest cases and 67 upstream Python executions. Remote engine remains
bbf438c066 with matching CLI hash; no new CLI/native-extension gate is claimed.
Fixture failures from missing Python initialization, PlanService and inadvertent
DataFusion defaults are retained and separated from engine compatibility evidence.

An initial exact view-text test found a real gap: shared query.text() reconstructs
spacing and retains a trailing space. TreeText documents that contract, so changing
it in place would conflate reconstruction with original source preservation.
The exact failing test, initial candidate patch and log are retained under the
[design evidence](evidence/view-source-design-boundary/provenance.json); the
passing Sail commit does not include or weaken that failing assertion. The
[shared SQL handoff](SQL-CATALOG-DESIGN-HANDOFF.md) now records this Astra design
boundary, including character-versus-byte span handling and general view behavior.

The schema assertion coverage improves; source-text compatibility remains open.
SQL counts remain 26 partial ports/twelve unmapped, overall 97 reviewed and 365
unaudited. Original Scala-suite execution, full batch acceptance and later
architecture phases remain incomplete. No new production architecture selected.

## Review reusable catalog namespace matrix

Commit `b2150a2783` adds a standalone PySpark 4.2.1 runner for all six namespace
pairs in SqlPipelineSuite:759. Catalogs and table providers are arguments; there
is no LakeCat-specific query path or Sail fixture import. Unique owned names
allow table/namespace cleanup on success or failure. Data, declared BIGINT
schema, provider metadata, graph disposal and metadata cleanup are checked.

The [receipt](evidence/b2150a27831dbfc7b285d0d3da62305f8e302b97/gate.json)
records Ruff, six passes on two memory/Parquet catalogs and six passes with a
memory/Parquet primary and LakeCat/Iceberg secondary over REST. All cases use
verified engine bbf438c066 with matching CLI hash and unchanged LakeCat 27e18f39.
Three invalid invocation controls reject with exit 2. An injected failure after
successful materialization records failed acceptance and still cleans the tables
and namespaces. Independent REST GET confirms default namespace exists and the
generated LakeCat namespace returns 404. Initial memory baseline is retained.

This Python-only tool unit claims no new Rust/native build, broad pytest/upstream
run or Spark JVM matrix execution. LakeCat uses its existing memory store,
allow-all test governance and local files; no production LakeCat source changes,
durability, authentication or distributed verdict. Existing Rust dependency
versions differ across client/server and remain separated by standard REST.

SqlPipelineSuite:759 now has partial behavioral coverage of all six source
combinations. SQL audit counts are 27 partial ports/eleven unmapped, with total
reviewed 97 and unaudited 365 unchanged. Full Scala-suite/batch acceptance and
Astra architecture work remain outstanding. No publication.

## Review batch file inputs and empty SQL location handling

Commit `9c42934ed8` rejects a recognized SQL format/path reference with an empty
path before source construction, returning the expected location cause through
existing PlanError analysis transport. This shared resolver guard applies outside
pipelines too. It does not change DataFrameReader path semantics or add structured
condition/SQL-state metadata. Three new batch input cases check Parquet/JSON/CSV
values, including CSV strings; two error cases check direct SQL and pipeline
cause observation and no publication.

The [receipt](evidence/9c42934ed8e095b2e7ccaafeef2faea3f35f797a/gate.json)
records fmt, strict Clippy, CLI build, Ruff, 222 selected pytest cases and 67
upstream Python executions. Six Spark 4.2.1 reference checks pass, including ORC
as a fixture-validity control. Only the three supported file formats are in
passing Sail coverage. The initial Sail probe had three passes and three failures:
ORC plus two empty-location diagnostics. The final ORC counterprobe remains a
failure and its exact source/XML/log are retained. No ORC pass or skip is claimed.

The initial Spark reference incorrectly required the pipeline cause in the outer
error; it actually arrives in preceding flow events. That reference is retained.
The corrected observer collects events and outer error while retaining the exact
cause assertion, and passes on both engines. Original internal failure container,
per-flow attribution and missing-file case remain open.

Two SQL registrations now have partial ports; SQL counts are 29 partial/nine
unmapped, overall 97 reviewed/365 unaudited unchanged. The ORC capability gap
reaches a shared data-source design checkpoint for Astra and is recorded in the
[file-source handoff](FILE-SOURCE-DESIGN-HANDOFF.md). No format implementation or
new dependency was selected. Full batch and original Scala-suite acceptance,
source-text/catalog-expression and event/REST-view architecture, streaming and
CDC remain outstanding.

## Shared original view SQL through ordinary and pipeline lowering

Sail a66461125f4970ebe3f99b7e3044c8a6972e8814 adds the shared SqlSource context and source-aware analyzer API with no new dependencies. Twenty analyzer library tests, formatting and strict Clippy pass. TreeText and AST-only reconstruction remain intact. Initial Clippy placement failure is retained.

Sail ac7bff5007545859b6c972e2d9b9a17ffc38fa97 wires ordinary SQL relations and pipeline commands to the shared context. The exact SqlPipelineSuite:617 Rust reproduction passes unchanged; additional checks cover multi-view source intervals, file atomicity, namespace reset and ordinary protocol conversion. Thirty selected Spark Connect library tests pass, with one filtered golden test. Strict Clippy, formatting, CLI build, Ruff, 226 selected pytest cases and 67 upstream Python executions pass. Four original-text publication checks fail against the pre-source engine and pass against Spark 4.2.1 and the candidate. See the [qualified receipt](evidence/ac7bff5007545859b6c972e2d9b9a17ffc38fa97/gate.json).

The full initial Rust library run is not green: 30 pass and the SQL-plan golden test fails on ddl_create_index.json. The same golden test fails on parent a66461125. A hash-verified pre-source 9c42934ed8 CLI probe confirms its expected-token diagnostic already includes MATERIALIZED/STREAMING/FLOW, unlike the fixture. Logs and the failing result remain retained; no golden data was regenerated. No full Rust-suite pass is claimed.

Inventory counts remain 97 reviewed/365 unaudited, SQL 29 partial/nine unmapped, with no fully qualified original Scala registration. Exact view text is no longer an open defect. Catalog-expression/namespace and event architecture, REST view operations, ORC, full batch, streaming and CDC remain incomplete.

## SQL plan golden expectations after pipeline and USE grammar

Sail 2d54d5a568f8dbac68d2b9ac8519380a25782fd3 changes eight expectations in two existing
fixture files. All inputs and captured Spark exception metadata remain unchanged. Four
CREATE diagnostics gain MATERIALIZED/STREAMING/FLOW alternatives. Two malformed USE
diagnostics advance to their invalid delimiter, and two Unicode USE inputs now produce
the existing SetCurrentDatabase plan under Sail's inherited Unicode identifier rule.

The full Spark Connect Rust library suite passes: 31 tests, zero failures, ignores or
filters. The SQL-plan golden test also passes with SAIL_UPDATE_GOLD_DATA explicitly
unset, checking 45 files and 880 cases. The earlier 30-pass/one-fail result remains
historical evidence; the failure is now resolved. See the [qualified
receipt](evidence/2d54d5a568f8dbac68d2b9ac8519380a25782fd3/gate.json).

The independent Spark 4.2.1 parser probe rejects both unquoted Unicode names and accepts
their backquoted controls. Sail's word lexer explicitly permits Unicode unquoted
identifiers in the original base commit; this fixture-only repair preserves that
decision and does not claim Spark identifier parity. No production SQL behavior changes
in this commit.

No remote or original Scala suite was rerun for this fixture-only unit. The preceding
view-source commit retains its 226 selected pytest and 67 upstream Python verdicts.
Inventory counts and full batch/streaming/CDC acceptance remain unchanged. The next
announced design phase is shared catalog expressions and pipeline namespace handling.

## Shared catalog-expression design and retained acceptance failures

The [selected design](CATALOG-EXPRESSION-DESIGN.md) completes the announced architecture
pass. All implementation is still pending. Typed SQL expression lowering and a shared
PlanResolver helper keep general catalog behavior in Sail; direct Catalog API names
retain their existing representation. LakeCat stays an adapter.

A new Spark 4.2.1 analyzer matrix observes 22 expressions. The paired registration probe
has 13 cases per engine, including both original invalid-expression instances, type/null
handling, file/default ANSI contrasts and unset/private/explicit namespaces. The
retained required assertions pass 13 on Spark and fail eleven on the unchanged Sail
engine (two controls pass). This is a failing implementation baseline, not thirteen
passing Sail ports. See the [provenance and scripts](evidence/catalog-expression-design/provenance.json).

The evidence corrects two tempting designs: catalog folding uses session configuration
rather than file/graph flow configuration, and execution errors such as
CAST_INVALID_INPUT must bypass the analysis registration wrapper. It also proves that
inspecting only resolved DataFusion expressions is insufficient because Sail lowers
context functions to literals before evaluation. Request-local constant mode and
function metadata preserve that distinction without changing ordinary SQL behavior.

Preparation is independent of graph definitions: parse/lower/fold outside the blocking
mutex, retain per-statement failures, then replay against a clone of the current
definition under lock. This preserves earlier error priority, file atomicity and
concurrent additions without a new graph revision system or holding a blocking guard
across await. Recheck membership and idle state at commit.

Five implementation units cover shared foldability/name resolution, typed ordinary SQL,
statement origins/error parameters, asynchronous prepare/commit and namespace plus
adapter acceptance. SQL inventory counts remain 29 partial/nine unmapped, overall 97
reviewed/365 unaudited. The original two-instance error grid now links its failing
reproduction; it remains unmapped. No new production, CLI, Scala-suite, publication,
REST, streaming or CDC qualification is claimed.

## Shared catalog-name resolver and request-local constant mode

Sail 5647383189ce71dd97d62fbe97b7013b7bd6e038 implements the first catalog-expression
unit: a shared PlanResolver::resolve_catalog_name entry point, request-local constant
mode, foldability annotations and pre-evaluation guards. No new dependency, SQL grammar
activation or pipeline expression wiring is included. See the [qualified
receipt](evidence/5647383189ce71dd97d62fbe97b7013b7bd6e038/gate.json).

Eight new direct Rust tests cover scalar/identifier forms, quoting and multipart
boundaries, typed-null/type priority, ANSI cast errors, time simplification, unchanged
ordinary resolution, registered-function canaries and early subquery rejection.
Non-foldable builders and registered function bodies are not invoked in constant mode.
The ordinary registered canary still runs once when explicitly evaluated outside that
mode.

The initial candidate passed 21 planner tests and failed the unchanged assertion for
bare 1 / 0. An independent Spark probe confirms WRONG_TYPE for /, DIV and %, while CAST
of division to STRING reaches DIVIDE_BY_ZERO. Sail's literal-zero shortcuts were
executing during resolution; constant mode now defers those shortcuts until after type
validation. Ordinary queries retain the existing fast paths. The initial patch and
failed log are retained.

Detached formatting, strict Clippy and CLI build pass. All 22 planner and 31 Connect
library tests pass without filters. The fresh CLI passes 236 selected pytest cases and
67 upstream Python executions; the selected set adds four IDENTIFIER parameter cases and
six signed-zero/projected-DIV cases to the previous 226-case set. No skip or xfail is
counted as a pass.

The public 13-case catalog registration baseline is not rerun or relabeled as passing:
its parser/pipeline activation is still pending. Source origins and asynchronous
preparation will precede expression grammar activation so each review unit can retain
existing pipeline behavior. Inventory counts and original Scala/full
batch/REST/streaming/CDC acceptance are unchanged.

## Shared statement origins and structured pipeline SQL errors

Sail 1f281cdfddf8dcc1594f9b5e4e5802dbaef7e167 adds the root parser span entry point and
checked SqlSource statement origins. The AST-only parser delegates to the same grammar
and drops spans; TreeText remains unchanged. Three new analyzer tests cover Unicode,
embedded semicolons, leading/trailing trivia, raw configuration values, CRLF and invalid
byte intervals. Detached parser six/analyzer 23 tests, formatting and strict Clippy
pass. The initial compiler inference error and patch are retained.

Sail 010469d3c079285d637752c4cde012ef9bad0b75 uses those origins for
PIPELINE_SQL_GRAPH_ELEMENT_REGISTRATION_ERROR through existing StructuredSparkError. It
supplies AnalysisException, SQL state 42000 and the exact
message/offendingQuery/codeLocation parameter keys. Rust covers both explicit and absent
paths. Two public controls verify original text and source lines two/four with Unicode
path/content and retained trailing comments. Both controls fail on the old engine and
pass unchanged on Spark 4.2.1 and the candidate. See the [qualified
receipt](evidence/010469d3c079285d637752c4cde012ef9bad0b75/gate.json).

Detached formatting, strict Clippy, CLI build and Ruff pass. The full Connect library
has 32 passing tests, with no filters. The fresh CLI passes 238 selected pytest cases
and 67 upstream Python executions, without skips or xfails. File-atomic registration and
view source preservation remain covered by the selected regressions.

This finishes the statement-origin/diagnostic prerequisite. Asynchronous preparation,
typed catalog-expression activation and unset-namespace/adaptor acceptance remain
pending. No original Scala registration is newly marked complete, and inventory counts
remain unchanged.

## Graph-independent SQL preparation and atomic replay

Sail 73305d1f7b3d69fefad19944e1270b69fe9adf8f adds a typed catalog-expression
command and prepares SQL without holding the pipeline graph lock. Commit rechecks graph
existence and idle state, then replays against its current definition. Earlier
registration failures retain source order ahead of later preparation failures, and a
failed file publishes no partial definition. Constant evaluation uses the shared Sail
planner and session SQL configuration; runtime errors retain native transport.

Six new tests cover graph lock availability during preparation, concurrent registration,
graph deletion, a newly started run, missing-graph priority, source-order rollback, and
analysis versus runtime error handling. An initial ANSI fixture failure is retained;
the fixture now explicitly selects ANSI mode without changing the assertion or
production defaults. Full Connect 38, planner 23 and analyzer 23 Rust tests pass, with
zero filters. Detached formatting, strict Clippy and CLI build pass, followed by 238
selected Python regressions and 67 upstream Python executions. See the
[receipt](evidence/73305d1f7b3d69fefad19944e1270b69fe9adf8f/gate.json).

These deterministic schedules do not qualify general concurrency under saturated
release execution. Expression grammar activation remains a separate next unit;
original Scala, full batch, streaming and CDC acceptance remain outstanding.

## Enable shared catalog expressions in SQL and pipelines

Sail 992f5bcbf60added5b44596f279ab8801f0c0045 switches SET CATALOG to the expression AST and shared
resolver command. The direct catalog API and USE CATALOG keep their static-name
commands. Pipeline qualification rejects implicit persistent names while the file
database is unset after SET CATALOG; explicit namespaces and private views work.
No dependency or catalog adapter is added.

Eight new public tests fail against the prior CLI and pass unchanged on Spark
4.2.1 and this candidate: ordinary CONCAT/CAST, pipeline publication, both
SqlPipelineSuite:739 invalid expressions, numeric type and typed null diagnostics.
The retained 13-case registration assertions now pass 11/13 on Sail. Both remaining
failures preserve NumberFormatException but lack CAST_INVALID_INPUT and SQL state
22018 in shared execution-error transport; ordinary SQL reproduces the same gap.
Analysis wrappers, configuration priority and unset/explicit/private namespace
controls pass. The historical 2/13 Sail failure package and all thirteen unchanged
assertions are preserved. See the
[receipt](evidence/992f5bcbf60added5b44596f279ab8801f0c0045/gate.json).

Detached fmt, strict Clippy and CLI build pass. Full Connect 38, parser six,
analyzer 23 and planner 23 library tests pass without filters. Fresh-server
regressions pass 246 selected Python cases and 67 upstream executions. The one
changed golden case now parses subtraction before later catalog resolution; its
input and original captured Spark error are unchanged. Initial golden failure
and the eight Spark fixture setup errors are retained separately from passing
function-level reference evidence.

This qualifies shared expression activation and the selected registration/publication
behaviors. It does not execute the original Scala suite or finish catalog adapter,
full batch, REST view, event/failure, ORC, streaming or CDC acceptance.

## Shared cast error design checkpoint

The [selected design](EXECUTION-ERROR-DESIGN.md) reuses StructuredSparkError and
CommonErrorCause, captures value/type details at shared cast producers, and keeps
Connect wire conversion at its existing boundary. Five granular implementation
units separate extraction, transport, scalar/codec support, SQL activation and
acceptance. The paired 24-case required baseline passes 24/24 on Spark and 4/24 on
Sail; every mismatch is retained, including distinct overflow/temporal conditions
and row-dependent exception classes. Engine/source remain 992f5bcbf; this is a
design/evidence commit, with no runtime fix or new passing SDP verdict.

## Extract shared structured error data

Sail cd79b2bcc94fdf69418615fb0c0c60b5bee9f871 moves the existing StructuredSparkError record into
sail-common-datafusion with owned serializable fields. Nine existing constructors
receive mechanical ownership conversions; the existing Connect import is re-exported
and its wire formatting/truncation stays local. No dependency or cast behavior is
added. Detached formatting, strict Clippy, full common 63/Connect 38 library tests,
CLI build, 246 selected Python cases and 67 upstream Python executions pass. See
the [receipt](evidence/cd79b2bcc94fdf69418615fb0c0c60b5bee9f871/gate.json).

Fresh-CLI retained probes preserve the known failures: catalog 11/13, ordinary
casts 4/24. This extraction does not close either gap or newly qualify task/serde
metadata preservation. The next unit adds typed-cause and transport retention;
producer/codec/SQL activation remain later granular units. Full SDP goal active.
