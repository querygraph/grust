# Sail pipeline review units

The operator requires small, logically scoped Sail changes that preserve Sail's
existing design. Work is on `work/spark-declarative-pipelines`, based on Sail
`0ba425c0331aee4dd4e9a280c6a793926fd0876e`. These are local commits; no upstream
pull requests have been opened or branches pushed.

Current batch source `5a5e256328` publishes table and persisted-view metadata
before batch writes and refreshes existing tables through catalog operations.
Its detached gate passed 112 selected Sail cases and 67 unchanged upstream Python
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
