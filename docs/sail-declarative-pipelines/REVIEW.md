# Sail pipeline review units

The operator requires small, logically scoped Sail changes that preserve Sail's
existing design. Work is on `work/spark-declarative-pipelines`, based on Sail
`0ba425c0331aee4dd4e9a280c6a793926fd0876e`. These are local commits; no upstream
pull requests have been opened or branches pushed.

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

## Constraints for subsequent units

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
